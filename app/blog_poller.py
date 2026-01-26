"""
Blog Polling Service for Automatic Blog Ingestion

Polls WordPress API at configurable intervals, detects new posts,
and incrementally adds them to the vectorstore without requiring a full rebuild.
"""

import os
import json
import time
import signal
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
from langchain_core.documents import Document

from config import (
    BLOG_POLLING_ENABLED,
    BLOG_POLLING_INTERVAL,
    BLOG_LAST_POLL_FILE,
    WEB_SOURCE_URL,
    ENABLE_WEB_SOURCE,
    CHROMA_DB_PATH
)
from app.helpers import fetch_latest_web_content, get_last_blog_post_date
from app.enhanced_helpers import EnhancedVectorstoreBuilder


class BlogPoller:
    """Service that polls WordPress API for new blog posts and adds them to vectorstore."""
    
    def __init__(self):
        """Initialize the blog poller."""
        self.running = False
        self.last_poll_time = None
        self.poll_count = 0
        self.total_posts_added = 0
        
    def load_last_poll_time(self) -> Optional[datetime]:
        """Load the last poll timestamp from file."""
        if not os.path.exists(BLOG_LAST_POLL_FILE):
            return None
        
        try:
            with open(BLOG_LAST_POLL_FILE, 'r') as f:
                data = json.load(f)
                timestamp_str = data.get("last_poll_time")
                if timestamp_str:
                    dt = datetime.fromisoformat(timestamp_str)
                    # Ensure timezone-aware (assume UTC if naive)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
        except Exception as e:
            print(f"[WARN] Could not load last poll time: {e}")
        
        return None
    
    def save_last_poll_time(self, poll_time: datetime):
        """Save the last poll timestamp to file."""
        os.makedirs(os.path.dirname(BLOG_LAST_POLL_FILE), exist_ok=True)
        try:
            # Ensure timezone-aware datetime (UTC)
            if poll_time.tzinfo is None:
                poll_time = poll_time.replace(tzinfo=timezone.utc)
            
            with open(BLOG_LAST_POLL_FILE, 'w') as f:
                json.dump({
                    "last_poll_time": poll_time.isoformat(),
                    "poll_count": self.poll_count,
                    "total_posts_added": self.total_posts_added
                }, f, indent=2)
        except Exception as e:
            print(f"[WARN] Could not save last poll time: {e}")
    
    def get_existing_blog_slugs(self) -> Set[str]:
        """Get set of existing blog post slugs from vectorstore to avoid duplicates."""
        existing_slugs = set()
        
        try:
            if not os.path.exists(CHROMA_DB_PATH):
                return existing_slugs
            
            from langchain_openai import OpenAIEmbeddings
            from langchain_chroma import Chroma
            
            embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
            vectorstore = Chroma(
                persist_directory=CHROMA_DB_PATH,
                embedding_function=embeddings
            )
            
            # Get all documents with blog metadata
            all_docs = vectorstore.get(
                where={"is_blog_post": True},
                include=["metadatas"]
            )
            
            for meta in all_docs.get("metadatas", []):
                slug = meta.get("post_slug")
                if slug:
                    existing_slugs.add(slug)
            
            print(f"[DEBUG] Found {len(existing_slugs)} existing blog posts in vectorstore")
            
        except Exception as e:
            print(f"[WARN] Could not check existing blog posts: {e}")
        
        return existing_slugs
    
    def filter_new_posts(self, posts: List[Document], existing_slugs: Set[str]) -> List[Document]:
        """Filter out posts that already exist in vectorstore."""
        new_posts = []
        duplicate_count = 0
        
        for post in posts:
            slug = post.metadata.get("post_slug", "")
            if slug and slug not in existing_slugs:
                new_posts.append(post)
            else:
                duplicate_count += 1
        
        if duplicate_count > 0:
            print(f"[INFO] Skipped {duplicate_count} duplicate posts")
        
        return new_posts
    
    def add_posts_to_vectorstore(self, posts: List[Document]) -> bool:
        """Add new blog posts to the vectorstore incrementally."""
        if not posts:
            print("[INFO] No new posts to add")
            return True
        
        try:
            if not os.path.exists(CHROMA_DB_PATH):
                print("[ERROR] Vectorstore does not exist. Please build it first.")
                return False
            
            from langchain_openai import OpenAIEmbeddings
            from langchain_chroma import Chroma
            from app.enhanced_helpers import EnhancedVectorstoreBuilder
            
            # Load existing vectorstore
            embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
            vectorstore = Chroma(
                persist_directory=CHROMA_DB_PATH,
                embedding_function=embeddings
            )
            
            # Process new posts with enhanced pipeline
            builder = EnhancedVectorstoreBuilder()
            chunks = builder.process_documents(posts, source_type="web")
            
            if not chunks:
                print("[WARN] No chunks generated from new posts")
                return False
            
            # Add chunks to vectorstore in batches
            batch_size = 50
            total_batches = (len(chunks) + batch_size - 1) // batch_size
            
            print(f"[*] Adding {len(chunks)} chunks from {len(posts)} new posts in {total_batches} batches...")
            
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                print(f"   [*] Adding batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
                vectorstore.add_documents(batch)
            
            print(f"[OK] Successfully added {len(posts)} new blog posts ({len(chunks)} chunks) to vectorstore")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to add posts to vectorstore: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def poll_once(self) -> bool:
        """Perform a single poll for new blog posts."""
        if not ENABLE_WEB_SOURCE:
            print("[WARN] Web source is disabled. Skipping poll.")
            return False
        
        print("=" * 60)
        print(f"BLOG POLL #{self.poll_count + 1}")
        print("=" * 60)
        print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        try:
            # Get last processed post date from metadata
            last_post_date = get_last_blog_post_date()
            since_date = None
            
            if last_post_date:
                # Convert to YYYY-MM-DD format for WordPress API
                try:
                    # Parse ISO datetime and extract date part
                    dt = datetime.fromisoformat(last_post_date.replace('Z', '+00:00'))
                    since_date = dt.strftime('%Y-%m-%d')
                    print(f"[*] Filtering posts after {since_date}...")
                except:
                    # If already in YYYY-MM-DD format, use as-is
                    since_date = last_post_date.split('T')[0] if 'T' in last_post_date else last_post_date
                    print(f"[*] Filtering posts after {since_date}...")
            
            # Fetch latest posts
            print(f"[*] Fetching latest blog posts from {WEB_SOURCE_URL}...")
            all_posts = fetch_latest_web_content(WEB_SOURCE_URL, max_posts=100, since_date=since_date)
            
            if not all_posts:
                print("[INFO] No new posts found")
                self.last_poll_time = datetime.now(timezone.utc)
                self.save_last_poll_time(self.last_poll_time)
                return True
            
            print(f"[*] Fetched {len(all_posts)} blog post chunks")
            
            # Get existing blog slugs to filter duplicates
            existing_slugs = self.get_existing_blog_slugs()
            
            # Group chunks by post (using post_slug)
            posts_by_slug = {}
            for chunk in all_posts:
                slug = chunk.metadata.get("post_slug", "")
                if slug:
                    if slug not in posts_by_slug:
                        posts_by_slug[slug] = []
                    posts_by_slug[slug].append(chunk)
            
            # Filter out existing posts
            new_slugs = set(posts_by_slug.keys()) - existing_slugs
            new_posts = []
            for slug in new_slugs:
                new_posts.extend(posts_by_slug[slug])
            
            if not new_posts:
                print("[INFO] No new posts found (all posts already in vectorstore)")
                self.last_poll_time = datetime.now(timezone.utc)
                self.save_last_poll_time(self.last_poll_time)
                return True
            
            # Get unique post count
            unique_new_posts = len(new_slugs)
            print(f"[*] Found {unique_new_posts} new blog posts ({len(new_posts)} chunks)")
            
            # Add to vectorstore
            success = self.add_posts_to_vectorstore(new_posts)
            
            if success:
                # Update metadata with latest post date
                self.update_blog_metadata(new_posts)
                self.total_posts_added += unique_new_posts
                print(f"[OK] Poll completed successfully. Total posts added: {self.total_posts_added}")
            else:
                print("[ERROR] Poll completed with errors")
            
            self.last_poll_time = datetime.now(timezone.utc)
            self.poll_count += 1
            self.save_last_poll_time(self.last_poll_time)
            
            return success
            
        except Exception as e:
            print(f"[ERROR] Poll failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def update_blog_metadata(self, new_posts: List[Document]):
        """Update vectorstore metadata with latest blog post information."""
        try:
            from app.vectorstore import load_stored_metadata, save_metadata, get_current_metadata
            
            # Get current metadata
            metadata = get_current_metadata()
            
            # Find the most recent post date
            latest_date = None
            for post in new_posts:
                post_date = post.metadata.get("post_date")
                if post_date:
                    if latest_date is None or post_date > latest_date:
                        latest_date = post_date
            
            if latest_date:
                metadata["last_blog_post_date"] = latest_date
            
            metadata["last_blog_poll"] = datetime.now(timezone.utc).isoformat()
            
            # Count blog posts in vectorstore
            try:
                from langchain_openai import OpenAIEmbeddings
                from langchain_chroma import Chroma
                
                embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
                vectorstore = Chroma(
                    persist_directory=CHROMA_DB_PATH,
                    embedding_function=embeddings
                )
                
                all_docs = vectorstore.get(
                    where={"is_blog_post": True},
                    include=["metadatas"]
                )
                
                # Count unique posts by slug
                unique_slugs = set()
                for meta in all_docs.get("metadatas", []):
                    slug = meta.get("post_slug")
                    if slug:
                        unique_slugs.add(slug)
                
                metadata["blog_post_count"] = len(unique_slugs)
                
            except Exception as e:
                print(f"[WARN] Could not count blog posts: {e}")
            
            # Save updated metadata
            save_metadata(metadata)
            
        except Exception as e:
            print(f"[WARN] Could not update blog metadata: {e}")
    
    def run_continuous(self):
        """Run polling service continuously at configured intervals."""
        if not BLOG_POLLING_ENABLED:
            print("[WARN] Blog polling is disabled. Set BLOG_POLLING_ENABLED=true to enable.")
            return
        
        print("=" * 60)
        print("BLOG POLLING SERVICE STARTED")
        print("=" * 60)
        print(f"Polling interval: {BLOG_POLLING_INTERVAL} seconds ({BLOG_POLLING_INTERVAL / 60:.1f} minutes)")
        print(f"WordPress URL: {WEB_SOURCE_URL}")
        print("=" * 60)
        
        # Load last poll time
        self.last_poll_time = self.load_last_poll_time()
        if self.last_poll_time:
            print(f"Last poll: {self.last_poll_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print("No previous poll found - this will be the first poll")
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            print("\n[INFO] Shutting down blog polling service...")
            self.running = False
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.running = True
        
        # Initial poll
        print("\n[*] Starting initial poll...")
        self.poll_once()
        
        # Continuous polling loop
        while self.running:
            try:
                # Wait for next poll interval
                print(f"\n[*] Next poll in {BLOG_POLLING_INTERVAL} seconds...")
                time.sleep(BLOG_POLLING_INTERVAL)
                
                if not self.running:
                    break
                
                # Perform poll
                self.poll_once()
                
            except KeyboardInterrupt:
                print("\n[INFO] Shutting down blog polling service...")
                self.running = False
                break
            except Exception as e:
                print(f"[ERROR] Error in polling loop: {e}")
                import traceback
                traceback.print_exc()
                # Continue polling even if one poll fails
                time.sleep(60)  # Wait 1 minute before retrying after error


def main():
    """Main entry point for blog polling service."""
    poller = BlogPoller()
    poller.run_continuous()


if __name__ == "__main__":
    main()
