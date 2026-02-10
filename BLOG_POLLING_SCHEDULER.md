# Automatic Blog Ingestion Scheduler

## Overview

The automatic blog ingestion feature polls the WordPress API at regular intervals to check for new blog posts and automatically ingest them into the Weaviate vectorstore.

## How It Works

1. **Scheduler**: Uses APScheduler to run periodic tasks
2. **Incremental Ingestion**: Only fetches blog posts published after the last ingestion date
3. **Tracking**: Maintains metadata about the last ingested post in `./data/blog_metadata.json`
4. **No Duplicates**: Skips posts that have already been ingested

## Configuration

Configure automatic blog polling in your `.env` file:

```env
# Enable automatic blog polling
BLOG_POLLING_ENABLED=true

# Polling interval in seconds
# Examples:
#   3600    = 1 hour
#   21600   = 6 hours
#   43200   = 12 hours
#   86400   = 24 hours (1 day)
#   604800  = 7 days (1 week)
BLOG_POLLING_INTERVAL=604800

# File to store metadata about last poll
BLOG_LAST_POLL_FILE=./data/blog_last_poll.json

# WordPress API endpoint
WEB_SOURCE_URL=https://cloudfuze.com/wp-json/wp/v2/posts?per_page=100
```

## Files

### Core Files

- **`app/blog_polling_scheduler.py`**: Scheduler wrapper for blog polling
- **`app/blog_ingestion.py`**: Core blog ingestion logic
- **`server.py`**: Scheduler initialization (runs on server startup)

### Tracking Files

- **`data/blog_metadata.json`**: Stores metadata about last ingested post
  - `last_blog_post_date`: Date of the most recent blog post
  - `last_run_at`: Timestamp of last ingestion run
  - `total_chunks_ingested`: Number of chunks inserted in last run
  - `last_blog_post_url`: URL of last ingested post
  - `last_blog_post_title`: Title of last ingested post
  - `total_posts_ingested_cumulative`: Total posts ingested over all runs

## Scheduler Behavior

### On Server Startup

The scheduler is initialized when the server starts:

```
[STARTUP] ✅ Blog polling scheduler added (runs every 7d)
[STARTUP] ✅ Scheduler started successfully
```

### During Polling

When the scheduled poll runs, you'll see logs like:

```
======================================================================
[BLOG POLL] 🔄 Starting scheduled blog polling...
[BLOG POLL] Time: 2026-02-10 14:30:00
======================================================================
[BLOG INGEST] Incremental run → fetching posts after 2026-02-06
[BLOG INGEST] fetched_chunks=9 | mode=incremental
...
[BLOG POLL] ✅ Blog polling completed successfully
[BLOG POLL] 📊 Processed: 10 chunks
[BLOG POLL] ➕ Inserted: 10 new chunks
======================================================================
```

## Manual Triggering

You can also manually trigger blog polling:

### Via Admin UI

1. Navigate to `/admin/blog`
2. Click "Trigger Blog Poll"

### Via API

```bash
curl -X POST http://localhost:8002/admin/blog/poll \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Via CLI

```bash
python scripts/ingest_to_weaviate.py --source blog
```

## Monitoring

### Check Scheduler Status

Look for these logs on server startup:

```
[STARTUP] ✅ Blog polling scheduler added (runs every 7d)
[STARTUP] ✅ Scheduler started successfully
```

### Check Last Poll Metadata

```bash
cat data/blog_metadata.json
```

Example output:
```json
{
  "last_blog_post_date": "2026-02-06",
  "last_run_at": "2026-02-10T08:53:10Z",
  "total_chunks_ingested": 10,
  "last_blog_post_url": "https://www.cloudfuze.com/...",
  "last_blog_post_title": "10 Best Practices...",
  "total_posts_ingested_cumulative": 9
}
```

### Check Vectorstore

View blog count on server startup:

```
[STARTUP]   Blogs: 9027 documents
```

Or via admin UI:
- Navigate to `/admin/blog` to see stats

## Troubleshooting

### Scheduler Not Starting

**Issue**: No scheduler logs on startup

**Solution**: Check that `BLOG_POLLING_ENABLED=true` in `.env`

### No New Posts Being Ingested

**Possible Causes**:
1. No new posts published since last poll
2. WordPress API is down or rate-limited
3. Date filtering is too restrictive

**Check**:
```bash
# View last poll date
cat data/blog_metadata.json

# Manually test ingestion
python scripts/ingest_to_weaviate.py --source blog
```

### Scheduler Errors

**Check logs** for error messages:
```
[BLOG POLL] ❌ Blog polling failed: <error message>
```

Common issues:
- Weaviate is not running: `docker ps` to check
- MongoDB connection issues: Check `MONGODB_URL`
- API key issues: Check `OPENAI_API_KEY` for embeddings

## Architecture

```
Server Startup
    ↓
Initialize APScheduler
    ↓
Add Blog Polling Job (if enabled)
    ↓
Schedule runs every BLOG_POLLING_INTERVAL seconds
    ↓
    ┌─────────────────────────────────────┐
    │  scheduled_blog_poll()              │
    │  (app/blog_polling_scheduler.py)    │
    └─────────────────┬───────────────────┘
                      ↓
    ┌─────────────────────────────────────┐
    │  run_blog_ingestion()               │
    │  (app/blog_ingestion.py)            │
    └─────────────────┬───────────────────┘
                      ↓
        Load last_blog_post_date
                      ↓
    Fetch posts after that date (incremental)
                      ↓
    ┌─────────────────────────────────────┐
    │  WeaviateIngestionPipeline          │
    │  (app/weaviate_ingestion.py)        │
    └─────────────────┬───────────────────┘
                      ↓
        Chunk → Embed → Insert
                      ↓
        Save metadata (next poll uses this)
```

## Testing

### Test Immediate Polling (1 minute interval)

For testing, you can set a short interval:

```env
# Test with 1 minute polling
BLOG_POLLING_INTERVAL=60
```

Restart the server and watch the logs for the next poll.

### Verify Scheduler is Running

After server starts, check logs:

```
[STARTUP] ✅ Blog polling scheduler added (runs every 1m)
[STARTUP] ✅ Scheduler started successfully
```

Then wait for the interval and watch for:

```
[BLOG POLL] 🔄 Starting scheduled blog polling...
```

## Production Recommendations

### Recommended Intervals

- **High-volume blog**: 1-6 hours (3600-21600 seconds)
- **Medium-volume blog**: 12-24 hours (43200-86400 seconds)
- **Low-volume blog**: 1-7 days (86400-604800 seconds)

### Current Setup (CloudFuze)

- **Interval**: 7 days (604800 seconds)
- **Reason**: Blog posts are published weekly
- **Trade-off**: Balance freshness vs. API load

### Monitoring in Production

1. **Set up alerting** for scheduler failures
2. **Monitor disk space** for metadata files
3. **Track Weaviate storage** growth
4. **Monitor API rate limits** (WordPress API)

## Deployment (ai.cloudfuze.com / Docker)

The blog scheduler runs **inside the backend container** when you use `docker-compose.ai.yml`. It does **not** run as a separate process.

### Checklist for deployment

1. **Set env on the server** (in `/opt/chatbot/.env.ai` or your production env file):
   ```env
   BLOG_POLLING_ENABLED=true
   BLOG_POLLING_INTERVAL=604800
   ```
   If `BLOG_POLLING_ENABLED` is missing or `false`, the scheduler will **not** start (no error; the app still runs).

2. **Redeploy / restart backend** so it picks up the env (e.g. `docker compose -f docker-compose.ai.yml up -d --build`).

3. **Verify after deploy** – check backend container logs for scheduler startup:
   ```bash
   docker logs slack2teams-backend-ai 2>&1 | head -80
   ```
   Look for:
   - `[STARTUP] ✅ Blog polling scheduler added (runs every 168h)` (or your interval)
   - `[STARTUP] ✅ Scheduler started successfully`
   If you see `Blog polling scheduler is disabled (BLOG_POLLING_ENABLED=false)` then the env is not set on the server.

4. **No deploy workflow change needed** – the GitHub Actions deploy does not need to reference blog polling; the backend reads `.env.ai` on the server.

### Common deployment issues

| Issue | Cause | Fix |
|-------|--------|-----|
| Scheduler not running | `BLOG_POLLING_ENABLED` not set or `false` in production `.env.ai` | Set `BLOG_POLLING_ENABLED=true` in server `.env.ai` and restart backend. |
| Startup error adding blog job | Invalid `BLOG_POLLING_INTERVAL` (e.g. non-numeric) | Use a number (seconds), e.g. `604800`. App still starts; only the blog job is skipped. |
| Blog poll fails at runtime | Weaviate/OpenAI/Mongo not reachable from container | Check Weaviate/API connectivity and env vars inside the backend container. |

### Local verification (before deploy)

Run the test script to confirm config and scheduler code:

```bash
python scripts/test_blog_scheduler.py
```

Answer `n` to skip the manual poll. All other tests should pass.

## Related Features

- **Manual Poll**: Admin UI `/admin/blog`
- **CLI Ingestion**: `scripts/ingest_to_weaviate.py`
- **Weekly Reports**: Similar scheduler for team reports
- **Incremental Tracking**: `app/incremental_ingestion.py`
