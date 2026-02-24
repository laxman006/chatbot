"""Recompute and repair daily_stats.unique_users from daily_users.
Run periodically or on demand to fix drift.
"""
from pymongo import MongoClient
import os
from datetime import datetime, timezone

# Use existing MONGODB_URL from .env (Atlas cluster); fallback to MONGO_URI or localhost
MONGO_URI = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client.analytics


def reconcile_date(date: str, hostname: str = "ai.cloudfuze.com"):
    # Compute exact unique users from daily_users and update daily_stats
    count = db.daily_users.count_documents({"hostname": hostname, "date": date})
    db.daily_stats.update_one(
        {"hostname": hostname, "date": date},
        {"$set": {"unique_users": int(count), "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    print(f"Reconciled {date} -> unique_users={count}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: reconcile_daily_stats.py YYYY-MM-DD [hostname]")
        sys.exit(1)
    date = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else "ai.cloudfuze.com"
    reconcile_date(date, host)
