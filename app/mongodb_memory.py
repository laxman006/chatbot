from typing import List, Dict, Optional
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError
import logging

from config import MONGODB_URL, MONGODB_DATABASE, MONGODB_CHAT_COLLECTION

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MongoDBMemoryManager:
    """MongoDB-based chat history management."""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.database = None
        self.collection = None
        self._connection_lock = asyncio.Lock()
    
    async def connect(self):
        """Initialize MongoDB connection."""
        async with self._connection_lock:
            if self.client is None:
                try:
                    # Configure SSL settings for MongoDB connection
                    import ssl
                    
                    # Determine if this is a MongoDB Atlas connection
                    is_atlas = "mongodb+srv://" in MONGODB_URL or "mongodb.net" in MONGODB_URL
                    
                    if is_atlas:
                        # For MongoDB Atlas, use SSL with certificate validation
                        self.client = AsyncIOMotorClient(
                            MONGODB_URL,
                            tls=True,
                            tlsAllowInvalidCertificates=False,
                            tlsAllowInvalidHostnames=False,
                            serverSelectionTimeoutMS=5000,
                            connectTimeoutMS=10000,
                            socketTimeoutMS=10000
                        )
                    else:
                        # For local MongoDB, try with SSL disabled first
                        try:
                            self.client = AsyncIOMotorClient(
                                MONGODB_URL,
                                tls=False,
                                serverSelectionTimeoutMS=5000,
                                connectTimeoutMS=10000,
                                socketTimeoutMS=10000
                            )
                        except Exception as ssl_error:
                            logger.warning(f"SSL disabled connection failed: {ssl_error}")
                            # Try with SSL enabled for local MongoDB
                            self.client = AsyncIOMotorClient(
                                MONGODB_URL,
                                tls=True,
                                tlsAllowInvalidCertificates=True,
                                tlsAllowInvalidHostnames=True,
                                serverSelectionTimeoutMS=5000,
                                connectTimeoutMS=10000,
                                socketTimeoutMS=10000
                            )
                    
                    self.database = self.client[MONGODB_DATABASE]
                    self.collection = self.database[MONGODB_CHAT_COLLECTION]
                    
                    # Test connection
                    await self.client.admin.command('ping')
                    logger.info(f"Connected to MongoDB: {MONGODB_DATABASE}.{MONGODB_CHAT_COLLECTION}")
                    
                    # Create indexes for better performance
                    await self._create_indexes()
                    
                except ConnectionFailure as e:
                    logger.error(f"Failed to connect to MongoDB: {e}")
                    raise e
                except Exception as e:
                    logger.error(f"Unexpected error connecting to MongoDB: {e}")
                    raise e
    
    async def _create_indexes(self):
        """Create database indexes for better performance."""
        try:
            # Index on user_id for fast lookups
            await self.collection.create_index("user_id", unique=True)
            # Index on timestamp for sorting
            await self.collection.create_index("last_updated")
            
            # Create indexes for sessions collection
            sessions_collection = self.database["chat_sessions"]
            await sessions_collection.create_index("session_id", unique=True)
            await sessions_collection.create_index("user_id")
            await sessions_collection.create_index("created_at")
            await sessions_collection.create_index([("created_at", -1)])
            
            # Create indexes for shared chats collection
            shared_chats_collection = self.database["shared_chats"]
            await shared_chats_collection.create_index("share_token", unique=True)
            await shared_chats_collection.create_index("session_id")
            await shared_chats_collection.create_index("user_email")
            await shared_chats_collection.create_index("created_at")
            
            # Create indexes for user_activity collection (single source of truth for analytics)
            user_activity_collection = self.database["user_activity"]
            await user_activity_collection.create_index("user_id", unique=True)
            await user_activity_collection.create_index("last_active")
            await user_activity_collection.create_index("total_messages")
            await user_activity_collection.create_index("total_sessions")
            
            # Create indexes for message_events collection (time-based analytics)
            message_events_collection = self.database["message_events"]
            await message_events_collection.create_index("created_at")
            await message_events_collection.create_index([("user_id", 1), ("created_at", -1)])
            await message_events_collection.create_index("user_email")  # For exclusion filtering
            await message_events_collection.create_index("session_id")
            
            # Create indexes for faq_events collection (FAQ analytics)
            faq_events_collection = self.database["faq_events"]
            await faq_events_collection.create_index("created_at")
            await faq_events_collection.create_index([("user_id", 1), ("created_at", -1)])
            await faq_events_collection.create_index("question_hash")
            
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.warning(f"Could not create indexes: {e}")
    
    async def disconnect(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.database = None
            self.collection = None
            logger.info("Disconnected from MongoDB")
    
    async def get_or_create_user_conversation(self, user_id: str) -> List[Dict[str, str]]:
        """Get or create a conversation for a specific user."""
        await self.connect()
        
        try:
            # Try to find existing conversation
            user_doc = await self.collection.find_one({"user_id": user_id})
            
            if user_doc:
                return user_doc.get("messages", [])
            else:
                # Create new conversation
                new_conversation = {
                    "user_id": user_id,
                    "messages": [],
                    "created_at": datetime.utcnow(),
                    "last_updated": datetime.utcnow()
                }
                await self.collection.insert_one(new_conversation)
                return []
                
        except Exception as e:
            logger.error(f"Error getting/creating conversation for user {user_id}: {e}")
            return []
    
    async def add_to_conversation(self, user_id: str, role: str, content: str):
        """Add a message to the user's conversation history."""
        await self.connect()
        
        try:
            # Get current conversation
            conversation = await self.get_or_create_user_conversation(user_id)
            
            # Add new message
            new_message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            }
            conversation.append(new_message)
            
            # Keep only last 20 messages to prevent context overflow
            if len(conversation) > 20:
                conversation = conversation[-20:]
            
            # Update in database
            await self.collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "messages": conversation,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"Error adding message to conversation for user {user_id}: {e}")
    
    async def get_conversation_context(self, user_id: str) -> str:
        """Get formatted conversation context for a user (legacy method)."""
        conversation = await self.get_or_create_user_conversation(user_id)
        
        if not conversation:
            return ""
        
        context = "\n\nPrevious conversation:\n"
        # Get last 5 messages for context
        for msg in conversation[-5:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            context += f"{role}: {msg['content']}\n"
        
        return context
    
    async def get_user_chat_history(self, user_id: str) -> List[Dict[str, str]]:
        """Get full chat history for a user."""
        return await self.get_or_create_user_conversation(user_id)
    
    async def clear_user_chat_history(self, user_id: str):
        """Clear chat history for a specific user."""
        await self.connect()
        
        try:
            await self.collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "messages": [],
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )
            logger.info(f"Cleared chat history for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error clearing chat history for user {user_id}: {e}")
    
    async def get_all_users(self) -> List[str]:
        """Get list of all user IDs in the database."""
        await self.connect()
        
        try:
            cursor = self.collection.find({}, {"user_id": 1})
            user_ids = [doc["user_id"] async for doc in cursor]
            return user_ids
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    async def get_conversation_stats(self) -> Dict:
        """Get statistics about conversations."""
        await self.connect()
        
        try:
            total_users = await self.collection.count_documents({})
            
            # Get total messages across all users
            pipeline = [
                {"$project": {"message_count": {"$size": "$messages"}}},
                {"$group": {"_id": None, "total_messages": {"$sum": "$message_count"}}}
            ]
            
            result = await self.collection.aggregate(pipeline).to_list(1)
            total_messages = result[0]["total_messages"] if result else 0
            
            return {
                "total_users": total_users,
                "total_messages": total_messages,
                "database": MONGODB_DATABASE,
                "collection": MONGODB_CHAT_COLLECTION
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation stats: {e}")
            return {"error": str(e)}
    
    async def save_session(self, session_data: Dict):
        """Save or update a chat session with messages."""
        await self.connect()
        
        try:
            sessions_collection = self.database["chat_sessions"]
            
            # Prepare session document
            session_doc = {
                "session_id": session_data["session_id"],
                "user_id": session_data["user_id"],
                "user_email": session_data.get("user_email", ""),
                "user_name": session_data.get("user_name", ""),
                "title": session_data["title"],
                "created_at": datetime.fromtimestamp(session_data["created_at"] / 1000),
                "updated_at": datetime.fromtimestamp(session_data.get("updated_at", session_data["created_at"]) / 1000),
                "message_count": session_data.get("message_count", 0)
            }
            
            # Include messages if provided
            if "messages" in session_data:
                session_doc["messages"] = session_data["messages"]
            
            # Upsert session
            await sessions_collection.update_one(
                {"session_id": session_data["session_id"]},
                {"$set": session_doc},
                upsert=True
            )
            
            logger.info(f"Saved session {session_data['session_id']} for user {session_data['user_id']}")
            
            # Update user_activity collection (single source of truth for analytics)
            await self._update_user_activity(session_data)
            
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            raise e
    
    async def _update_user_activity(self, session_data: Dict):
        """
        Update user_activity collection - single source of truth for analytics.
        This ensures accurate statistics without aggregating from chat logs.
        """
        try:
            user_activity_collection = self.database["user_activity"]
            user_id = session_data["user_id"]
            session_id = session_data["session_id"]
            message_count = session_data.get("message_count", 0)
            created_at = datetime.fromtimestamp(session_data["created_at"] / 1000)
            updated_at = datetime.fromtimestamp(session_data.get("updated_at", session_data["created_at"]) / 1000)
            
            # Check if this is a new session (by checking if session exists in user_activity)
            existing_activity = await user_activity_collection.find_one({"user_id": user_id})
            
            if existing_activity:
                # User exists - update activity
                sessions = existing_activity.get("sessions", [])
                
                # Check if this session already exists in sessions array
                session_exists = any(s.get("session_id") == session_id for s in sessions)
                
                if not session_exists:
                    # New session - add to sessions array
                    sessions.append({
                        "session_id": session_id,
                        "started_at": created_at,
                        "ended_at": None,  # Will be set when session ends
                        "message_count": message_count
                    })
                else:
                    # Update existing session
                    for s in sessions:
                        if s.get("session_id") == session_id:
                            s["message_count"] = message_count
                            # Update ended_at if session is being finalized
                            if updated_at > created_at:
                                s["ended_at"] = updated_at
                            break
                
                # Calculate totals
                total_messages = sum(s.get("message_count", 0) for s in sessions)
                # Count sessions with messages (active or completed)
                total_sessions = len([s for s in sessions if s.get("message_count", 0) > 0])
                avg_messages = total_messages / total_sessions if total_sessions > 0 else 0
                
                # Update user activity document
                # Preserve existing team/manager/role fields if not provided in session_data
                update_data = {
                    "user_email": session_data.get("user_email", existing_activity.get("user_email", "")),
                    "user_name": session_data.get("user_name", existing_activity.get("user_name", "")),
                    "sessions": sessions,
                    "total_messages": total_messages,
                    "total_sessions": total_sessions,
                    "avg_messages_per_session": round(avg_messages, 2),
                    "last_active": updated_at
                }
                
                # Preserve team/manager/role fields if they exist (don't overwrite with empty values)
                if existing_activity.get("team_name"):
                    update_data["team_name"] = existing_activity.get("team_name")
                if existing_activity.get("manager_email"):
                    update_data["manager_email"] = existing_activity.get("manager_email")
                if existing_activity.get("manager_name"):
                    update_data["manager_name"] = existing_activity.get("manager_name")
                if existing_activity.get("role"):
                    update_data["role"] = existing_activity.get("role")
                
                # Allow session_data to override if explicitly provided
                if session_data.get("team_name"):
                    update_data["team_name"] = session_data.get("team_name")
                if session_data.get("manager_email"):
                    update_data["manager_email"] = session_data.get("manager_email")
                if session_data.get("manager_name"):
                    update_data["manager_name"] = session_data.get("manager_name")
                if session_data.get("role"):
                    update_data["role"] = session_data.get("role")
                
                await user_activity_collection.update_one(
                    {"user_id": user_id},
                    {"$set": update_data}
                )
            else:
                # New user - create activity document
                sessions = [{
                    "session_id": session_id,
                    "started_at": created_at,
                    "ended_at": None,
                    "message_count": message_count
                }]
                
                new_user_doc = {
                    "user_id": user_id,
                    "user_email": session_data.get("user_email", ""),
                    "user_name": session_data.get("user_name", ""),
                    "sessions": sessions,
                    "total_messages": message_count,
                    "total_sessions": 1,
                    "avg_messages_per_session": float(message_count),
                    "last_active": updated_at,
                    "created_at": created_at
                }
                
                # Add team/manager/role fields if provided
                if session_data.get("team_name"):
                    new_user_doc["team_name"] = session_data.get("team_name")
                if session_data.get("manager_email"):
                    new_user_doc["manager_email"] = session_data.get("manager_email")
                if session_data.get("manager_name"):
                    new_user_doc["manager_name"] = session_data.get("manager_name")
                if session_data.get("role"):
                    new_user_doc["role"] = session_data.get("role")
                
                await user_activity_collection.insert_one(new_user_doc)
            
            logger.debug(f"Updated user_activity for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error updating user_activity: {e}")
            # Don't raise - analytics update failure shouldn't break session save
    
    async def _increment_user_message_count(self, user_id: str, session_id: str):
        """
        Increment message count for a user in user_activity collection.
        Called when a new message is sent.
        """
        try:
            user_activity_collection = self.database["user_activity"]
            now = datetime.utcnow()
            
            # Find or create user activity
            existing = await user_activity_collection.find_one({"user_id": user_id})
            
            if existing:
                # Update message count and last active
                sessions = existing.get("sessions", [])
                
                # Find and update the current session
                session_found = False
                for s in sessions:
                    if s.get("session_id") == session_id:
                        s["message_count"] = s.get("message_count", 0) + 1
                        session_found = True
                        break
                
                # If session not found, create it
                if not session_found:
                    sessions.append({
                        "session_id": session_id,
                        "started_at": now,
                        "ended_at": None,
                        "message_count": 1
                    })
                
                # Recalculate totals
                total_messages = sum(s.get("message_count", 0) for s in sessions)
                total_sessions = len([s for s in sessions if s.get("message_count", 0) > 0])
                avg_messages = total_messages / total_sessions if total_sessions > 0 else 0
                
                await user_activity_collection.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "sessions": sessions,
                            "total_messages": total_messages,
                            "total_sessions": total_sessions,
                            "avg_messages_per_session": round(avg_messages, 2),
                            "last_active": now
                        }
                    }
                )
            else:
                # Create new user activity
                await user_activity_collection.insert_one({
                    "user_id": user_id,
                    "sessions": [{
                        "session_id": session_id,
                        "started_at": now,
                        "ended_at": None,
                        "message_count": 1
                    }],
                    "total_messages": 1,
                    "total_sessions": 1,
                    "avg_messages_per_session": 1.0,
                    "last_active": now,
                    "created_at": now
                })
            
        except Exception as e:
            logger.error(f"Error incrementing message count: {e}")
            # Don't raise - analytics update failure shouldn't break message sending
    
    async def get_all_sessions(self, limit: int = 30) -> List[Dict]:
        """Get recent sessions from all users."""
        await self.connect()
        
        try:
            sessions_collection = self.database["chat_sessions"]
            
            # Get recent sessions sorted by created_at
            cursor = sessions_collection.find({}).sort("created_at", -1).limit(limit)
            sessions = []
            
            async for doc in cursor:
                sessions.append({
                    "session_id": doc["session_id"],
                    "user_id": doc["user_id"],
                    "user_email": doc.get("user_email", ""),
                    "user_name": doc.get("user_name", ""),
                    "title": doc["title"],
                    "created_at": int(doc["created_at"].timestamp() * 1000),
                    "updated_at": int(doc["updated_at"].timestamp() * 1000),
                    "message_count": doc.get("message_count", 0)
                })
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting all sessions: {e}")
            return []
    
    async def get_user_sessions(self, user_id: str, limit: int = 50, include_messages: bool = False) -> List[Dict]:
        """Get sessions for a specific user."""
        await self.connect()
        
        try:
            sessions_collection = self.database["chat_sessions"]
            
            cursor = sessions_collection.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
            sessions = []
            
            async for doc in cursor:
                session = {
                    "session_id": doc["session_id"],
                    "user_id": doc["user_id"],
                    "title": doc["title"],
                    "created_at": int(doc["created_at"].timestamp() * 1000),
                    "updated_at": int(doc["updated_at"].timestamp() * 1000),
                    "message_count": doc.get("message_count", 0)
                }
                
                # Include messages if requested
                if include_messages and "messages" in doc:
                    session["messages"] = doc["messages"]
                
                sessions.append(session)
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []
    
    async def get_session_by_id(self, session_id: str, include_messages: bool = False) -> Optional[Dict]:
        """Get a specific session by ID."""
        await self.connect()
        
        try:
            sessions_collection = self.database["chat_sessions"]
            doc = await sessions_collection.find_one({"session_id": session_id})
            
            if doc:
                session = {
                    "session_id": doc["session_id"],
                    "user_id": doc["user_id"],
                    "user_email": doc.get("user_email", ""),
                    "user_name": doc.get("user_name", ""),
                    "title": doc["title"],
                    "created_at": int(doc["created_at"].timestamp() * 1000),
                    "updated_at": int(doc["updated_at"].timestamp() * 1000),
                    "message_count": doc.get("message_count", 0)
                }
                
                # Include messages if requested
                if include_messages and "messages" in doc:
                    session["messages"] = doc["messages"]
                
                return session
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    async def create_shared_chat(self, session_id: str, user_email: str, share_token: str) -> Dict:
        """Create a shareable link for a chat session."""
        await self.connect()
        
        try:
            shared_chats_collection = self.database["shared_chats"]
            
            # Create shared chat document
            shared_chat_doc = {
                "share_token": share_token,
                "session_id": session_id,
                "user_email": user_email,
                "created_at": datetime.utcnow(),
                "expires_at": None  # No expiration for now
            }
            
            # Insert into database
            await shared_chats_collection.insert_one(shared_chat_doc)
            
            logger.info(f"Created shared chat token for session {session_id}")
            return shared_chat_doc
            
        except DuplicateKeyError:
            # Token already exists, return existing
            doc = await shared_chats_collection.find_one({"share_token": share_token})
            return doc
        except Exception as e:
            logger.error(f"Error creating shared chat: {e}")
            raise e
    
    async def get_shared_chat(self, share_token: str) -> Optional[Dict]:
        """Get shared chat information by token."""
        await self.connect()
        
        try:
            shared_chats_collection = self.database["shared_chats"]
            doc = await shared_chats_collection.find_one({"share_token": share_token})
            
            if doc:
                # Check if expired (if expiration is set)
                if doc.get("expires_at") and doc["expires_at"] < datetime.utcnow():
                    logger.info(f"Shared chat token {share_token} has expired")
                    return None
                
                return {
                    "share_token": doc["share_token"],
                    "session_id": doc["session_id"],
                    "user_email": doc["user_email"],
                    "created_at": doc["created_at"],
                    "expires_at": doc.get("expires_at")
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting shared chat {share_token}: {e}")
            return None
    
    async def insert_message_event(self, user_id: str, session_id: str, user_email: str = None):
        """
        Insert a message event for time-based analytics.
        This is called every time a user sends a message.
        
        Args:
            user_id: User ID (Microsoft GUID)
            session_id: Session ID
            user_email: User email (for exclusion filtering)
        """
        try:
            await self.connect()
            message_events_collection = self.database["message_events"]
            
            event_doc = {
                "user_id": user_id,
                "session_id": session_id,
                "created_at": datetime.utcnow()
            }
            
            # Store email if provided (for exclusion filtering)
            if user_email:
                event_doc["user_email"] = user_email.lower()
            
            await message_events_collection.insert_one(event_doc)
            
            logger.info(f"[EVENT] Inserted message event for user {user_id} ({user_email or 'no email'}), session {session_id}")
            
        except Exception as e:
            logger.error(f"Error inserting message event: {e}")
            # Don't raise - event tracking should not break chat flow
    
    async def insert_faq_event(self, user_id: str, question: str, user_email: str = None):
        """
        Insert an FAQ event for analytics.
        This is called when a user asks a question that should be tracked as FAQ.
        
        Args:
            user_id: User ID (Microsoft GUID)
            question: User's question
            user_email: User email (for exclusion filtering)
        """
        try:
            await self.connect()
            import hashlib
            
            faq_events_collection = self.database["faq_events"]
            
            # Create hash for deduplication (normalized question)
            question_normalized = question.lower().strip()
            question_hash = hashlib.sha256(question_normalized.encode()).hexdigest()[:16]
            
            event_doc = {
                "user_id": user_id,
                "question": question,
                "question_hash": question_hash,
                "created_at": datetime.utcnow()
            }
            
            # Store email if provided (for exclusion filtering)
            if user_email:
                event_doc["user_email"] = user_email.lower()
            
            await faq_events_collection.insert_one(event_doc)
            
            logger.info(f"[EVENT] Inserted FAQ event for user {user_id} ({user_email or 'no email'}), question hash {question_hash}")
            
        except Exception as e:
            logger.error(f"Error inserting FAQ event: {e}")
            # Don't raise - event tracking should not break chat flow
    
    async def get_user_statistics(
        self, 
        exclude_users: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get ALL-TIME user statistics from user_activity collection (single source of truth).
        This reads pre-calculated lifetime metrics - NO date filtering.
        
        Args:
            exclude_users: Optional list of user emails or names to exclude
        """
        await self.connect()
        
        try:
            user_activity_collection = self.database["user_activity"]
            
            # Query ALL user_activity documents (no date filtering - lifetime stats only)
            logger.info(f"Querying user_activity (all-time) with exclude_users={exclude_users}")
            
            cursor = user_activity_collection.find({})
            results = await cursor.to_list(length=None)
            
            logger.info(f"Raw user_activity results count: {len(results)}")
            
            # Format results and apply user exclusion filter
            formatted = []
            exclude_emails_lower = [email.lower() for email in (exclude_users or [])]
            
            for doc in results:
                user_email = doc.get("user_email", "").lower()
                user_name = doc.get("user_name", "").lower()
                
                # Skip excluded users (check both email and name)
                if exclude_users:
                    if user_email in exclude_emails_lower or user_name in exclude_emails_lower:
                        continue
                    # Also check if any excluded email/name is contained in user_email or user_name
                    if any(excluded.lower() in user_email or excluded.lower() in user_name for excluded in exclude_users):
                        continue
                
                last_active = doc.get("last_active")
                if isinstance(last_active, datetime):
                    last_active = last_active.isoformat()
                
                formatted.append({
                    "user_id": doc.get("user_id", ""),
                    "user_email": doc.get("user_email", ""),
                    "user_name": doc.get("user_name", ""),
                    "total_messages": doc.get("total_messages", 0),
                    "total_sessions": doc.get("total_sessions", 0),
                    "avg_messages_per_session": round(doc.get("avg_messages_per_session", 0), 2),
                    "last_active": last_active
                })
            
            # Sort by total_messages descending
            formatted.sort(key=lambda x: x.get("total_messages", 0), reverse=True)
            
            logger.info(f"Final formatted results count (after exclusion): {len(formatted)}")
            if formatted:
                logger.info(f"Top user: {formatted[0].get('user_email', 'N/A')} with {formatted[0].get('total_messages', 0)} messages")
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return []
    
    async def get_rankers_by_date(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        exclude_users: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get user rankers by date range from message_events collection.
        This provides accurate time-based analytics.
        
        Args:
            start_date: Start date for filtering (inclusive)
            end_date: End date for filtering (inclusive)
            exclude_users: Optional list of user emails or names to exclude
            limit: Maximum number of results to return
        """
        await self.connect()
        
        try:
            message_events_collection = self.database["message_events"]
            
            # First, check total events count (for debugging)
            total_events = await message_events_collection.count_documents({})
            logger.info(f"[RANKERS] Total events in message_events collection: {total_events}")
            
            # Build date filter
            date_filter = {}
            if start_date or end_date:
                date_range = {}
                if start_date:
                    # Ensure timezone-aware comparison (MongoDB stores UTC)
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                    date_range["$gte"] = start_date
                    logger.info(f"[RANKERS] Start date filter: {start_date} (UTC)")
                if end_date:
                    # Ensure timezone-aware comparison
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                    date_range["$lte"] = end_date
                    logger.info(f"[RANKERS] End date filter: {end_date} (UTC)")
                if date_range:
                    date_filter["created_at"] = date_range
            
            # Build exclusion filter (apply BEFORE grouping for correct ranking)
            exclude_filter = {}
            if exclude_users:
                exclude_emails_lower = [email.lower() for email in exclude_users]
                # Exclude users by email (case-insensitive)
                exclude_filter["user_email"] = {"$nin": exclude_emails_lower}
                logger.info(f"[RANKERS] Excluding users in aggregation: {exclude_users}")
                logger.info(f"[RANKERS] Exclude emails (lowercase): {exclude_emails_lower}")
            
            # Combine filters for $match stage
            match_filter = {}
            if date_filter:
                match_filter.update(date_filter)
            if exclude_filter:
                match_filter.update(exclude_filter)
            
            # Check how many events match the combined filter
            if match_filter:
                matching_count = await message_events_collection.count_documents(match_filter)
                logger.info(f"[RANKERS] Events matching date + exclusion filter: {matching_count}")
            
            # Aggregate: EXCLUDE → GROUP → SORT (correct order for analytics)
            # FIX: Compute sessions dynamically from distinct session_id for date-based views
            pipeline = [
                {"$match": match_filter} if match_filter else {"$match": {}},
                {
                    "$group": {
                        "_id": "$user_id",
                        "message_count": {"$sum": 1},
                        "sessions": {"$addToSet": "$session_id"},  # Collect unique session_ids
                        "last_message_at": {"$max": "$created_at"},
                        "user_email": {"$first": "$user_email"}  # Get email from event if stored
                    }
                },
                {
                    "$project": {
                        "message_count": 1,
                        "sessions": {"$size": "$sessions"},  # Count distinct sessions
                        "last_message_at": 1,
                        "user_email": 1
                    }
                },
                {"$sort": {"message_count": -1}},
                {"$limit": limit}
            ]
            
            results = await message_events_collection.aggregate(pipeline).to_list(length=limit)
            
            logger.info(f"Found {len(results)} users in message_events after exclusion + grouping")
            if results and exclude_users:
                result_emails = [r.get("user_email", "NO_EMAIL") for r in results]
                logger.info(f"[RANKERS] Result emails after exclusion: {result_emails}")
                excluded_in_results = [email for email in exclude_emails_lower if email in [e.lower() if e else "" for e in result_emails]]
                if excluded_in_results:
                    logger.warning(f"[RANKERS] ⚠️ WARNING: Excluded emails still in results: {excluded_in_results}")
            
            # Get user details from user_activity (but don't skip if not found)
            # Note: Exclusion already applied in aggregation, but we also check here as a safety net
            user_activity_collection = self.database["user_activity"]
            formatted = []
            exclude_emails_lower_set = set([email.lower() for email in (exclude_users or [])])
            
            for doc in results:
                user_id = doc.get("_id")
                if not user_id:
                    continue
                
                # Get email from event first (most reliable), then try user_activity, then fallback
                event_email = doc.get("user_email", "").lower() if doc.get("user_email") else None
                
                # Try to get user details from user_activity (for name and other details)
                user_activity = await user_activity_collection.find_one({"user_id": user_id})
                
                # Determine user_email and user_name
                if event_email:
                    # Email stored in event - use it (most reliable)
                    user_email = event_email
                    user_name = user_activity.get("user_name", "") if user_activity else event_email.split("@")[0]
                elif user_activity:
                    # Fallback to user_activity
                    user_email = user_activity.get("user_email", "").lower() if user_activity.get("user_email") else ""
                    user_name = user_activity.get("user_name", "")
                else:
                    # Last resort: try to extract from user_id (unlikely to work for Microsoft GUIDs)
                    user_id_str = str(user_id)
                    if "@" in user_id_str:
                        user_email = user_id_str.lower()
                        user_name = user_id_str.split("@")[0]
                    else:
                        # Microsoft GUID - can't extract email
                        user_email = ""
                        user_name = user_id_str
                
                # SAFETY NET: Double-check exclusion (in case email format differs between event and user_activity)
                if exclude_users and user_email and user_email.lower() in exclude_emails_lower_set:
                    logger.warning(f"[RANKERS] Filtering out excluded user in formatting step: {user_email}")
                    continue
                
                last_message_at = doc.get("last_message_at")
                if isinstance(last_message_at, datetime):
                    last_message_at = last_message_at.isoformat()
                
                # Get sessions count from aggregation (date-based, computed from distinct session_ids)
                sessions_count = doc.get("sessions", 0)
                
                formatted.append({
                    "user_id": user_id,
                    "user_email": user_email or (user_activity.get("user_email", "") if user_activity else ""),
                    "user_name": user_name or (user_activity.get("user_name", "") if user_activity else str(user_id)),
                    "total_messages": doc.get("message_count", 0),
                    "sessions": sessions_count,  # Date-based sessions (distinct session_ids)
                    "last_active": last_message_at
                })
            
            logger.info(f"Rankers by date: {len(formatted)} users (start_date={start_date}, end_date={end_date})")
            return formatted
            
        except Exception as e:
            logger.error(f"Error getting rankers by date: {e}")
            return []
    
    async def get_faqs_by_date(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get most frequently asked questions by date range from faq_events collection.
        
        Args:
            start_date: Start date for filtering (inclusive)
            end_date: End date for filtering (inclusive)
            limit: Maximum number of results to return
        """
        await self.connect()
        
        try:
            faq_events_collection = self.database["faq_events"]
            
            # Build date filter
            date_filter = {}
            if start_date or end_date:
                date_range = {}
                if start_date:
                    date_range["$gte"] = start_date
                if end_date:
                    date_range["$lte"] = end_date
                if date_range:
                    date_filter["created_at"] = date_range
            
            # Aggregate: group by question_hash, count occurrences
            pipeline = [
                {"$match": date_filter} if date_filter else {"$match": {}},
                {
                    "$group": {
                        "_id": "$question_hash",
                        "question": {"$first": "$question"},
                        "count": {"$sum": 1},
                        "last_asked": {"$max": "$created_at"}
                    }
                },
                {"$sort": {"count": -1, "last_asked": -1}},
                {"$limit": limit}
            ]
            
            results = await faq_events_collection.aggregate(pipeline).to_list(length=limit)
            
            formatted = []
            for doc in results:
                last_asked = doc.get("last_asked")
                if isinstance(last_asked, datetime):
                    last_asked = last_asked.isoformat()
                
                formatted.append({
                    "question": doc.get("question", ""),
                    "count": doc.get("count", 0),
                    "last_asked": last_asked
                })
            
            logger.info(f"FAQs by date: {len(formatted)} questions (start_date={start_date}, end_date={end_date})")
            return formatted
            
        except Exception as e:
            logger.error(f"Error getting FAQs by date: {e}")
            return []
    
    async def mark_session_ended(self, user_id: str, session_id: str):
        """
        Mark a session as ended in user_activity collection.
        This should be called when a session is explicitly closed or times out.
        """
        try:
            await self.connect()
            user_activity_collection = self.database["user_activity"]
            now = datetime.utcnow()
            
            # Find user activity
            user_activity = await user_activity_collection.find_one({"user_id": user_id})
            
            if user_activity:
                sessions = user_activity.get("sessions", [])
                
                # Find and update the session
                for s in sessions:
                    if s.get("session_id") == session_id and s.get("ended_at") is None:
                        s["ended_at"] = now
                        break
                
                # Recalculate totals (only count completed sessions)
                completed_sessions = [s for s in sessions if s.get("ended_at") is not None]
                total_messages = sum(s.get("message_count", 0) for s in sessions)
                total_sessions = len(completed_sessions)
                avg_messages = total_messages / total_sessions if total_sessions > 0 else 0
                
                await user_activity_collection.update_one(
                    {"user_id": user_id},
                    {
                        "$set": {
                            "sessions": sessions,
                            "total_sessions": total_sessions,
                            "avg_messages_per_session": round(avg_messages, 2)
                        }
                    }
                )
                
                logger.info(f"Marked session {session_id} as ended for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error marking session as ended: {e}")
    
    async def migrate_existing_data_to_user_activity(self):
        """
        Migration helper: Backfill user_activity collection from existing chat_sessions.
        This should be run once to migrate existing data.
        """
        try:
            await self.connect()
            sessions_collection = self.database["chat_sessions"]
            user_activity_collection = self.database["user_activity"]
            
            logger.info("Starting migration: chat_sessions -> user_activity")
            
            # Get all sessions
            all_sessions = await sessions_collection.find({}).to_list(length=None)
            
            # Group by user_id
            user_sessions_map = {}
            for session in all_sessions:
                user_id = session.get("user_id")
                if not user_id:
                    continue
                
                if user_id not in user_sessions_map:
                    user_sessions_map[user_id] = {
                        "user_id": user_id,
                        "user_email": session.get("user_email", ""),
                        "user_name": session.get("user_name", ""),
                        "sessions": [],
                        "total_messages": 0,
                        "total_sessions": 0,
                        "last_active": session.get("updated_at") or session.get("created_at"),
                        "created_at": session.get("created_at")
                    }
                
                # Count user messages in this session
                messages = session.get("messages", [])
                user_message_count = sum(1 for msg in messages if msg.get("role") == "user")
                
                user_sessions_map[user_id]["sessions"].append({
                    "session_id": session.get("session_id"),
                    "started_at": session.get("created_at"),
                    "ended_at": session.get("updated_at"),  # Assume ended if updated_at exists
                    "message_count": user_message_count
                })
                user_sessions_map[user_id]["total_messages"] += user_message_count
            
            # Calculate totals and upsert user_activity documents
            migrated_count = 0
            for user_id, activity_data in user_sessions_map.items():
                # Calculate totals
                completed_sessions = [s for s in activity_data["sessions"] if s.get("ended_at") is not None]
                activity_data["total_sessions"] = len(completed_sessions)
                activity_data["avg_messages_per_session"] = (
                    activity_data["total_messages"] / activity_data["total_sessions"]
                    if activity_data["total_sessions"] > 0 else 0
                )
                
                # Upsert user activity
                await user_activity_collection.update_one(
                    {"user_id": user_id},
                    {"$set": activity_data},
                    upsert=True
                )
                migrated_count += 1
            
            logger.info(f"Migration complete: {migrated_count} users migrated to user_activity")
            return {"migrated_users": migrated_count, "total_sessions": len(all_sessions)}
            
        except Exception as e:
            logger.error(f"Error migrating data: {e}")
            raise e
    
    async def update_user_profile(
        self,
        user_id: str,
        team_name: str,
        manager_email: str,
        manager_name: str,
        role: str
    ) -> bool:
        """
        Update user profile with team, manager, and role information.
        
        Args:
            user_id: User ID (email)
            team_name: Team name from teams.py
            manager_email: Team lead email
            manager_name: Team lead name
            role: User's role/job title
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.connect()
            user_activity_collection = self.database["user_activity"]
            
            # Update or create user_activity document with profile info
            await user_activity_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "team_name": team_name,
                        "manager_email": manager_email,
                        "manager_name": manager_name,
                        "role": role
                    }
                },
                upsert=True
            )
            
            logger.info(f"Updated user profile for {user_id}: team={team_name}, role={role}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating user profile for {user_id}: {e}")
            return False
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        Get user profile including team, manager, and role from user_activity.
        
        Args:
            user_id: User ID (email)
            
        Returns:
            Dictionary with profile info or None if not found
        """
        try:
            await self.connect()
            user_activity_collection = self.database["user_activity"]
            
            user_doc = await user_activity_collection.find_one(
                {"user_id": user_id},
                {
                    "user_id": 1,
                    "user_email": 1,
                    "user_name": 1,
                    "team_name": 1,
                    "manager_email": 1,
                    "manager_name": 1,
                    "role": 1
                }
            )
            
            if user_doc:
                # Convert ObjectId to string if present
                if "_id" in user_doc:
                    user_doc["_id"] = str(user_doc["_id"])
                return user_doc
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user profile for {user_id}: {e}")
            return None

# Global instance
mongodb_memory = MongoDBMemoryManager()

# Async wrapper functions to maintain compatibility with existing code
async def get_or_create_user_conversation(user_id: str) -> List[Dict[str, str]]:
    """Get or create a conversation for a specific user."""
    return await mongodb_memory.get_or_create_user_conversation(user_id)

async def add_to_conversation(user_id: str, role: str, content: str):
    """Add a message to the user's conversation history."""
    await mongodb_memory.add_to_conversation(user_id, role, content)

async def get_conversation_context(user_id: str) -> str:
    """Get formatted conversation context for a user (legacy method)."""
    return await mongodb_memory.get_conversation_context(user_id)

async def get_user_chat_history(user_id: str) -> List[Dict[str, str]]:
    """Get full chat history for a user."""
    return await mongodb_memory.get_user_chat_history(user_id)

async def clear_user_chat_history(user_id: str):
    """Clear chat history for a specific user."""
    await mongodb_memory.clear_user_chat_history(user_id)

# Additional utility functions
async def get_all_users() -> List[str]:
    """Get list of all user IDs in the database."""
    return await mongodb_memory.get_all_users()

async def get_conversation_stats() -> Dict:
    """Get statistics about conversations."""
    return await mongodb_memory.get_conversation_stats()

async def close_mongodb_connection():
    """Close MongoDB connection."""
    await mongodb_memory.disconnect()

# Session management functions
async def save_session(session_data: Dict):
    """Save or update a chat session."""
    await mongodb_memory.save_session(session_data)

async def get_all_sessions(limit: int = 30) -> List[Dict]:
    """Get recent sessions from all users."""
    return await mongodb_memory.get_all_sessions(limit)

async def get_user_sessions(user_id: str, limit: int = 50, include_messages: bool = False) -> List[Dict]:
    """Get sessions for a specific user."""
    return await mongodb_memory.get_user_sessions(user_id, limit, include_messages)

async def get_session_by_id(session_id: str, include_messages: bool = False) -> Optional[Dict]:
    """Get a specific session by ID."""
    return await mongodb_memory.get_session_by_id(session_id, include_messages)

async def create_shared_chat(session_id: str, user_email: str, share_token: str) -> Dict:
    """Create a shareable link for a chat session."""
    return await mongodb_memory.create_shared_chat(session_id, user_email, share_token)

async def get_shared_chat(share_token: str) -> Optional[Dict]:
    """Get shared chat information by token."""
    return await mongodb_memory.get_shared_chat(share_token)

async def get_user_statistics(
    exclude_users: Optional[List[str]] = None
) -> List[Dict]:
    """Get ALL-TIME user statistics from user_activity collection (single source of truth)."""
    return await mongodb_memory.get_user_statistics(exclude_users=exclude_users)

async def get_rankers_by_date(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    exclude_users: Optional[List[str]] = None,
    limit: int = 100
) -> List[Dict]:
    """Get user rankers by date range from message_events collection."""
    return await mongodb_memory.get_rankers_by_date(start_date, end_date, exclude_users, limit)

async def get_faqs_by_date(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 50
) -> List[Dict]:
    """Get most frequently asked questions by date range from faq_events collection."""
    return await mongodb_memory.get_faqs_by_date(start_date, end_date, limit)

async def mark_session_ended(user_id: str, session_id: str):
    """Mark a session as ended in user_activity collection."""
    return await mongodb_memory.mark_session_ended(user_id, session_id)

async def update_user_profile(
    user_id: str,
    team_name: str,
    manager_email: str,
    manager_name: str,
    role: str
) -> bool:
    """Update user profile with team, manager, and role information."""
    return await mongodb_memory.update_user_profile(
        user_id, team_name, manager_email, manager_name, role
    )

async def get_user_profile(user_id: str) -> Optional[Dict]:
    """Get user profile including team, manager, and role."""
    return await mongodb_memory.get_user_profile(user_id)

async def migrate_existing_data_to_user_activity():
    """Migration helper: Backfill user_activity collection from existing chat_sessions."""
    return await mongodb_memory.migrate_existing_data_to_user_activity()
