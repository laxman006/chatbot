import { ChatSession, User, OtherUserChat } from '@/types/chat';
import { apiFetch } from '@/lib/api';

// Get user-specific localStorage key
export function getUserStorageKey(key: string): string {
  if (typeof window === 'undefined') return key;
  
  const user = JSON.parse(localStorage.getItem('user') || 'null');
  const userId = user?.id || 'anonymous';
  return `${key}_${userId}`;
}

// Create a new session ID
export function createNewSessionId(): string {
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const randomId = Math.random().toString(36).substr(2, 9);
  return `cf.conversation.${date}.${randomId}`;
}

// Get current session ID from localStorage
export function getCurrentSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(getUserStorageKey('chatbot_session_id'));
}

// Set current session ID to localStorage
export function setCurrentSessionId(sessionId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(getUserStorageKey('chatbot_session_id'), sessionId);
}

// Get all sessions from localStorage (filter out empty sessions)
export function getAllSessions(): ChatSession[] {
  if (typeof window === 'undefined') return [];
  
  try {
    const storageKey = getUserStorageKey('chat_sessions');
    const sessionsStr = localStorage.getItem(storageKey);
    const sessions = sessionsStr ? JSON.parse(sessionsStr) : [];
    // Filter out sessions with no messages (empty chats)
    return sessions.filter((s: ChatSession) => s.messages && s.messages.length > 0);
  } catch (e) {
    console.error('[SESSIONS] Failed to load sessions:', e);
    return [];
  }
}

// Save all sessions to localStorage
export function saveAllSessions(sessions: ChatSession[]): void {
  if (typeof window === 'undefined') return;
  
  try {
    const storageKey = getUserStorageKey('chat_sessions');
    localStorage.setItem(storageKey, JSON.stringify(sessions));
  } catch (e) {
    console.error('[SESSIONS] Failed to save sessions:', e);
  }
}

// Get a specific session by ID
export function getSessionById(sessionId: string): ChatSession | null {
  const sessions = getAllSessions();
  return sessions.find(s => s.id === sessionId) || null;
}

// Get all deleted sessions from localStorage
export function getDeletedSessions(): ChatSession[] {
  if (typeof window === 'undefined') return [];
  
  try {
    const storageKey = getUserStorageKey('deleted_chat_sessions');
    const deletedStr = localStorage.getItem(storageKey);
    return deletedStr ? JSON.parse(deletedStr) : [];
  } catch (e) {
    console.error('[DELETED_SESSIONS] Failed to load deleted sessions:', e);
    return [];
  }
}

// Save deleted sessions to localStorage
export function saveDeletedSessions(sessions: ChatSession[]): void {
  if (typeof window === 'undefined') return;
  
  try {
    const storageKey = getUserStorageKey('deleted_chat_sessions');
    localStorage.setItem(storageKey, JSON.stringify(sessions));
    console.log('[DELETED_SESSIONS] Saved', sessions.length, 'deleted sessions');
  } catch (e) {
    console.error('[DELETED_SESSIONS] Failed to save deleted sessions:', e);
  }
}

// Delete a session (soft delete - move to deleted_chat_sessions)
export function deleteSession(sessionId: string): void {
  const sessions = getAllSessions();
  const sessionIndex = sessions.findIndex(s => s.id === sessionId);
  
  if (sessionIndex >= 0) {
    const [deletedSession] = sessions.splice(sessionIndex, 1);
    deletedSession.deletedAt = Date.now();
    
    // Save to deleted sessions
    const deletedSessions = getDeletedSessions();
    
    // 🔒 CRITICAL FIX: Defensive check before unshift
    if (!Array.isArray(deletedSessions)) {
      console.error('[SESSION] DeletedSessions is not an array:', deletedSessions);
      return;
    }
    
    deletedSessions.unshift(deletedSession);
    saveDeletedSessions(deletedSessions);
    
    // Save updated active sessions
    saveAllSessions(sessions);
    
    console.log('[SESSION] Soft deleted session:', sessionId);
  }
}

// ✅ NEW: Sync session with messages to backend (session-based auth)
export async function syncSessionToBackend(sessionData: ChatSession, retries = 2): Promise<void> {
  try {
    if (typeof window === 'undefined') return;
    
    // ✅ Session-based auth - session_id cookie sent automatically via proxy
    const response = await apiFetch('/chat/sessions/save', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionData.id,
        title: sessionData.title,
        created_at: sessionData.createdAt,
        updated_at: sessionData.timestamp,
        message_count: sessionData.messages.length,
        messages: sessionData.messages
      })
    });
    
    if (!response.ok) {
      if (response.status === 502 && retries > 0) {
        // ✅ Retry on 502 errors (backend unavailable) - transient connection issues
        console.warn(`[SESSION SYNC] Backend unavailable (502) - retrying (${retries} attempts left)`);
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second before retry
        return syncSessionToBackend(sessionData, retries - 1);
      }
      
      // ✅ Improved error handling for 502 and other errors
      const errorText = await response.text().catch(() => 'No error details');
      console.error('[SESSION SYNC] Failed with status:', response.status, {
        statusText: response.statusText,
        error: errorText,
        sessionId: sessionData.id,
        messageCount: sessionData.messages.length,
        retriesLeft: retries
      });
      
      if (response.status === 502) {
        console.warn('[SESSION SYNC] Backend unavailable (502) - session saved locally only');
      }
    } else {
      console.log('[SESSION SYNC] Successfully synced to backend');
    }
  } catch (error) {
    // ✅ Better error logging
    console.error('[SESSION] Failed to sync session to backend:', {
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      sessionId: sessionData.id,
      retriesLeft: retries
    });
    
    // ✅ Retry on network errors if retries available
    if (retries > 0 && (error instanceof TypeError || error instanceof Error)) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      // Retry on network errors (fetch failures, connection errors)
      if (errorMessage.includes('fetch') || errorMessage.includes('network') || errorMessage.includes('Failed to fetch')) {
        console.warn(`[SESSION SYNC] Network error - retrying (${retries} attempts left)`);
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second before retry
        return syncSessionToBackend(sessionData, retries - 1);
      }
    }
    
    // ✅ Don't throw - session is saved locally, sync can retry later
    console.warn('[SESSION SYNC] Session saved locally - will retry sync on next save');
  }
}

// ✅ NEW: Fetch user sessions from backend (session-based auth)
export async function fetchAndMergeUserSessions(): Promise<void> {
  try {
    if (typeof window === 'undefined') return;
    
    const user = getCurrentUser();
    if (!user || !user.id) {
      console.log('[SESSIONS] No authenticated user, skipping backend fetch');
      return;
    }
    
    console.log('[SESSIONS] Fetching sessions from backend for user:', user.id);
    
    // ✅ Session-based auth - session_id cookie sent automatically via proxy
    const response = await apiFetch(`/chat/sessions/user/${user.id}?include_messages=true`, {
      method: 'GET'
    });
    
    // ✅ NEW: Handle 401 - session expired, redirect to login
    if (response.status === 401) {
      console.warn('[SESSIONS] Session expired, redirecting to login');
      localStorage.removeItem('user');
      window.location.href = '/login?error=session_expired';
      return;
    }
    
    if (!response.ok) {
      console.error('[SESSIONS] Failed to fetch sessions:', response.status);
      return;
    }
    
    const data = await response.json();
    const backendSessions = data.sessions || [];
    
    console.log(`[SESSIONS] Fetched ${backendSessions.length} sessions from backend`);
    
    if (backendSessions.length === 0) {
      return;
    }
    
    // Get local sessions
    const localSessions = getAllSessions();
    const localSessionIds = new Set(localSessions.map((s: ChatSession) => s.id));
    
    // Merge backend sessions with local sessions
    const mergedSessions = [...localSessions];
    let addedCount = 0;
    
    for (const backendSession of backendSessions) {
      if (!localSessionIds.has(backendSession.session_id)) {
        // Convert backend session format to frontend format
        mergedSessions.push({
          id: backendSession.session_id,
          title: backendSession.title,
          timestamp: backendSession.updated_at,
          createdAt: backendSession.created_at,
          messages: backendSession.messages || []
        });
        addedCount++;
      }
    }
    
    if (addedCount > 0) {
      console.log(`[SESSIONS] Added ${addedCount} sessions from backend`);
      // Sort by timestamp (most recent first)
      mergedSessions.sort((a, b) => b.timestamp - a.timestamp);
      saveAllSessions(mergedSessions);
    }
  } catch (error) {
    console.error('[SESSIONS] Failed to fetch and merge sessions:', error);
  }
}

// ✅ NEW: Fetch all users' chats (session-based auth)
export async function fetchAllUsersChats(): Promise<OtherUserChat[]> {
  try {
    if (typeof window === 'undefined') return [];
    
    // ✅ Session-based auth - session_id cookie sent automatically via proxy
    const response = await apiFetch('/chat/sessions/all?limit=15', {
      method: 'GET'
    });
    
    // ✅ NEW: Handle 401 - session expired, redirect to login
    if (response.status === 401) {
      console.warn('[SESSIONS] Session expired, redirecting to login');
      localStorage.removeItem('user');
      window.location.href = '/login?error=session_expired';
      return [];
    }
    
    if (response.ok) {
      const data = await response.json();
      return data.sessions || [];
    }
    
    return [];
  } catch (error) {
    console.error('[SESSION] Failed to fetch all users chats:', error);
    return [];
  }
}

// ✅ NEW: Load another user's chat session (read-only, session-based auth)
export async function loadOthersSession(
  otherSessionId: string
): Promise<ChatSession | null> {
  try {
    if (typeof window === 'undefined') return null;
    
    const user = getCurrentUser();
    if (!user) {
      console.error('[SESSION] User not authenticated for loading others session');
      return null;
    }
    
    console.log('[SESSION] Attempting to load others session:', otherSessionId);
    
    // Check if this is a conversation_id format (MongoDB ObjectId - 24 hex characters)
    // MongoDB ObjectIds are 24 hex characters, so check if it matches that pattern
    const isConversationId = /^[0-9a-fA-F]{24}$/.test(otherSessionId);
    
    if (isConversationId) {
      // New format: conversation_id (MongoDB _id)
      console.log('[SESSION] Loading others session with conversation_id:', otherSessionId);
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      // Use encodeURIComponent to handle URL encoding properly
      const response = await apiFetch(`/chat/sessions/by-conversation/${encodeURIComponent(otherSessionId)}`, {
        method: 'GET'
      });
      
      // ✅ NEW: Handle 401 - session expired, redirect to login
      if (response.status === 401) {
        console.warn('[SESSION] Session expired, redirecting to login');
        localStorage.removeItem('user');
        window.location.href = '/login?error=session_expired';
        return null;
      }
      
      if (response.status === 403) {
        console.error('[SESSION] Access denied (403) - user does not have permission to view this chat');
        console.error('[SESSION] This chat may be from another user that you no longer have access to');
        return null;
      }
      
      if (response.status === 404) {
        console.error('[SESSION] Chat not found (404) - this chat may have been deleted');
        return null;
      }
      
      if (!response.ok) {
        console.error('[SESSION] Failed to load other user session: HTTP', response.status);
        const errorText = await response.text();
        console.error('[SESSION] Error details:', errorText);
        return null;
      }
      
      const data = await response.json();
      
      if (data.error) {
        console.error('[SESSION] Backend error:', data.error);
        return null;
      }
      
      console.log('[SESSION] Successfully loaded others session:', data.title);
      
      return {
        id: otherSessionId, // Use conversation_id as session id
        title: data.title,
        timestamp: Date.now(), // Use current timestamp
        createdAt: Date.now(),
        messages: data.messages || []
      };
    } else if (otherSessionId.startsWith('user_chat_')) {
      // Legacy format: user_chat_{user_id} (backward compatibility)
      const userId = otherSessionId.replace('user_chat_', '');
      console.log('[SESSION] Loading others session with userId (legacy format):', userId);
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch(`/chat/sessions/user/${userId}?include_messages=true`, {
        method: 'GET'
      });
      
      // ✅ NEW: Handle 401 - session expired, redirect to login
      if (response.status === 401) {
        console.warn('[SESSION] Session expired, redirecting to login');
        localStorage.removeItem('user');
        window.location.href = '/login?error=session_expired';
        return null;
      }
      
      if (response.status === 403) {
        console.error('[SESSION] Access denied (403) - user does not have permission to view this chat');
        console.error('[SESSION] This chat may be from another user that you no longer have access to');
        return null;
      }
      
      if (response.status === 404) {
        console.error('[SESSION] Chat not found (404) - this chat may have been deleted');
        return null;
      }
      
      if (!response.ok) {
        console.error('[SESSION] Failed to load other user session: HTTP', response.status);
        const errorText = await response.text();
        console.error('[SESSION] Error details:', errorText);
        return null;
      }
      
      const data = await response.json();
      const sessions = data.sessions || [];
      
      if (sessions.length === 0) {
        console.log('[SESSION] No sessions found for user');
        return null;
      }
      
      // Get the most recent session
      const mostRecentSession = sessions[0];
      
      console.log('[SESSION] Successfully loaded others session:', mostRecentSession.title);
      
      return {
        id: mostRecentSession.session_id,
        title: mostRecentSession.title,
        timestamp: mostRecentSession.updated_at,
        createdAt: mostRecentSession.created_at,
        messages: mostRecentSession.messages || []
      };
    } else {
      // Invalid format
      console.error('[SESSION] Invalid others session format:', otherSessionId);
      console.error('[SESSION] Expected format: MongoDB ObjectId (24 hex chars) or user_chat_* for legacy');
      return null;
    }
  } catch (error) {
    console.error('[SESSION] Failed to load other user session:', error);
    return null;
  }
}

// ✅ NEW: Get current user from localStorage (no tokens stored)
// User info (id, name, email) is stored for UI display only
// Session is managed via httpOnly cookie (session_id)
export function getCurrentUser(): User | null {
  if (typeof window === 'undefined') return null;
  
  try {
    const userStr = localStorage.getItem('user');
    if (!userStr) return null;
    const user = JSON.parse(userStr);
    // Remove any legacy token fields if they exist
    delete user.access_token;
    delete user.refresh_token;
    delete user.token_expires_at;
    delete user.token_issued_at;
    return user;
  } catch (e) {
    console.error('[USER] Failed to parse user:', e);
    return null;
  }
}

// ✅ SIMPLE SESSION CHECK (ONLY SOURCE OF TRUTH)
// This is the ONLY function that should be used to check authentication
export async function checkSession(): Promise<boolean> {
  try {
    const response = await apiFetch('/chat/sessions/all?limit=1', {
      method: 'GET'
    });
    return response.status === 200;
  } catch (error) {
    console.error('[SESSION] checkSession failed:', error);
    return false;
  }
}

// ✅ DEPRECATED: Token verification no longer needed
// Session is validated automatically via session_id cookie
// This function is kept for backward compatibility but should not be used
export async function verifyToken(accessToken: string): Promise<boolean> {
  console.warn('[AUTH] verifyToken() is deprecated - use checkSession() instead');
  return checkSession();
}

// ============================================================================
// ✅ NEW: Session Refresh (replaces token refresh)
// ============================================================================

/**
 * ✅ NEW: Refresh session tokens (backend handles everything)
 * Session tokens are refreshed automatically by backend when needed.
 * Frontend just calls this endpoint periodically to ensure session stays fresh.
 * 
 * @returns true if session is valid, false if session expired
 */
export async function refreshSession(): Promise<boolean> {
  try {
    if (typeof window === 'undefined') return false;
    
    console.log('[AUTH] Refreshing session...');
    
    // ✅ Session-based auth - session_id cookie sent automatically via proxy
    const response = await apiFetch('/auth/session/refresh', {
      method: 'POST'
    });
    
    if (response.ok) {
      console.log('[AUTH] ✅ Session refreshed successfully');
      return true;
    } else if (response.status === 401) {
      console.warn('[AUTH] Session expired');
      localStorage.removeItem('user');
      window.location.href = '/login?error=session_expired';
      return false;
    } else {
      console.error('[AUTH] Session refresh failed:', response.status);
      return false;
    }
  } catch (error) {
    console.error('[AUTH] Session refresh error:', error);
    return false;
  }
}

// ============================================================================
// ✅ NEW: Background Session Monitor (replaces token monitor)
// ============================================================================

let sessionMonitorInterval: NodeJS.Timeout | null = null;

/**
 * ✅ NEW: Start background session monitoring.
 * Checks session validity every 5 minutes and refreshes if needed.
 */
export function startSessionMonitor(): void {
  if (typeof window === 'undefined') return;
  
  // Don't start multiple monitors
  if (sessionMonitorInterval) {
    console.log('[SESSION_MONITOR] Already running');
    return;
  }
  
  console.log('[SESSION_MONITOR] Starting background session monitor (checks every 5 minutes)');
  
  sessionMonitorInterval = setInterval(async () => {
    const user = getCurrentUser();
    if (!user) {
      console.log('[SESSION_MONITOR] No authenticated user, stopping monitor');
      stopSessionMonitor();
      return;
    }
    
    console.log('[SESSION_MONITOR] Periodic session check...');
    const sessionValid = await refreshSession();
    if (!sessionValid) {
      console.warn('[SESSION_MONITOR] Session invalid, user will be redirected to login');
    }
  }, 5 * 60 * 1000); // Every 5 minutes
}

/**
 * ✅ NEW: Stop background session monitoring.
 */
export function stopSessionMonitor(): void {
  if (sessionMonitorInterval) {
    clearInterval(sessionMonitorInterval);
    sessionMonitorInterval = null;
    console.log('[SESSION_MONITOR] Stopped background session monitor');
  }
}

// ============================================================================
// ❌ DEPRECATED: Token refresh functions (kept for backward compatibility)
// ============================================================================

/**
 * @deprecated Use refreshSession() instead - token refresh is handled by backend
 */
export async function refreshAccessToken(): Promise<boolean> {
  console.warn('[AUTH] refreshAccessToken() is deprecated - use refreshSession() instead');
  return refreshSession();
}

/**
 * @deprecated Token expiration is handled by backend session
 */
export function isTokenExpiringSoon(marginMinutes: number = 5): boolean {
  console.warn('[AUTH] isTokenExpiringSoon() is deprecated - session expiration handled by backend');
  return false;
}

/**
 * @deprecated Use session-based auth - no token validation needed
 */
export async function ensureValidToken(): Promise<boolean> {
  console.warn('[AUTH] ensureValidToken() is deprecated - use session-based auth instead');
  return refreshSession();
}

/**
 * @deprecated Use startSessionMonitor() instead
 */
export function startTokenMonitor(): void {
  console.warn('[AUTH] startTokenMonitor() is deprecated - use startSessionMonitor() instead');
  startSessionMonitor();
}

/**
 * @deprecated Use stopSessionMonitor() instead
 */
export function stopTokenMonitor(): void {
  console.warn('[AUTH] stopTokenMonitor() is deprecated - use stopSessionMonitor() instead');
  stopSessionMonitor();
}

