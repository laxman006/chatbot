from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
import os

TimeFilter = Literal["today", "yesterday", "this_week", "last_week"]
VALID_TIME_FILTERS: tuple[TimeFilter, ...] = ("today", "yesterday", "this_week", "last_week")

PROD_HOST = os.getenv("PROD_HOST", "ai.cloudfuze.com")
# Use existing MONGODB_URL from .env (Atlas cluster); fallback to MONGO_URI or localhost
MONGO_URI = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI", "mongodb://localhost:27017")

app = FastAPI(title="Analytics Service")
router = APIRouter(tags=["site-analytics"])
client = AsyncIOMotorClient(MONGO_URI)
db = client.analytics


class TrackEvent(BaseModel):
    hostname: str
    event_type: str
    endpoint: Optional[str] = None
    timestamp: Optional[datetime] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    properties: Optional[dict] = None


def utc_date_str(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d")


def sanitize_key(k: str) -> str:
    return k.replace(".", "_").replace("$", "")


def get_date_range_for_time_filter(time_filter: str) -> tuple[str, str]:
    """Return (start_date, end_date) as YYYY-MM-DD in UTC for today, yesterday, this_week, last_week."""
    now = datetime.now(timezone.utc).date()
    if time_filter == "today":
        s = now.isoformat()
        return s, s
    if time_filter == "yesterday":
        d = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        s = d.isoformat()
        return s, s
    # ISO week: Monday = 0
    if time_filter == "this_week":
        weekday = now.weekday()  # Mon=0 .. Sun=6
        start = now - timedelta(days=weekday)
        end = start + timedelta(days=6)
        return start.isoformat(), end.isoformat()
    if time_filter == "last_week":
        weekday = now.weekday()
        end = now - timedelta(days=weekday) - timedelta(days=1)
        start = end - timedelta(days=6)
        return start.isoformat(), end.isoformat()
    raise ValueError(f"Invalid time_filter. Use one of: {VALID_TIME_FILTERS}")


@router.post("/track", status_code=202)
async def track(event: TrackEvent, request: Request):
    # Enforce production hostname only
    if event.hostname != PROD_HOST:
        raise HTTPException(400, "hostname not allowed")

    now = event.timestamp or datetime.now(timezone.utc)
    date = utc_date_str(now)

    raw = {
        "hostname": event.hostname,
        "timestamp": now,
        "date": date,
        "event_type": event.event_type,
        "endpoint": event.endpoint,
        "user_id": event.user_id,
        "session_id": event.session_id,
        "properties": event.properties or {},
    }

    # 1) Insert raw event
    await db.events.insert_one(raw)

    # 2) If user_id exists: upsert daily_users and set step timestamps
    if event.user_id:
        query = {"hostname": event.hostname, "date": date, "user_id": event.user_id}
        step_field = None
        if event.event_type == "entry":
            step_field = "steps.entry_at"
        elif event.event_type == "login_page":
            step_field = "steps.login_page_at"
        elif event.event_type == "login_success":
            step_field = "steps.login_success_at"
        elif event.event_type == "chat_start":
            step_field = "steps.chat_start_at"

        update = {"$setOnInsert": {"first_seen_at": now}, "$set": {"last_seen_at": now}}
        if step_field:
            update["$set"][step_field] = now

        await db.daily_users.update_one(query, update, upsert=True)

    # 3) Increment daily_stats counters atomically
    stats_query = {"hostname": event.hostname, "date": date}

    inc_ops = {"total_events": 1}
    if event.event_type == "page_view":
        inc_ops["total_page_views"] = 1
    elif event.event_type in ("login_success", "chat_start", "login_page", "entry"):
        inc_ops[f"event_counts.{event.event_type}"] = 1

    if event.endpoint:
        key = sanitize_key(event.endpoint)
        inc_ops[f"per_endpoint.{key}"] = 1

    await db.daily_stats.update_one(
        stats_query, {"$inc": inc_ops, "$set": {"updated_at": datetime.now(timezone.utc)}}, upsert=True
    )

    # 4) If user_id present: ensure unique_users increments only once per (date,user_id)
    if event.user_id:
        try:
            await db.daily_user_markers.insert_one({"hostname": event.hostname, "date": date, "user_id": event.user_id})
            # marker insert succeeded -> increment unique_users
            await db.daily_stats.update_one(stats_query, {"$inc": {"unique_users": 1}})
        except DuplicateKeyError:
            # marker already existed -> do nothing
            pass
        except Exception:
            # unexpected error: ignore to avoid breaking ingestion; reconciliation job will repair counts
            pass

    return {"status": "accepted"}


@router.get("/analytics/daily")
async def daily(date: str, hostname: str = PROD_HOST):
    doc = await db.daily_stats.find_one({"hostname": hostname, "date": date}, {"_id": 0})
    if not doc:
        return {"date": date, "hostname": hostname, "total_page_views": 0, "unique_users": 0, "event_counts": {}, "per_endpoint": {}}
    return doc


@router.get("/analytics/weekly")
async def weekly(start: str, end: str, hostname: str = PROD_HOST):
    pipeline = [
        {"$match": {"hostname": hostname, "date": {"$gte": start, "$lte": end}}},
        {
            "$facet": {
                "totals": [
                    {"$group": {"_id": None, "total_page_views": {"$sum": "$total_page_views"}, "total_events": {"$sum": "$total_events"}, "unique_users": {"$sum": "$unique_users"}}}
                ],
                "endpoints": [
                    {"$project": {"per_kv": {"$objectToArray": "$per_endpoint"}}},
                    {"$unwind": "$per_kv"},
                    {"$group": {"_id": "$per_kv.k", "count": {"$sum": "$per_kv.v"}}},
                    {"$group": {"_id": None, "per_endpoint": {"$push": {"k": "$_id", "v": "$count"}}}},
                    {"$project": {"per_endpoint": {"$arrayToObject": "$per_endpoint"}}},
                ],
            }
        },
        {"$project": {"totals": {"$arrayElemAt": ["$totals", 0]}, "per_endpoint": {"$arrayElemAt": ["$endpoints.per_endpoint", 0]}}}
    ]

    res = await db.daily_stats.aggregate(pipeline).to_list(length=1)
    if not res:
        return {"total_page_views": 0, "unique_users": 0, "per_endpoint": {}}
    out = res[0]
    totals = out.get("totals", {}) or {}
    return {"total_page_views": totals.get("total_page_views", 0), "unique_users": totals.get("unique_users", 0), "per_endpoint": out.get("per_endpoint", {}) or {}}


@router.get("/analytics/funnel")
async def funnel(start: str, end: str, hostname: str = PROD_HOST):
    pipeline = [
        {"$match": {"hostname": hostname, "date": {"$gte": start, "$lte": end}}},
        {
            "$group": {
                "_id": None,
                "entry": {"$sum": {"$cond": [{"$ifNull": ["$steps.entry_at", False]}, 1, 0]}},
                "login_page": {"$sum": {"$cond": [{"$ifNull": ["$steps.login_page_at", False]}, 1, 0]}},
                "login_success": {"$sum": {"$cond": [{"$ifNull": ["$steps.login_success_at", False]}, 1, 0]}},
                "chat_start": {"$sum": {"$cond": [{"$ifNull": ["$steps.chat_start_at", False]}, 1, 0]}},
            }
        },
    ]

    res = await db.daily_users.aggregate(pipeline).to_list(length=1)
    if not res:
        return {"entry": 0, "login_page": 0, "login_success": 0, "chat_start": 0, "conversion_rates": {}}
    out = res[0]
    entry = out.get("entry", 0)
    chat_start = out.get("chat_start", 0)
    conv_entry_to_chat = (chat_start / entry) if entry else 0.0
    return {"entry": entry, "login_page": out.get("login_page", 0), "login_success": out.get("login_success", 0), "chat_start": chat_start, "conversion_rates": {"entry_to_chat": conv_entry_to_chat}}


def _period_label(time_filter: str, start: str, end: str) -> str:
    if time_filter == "today":
        return "Today"
    if time_filter == "yesterday":
        return "Yesterday"
    if time_filter == "this_week":
        return "This week"
    if time_filter == "last_week":
        return "Last week"
    return f"{start} to {end}"


@router.get("/analytics/summary")
async def summary(time_filter: str = "today", hostname: str = PROD_HOST):
    """Single endpoint for time-filtered analytics: today, yesterday, this_week, last_week.
    Returns combined stats (page views, unique users, event_counts, per_endpoint) and funnel.
    """
    if time_filter not in VALID_TIME_FILTERS:
        raise HTTPException(400, f"time_filter must be one of: {list(VALID_TIME_FILTERS)}")
    start, end = get_date_range_for_time_filter(time_filter)

    # Fetch stats: single day vs range
    if start == end:
        doc = await db.daily_stats.find_one({"hostname": hostname, "date": start}, {"_id": 0})
        total_page_views = (doc or {}).get("total_page_views", 0)
        total_events = (doc or {}).get("total_events", 0)
        unique_users = (doc or {}).get("unique_users", 0)
        event_counts = (doc or {}).get("event_counts", {}) or {}
        per_endpoint = (doc or {}).get("per_endpoint", {}) or {}
    else:
        pipeline = [
            {"$match": {"hostname": hostname, "date": {"$gte": start, "$lte": end}}},
            {
                "$facet": {
                    "totals": [
                        {"$group": {"_id": None, "total_page_views": {"$sum": "$total_page_views"}, "total_events": {"$sum": "$total_events"}, "unique_users": {"$sum": "$unique_users"}}}
                    ],
                    "event_counts": [
                        {"$project": {"ec": {"$objectToArray": "$event_counts"}}},
                        {"$unwind": "$ec"},
                        {"$group": {"_id": "$ec.k", "v": {"$sum": "$ec.v"}}},
                        {"$group": {"_id": None, "pairs": {"$push": {"k": "$_id", "v": "$v"}}}},
                        {"$project": {"event_counts": {"$arrayToObject": "$pairs"}}},
                    ],
                    "endpoints": [
                        {"$project": {"per_kv": {"$objectToArray": "$per_endpoint"}}},
                        {"$unwind": "$per_kv"},
                        {"$group": {"_id": "$per_kv.k", "count": {"$sum": "$per_kv.v"}}},
                        {"$group": {"_id": None, "per_endpoint": {"$push": {"k": "$_id", "v": "$count"}}}},
                        {"$project": {"per_endpoint": {"$arrayToObject": "$per_endpoint"}}},
                    ],
                }
            },
            {
                "$project": {
                    "totals": {"$arrayElemAt": ["$totals", 0]},
                    "ecDoc": {"$arrayElemAt": ["$event_counts", 0]},
                    "per_endpoint": {"$arrayElemAt": ["$endpoints.per_endpoint", 0]},
                }
            },
            {"$project": {"totals": 1, "event_counts": "$ecDoc.event_counts", "per_endpoint": 1}},
        ]
        res = await db.daily_stats.aggregate(pipeline).to_list(length=1)
        if not res:
            total_page_views = total_events = unique_users = 0
            event_counts = {}
            per_endpoint = {}
        else:
            out = res[0]
            totals = out.get("totals", {}) or {}
            total_page_views = totals.get("total_page_views", 0)
            total_events = totals.get("total_events", 0)
            unique_users = totals.get("unique_users", 0)
            event_counts = out.get("event_counts", {}) or {}
            per_endpoint = out.get("per_endpoint", {}) or {}

    # Funnel for same range
    funnel_pipeline = [
        {"$match": {"hostname": hostname, "date": {"$gte": start, "$lte": end}}},
        {
            "$group": {
                "_id": None,
                "entry": {"$sum": {"$cond": [{"$ifNull": ["$steps.entry_at", False]}, 1, 0]}},
                "login_page": {"$sum": {"$cond": [{"$ifNull": ["$steps.login_page_at", False]}, 1, 0]}},
                "login_success": {"$sum": {"$cond": [{"$ifNull": ["$steps.login_success_at", False]}, 1, 0]}},
                "chat_start": {"$sum": {"$cond": [{"$ifNull": ["$steps.chat_start_at", False]}, 1, 0]}},
            }
        },
    ]
    funnel_res = await db.daily_users.aggregate(funnel_pipeline).to_list(length=1)
    if not funnel_res:
        funnel_data = {"entry": 0, "login_page": 0, "login_success": 0, "chat_start": 0, "conversion_rates": {}}
    else:
        out = funnel_res[0]
        entry = out.get("entry", 0)
        chat_start = out.get("chat_start", 0)
        conv = (chat_start / entry) if entry else 0.0
        funnel_data = {
            "entry": entry,
            "login_page": out.get("login_page", 0),
            "login_success": out.get("login_success", 0),
            "chat_start": chat_start,
            "conversion_rates": {"entry_to_chat": conv},
        }

    return {
        "time_filter": time_filter,
        "period": {"label": _period_label(time_filter, start, end), "start": start, "end": end},
        "total_page_views": total_page_views,
        "total_events": total_events,
        "unique_users": unique_users,
        "event_counts": event_counts,
        "per_endpoint": per_endpoint,
        "funnel": funnel_data,
    }


# Mount router under /api so standalone app still serves /api/track, /api/analytics/*
app.include_router(router, prefix="/api")

