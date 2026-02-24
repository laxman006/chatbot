"""Run once to create required indexes for the analytics collections."""
from pymongo import MongoClient
import os

# Use existing MONGODB_URL from .env (Atlas cluster); fallback to MONGO_URI or localhost
MONGO_URI = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client.analytics


def create_indexes():
    print("Creating indexes...")
    db.events.create_index([("hostname", 1), ("date", 1), ("event_type", 1), ("endpoint", 1), ("timestamp", -1)])
    db.daily_users.create_index([("hostname", 1), ("date", 1), ("user_id", 1)], unique=True)
    db.daily_users.create_index([("hostname", 1), ("date", 1)])
    db.daily_user_markers.create_index([("hostname", 1), ("date", 1), ("user_id", 1)], unique=True)
    db.daily_stats.create_index([("hostname", 1), ("date", 1)], unique=True)
    print("Indexes created.")


if __name__ == "__main__":
    create_indexes()

