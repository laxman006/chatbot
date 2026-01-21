/* eslint-disable @typescript-eslint/no-explicit-any */
'use client';

import { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import type { ChatSession, SuggestedQuestion } from '@/types/chat';
import { fetchAndMergeUserSessions, getCurrentUser, clearUserLocalStorage } from '@/lib/session-utils';
import { apiFetch } from '@/lib/api';

// Character limit constants
const MAX_PROMPT_LENGTH = 20000; // ~5K tokens (safe for RAG)
const WARN_PROMPT_LENGTH = 10000; // ~2.5K tokens - warning threshold

interface InitOptions {
  router?: AppRouterInstance;
  initialSessionId?: string | null;
  preloadedSession?: ChatSession;
}

// Module-level state to track initialization
let isAppInitialized = false;
let currentInitializedSessionId: string | null = null;

// ============================================================================
// PHASE 2.5: Parallel Chat Generation (Frontend-Managed)
// ============================================================================
// Architecture: Each chat session owns its own generation state
// - Multiple chats can generate simultaneously
// - Switching sessions does NOT abort ongoing generation
// - UI state (disabled buttons) is scoped to ACTIVE session only
// - Backend receives independent requests per session
// ============================================================================

// Per-session generation state (NOT global)
const generatingStatus = new Map<string, boolean>();
// ✅ PHASE 2.5.4: Removed activeRequests - streams complete independently
// const activeRequests = new Map<string, AbortController>();

export function initializeChatApp(options: InitOptions = {}) {
  const { router, initialSessionId, preloadedSession } = options;
  
  // Guard: If already initialized with the same session, skip
  if (isAppInitialized && currentInitializedSessionId === initialSessionId) {
    console.log('[CHAT] App already initialized for session:', initialSessionId);
    return;
  }
  
  // Check if we're switching sessions (already initialized but different session)
  const isSwitchingSession = isAppInitialized && currentInitializedSessionId !== initialSessionId;
  
  if (isSwitchingSession) {
    console.log('[CHAT] Switching session from', currentInitializedSessionId, 'to', initialSessionId);
    
    // ✅ PHASE 2.5: DO NOT abort previous session's request
    // Allow multiple chats to generate in parallel
    // The previous session continues generating in the background
    // UI state is scoped to active session only (see updateUIForActiveSession)
    console.log('[CHAT] Previous session continues generating in background');
  }
  

  const messagesDiv = document.getElementById("messages");
  const input = document.getElementById("user-input") as HTMLTextAreaElement;
  const sendBtn = document.getElementById("send-btn") as HTMLButtonElement;
  const emptyState = document.getElementById("empty-state");
  const inputEmptyState = document.getElementById("user-input-empty") as HTMLTextAreaElement;
  const sendBtnEmptyState = document.getElementById("send-btn-empty") as HTMLButtonElement;
  const inputSection = document.querySelector(".chatgpt-input-section") as HTMLElement;

  // Helper function to check if a specific session is generating
  function isSessionGenerating(sid: string): boolean {
    return generatingStatus.get(sid) === true;
  }

  // Helper function to set generating state for a specific session
  function setSessionGenerating(sid: string, generating: boolean) {
    generatingStatus.set(sid, generating);
    updateUIForActiveSession();
  }

  // ✅ CORRECTION 1: UI updates only affect the active session
  // This prevents blocking all chats when one is generating
  function updateUIForActiveSession() {
    const isActiveGenerating = activeSessionId ? isSessionGenerating(activeSessionId) : false;
    
    const buttons = [sendBtn, sendBtnEmptyState];
    const inputs = [input, inputEmptyState];
    
    buttons.forEach(btn => {
      if (btn) {
        btn.disabled = isActiveGenerating;
        btn.style.opacity = isActiveGenerating ? '0.5' : '1';
        btn.style.cursor = isActiveGenerating ? 'not-allowed' : 'pointer';
        btn.title = isActiveGenerating ? 'Response is generating...' : 'Send message';
      }
    });
    
    inputs.forEach(inp => {
      if (inp) {
        inp.disabled = isActiveGenerating;
        inp.style.opacity = isActiveGenerating ? '0.7' : '1';
      }
    });
  }

  // Hide empty state when messages exist
  function updateEmptyState() {
    if (messagesDiv && emptyState && inputSection) {
      const hasMessages = messagesDiv.children.length > 0;
      emptyState.style.display = hasMessages ? 'none' : 'flex';
      messagesDiv.style.display = hasMessages ? 'block' : 'none';
      
      // Show/hide suggested questions based on message state
      const emptyStateQuestions = emptyState.querySelector('.suggested-questions-container') as HTMLElement;
      const inputSectionQuestions = inputSection.querySelector('.suggested-questions-container') as HTMLElement;
      
      if (emptyStateQuestions) {
        emptyStateQuestions.style.display = hasMessages ? 'none' : 'grid';
      }
      // Always hide suggested questions in bottom input section - only show in empty state
      if (inputSectionQuestions) {
        inputSectionQuestions.style.display = 'none';
      }
      
      // Show bottom input only when there are messages
      if (hasMessages) {
        inputSection.classList.add('show');
      } else {
        inputSection.classList.remove('show');
      }
      
      // Update chat header visibility
      renderChatHeader(isReadOnlyMode);
    }
  }
  
  // Get user-specific localStorage key
  function getUserStorageKey(key: string): string {
    const user = JSON.parse(localStorage.getItem('user') || 'null');
    const userId = user?.id || 'anonymous';
    return `${key}_${userId}`;
  }
  
  // Session management
  // Only load from localStorage if we're on /chat/[sessionId] route (initialSessionId is explicitly undefined)
  let sessionId: string | null;
  if (initialSessionId === null) {
    // We're on /chat/new - don't load any existing session
    sessionId = null;
  } else if (initialSessionId) {
    // We're on /chat/[sessionId] - use the provided session ID
    sessionId = initialSessionId;
  } else {
    // Legacy fallback - load from localStorage
    sessionId = localStorage.getItem(getUserStorageKey('chatbot_session_id'));
  }
  let currentSessionTitle = '';
  
  interface ChatSession {
    id: string;
    title: string;
    timestamp: number;
    createdAt: number;
    messages: Array<{role: string, content: string, traceId?: string, feedbackSubmitted?: boolean, feedbackRating?: 'thumbs_up' | 'thumbs_down', recommendedQuestions?: string[]}>;
    deletedAt?: number; // Timestamp when session was deleted (for soft delete)
  }

  // Type for API response from /chat/sessions/all endpoint
  interface OtherUserChat {
    session_id: string;
    conversation_id?: string;
    title: string;
    user_email?: string;
    created_at?: string;
  }
  
  function createNewSession(): string {
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const randomId = Math.random().toString(36).substr(2, 9);
    return `cf.conversation.${date}.${randomId}`;
  }
  
  // ✅ FIX: Declare isReadOnlyMode BEFORE it's used in updateEmptyState()
  // Track if we're in read-only mode (viewing others' chats)
  let isReadOnlyMode = false;
  
  // Initialize or create session (only auto-create if not provided explicitly)
  // Don't navigate immediately - wait for first message
  if (!initialSessionId) {
    // We're on /chat/new route - create a fresh session
    sessionId = createNewSession();
    localStorage.setItem(getUserStorageKey('chatbot_session_id'), sessionId);
    console.log('[SESSION] Created new session (will navigate after first message):', sessionId);
    
    // ✅ ALWAYS clear messages for new chat (defense in depth)
    if (messagesDiv) {
      messagesDiv.innerHTML = '';
    }
    // ✅ Also update empty state immediately to ensure UI is clean
    updateEmptyState();
  } else {
    // We're on /chat/[sessionId] route - use the provided session ID
    sessionId = initialSessionId;
    console.log('[SESSION] Using session from URL:', sessionId);
    localStorage.setItem(getUserStorageKey('chatbot_session_id'), sessionId);
  }
  
  // Track the currently active session (for UI highlighting)
  let activeSessionId: string | null = sessionId || null;
  
  // Track if this is a brand new session that needs URL navigation after first message
  let isNewSessionPendingNavigation = !initialSessionId && sessionId;
  
  // Load all sessions from localStorage (filter out empty sessions)
  function getAllSessions(): ChatSession[] {
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
  function saveAllSessions(sessions: ChatSession[]) {
    try {
      const storageKey = getUserStorageKey('chat_sessions');
      localStorage.setItem(storageKey, JSON.stringify(sessions));
    } catch (e) {
      console.error('[SESSIONS] Failed to save sessions:', e);
    }
  }
  
  // Get all deleted sessions from localStorage
  function getDeletedSessions(): ChatSession[] {
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
  function saveDeletedSessions(sessions: ChatSession[]) {
    try {
      const storageKey = getUserStorageKey('deleted_chat_sessions');
      localStorage.setItem(storageKey, JSON.stringify(sessions));
      console.log('[DELETED_SESSIONS] Saved', sessions.length, 'deleted sessions');
    } catch (e) {
      console.error('[DELETED_SESSIONS] Failed to save deleted sessions:', e);
    }
  }
  
  // Remove test sessions from localStorage (cleanup for production)
  function removeTestSessions() {
    try {
      const sessions = getAllSessions();
      const cleanedSessions = sessions.filter(session => {
        // Skip sessions with null/undefined id or title
        if (!session?.id || !session?.title) {
          return false; // Remove invalid sessions
        }
        return (
          !session.id.startsWith('test-') && 
          !session.title.toLowerCase().includes('test chat')
        );
      });
      
      if (sessions.length !== cleanedSessions.length) {
        console.log('[CLEANUP] Removed', sessions.length - cleanedSessions.length, 'test sessions');
        saveAllSessions(cleanedSessions);
        return true;
      }
      return false;
    } catch (e) {
      console.error('[CLEANUP] Failed to remove test sessions:', e);
      return false;
    }
  }

  // Utility: clear and reload suggested questions containers
  function reloadSuggestedQuestions() {
    const emptyContainer = document.getElementById('suggested-questions-empty');
    const mainContainer = document.getElementById('suggested-questions-main');
    if (emptyContainer) emptyContainer.innerHTML = '';
    if (mainContainer) mainContainer.innerHTML = '';
    loadSuggestedQuestions();
  }
  
  // Add test data for all time periods (for UI testing)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function addTestSessions() {
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    
    const testSessions: ChatSession[] = [
      // Today
      {
        id: 'test-today-1',
        title: 'Test chat from Today - Morning',
        timestamp: now - (2 * 60 * 60 * 1000), // 2 hours ago
        createdAt: now - (2 * 60 * 60 * 1000),
        messages: [
          { role: 'user', content: 'Test message from today' },
          { role: 'assistant', content: 'Test response from today' }
        ]
      },
      {
        id: 'test-today-2',
        title: 'Another test chat from Today',
        timestamp: now - (5 * 60 * 60 * 1000), // 5 hours ago
        createdAt: now - (5 * 60 * 60 * 1000),
        messages: [
          { role: 'user', content: 'Another test from today' },
          { role: 'assistant', content: 'Another response from today' }
        ]
      },
      // Yesterday
      {
        id: 'test-yesterday-1',
        title: 'Test chat from Yesterday - Morning',
        timestamp: now - (1.2 * oneDay), // 1.2 days ago
        createdAt: now - (1.2 * oneDay),
        messages: [
          { role: 'user', content: 'Test message from yesterday morning' },
          { role: 'assistant', content: 'Test response from yesterday morning' }
        ]
      },
      {
        id: 'test-yesterday-2',
        title: 'Test chat from Yesterday - Evening',
        timestamp: now - (1.8 * oneDay), // 1.8 days ago
        createdAt: now - (1.8 * oneDay),
        messages: [
          { role: 'user', content: 'Test message from yesterday evening' },
          { role: 'assistant', content: 'Test response from yesterday evening' }
        ]
      },
      // Older
      {
        id: 'test-older-1',
        title: 'Test chat from 3 days ago',
        timestamp: now - (3 * oneDay),
        createdAt: now - (3 * oneDay),
        messages: [
          { role: 'user', content: 'Test message from 3 days ago' },
          { role: 'assistant', content: 'Test response from 3 days ago' }
        ]
      },
      {
        id: 'test-older-2',
        title: 'Test chat from 1 week ago',
        timestamp: now - (7 * oneDay),
        createdAt: now - (7 * oneDay),
        messages: [
          { role: 'user', content: 'Test message from 1 week ago' },
          { role: 'assistant', content: 'Test response from 1 week ago' }
        ]
      },
      {
        id: 'test-older-3',
        title: 'Test chat from 2 weeks ago',
        timestamp: now - (14 * oneDay),
        createdAt: now - (14 * oneDay),
        messages: [
          { role: 'user', content: 'Test message from 2 weeks ago' },
          { role: 'assistant', content: 'Test response from 2 weeks ago' }
        ]
      },
      {
        id: 'test-older-4',
        title: 'Test chat from 1 month ago',
        timestamp: now - (30 * oneDay),
        createdAt: now - (30 * oneDay),
        messages: [
          { role: 'user', content: 'Test message from 1 month ago' },
          { role: 'assistant', content: 'Test response from 1 month ago' }
        ]
      }
    ];
    
    const existingSessions = getAllSessions();
    
    // Filter out test sessions that already exist
    const newTestSessions = testSessions.filter(test => 
      !existingSessions.some(existing => existing.id === test.id)
    );
    
    if (newTestSessions.length > 0) {
      const updatedSessions = [...existingSessions, ...newTestSessions];
      saveAllSessions(updatedSessions);
      console.log('[TEST DATA] Added', newTestSessions.length, 'test sessions');
    }
  }
  
  // View deleted sessions (for debugging)
  function viewDeletedSessions() {
    const deleted = getDeletedSessions();
    console.log('[DELETED_SESSIONS] Total deleted sessions:', deleted.length);
    console.table(deleted.map(s => ({
      id: s.id,
      title: s.title,
      deletedAt: s.deletedAt ? new Date(s.deletedAt).toLocaleString() : 'N/A',
      messageCount: s.messages?.length || 0
    })));
    return deleted;
  }
  
  // Clear all deleted sessions (permanent delete)
  function clearDeletedSessions() {
    if (!confirm('Permanently delete all sessions in trash? This cannot be undone.')) return;
    const storageKey = getUserStorageKey('deleted_chat_sessions');
    localStorage.removeItem(storageKey);
    console.log('[DELETED_SESSIONS] Cleared all deleted sessions');
  }
  
  // View current user's storage data (for debugging)
  function viewUserData() {
    const user = JSON.parse(localStorage.getItem('user') || 'null');
    console.log('=== Current User Data ===');
    console.log('User:', user ? `${user.name} (${user.email})` : 'Not logged in');
    console.log('User ID:', user?.id || 'N/A');
    console.log('\n=== Storage Keys ===');
    console.log('Active Sessions Key:', getUserStorageKey('chat_sessions'));
    console.log('Deleted Sessions Key:', getUserStorageKey('deleted_chat_sessions'));
    console.log('Session ID Key:', getUserStorageKey('chatbot_session_id'));
    console.log('\n=== Data Counts ===');
    const sessions = getAllSessions();
    const deleted = getDeletedSessions();
    console.log('Active Chats:', sessions.length);
    console.log('Deleted Chats:', deleted.length);
    console.log('Current Session ID:', sessionId);
    
    // Show all localStorage keys for this user
    console.log('\n=== All LocalStorage Keys ===');
    const userId = user?.id || 'anonymous';
    Object.keys(localStorage).forEach(key => {
      if (key.includes(userId)) {
        console.log(`- ${key}`);
      }
    });
  }
  
  // Expose to window for easy access in console
  (window as any).removeTestSessions = removeTestSessions;
  (window as any).viewDeletedSessions = viewDeletedSessions;
  (window as any).clearDeletedSessions = clearDeletedSessions;
  (window as any).viewUserData = viewUserData;
  
  // Save current session
  function saveCurrentSession(title?: string) {
    // ✅ FIX 3: Guard against saving inactive sessions from DOM
    // DOM only represents the currently active chat, not background chats
    if (!sessionId) {
      console.log('[SESSION SAVE] ⏭️ Skipping save — no active session');
      return;
    }
    
    // ✅ FIX: Prevent saving others' chats (read-only mode) to MY CHATS
    // Only save when user explicitly clicks "Continue in this thread"
    if (isReadOnlyMode) {
      console.log('[SESSION SAVE] ⏭️ Skipping save — read-only mode (others\' chat)');
      return;
    }
    
    const sessions = getAllSessions();
    
    // 🔒 CRITICAL FIX: Defensive check - ensure sessions is an array
    if (!Array.isArray(sessions)) {
      console.error('[SESSION SAVE] Sessions is not an array:', sessions);
      return; // Cannot save if sessions is not an array
    }
    
    const messages = Array.from(messagesDiv!.children)
      .map((child, index) => {
        const isUser = child.classList.contains('user-message-wrapper') || 
                       child.querySelector('.message.user');
        
        if (isUser) {
          const content = (child.querySelector('.message.user') as HTMLElement)?.textContent || '';
          return {
            role: 'user',
            content: content
          };
        } else {
          /* ================================
             PHASE 2.5.3 – STREAM-SAFE PERSISTENCE
             Skip messages that are still streaming to prevent partial content overwrites
             ================================ */
          if ((child as HTMLElement).dataset.generating === 'true') {
            console.log('[SESSION SAVE] ⏭️ Skipping in-progress bot message');
            return null; // Skip this message
          }
          /* ================================ */
          
          // Bot message - capture content and recommended questions
          const messageContentDiv = child.querySelector('.message-content') as HTMLElement;
        const content = messageContentDiv?.innerHTML || '';
        const traceId = (child as HTMLElement).dataset.traceId || undefined;
        const feedbackSubmitted = (child as HTMLElement).dataset.feedbackSubmitted === 'true';
        const feedbackRating = (child as HTMLElement).dataset.feedbackRating as ('thumbs_up' | 'thumbs_down' | undefined);
        const recommendedQuestionsDiv = child.querySelector('.recommended-questions');
        const recommendedQuestions: string[] = [];
        
        console.log(`[SESSION SAVE] Processing bot message ${index}, has .recommended-questions:`, !!recommendedQuestionsDiv);
        
        if (recommendedQuestionsDiv) {
          const questionBtns = recommendedQuestionsDiv.querySelectorAll('.recommended-question-btn');
          console.log(`[SESSION SAVE] Found ${questionBtns.length} question buttons`);
          questionBtns.forEach(btn => {
            const question = btn.getAttribute('data-question');
            if (question) {
              recommendedQuestions.push(question);
              console.log(`[SESSION SAVE] Captured question: "${question}"`);
            }
          });
        }
        
        const result = {
          role: 'assistant',
          content: content,
          traceId,
          feedbackSubmitted,
          feedbackRating,
          recommendedQuestions: recommendedQuestions.length > 0 ? recommendedQuestions : undefined
        };
        
        if (result.recommendedQuestions) {
          console.log('[SESSION SAVE] Saving', result.recommendedQuestions.length, 'recommended questions with message');
        }
        
        return result;
      }
    })
    .filter(msg => msg !== null); // 🔒 PHASE 2.5.3: Remove skipped generating messages
    
    if (messages.length === 0) return;
    
    // Generate title from first user message if not provided
    const sessionTitle = title || currentSessionTitle || messages[0]?.content.substring(0, 50) || 'New Chat';
    currentSessionTitle = sessionTitle;
    
    const existingIndex = sessions.findIndex(s => s.id === sessionId);
    const now = Date.now();
    const sessionData: ChatSession = {
      id: sessionId!,
      title: sessionTitle,
      timestamp: now,
      createdAt: existingIndex >= 0 ? sessions[existingIndex].createdAt : now,
      messages: messages
    };
    
    // Log what we're about to save
    const questionsCount = messages.filter(m => m.role === 'assistant' && 'recommendedQuestions' in m && m.recommendedQuestions).length;
    console.log(`[SESSION SAVE] Saving session with ${messages.length} messages, ${questionsCount} have recommended questions`);
    
    // Sessions is already validated as array above, safe to use unshift
    if (existingIndex >= 0) {
      sessions[existingIndex] = sessionData;
    } else {
      sessions.unshift(sessionData);
    }
    
    // Keep only last 50 sessions
    if (sessions.length > 50) {
      sessions.splice(50);
    }
    
    saveAllSessions(sessions);
    
    // Delay renderSessionHistory to allow immediate sidebar update to complete first
    // This ensures the sidebar shows the new chat immediately before the full re-render
    setTimeout(() => {
      renderSessionHistory().catch(err => console.error('[SESSION] Failed to render history:', err));
    }, 100);
    
    // Sync session metadata to backend
    syncSessionToBackend(sessionData);
  }
  
  // Save a session that completed generation in the background (not currently displayed)
  function saveCompletedBackgroundSession(completedSessionId: string, botDiv: HTMLElement) {
    console.log('[SESSION SYNC] Saving completed background session:', completedSessionId);
    
    const sessions = getAllSessions();
    const sessionIndex = sessions.findIndex(s => s.id === completedSessionId);
    
    if (sessionIndex === -1) {
      console.error('[SESSION SYNC] ❌ Session not found:', completedSessionId);
      return;
    }
    
    // Extract completed message data from botDiv
    const contentDiv = botDiv.querySelector('.message-content') as HTMLElement;
    const content = contentDiv?.innerHTML || '';
    const traceId = botDiv.dataset.traceId;
    const recommendedQuestionsDiv = botDiv.querySelector('.recommended-questions');
    const recommendedQuestions: string[] = [];
    
    // Extract recommended questions if present
    if (recommendedQuestionsDiv) {
      const questionBtns = recommendedQuestionsDiv.querySelectorAll('.recommended-question-btn');
      questionBtns.forEach(btn => {
        const question = btn.getAttribute('data-question');
        if (question) recommendedQuestions.push(question);
      });
    }
    
    // Add completed message to session
    sessions[sessionIndex].messages.push({
      role: 'assistant',
      content: content,
      traceId: traceId,
      recommendedQuestions: recommendedQuestions.length > 0 ? recommendedQuestions : undefined
    });
    
    // Update timestamp
    sessions[sessionIndex].timestamp = Date.now();
    
    // Save to storage
    saveAllSessions(sessions);
    
    console.log('[SESSION SYNC] ✅ Successfully synced background session, message count:', sessions[sessionIndex].messages.length);
    
    // Sync to backend
    syncSessionToBackend(sessions[sessionIndex]);
  }
  
  // ✅ NEW: Sync session metadata to backend (session-based auth)
  async function syncSessionToBackend(sessionData: ChatSession, retries = 2) {
    try {
      // ✅ Session-based auth - no token check needed, session_id cookie sent automatically
      console.log('[SESSION SYNC] Syncing to backend with', sessionData.messages.length, 'messages');
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch('/chat/sessions/save', {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionData.id,
          title: sessionData.title,
          created_at: sessionData.createdAt,
          updated_at: sessionData.timestamp,
          messages: sessionData.messages,  // ✅ Include messages array
          message_count: sessionData.messages.length
        })
      });
      
      if (response.ok) {
        console.log('[SESSION SYNC] Successfully synced to backend');
      } else if (response.status === 502 && retries > 0) {
        // ✅ Retry on 502 errors (backend unavailable) - transient connection issues
        console.warn(`[SESSION SYNC] Backend unavailable (502) - retrying (${retries} attempts left)`);
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second before retry
        return syncSessionToBackend(sessionData, retries - 1);
      } else {
        // ✅ Improved error handling for 502 and other errors
        const errorText = await response.text().catch(() => 'No error details');
        console.error('[SESSION SYNC] Failed with status:', response.status, {
          statusText: response.statusText,
          error: errorText,
          sessionId: sessionData.id,
          messageCount: sessionData.messages.length,
          retriesLeft: retries
        });
        
        // ✅ Don't throw error - session sync failure shouldn't break the app
        // The session is still saved locally, so it's not critical
        if (response.status === 502) {
          console.warn('[SESSION SYNC] Backend unavailable (502) - session saved locally only');
        }
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
  
  // ✅ NEW: Fetch all users' chats (session-based auth)
  async function fetchAllUsersChats(): Promise<OtherUserChat[]> {
    try {
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch('/chat/sessions/all?limit=15', {
        method: 'GET'
      });
      
      if (response.ok) {
        const data = await response.json();
        // Already filtered on backend, return all sessions
        return data.sessions || [];
      }
      
      return [];
    } catch (error) {
      console.error('[SESSION] Failed to fetch all users chats:', error);
      return [];
    }
  }
  
  // ✅ NEW: Load another user's chat session (read-only, session-based auth)
  async function loadOthersSession(otherSessionId: string) {
    try {
      // Set read-only mode
      isReadOnlyMode = true;
      
      console.log('[SESSION] Loading others session:', otherSessionId);
      
      let response: Response;
      
      // Check if this is a conversation_id format (MongoDB ObjectId - 24 hex characters)
      const isConversationId = /^[0-9a-fA-F]{24}$/.test(otherSessionId);
      
      if (isConversationId) {
        // New format: conversation_id (MongoDB _id)
        console.log('[SESSION] Loading others session with conversation_id:', otherSessionId);
        // Use encodeURIComponent to handle URL encoding properly
        response = await apiFetch(`/chat/sessions/by-conversation/${encodeURIComponent(otherSessionId)}`, {
          method: 'GET'
        });
      } else if (otherSessionId.startsWith('user_chat_')) {
        // Legacy format: user_chat_{user_id} (backward compatibility)
        const userId = otherSessionId.replace('user_chat_', '');
        console.log('[SESSION] Loading others session with userId (legacy format):', userId);
        response = await apiFetch(`/chat/sessions/messages/${userId}`, {
          method: 'GET'
        });
      } else {
        console.error('[SESSION] Invalid others session format:', otherSessionId);
        showToast('Invalid chat session format', 'error', 5000);
        return;
      }
      
      if (response.status === 403) {
        console.error('[SESSION] Access denied (403) - You do not have permission to view this chat');
        console.error('[SESSION] This chat may be from another user that you no longer have access to');
        showToast('Access denied: You cannot view this chat', 'error', 5000);
        return;
      }
      
      if (response.status === 404) {
        console.error('[SESSION] Chat not found (404) - This chat may have been deleted');
        showToast('Chat not found: This conversation may have been deleted', 'error', 5000);
        return;
      }
      
      if (!response.ok) {
        console.error('[SESSION] Failed to fetch messages:', response.status);
        const errorText = await response.text();
        console.error('[SESSION] Error details:', errorText);
        showToast('Failed to load chat: ' + response.statusText, 'error', 5000);
        return;
      }
      
      const data = await response.json();
      
      if (data.error) {
        console.error('[SESSION] Backend error:', data.error);
        showToast('Error: ' + data.error, 'error', 5000);
        return;
      }
      
      // Create a temporary session object that won't be saved
      const sessionData: ChatSession = {
        id: otherSessionId,
        title: data.title || 'Others Chat',
        timestamp: Date.now(),
        createdAt: Date.now(),
        messages: data.messages || []
      };
      
      console.log('[SESSION] Successfully loaded others session with', data.messages?.length || 0, 'messages');
      
      // Don't update sessionId to prevent this from being saved to user's history
      // Just display the messages
      loadSession(sessionData, true);
    } catch (error) {
      console.error('[SESSION] Failed to load others session:', error);
      alert('Failed to load this chat session.');
    }
  }
  
  // Continue in this thread - copy others' chat to user's own chats
  function continueInThisThread() {
    try {
      console.log('[CONTINUE] Starting continue in thread functionality');
      
      // Get current messages from the DOM
      const messages: Array<{role: string, content: string, traceId?: string, feedbackSubmitted?: boolean, feedbackRating?: 'thumbs_up' | 'thumbs_down', recommendedQuestions?: string[]}> = [];
      const messageElements = messagesDiv!.children;
      
      // Skip the read-only banner (first element)
      for (let i = 0; i < messageElements.length; i++) {
        const element = messageElements[i];
        
        // Skip read-only banner
        if (element.classList.contains('read-only-banner')) {
          continue;
        }
        
        // Check if it's a user message
        if (element.classList.contains('user-message-wrapper')) {
          const messageDiv = element.querySelector('.message.user') as HTMLElement;
          if (messageDiv) {
            messages.push({
              role: 'user',
              content: messageDiv.textContent || messageDiv.innerText || ''
            });
          }
        } 
        // Check if it's a bot message
        else if (element.classList.contains('message') && element.classList.contains('bot')) {
          const messageContentDiv = element.querySelector('.message-content') as HTMLElement;
          const content = messageContentDiv?.innerHTML || messageContentDiv?.textContent || '';
          const traceId = (element as HTMLElement).dataset.traceId || undefined;
          const feedbackSubmitted = (element as HTMLElement).dataset.feedbackSubmitted === 'true';
          const feedbackRating = (element as HTMLElement).dataset.feedbackRating as ('thumbs_up' | 'thumbs_down' | undefined);
          
          // Extract recommended questions if present
          const recommendedQuestionsDiv = element.querySelector('.recommended-questions');
          const recommendedQuestions: string[] = [];
          
          if (recommendedQuestionsDiv) {
            const questionBtns = recommendedQuestionsDiv.querySelectorAll('.recommended-question-btn');
            questionBtns.forEach(btn => {
              const question = btn.getAttribute('data-question');
              if (question) {
                recommendedQuestions.push(question);
              }
            });
          }
          
          messages.push({
            role: 'assistant',
            content: content,
            traceId,
            feedbackSubmitted,
            feedbackRating,
            recommendedQuestions: recommendedQuestions.length > 0 ? recommendedQuestions : undefined
          });
        }
      }
      
      if (messages.length === 0) {
        console.error('[CONTINUE] No messages found to copy');
        showToast('No messages to copy', 'error', 3000);
        return;
      }
      
      // Create new session ID
      const newSessionId = createNewSession();
      console.log('[CONTINUE] Created new session ID:', newSessionId);
      
      // Get the title from the current session (use first user message if no title)
      const firstUserMessage = messages.find(m => m.role === 'user');
      const sessionTitle = firstUserMessage 
        ? firstUserMessage.content.substring(0, 50) + (firstUserMessage.content.length > 50 ? '...' : '')
        : 'Copied Chat';
      
      // Create new session object
      const now = Date.now();
      const newSession: ChatSession = {
        id: newSessionId,
        title: sessionTitle,
        timestamp: now,
        createdAt: now,
        messages: messages
      };
      
      // Save to localStorage
      const sessions = getAllSessions();
      
      // 🔒 CRITICAL FIX: Defensive check before unshift
      if (!Array.isArray(sessions)) {
        console.error('[SESSION] Sessions is not an array:', sessions);
        return;
      }
      
      sessions.unshift(newSession);
      
      // Keep only last 50 sessions
      if (sessions.length > 50) {
        sessions.splice(50);
      }
      
      saveAllSessions(sessions);
      console.log('[CONTINUE] Saved new session to localStorage with', messages.length, 'messages');
      
      // Sync session metadata to backend
      syncSessionToBackend(newSession);
      
      // Reset read-only mode
      isReadOnlyMode = false;
      
      // Navigate to the new session
      if (router) {
        router.push(`/chat/${newSessionId}`);
      } else {
        // Fallback: reload the session directly
        loadSession(newSession, false);
        showToast('Chat copied successfully! You can now continue the conversation.', 'success', 4000);
      }
      
    } catch (error) {
      console.error('[CONTINUE] Failed to continue in thread:', error);
      showToast('Failed to copy chat. Please try again.', 'error', 4000);
    }
  }
  
  // Expose continueInThisThread to window for onclick handler
  (window as any).continueInThisThread = continueInThisThread;
  
  // Expose loadOthersSession globally for client-side navigation from sidebar
  (window as any).loadOthersSession = loadOthersSession;
  
  // Share chat functionality
  async function shareChat() {
    // Get share button reference
    const shareButton = document.querySelector('.share-button') as HTMLButtonElement;
    const shareButtonSpan = shareButton?.querySelector('span');
    const originalButtonText = shareButtonSpan?.textContent || 'Share';
    
    try {
      // Show loading state
      if (shareButton) {
        shareButton.disabled = true;
        shareButton.style.opacity = '0.6';
        shareButton.style.cursor = 'not-allowed';
      }
      if (shareButtonSpan) {
        shareButtonSpan.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite; display: inline-block; margin-right: 4px;">
            <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
            <path d="M12 2 A10 10 0 0 1 22 12" stroke-opacity="0.75"></path>
          </svg>
          Sharing...
        `;
      }
      
      if (!sessionId) {
        showToast('No active chat session to share', 'error', 3000);
        console.warn('[SHARE] No session ID available');
        return;
      }
      
      // ✅ FIX 2: Session-based auth - check user exists (no token needed)
      const user = getCurrentUser();
      if (!user) {
        showToast('Authentication required to share chat', 'error', 3000);
        console.warn('[SHARE] User not authenticated');
        window.location.href = '/login?error=session_expired';
        return;
      }
      
      console.log('[SHARE] Attempting to share session:', sessionId);
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch(`/chat/share/${sessionId}`, {
        method: 'POST'
      });
      
      console.log('[SHARE] Response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('[SHARE] API Error Response:', response.status, errorText);
        
        // Parse error message
        let errorMessage = `Failed to create share link (${response.status})`;
        try {
          const errorData = JSON.parse(errorText);
          if (errorData.detail) {
            errorMessage = errorData.detail;
          }
        } catch {
          // Use default error message
        }
        
        // Provide helpful guidance based on error
        if (response.status === 404) {
          errorMessage = "Chat not found. Make sure the chat is saved before sharing. Try refreshing the page.";
        } else if (response.status === 403) {
          errorMessage = "You don't have permission to share this chat.";
        }
        
        throw new Error(errorMessage);
      }
      
      const data = await response.json();
      
      console.log('[SHARE] Response data:', data);
      
      // Build full shareable URL
      const shareUrl = `${window.location.origin}${data.share_url}`;
      
      // Copy to clipboard with fallback
      try {
        await navigator.clipboard.writeText(shareUrl);
        showToast('Share link copied to clipboard!', 'success', 4000);
      } catch (clipboardError) {
        console.warn('[SHARE] Clipboard copy failed, using fallback:', clipboardError);
        // Fallback: create a temporary textarea to copy
        const textarea = document.createElement('textarea');
        textarea.value = shareUrl;
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand('copy');
          showToast('Share link copied to clipboard!', 'success', 4000);
        } catch (execError) {
          console.error('[SHARE] Fallback copy also failed:', execError);
          showToast(`Share link: ${shareUrl}`, 'info', 5000);
        }
        document.body.removeChild(textarea);
      }
      
      console.log('[SHARE] Created share link:', shareUrl);
      
    } catch (error) {
      console.error('[SHARE] Failed to share chat:', error);
      showToast('Failed to create share link. Please try again.', 'error', 4000);
    } finally {
      // Restore button state
      if (shareButton) {
        shareButton.disabled = false;
        shareButton.style.opacity = '1';
        shareButton.style.cursor = 'pointer';
      }
      if (shareButtonSpan) {
        shareButtonSpan.textContent = originalButtonText;
      }
    }
  }
  
  // Expose shareChat to window for onclick handler
  (window as any).shareChat = shareChat;
  
  
  // Render chat header with conditional buttons
  function renderChatHeader(isReadOnly: boolean) {
    const headerContainer = document.getElementById('chat-header-container');
    if (!headerContainer) return;
    
    // Only show header if there are messages
    const hasMessages = messagesDiv && messagesDiv.children.length > 0;
    if (!hasMessages && messagesDiv && messagesDiv.innerHTML.trim() === '') {
      headerContainer.innerHTML = '';
      headerContainer.style.display = 'none';
      return;
    }
    
    headerContainer.style.display = 'block';
    
    // Build header HTML
    const readOnlyBadge = isReadOnly ? `
      <div class="read-only-badge">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
        <span>Read-Only</span>
      </div>
    ` : '';
    
    const continueButton = isReadOnly ? `
      <button class="header-btn continue-button" data-action="continue-thread" title="Copy this chat to your own chats and continue">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
          <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
        </svg>
        <span>Continue in this thread</span>
      </button>
    ` : '';
    
    // Share button is only for own chats (not read-only/others' chats)
    const shareButton = !isReadOnly ? `
      <button class="header-btn share-button" data-action="share-chat" title="Share this chat">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="18" cy="5" r="3"></circle>
          <circle cx="6" cy="12" r="3"></circle>
          <circle cx="18" cy="19" r="3"></circle>
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
        </svg>
        <span>Share</span>
      </button>
    ` : '';
    
    headerContainer.innerHTML = `
      <div class="chat-header">
        <div class="chat-header-content">
          ${readOnlyBadge}
          <div class="header-actions">
            ${continueButton}
            ${shareButton}
          </div>
        </div>
      </div>
    `;
  }
  
  // Add UTM parameter to URLs for tracking
  function addUtmParameter(url: string): string {
    if (!url || typeof url !== 'string') return url;
    
    // Skip if URL already has utm_source parameter
    if (url.includes('utm_source=')) return url;
    
    try {
      const urlObj = new URL(url);
      urlObj.searchParams.set('utm_source', 'ai.cloudfuze.com');
      return urlObj.toString();
    } catch {
      // If URL parsing fails, try simple string append
      const separator = url.includes('?') ? '&' : '?';
      return `${url}${separator}utm_source=ai.cloudfuze.com`;
    }
  }

  // Convert plain text URLs and markdown links to clickable links, preserving HTML
  function linkifyText(text: string): string {
    // Check if the text already contains HTML tags (from formatted responses)
    const hasHtmlTags = /<[^>]+>/.test(text);
    
    let processed = text;
    
    if (hasHtmlTags) {
      // Text has HTML formatting (from renderMarkdown)
      // First, add UTM to existing <a> tags
      processed = processed.replace(/href\s*=\s*["']([^"']+)["']/gi, (match, url) => {
        // Skip if URL already has utm_source
        if (url.includes('utm_source=')) {
          return match;
        }
        // Add UTM parameter
        const utmUrl = addUtmParameter(url);
        // Replace just the href value, keeping the quotes
        const quote = match.includes("'") ? "'" : '"';
        return `href=${quote}${utmUrl}${quote}`;
      });
      
      // Also handle any remaining markdown links that weren't converted (fallback case)
      // Only convert markdown links that aren't already inside HTML tags
      processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, linkText, url) => {
        // Check if this markdown link is inside an HTML tag (shouldn't convert)
        const beforeMatch = processed.substring(Math.max(0, processed.indexOf(match) - 50), processed.indexOf(match));
        if (beforeMatch.includes('<') && !beforeMatch.includes('>')) {
          return match; // Inside an HTML tag, don't convert
        }
        const utmUrl = addUtmParameter(url);
        return `<a href="${utmUrl}" target="_blank" rel="noopener noreferrer" style="color: #0033CC; text-decoration: underline;">${linkText}</a>`;
      });
    } else {
      // Plain text - convert markdown and URLs to links
      // First handle markdown links [text](url)
      processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, linkText, url) => {
        const utmUrl = addUtmParameter(url);
        return `<a href="${utmUrl}" target="_blank" rel="noopener noreferrer" style="color: #0033CC; text-decoration: underline;">${linkText}</a>`;
      });
      
      // Then handle plain URLs (that aren't already in anchor tags)
      const urlPattern = /(\b(https?|ftp|file):\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])/ig;
      processed = processed.replace(urlPattern, (url) => {
        // Avoid double-linking by checking if URL is already in a href attribute
        const beforeUrl = processed.substring(Math.max(0, processed.indexOf(url) - 10), processed.indexOf(url));
        if (beforeUrl.includes('href=')) {
          return url; // Already linked, don't modify
        }
        const utmUrl = addUtmParameter(url);
        return `<a href="${utmUrl}" target="_blank" rel="noopener noreferrer" style="color: #0033CC; text-decoration: underline;">${url}</a>`;
      });
    }
    
    return processed;
  }
  
  // Load a specific session
  function loadSession(sessionData: ChatSession, isReadOnly = false) {
    console.log('[SESSION] Loading session:', sessionData.id, 'with', sessionData.messages.length, 'messages', isReadOnly ? '(read-only)' : '');
    
    // Update read-only mode state
    isReadOnlyMode = isReadOnly;
    
    // Always update activeSessionId for UI highlighting
    activeSessionId = sessionData.id;
    
    // Update sessionId for both own and others' chats (needed for sharing)
    // But only save to localStorage for own chats (to prevent others' chats from being saved)
    sessionId = sessionData.id;
    currentSessionTitle = sessionData.title;
    
    if (!isReadOnly) {
      localStorage.setItem(getUserStorageKey('chatbot_session_id'), sessionId);
    }
    
    // Clear current messages
    messagesDiv!.innerHTML = '';
    
    // Render chat header
    renderChatHeader(isReadOnly);
    
    // Load session messages
    sessionData.messages.forEach((msg, index) => {
      if (msg.role === 'user') {
        addMessage(msg.content, 'user');
      } else {
        // Bot message with optional recommended questions
        const isLastMessage = index === sessionData.messages.length - 1;
        const hasRecommendations = msg.recommendedQuestions && msg.recommendedQuestions.length > 0;
        const showRecommendations = isLastMessage && hasRecommendations;
        
        if (showRecommendations) {
          console.log('[SESSION] Restoring', msg.recommendedQuestions!.length, 'recommended questions for last message');
        }
        
        const recommendedQuestionsHTML = showRecommendations 
          ? buildRecommendedQuestionsHTML(msg.recommendedQuestions!) 
          : '';
        
        const div = document.createElement("div");
        div.className = "message bot";
        if (msg.traceId) {
          div.dataset.traceId = msg.traceId;
          div.setAttribute('data-trace-id', msg.traceId);
        }
        
        // Render markdown to HTML first, then make links clickable
        let formattedContent = msg.content;
        
        // Check if content needs markdown rendering (doesn't already have HTML tags)
        const hasHtmlTags = /<[^>]+>/.test(msg.content);
        if (!hasHtmlTags) {
          // Content is markdown or plain text, render it
          formattedContent = renderMarkdown(msg.content);
        }
        
        // Make sure links are clickable
        const contentWithLinks = linkifyText(formattedContent);
        
        div.innerHTML = `
          <div class="message-content">${contentWithLinks}</div>
          <div class="feedback-buttons">
            <button class="copy-button" data-action="copy-message" title="Copy message">
              <img src="/images/copy-icon.svg?v=2" alt="Copy" width="16" height="16">
            </button>
            ${!isReadOnly ? `
            <button class="feedback-btn thumbs-up" data-action="feedback" data-rating="thumbs_up" title="Good response">
              <img src="/images/thumbs-up-icon.svg?v=2" alt="Thumbs up" width="16" height="16">
            </button>
            <button class="feedback-btn thumbs-down" data-action="feedback" data-rating="thumbs_down" title="Bad response">
              <img src="/images/thumbs-down-icon.svg?v=2" alt="Thumbs down" width="16" height="16">
            </button>
            ` : ''}
            <span class="feedback-text"></span>
          </div>
          ${recommendedQuestionsHTML}
        `;
        messagesDiv!.appendChild(div);

        // If feedback was already submitted, reflect it in the UI and disable buttons
        if (msg.feedbackSubmitted) {
          const feedbackButtons = div.querySelectorAll('.feedback-btn');
          feedbackButtons.forEach(btn => {
            const buttonEl = btn as HTMLButtonElement;
            buttonEl.disabled = true;
            buttonEl.style.cursor = 'not-allowed';
            buttonEl.style.opacity = '0.5';
            buttonEl.classList.remove('selected');
          });

          // Mark selected state based on stored rating
          if (msg.feedbackRating) {
            const targetBtn = div.querySelector(`.feedback-btn.${msg.feedbackRating === 'thumbs_up' ? 'thumbs-up' : 'thumbs-down'}`);
            if (targetBtn) targetBtn.classList.add('selected');
          }

          // Show confirmation text in matching color
          const feedbackText = div.querySelector('.feedback-text') as HTMLElement | null;
          if (feedbackText) {
            feedbackText.textContent = msg.feedbackRating === 'thumbs_down'
              ? "Thanks! We'll improve."
              : 'Thanks for your feedback!';
            feedbackText.style.color = msg.feedbackRating === 'thumbs_down' ? '#ef4444' : '#10a37f';
          }

          // Persist markers on the element
          div.dataset.feedbackSubmitted = 'true';
          if (msg.feedbackRating) {
            div.dataset.feedbackRating = msg.feedbackRating;
          }
        }
      }
    });
    
    // Disable input for read-only mode
    if (isReadOnly) {
      const inputEl = document.getElementById('user-input') as HTMLTextAreaElement;
      const sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
      if (inputEl) {
        inputEl.disabled = true;
        inputEl.placeholder = "Read-only mode - You cannot send messages";
        
        // Add security listener to prevent input even if disabled is bypassed
        inputEl.addEventListener('input', (e) => {
          if (isReadOnlyMode) {
            console.warn('[SECURITY] Attempted input in read-only mode detected');
            (e.target as HTMLTextAreaElement).value = '';
          }
        });
        
        // Prevent pasting in read-only mode
        inputEl.addEventListener('paste', (e) => {
          if (isReadOnlyMode) {
            console.warn('[SECURITY] Attempted paste in read-only mode detected');
            e.preventDefault();
          }
        });
      }
      if (sendBtn) {
        sendBtn.disabled = true;
        
        // Add security listener to prevent send even if disabled is bypassed
        sendBtn.addEventListener('click', (e) => {
          if (isReadOnlyMode) {
            console.warn('[SECURITY] Attempted send in read-only mode detected');
            e.preventDefault();
            e.stopPropagation();
            showToast('This chat is read-only. Use "Continue in this thread" to create an editable copy.', 'warning', 3000);
          }
        }, true);
      }
    } else {
      const inputEl = document.getElementById('user-input') as HTMLTextAreaElement;
      const sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
      if (inputEl) {
        inputEl.disabled = false;
        inputEl.placeholder = "Type your message here...";
      }
      if (sendBtn) sendBtn.disabled = false;
    }
    
    updateEmptyState();
    scrollToBottom();
  }
  
  // Update only the active state in sidebar (lightweight, no re-render)
  function updateSidebarActiveState(newActiveSessionId: string | null) {
    const sidebarHistory = document.getElementById('sidebar-history');
    const othersHistory = document.getElementById('others-history');
    
    const allHistoryItems = [
      ...(sidebarHistory ? Array.from(sidebarHistory.querySelectorAll('.history-item')) : []),
      ...(othersHistory ? Array.from(othersHistory.querySelectorAll('.history-item')) : [])
    ];
    
    allHistoryItems.forEach(item => {
      const sessionEl = item as HTMLElement;
      const sid = sessionEl.dataset.sessionId;
      if (sid === newActiveSessionId) {
        sessionEl.classList.add('active');
      } else {
        sessionEl.classList.remove('active');
      }
    });
    
    // Update activeSessionId for future reference
    activeSessionId = newActiveSessionId;
  }
  
  // Update sidebar immediately when a new message is sent (before response)
  function updateSidebarImmediately() {
    if (!sessionId) return;
    
    // ✅ FIX: Don't update sidebar for others' chats (read-only mode)
    if (isReadOnlyMode) {
      console.log('[SIDEBAR] ⏭️ Skipping sidebar update — read-only mode (others\' chat)');
      return;
    }
    
    const sidebarHistory = document.getElementById('sidebar-history');
    if (!sidebarHistory) return;
    
    // Check if this session already exists in the sidebar
    const existingItem = sidebarHistory.querySelector(`[data-session-id="${sessionId}"]`);
    if (existingItem) {
      // Session already exists, just update active state
      updateSidebarActiveState(sessionId);
      return;
    }
    
    // Get title from the first user message in DOM (most reliable source)
    let sessionTitle = 'New Chat';
    const firstUserMessage = messagesDiv!.querySelector('.message.user');
    if (firstUserMessage) {
      const messageText = firstUserMessage.textContent || '';
      sessionTitle = messageText.substring(0, 50) + (messageText.length > 50 ? '...' : '');
    }
    
      // Find or create "Today" section - optimize DOM queries
      let todaySection = sidebarHistory.querySelector('.history-section-content[data-section-id="today"]') as HTMLElement;
      
      if (!todaySection) {
        // Remove "no-history" message if exists
        const noHistory = sidebarHistory.querySelector('.no-history');
        if (noHistory) noHistory.remove();
        
        // Check if section title exists
        const sectionTitleExists = sidebarHistory.querySelector('.history-section-title[data-section-id="today"]');
        
        // Create Today section content
        todaySection = document.createElement('div');
        todaySection.className = 'history-section-content';
        todaySection.setAttribute('data-section-id', 'today');
        
        if (!sectionTitleExists) {
          // Create section title
          const sectionTitle = document.createElement('div');
          sectionTitle.className = 'history-section-title';
          sectionTitle.setAttribute('data-section-id', 'today');
          sectionTitle.innerHTML = `
            <span>Today</span>
            <button class="section-toggle-btn" data-section-id="today" title="Collapse">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="toggle-icon">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </button>
          `;
          sidebarHistory.appendChild(sectionTitle);
        }
        
        // Insert content after title
        const sectionTitle = sidebarHistory.querySelector('.history-section-title[data-section-id="today"]');
        if (sectionTitle) {
          sidebarHistory.insertBefore(todaySection, sectionTitle.nextSibling);
        } else {
          sidebarHistory.appendChild(todaySection);
        }
      }
      
      if (todaySection) {
        // Create new history item with minimal HTML for faster rendering
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item active';
        historyItem.setAttribute('data-session-id', sessionId);
        historyItem.style.transition = 'none'; // Disable transition for instant appearance
        historyItem.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
          <span class="history-item-title">${sessionTitle}</span>
          <button class="history-item-menu" data-session-id="${sessionId}" title="Delete chat">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              <line x1="10" y1="11" x2="10" y2="17"></line>
              <line x1="14" y1="11" x2="14" y2="17"></line>
            </svg>
          </button>
        `;
        
        // Insert at the beginning of Today section
        todaySection.insertBefore(historyItem, todaySection.firstChild);
        
        // Remove active class from all other items (optimize query)
        const allItems = sidebarHistory.querySelectorAll('.history-item');
        for (let i = 0; i < allItems.length; i++) {
          const item = allItems[i] as HTMLElement;
          if (item.getAttribute('data-session-id') !== sessionId) {
            item.classList.remove('active');
          }
        }
        
        // Re-enable transition after a brief moment for smooth interactions
        setTimeout(() => {
          historyItem.style.transition = '';
        }, 10);
        
        // Add click handler
        historyItem.addEventListener('click', (e) => {
          const target = e.target as HTMLElement;
          if (target.closest('.history-item-menu') || target.closest('.history-item-dropdown')) return;
          
          if (router) {
            router.push(`/chat/${sessionId}`);
          } else {
            const allSessions = getAllSessions();
            const session = allSessions.find(s => s.id === sessionId);
            if (session) {
              loadSession(session, false);
            }
          }
        });
        
        // Update activeSessionId
        activeSessionId = sessionId;
      }
  }
  
  // Render session history in sidebar
  async function renderSessionHistory() {
    const sidebarHistory = document.getElementById('sidebar-history');
    if (!sidebarHistory) return;
    
    const sessions = getAllSessions();
    
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    
    const today: ChatSession[] = [];
    const yesterday: ChatSession[] = [];
    const older: ChatSession[] = [];
    
    sessions.forEach(session => {
      const age = now - (session.createdAt || session.timestamp);
      if (age < oneDay) today.push(session);
      else if (age < 2 * oneDay) yesterday.push(session);
      else older.push(session);
    });
    
    let html = '';
    
    function renderSection(title: string, sessions: ChatSession[], sectionId: string, isOthersSection = false, defaultCollapsed = false) {
      if (sessions.length === 0) return '';
      
      // Check if section is collapsed (stored in localStorage, otherwise use default)
      const storedCollapsed = localStorage.getItem(`section_collapsed_${sectionId}`);
      const isCollapsed = storedCollapsed !== null ? storedCollapsed === 'true' : defaultCollapsed;
      
      let section = `
        <div class="history-section-title${isOthersSection ? ' others-section' : ''}" data-section-id="${sectionId}">
          <span>${title}</span>
          <button class="section-toggle-btn" data-section-id="${sectionId}" title="${isCollapsed ? 'Expand' : 'Collapse'}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="toggle-icon ${isCollapsed ? 'collapsed' : ''}">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>
        </div>
        <div class="history-section-content ${isCollapsed ? 'collapsed' : ''}" data-section-id="${sectionId}">
      `;
      
      sessions.forEach(session => {
        const isActive = session.id === activeSessionId;
        section += `
          <div class="history-item ${isActive ? 'active' : ''}${isOthersSection ? ' others-item' : ''}" data-session-id="${session.id}"${isOthersSection ? ' data-is-others="true"' : ''}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <span class="history-item-title">${session.title}</span>
            ${!isOthersSection ? `
            <button class="history-item-menu" data-session-id="${session.id}" title="Delete chat">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                <line x1="10" y1="11" x2="10" y2="17"></line>
                <line x1="14" y1="11" x2="14" y2="17"></line>
              </svg>
            </button>` : ''}
          </div>
        `;
      });
      
      section += '</div>';
      return section;
    }
    
    if (sessions.length === 0) {
      html = '<div class="no-history">No chat history yet</div>';
    } else {
      html += renderSection('Today', today, 'today', false, false);
      html += renderSection('Yesterday', yesterday, 'yesterday', false, true);
      html += renderSection('Older', older, 'older', false, true);
    }
    
    sidebarHistory.innerHTML = html;
    
    // Fetch and render others' chats in separate section
    const othersHistory = document.getElementById('others-history');
    let othersHtml = '';
    
    const othersChats = await fetchAllUsersChats();
    if (othersChats.length > 0) {
      // Render all others' chats without date grouping
      othersChats.forEach((chat: OtherUserChat) => {
        const displayTitle = chat.title.length > 40 ? chat.title.substring(0, 40) + '...' : chat.title;
        // Use conversation_id for URL routing, fallback to session_id for backward compatibility
        const urlId = chat.conversation_id || chat.session_id;
        const isActive = urlId === activeSessionId;
        
        othersHtml += `
          <div class="history-item others-item ${isActive ? 'active' : ''}" data-session-id="${urlId}" data-is-others="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <span class="history-item-title">${displayTitle}</span>
          </div>
        `;
      });
    } else {
      othersHtml = '<div class="no-history">No others\' chats yet</div>';
    }
    
    if (othersHistory) {
      othersHistory.innerHTML = othersHtml;
    }
    
    // Add click handlers for both my chats and others' chats
    const allHistoryItems = [...Array.from(sidebarHistory.querySelectorAll('.history-item')), 
                             ...(othersHistory ? Array.from(othersHistory.querySelectorAll('.history-item')) : [])];
    
    allHistoryItems.forEach(item => {
      const sessionEl = item as HTMLElement;
      const sid = sessionEl.dataset.sessionId;
      const isOthers = sessionEl.dataset.isOthers === 'true';
      
      sessionEl.addEventListener('click', (e) => {
        const target = e.target as HTMLElement;
        // Don't trigger if clicking on menu button or dropdown
        if (target.closest('.history-item-menu') || target.closest('.history-item-dropdown')) return;
        
        // Update active state immediately for visual feedback
        allHistoryItems.forEach(item => {
          (item as HTMLElement).classList.remove('active');
        });
        sessionEl.classList.add('active');
        
        /* =====================================================
           PHASE 2.5.2 – MANUAL SAVE BEFORE SESSION SWITCH
           
           Since we bypass router.push() to avoid page reload,
           we must manually trigger saveCurrentSession() here.
           
           This is Fix #2 from Phase 2.5.1, re-implemented for
           client-side-only navigation architecture.
           ===================================================== */
        
        // Save current session before switching (critical for data integrity)
        // ✅ FIX 1: Only save if session is not generating
        if (sessionId && typeof saveCurrentSession === 'function') {
          try {
            if (!isSessionGenerating(sessionId)) {
              saveCurrentSession();
              console.log('[SIDEBAR] ✅ Saved completed session before switch:', sessionId);
            } else {
              console.log('[SIDEBAR] ⏭️ Skip save — session still generating:', sessionId);
            }
          } catch (err) {
            console.error('[SIDEBAR] ❌ Failed to save before switch:', err);
          }
        }
        
        /* ===================================================== */
        
        // Now perform client-side session switch
        if (isOthers) {
          // Load others' session
          loadOthersSession(sid!);
          // ✅ CORRECT FIX: Use router.push() instead of window.history.pushState()
          // This keeps Next.js router in sync with browser URL
          if (router) {
            router.push(`/chat/others/${sid}`);
          }
        } else {
          // Load own session
          const session = sessions.find(s => s.id === sid);
          if (session) {
            loadSession(session, false);
            // ✅ CORRECT FIX: Use router.push() instead of window.history.pushState()
            // This keeps Next.js router in sync with browser URL
            if (router) {
              router.push(`/chat/${sid}`);
            }
          }
        }
        /* ===================================================== */
      });
    });
    
    // Use event delegation for delete button handlers (trash bin icon)
    // This ensures it works even when chat history is dynamically updated
    sidebarHistory.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      
      // Check if clicked on delete button or its child (SVG)
      const menuBtn = target.closest('.history-item-menu') as HTMLElement;
      if (menuBtn) {
        e.preventDefault();
        e.stopPropagation();
        const sid = menuBtn.dataset.sessionId;
        
        console.log('[DELETE] Trash icon clicked for session:', sid);
        
        // Close all other dropdowns first
        document.querySelectorAll('.history-item-dropdown').forEach(d => {
          d.remove();
        });
        
        // Create dropdown element
        const dropdown = document.createElement('div');
        dropdown.className = 'history-item-dropdown';
        dropdown.dataset.sessionId = sid!;
        dropdown.innerHTML = `
          <div class="delete-confirmation-text">Delete this chat?</div>
          <div class="delete-confirmation-buttons">
            <button class="confirm-yes-option" data-session-id="${sid}">
              <span>Yes</span>
            </button>
            <button class="confirm-no-option" data-session-id="${sid}">
              <span>No</span>
            </button>
          </div>
        `;
        
        // Append to body to avoid overflow clipping
        document.body.appendChild(dropdown);
        
        // Position dropdown relative to button
        const rect = menuBtn.getBoundingClientRect();
        
        // Calculate position
        const dropdownWidth = 160;
        const dropdownHeight = 75; // Approximate height for text + Yes/No buttons
        let top = rect.bottom + 4;
        let left = rect.right - dropdownWidth + 145; // Positioned to the right
        
        // Check if dropdown would go off bottom of screen
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        
        // If not enough space below but more space above, show above
        if (spaceBelow < dropdownHeight + 10 && spaceAbove > dropdownHeight + 10) {
          top = rect.top - dropdownHeight - 4; // Show above button
        }
        
        // Ensure dropdown doesn't go off right edge
        if (left + dropdownWidth > window.innerWidth - 10) {
          left = window.innerWidth - dropdownWidth - 10;
        }
        
        // Ensure dropdown doesn't go off left edge
        if (left < 10) {
          left = 10;
        }
        
        // Ensure dropdown doesn't go off top
        if (top < 10) {
          top = 10;
        }
        
        // Ensure dropdown doesn't go off bottom
        if (top + dropdownHeight > window.innerHeight - 10) {
          top = window.innerHeight - dropdownHeight - 10;
        }
        
        dropdown.style.top = `${top}px`;
        dropdown.style.left = `${left}px`;
        console.log('[DELETE] Confirmation opened at:', { top, left, spaceBelow, spaceAbove });
        
        return;
      }
    });
    
    // Close dropdowns when sidebar scrolls
    sidebarHistory.addEventListener('scroll', () => {
      document.querySelectorAll('.history-item-dropdown').forEach(dropdown => {
        dropdown.remove();
      });
    });
    
    // Add toggle handlers for section collapse/expand
    sidebarHistory.querySelectorAll('.section-toggle-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const sectionId = (btn as HTMLElement).dataset.sectionId;
        if (!sectionId) return;
        
        const content = sidebarHistory.querySelector(`.history-section-content[data-section-id="${sectionId}"]`);
        const icon = btn.querySelector('.toggle-icon');
        
        if (content && icon) {
          const isCollapsed = content.classList.contains('collapsed');
          
          if (isCollapsed) {
            content.classList.remove('collapsed');
            icon.classList.remove('collapsed');
            localStorage.removeItem(`section_collapsed_${sectionId}`);
            btn.setAttribute('title', 'Collapse');
          } else {
            content.classList.add('collapsed');
            icon.classList.add('collapsed');
            localStorage.setItem(`section_collapsed_${sectionId}`, 'true');
            btn.setAttribute('title', 'Expand');
          }
        }
      });
    });
  }
  
  // Delete a session (soft delete - moves to deleted collection)
  async function deleteSession(sid: string) {
    // No confirm dialog - Yes/No buttons in dropdown handle confirmation
    
    let sessions = getAllSessions();
    const sessionToDelete = sessions.find(s => s.id === sid);
    
    if (sessionToDelete) {
      // Add deleted timestamp to the session
      const deletedSession = {
        ...sessionToDelete,
        deletedAt: Date.now()
      };
      
      // Move to deleted collection
      const deletedSessions = getDeletedSessions();
      deletedSessions.push(deletedSession);
      saveDeletedSessions(deletedSessions);
      
      console.log('[DELETED_SESSIONS] Moved session to deleted collection:', sid);
    }
    
    // Remove from active sessions
    sessions = sessions.filter(s => s.id !== sid);
    saveAllSessions(sessions);
    
    // ✅ NEW: Delete from backend
    try {
      const response = await apiFetch(`/chat/sessions/${sid}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        console.log('[DELETE] Successfully deleted session from backend:', sid);
      } else if (response.status === 404) {
        console.warn('[DELETE] Session not found in backend (may have been already deleted):', sid);
      } else {
        console.error('[DELETE] Failed to delete session from backend:', response.status);
        // Session is still deleted locally, but backend deletion failed
        // This is okay - it will be cleaned up on next sync
      }
    } catch (error) {
      console.error('[DELETE] Error deleting session from backend:', error);
      // Session is still deleted locally, but backend deletion failed
      // This is okay - it will be cleaned up on next sync
    }
    
    // If deleted current session, clear the chat area immediately (like ChatGPT)
    if (sid === sessionId) {
      console.log('[DELETE] Deleted current session, clearing chat area');
      
      // INSTANT: Clear the messages immediately
      const messagesList = document.getElementById('messages');
      if (messagesList) {
        messagesList.innerHTML = '';
      }
      
      // DON'T create a new session immediately - wait until user sends a message (like ChatGPT)
      // Check if there are any remaining sessions
      const remainingSessions = getAllSessions();
      
      if (remainingSessions.length === 0) {
        // This was the last chat - clear session and wait for user to start typing
        console.log('[DELETE] Last chat deleted - showing welcome screen');
        sessionId = null; // Clear session ID
        localStorage.removeItem(getUserStorageKey('chatbot_session_id'));
        
        // Show welcome screen with example prompts
        updateEmptyState();
        reloadSuggestedQuestions();
      } else {
        // There are other chats, but we're not auto-loading them - just create a new empty session
        const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const randomId = Math.random().toString(36).substr(2, 9);
        sessionId = `cf.conversation.${date}.${randomId}`;
        localStorage.setItem(getUserStorageKey('chatbot_session_id'), sessionId);
        
        // Show welcome screen
        updateEmptyState();
        reloadSuggestedQuestions();
      }
      
      // INSTANT: Update the history list synchronously (don't wait for async)
      const sidebarHistory = document.querySelector('.sidebar-history');
      if (sidebarHistory) {
        // Quick update: just remove the deleted item from DOM
        const deletedItem = sidebarHistory.querySelector(`[data-session-id="${sid}"]`);
        if (deletedItem) {
          deletedItem.remove();
        }
      }
      
      // Background: Do full re-render in background (non-blocking)
      setTimeout(() => {
        renderSessionHistory().catch(err => console.error('[SESSION] Failed to render history:', err));
      }, 0);
    } else {
      // INSTANT: Just remove the deleted item from DOM
      const sidebarHistory = document.querySelector('.sidebar-history');
      if (sidebarHistory) {
        const deletedItem = sidebarHistory.querySelector(`[data-session-id="${sid}"]`);
        if (deletedItem) {
          deletedItem.remove();
        }
      }
      
      // Background: Do full re-render in background (non-blocking)
      setTimeout(() => {
        renderSessionHistory().catch(err => console.error('[SESSION] Failed to render history:', err));
      }, 0);
    }
  }

  // Helper functions for persisting recommended questions
  function saveRecommendedQuestions(messageIndex: number, questions: string[]) {
    try {
      const storageKey = `recommended_questions_${sessionId}`;
      const stored = localStorage.getItem(storageKey);
      const recommendations = stored ? JSON.parse(stored) : {};
      recommendations[messageIndex] = questions;
      localStorage.setItem(storageKey, JSON.stringify(recommendations));
    } catch (e) {
      console.error('[STORAGE] Failed to save recommendations:', e);
    }
  }

  function loadRecommendedQuestions(messageIndex: number): string[] {
    try {
      const storageKey = `recommended_questions_${sessionId}`;
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const recommendations = JSON.parse(stored);
        return recommendations[messageIndex] || [];
      }
    } catch (e) {
      console.error('[STORAGE] Failed to load recommendations:', e);
    }
    return [];
  }

  function clearRecommendedQuestions() {
    try {
      const storageKey = `recommended_questions_${sessionId}`;
      localStorage.removeItem(storageKey);
    } catch (e) {
      console.error('[STORAGE] Failed to clear recommendations:', e);
    }
  }

  function buildRecommendedQuestionsHTML(questions: string[]): string {
    if (!questions || questions.length === 0) {
      return '';
    }
    
    const questionsHTML = questions
      .map((q: string) => `
        <button class="recommended-question-btn" data-action="ask-recommended-question" data-question="${q.replace(/"/g, '&quot;')}">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 10 L12 10 M10 7 L13 10 L10 13" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span>${q}</span>
        </button>
      `)
      .join('');
    
    return `
      <div class="recommended-questions">
        <div class="recommended-questions-label">Related</div>
        <div class="recommended-questions-list">
          ${questionsHTML}
        </div>
      </div>
    `;
  }

  // Helper function to remove edit button from previous user messages
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function removeAllEditButtons() {
    const allWrappers = messagesDiv!.querySelectorAll('.user-message-wrapper');
    allWrappers.forEach(wrapper => {
      const editContainer = wrapper.querySelector('.edit-button-container');
      if (editContainer) {
        editContainer.remove();
      }
    });
  }

  // Toast notification function
  function showToast(
    message: string,
    type: 'success' | 'error' | 'info' | 'warning' = 'info',
    duration = 2000
  ) {
    // Remove existing toast if any
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) {
      existingToast.remove();
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Trigger animation
    setTimeout(() => {
      toast.classList.add('show');
    }, 10);
    
    // Remove after specified duration
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => {
        toast.remove();
      }, 300);
    }, duration);
  }

  function addMessage(content: string, sender: string) {
    if (sender === "user") {
      // Keep edit/copy buttons on all user messages
      // removeAllEditButtons(); // Commented out to show buttons on all messages
      
      // For user messages, create wrapper with message and edit button below
      // Hide edit button in read-only mode
      const editButtonHTML = isReadOnlyMode ? '' : `
          <button class="edit-btn" data-action="edit-message" title="Edit message">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
            </svg>
          </button>
      `;
      
      const wrapper = document.createElement("div");
      wrapper.className = "user-message-wrapper";
      wrapper.innerHTML = `
        <div class="message user">${content}</div>
        <div class="edit-button-container">
          <button class="copy-button-user" data-action="copy-user-message" title="Copy message">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          </button>
          ${editButtonHTML}
        </div>
      `;
      messagesDiv!.appendChild(wrapper);
      console.log(`[UI] Added ${sender} message. Total messages now: ${messagesDiv!.children.length}`);
      updateEmptyState();
      autoScrollToBottom();
      return wrapper;
    } else {
      // For bot messages, keep simple structure
      const div = document.createElement("div");
      div.className = "message " + sender;
      div.innerText = content;
      messagesDiv!.appendChild(div);
      console.log(`[UI] Added ${sender} message. Total messages now: ${messagesDiv!.children.length}`);
      updateEmptyState();
      autoScrollToBottom();
      return div;
    }
  }

  function addMessageHTML(content: string, sender: string, traceId: string | null = null) {
    const div = document.createElement("div");
    div.className = "message " + sender;
    
    if (sender === "bot") {
      // For bot messages, wrap content and add copy button + feedback buttons
      div.innerHTML = `
        <div class="message-content">${content}</div>
        <div class="feedback-buttons">
          <button class="copy-button" data-action="copy-message" title="Copy message">
            <img src="/images/copy-icon.svg?v=2" alt="Copy" width="16" height="16">
          </button>
          <button class="feedback-btn thumbs-up" data-action="feedback" data-rating="thumbs_up" title="Good response">
            <img src="/images/thumbs-up-icon.svg?v=2" alt="Thumbs up" width="16" height="16">
          </button>
          <button class="feedback-btn thumbs-down" data-action="feedback" data-rating="thumbs_down" title="Bad response">
            <img src="/images/thumbs-down-icon.svg?v=2" alt="Thumbs down" width="16" height="16">
          </button>
          <span class="feedback-text"></span>
        </div>
      `;
      
      // Store trace_id if provided
      if (traceId) {
        div.dataset.traceId = traceId;
      }
    } else {
      // For user messages, keep as is
      div.innerHTML = content;
    }
    
    messagesDiv!.appendChild(div);
    console.log(`[UI] Added ${sender} message HTML. Total messages now: ${messagesDiv!.children.length}`);
    updateEmptyState();
    autoScrollToBottom();
    return div;
  }

  function renderMarkdown(text: string) {
    let html = '';
    if (typeof window.marked !== 'undefined') {
      html = window.marked.parse(text);
    } else {
      // Fallback: basic markdown-like formatting
      const lines = text.split('\n');
      let inList = false;
      let inOrderedList = false;
      const result = [];
      
      for (const line of lines) {
        // Check for unordered list item
        if (line.match(/^\* /)) {
          if (!inList) {
            result.push('<ul>');
            inList = true;
          }
          result.push(line.replace(/^\* (.*)$/, '<li>$1</li>'));
        }
        // Check for ordered list item
        else if (line.match(/^\d+\. /)) {
          if (!inOrderedList) {
            result.push('<ol>');
            inOrderedList = true;
          }
          result.push(line.replace(/^\d+\. (.*)$/, '<li>$1</li>'));
        }
        // Not a list item
        else {
          // Close any open lists
          if (inList) {
            result.push('</ul>');
            inList = false;
          }
          if (inOrderedList) {
            result.push('</ol>');
            inOrderedList = false;
          }
          
          // Format the line
          let formattedLine = line
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>');
          
          // Handle headings
          if (line.match(/^### /)) {
            formattedLine = line.replace(/^### (.*)$/, '<h3>$1</h3>');
          } else if (line.match(/^## /)) {
            formattedLine = line.replace(/^## (.*)$/, '<h2>$1</h2>');
          } else if (line.match(/^# /)) {
            formattedLine = line.replace(/^# (.*)$/, '<h1>$1</h1>');
          } else if (line.trim() !== '') {
            formattedLine = '<p>' + formattedLine + '</p>';
          } else {
            formattedLine = '';
          }
          
          if (formattedLine) result.push(formattedLine);
        }
      }
      
      // Close any remaining open lists
      if (inList) result.push('</ul>');
      if (inOrderedList) result.push('</ol>');
      
      html = result.join('\n');
    }
    
    // Add target="_blank" and rel="noopener noreferrer" to all links
    html = html.replace(/<a href=/g, '<a target="_blank" rel="noopener noreferrer" href=');
    
    return html;
  }

  // [REST OF THE JAVASCRIPT CODE WILL CONTINUE IN NEXT MESSAGE DUE TO LENGTH]
  // For now, let me create a simplified version that makes it work

  // Check if user is near bottom of messages
  function isUserNearBottom(): boolean {
    const messagesContainer = document.querySelector('.messages-container') as HTMLElement;
    if (!messagesContainer) return true;
    
    const threshold = 150;
    const isNearBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < threshold;
    return isNearBottom;
  }

  // Scroll to bottom (forced - used when user clicks button)
  function scrollToBottom() {
    requestAnimationFrame(() => {
      const messagesContainer = document.querySelector('.messages-container') as HTMLElement;
      if (messagesContainer) {
        messagesContainer.scrollTo({
          top: messagesContainer.scrollHeight,
        behavior: 'smooth'
      });
      }
    });
  }

  // Auto-scroll only if user is already near bottom (ChatGPT behavior)
  function autoScrollToBottom() {
    if (isUserNearBottom()) {
      scrollToBottom();
    }
  }

  async function sendMessage() {
    // ✅ PHASE-1: Check per-session state instead of global
    if (!sessionId || isSessionGenerating(sessionId)) return;
    
    const question = input.value.trim();
    if (!question) return;

    // Validate prompt length
    if (question.length > MAX_PROMPT_LENGTH) {
      const tokens = Math.round(question.length / 4);
      alert(`G��n+� Message is too long!\n\nYour message: ~${tokens.toLocaleString()} tokens (${question.length.toLocaleString()} characters)\nMaximum allowed: 5,000 tokens (20,000 characters)\n\nPlease shorten your message or split it into multiple parts.`);
      return;
    }
    
    // Show warning for large prompts
    if (question.length > WARN_PROMPT_LENGTH) {
      const tokens = Math.round(question.length / 4);
      const proceed = confirm(`G��n+� Large Message Warning\n\nYour message is approximately ${tokens.toLocaleString()} tokens (${question.length.toLocaleString()} characters).\n\nLarge messages may:\nG�� Take longer to process\nG�� Produce less focused responses\n\nDo you want to continue?`);
      if (!proceed) return;
    }

    // Remove all previous recommended questions when user types a new query
    const allRecommendations = messagesDiv!.querySelectorAll('.recommended-questions');
    allRecommendations.forEach(rec => rec.remove());

    addMessage(question, "user");
    input.value = "";
    // Reset textarea height after sending
    input.style.height = '24px';
    
    // Hide character counter after sending
    const counter = document.getElementById('char-counter');
    if (counter) counter.style.display = 'none';
    
    // Update sidebar IMMEDIATELY before saving (for instant visual feedback)
    // This shows the new chat in sidebar right away
    updateSidebarImmediately();
    
    /* ================================
       PHASE 2.5.1 – CRITICAL FIX #1
       Persist user message immediately to localStorage BEFORE starting backend request
       
       This ensures user input is durable even if:
       - User switches sessions before bot responds
       - Page refreshes mid-generation
       - Any other interruption occurs
       
       User intent must be saved the moment Send is pressed, not when bot responds.
       ================================ */
    saveCurrentSession();
    /* ================================ */
    
    await sendMessageText(question);
  }

  async function sendMessageText(question: string) {
    if (!question) {
      console.warn('[SEND] No question provided');
      return;
    }
    
    // ✅ PHASE-1: Check per-session state instead of global
    if (!sessionId) {
      console.error('[SEND] No sessionId available');
      return;
    }
    
    if (isSessionGenerating(sessionId)) {
      console.warn('[SEND] Session is already generating, skipping');
      return;
    }
    
    console.log('[SEND] Starting message send for session:', sessionId);
    
    // ✅ PHASE 2.5.4: Removed AbortController - streams complete independently
    // This allows background streams to finish even when navigating to /chat/new
    // Streams are no longer tied to component lifecycle
    
    // Disable send buttons while generating
    setSessionGenerating(sessionId, true);

    const botDiv = addMessageHTML("", "bot", null);
    
    /* ================================
       PHASE 2.5.3 – STREAM-SAFE PERSISTENCE
       Mark message as generating to prevent partial saves during session switches
       ================================ */
    botDiv.dataset.generating = 'true';
    botDiv.dataset.sessionId = sessionId;
    // ✅ FIX: Use type assertion and setAttribute to avoid TypeScript errors
    (botDiv.dataset as any).generatingStartTime = Date.now().toString();
    botDiv.setAttribute('data-generating-start-time', Date.now().toString());
    /* ================================ */
    
    // ✅ FIX: Ensure botDiv is visible and scrolled into view
    botDiv.style.display = 'block';
    botDiv.style.visibility = 'visible';
    console.log('[SEND] Bot div created, starting stream...', {
      sessionId,
      botDivVisible: botDiv.offsetParent !== null,
      botDivInDOM: messagesDiv!.contains(botDiv)
    });
    
    // Status update function - simplified for better performance
    let isStreamingStatus = false;
    
    const updateThinkingStatus = (status: string, message: string) => {
      // Skip if already showing content or if we're done with thinking phase
      if (isStreamingStatus) return;
      
      // Update status immediately without word-by-word animation
      botDiv.innerHTML = `
        <div class="thinking">
          ${message}
          <span class="thinking-dots">
            <span></span>
            <span></span>
            <span></span>
          </span>
        </div>
      `;
      autoScrollToBottom();
    };
    
    // Initial "Thinking" state - wait for first status from backend
    botDiv.innerHTML = `
      <div class="thinking">
        Thinking
        <span class="thinking-dots">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </div>
    `;
    
    setTimeout(() => autoScrollToBottom(), 50);

    try {
      // ✅ FIX 2: Session-based auth - check user exists (no token needed)
      const currentUser = getCurrentUser();
      if (!currentUser) {
        console.error("[CHAT] User not authenticated, redirecting to login");
        localStorage.removeItem('user');
        window.location.href = "/login?error=session_expired";
        return;
      }
      
      // ✅ FIX 2: Session-based auth - no token validation needed
      // Session is validated automatically by backend via session_id cookie
      const requestBody = { 
        question,
        session_id: sessionId
      };
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch('/chat/stream', {
        method: "POST",
        body: JSON.stringify(requestBody),
        // No signal - allows streams to complete even when user navigates away
      });

      if (response.status === 401 || response.status === 403) {
        console.error("[CHAT] Authentication failed, redirecting to login");
        localStorage.removeItem('user');
        window.location.href = "/login?error=session_expired";
        return;
      }
      
      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        console.error(`[CHAT] HTTP error! status: ${response.status}, body: ${errorText}`);
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Check if response body exists before getting reader
      if (!response.body) {
        console.error("[CHAT] Response body is null - connection may have been closed");
        throw new Error("Connection closed: No response body received");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullResponse = "";
      let lastRenderTime = 0;
      const renderThrottle = 16;

      while (true) {
        // ✅ PHASE 2.5.4: Removed abort check - streams complete independently
        // Streams now run to completion regardless of navigation
        
        let readResult;
        try {
          readResult = await reader.read();
        } catch (readError) {
          console.error("[CHAT] Stream read error:", readError);
          // Check if it's a connection closed error
          if (readError instanceof Error && (readError.message.includes('Connection closed') || readError.message.includes('connection closed'))) {
            console.error("[CHAT] Connection closed unexpectedly. Backend may be unavailable.");
            botDiv.innerHTML = "Sorry, the connection was closed. Please check if the backend is running and try again.";
            setSessionGenerating(sessionId!, false);
            botDiv.dataset.generating = 'false';
            return;
          }
          throw readError; // Re-throw if it's a different error
        }
        
        const { done, value } = readResult;
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'status') {
                // Update thinking status with backend progress
                updateThinkingStatus(data.status, data.message);
              } else if (data.type === 'thinking_complete') {
                // Mark that we're done with thinking phase and starting content
                isStreamingStatus = true;
                botDiv.innerHTML = `<div class="message-content"></div>`;
              } else if (data.type === 'sources') {
                console.log("[CONSOLE]", data.sources);
              } else if (data.type === 'token') {
                const token = data.token;
                fullResponse += token;
                
                const now = Date.now();
                if (now - lastRenderTime > renderThrottle) {
                  const contentDiv = botDiv.querySelector('.message-content');
                  const renderedMarkdown = renderMarkdown(fullResponse);
                  const contentWithLinks = linkifyText(renderedMarkdown);
                  if (contentDiv) {
                    contentDiv.innerHTML = contentWithLinks;
                  } else {
                    botDiv.innerHTML = `<div class="message-content">${contentWithLinks}</div>`;
                  }
                  autoScrollToBottom();
                  lastRenderTime = now;
                }
              } else if (data.type === 'done') {
                fullResponse = data.full_response || fullResponse;
                const traceId = data.trace_id;
                const recommendedQuestions = data.recommended_questions || [];
                
                // Log trace_id status for debugging
                if (traceId) {
                  console.log('[TRACE_ID] ✓ Received trace_id from backend:', traceId);
                } else {
                  console.warn('[TRACE_ID] ⚠️ WARNING: No trace_id received from backend');
                  console.warn('[TRACE_ID] This means Langfuse trace creation failed - feedback will use fallback ID');
                }
                
                if (!fullResponse || fullResponse.trim() === '') {
                  fullResponse = "I apologize, but I wasn't able to generate a response. Please try again.";
                }
                
                // Save recommended questions to localStorage for persistence
                if (recommendedQuestions && recommendedQuestions.length > 0) {
                  const messageIndex = messagesDiv!.children.length - 1; // Current bot message index
                  saveRecommendedQuestions(messageIndex, recommendedQuestions);
                }
                
                // Build recommended questions HTML
                const recommendedQuestionsHTML = buildRecommendedQuestionsHTML(recommendedQuestions);
                
                // Render markdown and add UTM parameters to all links
                const renderedMarkdown = renderMarkdown(fullResponse);
                const contentWithLinks = linkifyText(renderedMarkdown);
                
                // ✅ Store trace_id BEFORE generating HTML (so we can disable buttons if missing)
                if (traceId) {
                  botDiv.dataset.traceId = traceId;
                  // Also set the literal attribute so DevTools shows it immediately
                  botDiv.setAttribute('data-trace-id', traceId);
                  
                  // Double-ensure the most recent bot message has the trace_id (in case DOM changes)
                  const latestBotMessage = messagesDiv?.querySelector('.message.bot:last-of-type') as HTMLElement | null;
                  if (latestBotMessage) {
                    latestBotMessage.dataset.traceId = traceId;
                    latestBotMessage.setAttribute('data-trace-id', traceId);
                  }
                  
                  console.log('[TRACE_ID] ✓ Stored trace_id in botDiv:', traceId);
                } else {
                  console.warn('[TRACE_ID] ⚠️ No trace_id to store - feedback buttons will be disabled');
                }
                
                // ✅ Disable feedback buttons if traceId is missing
                const feedbackDisabled = !traceId;
                const feedbackDisabledAttr = feedbackDisabled ? 'disabled' : '';
                const feedbackDisabledClass = feedbackDisabled ? 'disabled' : '';
                
                botDiv.innerHTML = `
                  <div class="message-content">${contentWithLinks}</div>
                  <div class="feedback-buttons">
                    <button class="copy-button" data-action="copy-message" title="Copy message">
                      <img src="/images/copy-icon.svg?v=2" alt="Copy" width="16" height="16">
                    </button>
                    <button class="feedback-btn thumbs-up ${feedbackDisabledClass}" 
                            data-action="feedback" 
                            data-rating="thumbs_up"
                            title="${feedbackDisabled ? 'Feedback unavailable (trace_id missing)' : 'Good response'}"
                            ${feedbackDisabledAttr}>
                      <img src="/images/thumbs-up-icon.svg?v=2" alt="Thumbs up" width="16" height="16">
                    </button>
                    <button class="feedback-btn thumbs-down ${feedbackDisabledClass}" 
                            data-action="feedback" 
                            data-rating="thumbs_down"
                            title="${feedbackDisabled ? 'Feedback unavailable (trace_id missing)' : 'Bad response'}"
                            ${feedbackDisabledAttr}>
                      <img src="/images/thumbs-down-icon.svg?v=2" alt="Thumbs down" width="16" height="16">
                    </button>
                    <span class="feedback-text"></span>
                  </div>
                  ${recommendedQuestionsHTML}
                `;
                
                // Propagate trace_id to feedback buttons so click handlers always have access
                if (traceId) {
                  const feedbackButtons = botDiv.querySelectorAll('.feedback-btn');
                  feedbackButtons.forEach(btn => {
                    (btn as HTMLElement).dataset.traceId = traceId;
                  });
                }
                
                // Save session after bot response
                saveCurrentSession();
                
                // If this was a new session from /chat/new, update URL to session-specific path
                // ✅ ZERO REFRESH FIX: Use window.history.replaceState() to update URL silently
                // This avoids Next.js router navigation which causes remount/loading
                // UI stays mounted, zero loading feel, URL updates correctly
                if (sessionId && isNewSessionPendingNavigation) {
                  const currentPath = window.location.pathname;
                  const targetPath = `/chat/${sessionId}`;
                  
                  // ✅ Only update URL if we're on /chat/new and path differs
                  if (currentPath === '/chat/new' && currentPath !== targetPath) {
                    console.log('[SESSION] Updating URL silently to:', targetPath);
                    isNewSessionPendingNavigation = false;
                    
                    // ✅ Silent URL update without Next.js navigation
                    // This prevents remount/loading while keeping URL in sync
                    if (typeof window !== 'undefined') {
                      window.history.replaceState(null, '', targetPath);
                      console.log('[SESSION] ✓ URL updated without refresh');
                    }
                  } else {
                    // Already on correct path or not on /chat/new, just clear the flag
                    isNewSessionPendingNavigation = false;
                  }
                }
                
                // ✅ PHASE-1: Clean up after successful completion
                // Re-enable send buttons after response complete
                setSessionGenerating(sessionId!, false);
                
                /* ================================
                   PHASE 2.5.3 FINAL FIX – STREAM-SAFE PERSISTENCE
                   Mark message as complete and save the CORRECT session
                   
                   CRITICAL: Check if this is the currently displayed session
                   or a background session. If background, we must load that
                   specific session from storage and append the completed message.
                   ================================ */
                botDiv.dataset.generating = 'false';
                
                // Check which session this message belongs to
                const completedSessionId = botDiv.dataset.sessionId;
                
                // ✅ FIX 2: CRITICAL - Clear generating flag for the completed session
                // This prevents UI freezing and allows the session to receive new messages
                if (completedSessionId) {
                  setSessionGenerating(completedSessionId, false);
                }
                
                if (completedSessionId === sessionId) {
                  // Still on this session - save normally from DOM
                  saveCurrentSession();
                  console.log('[STREAM] ✅ Auto-saved current session after generation complete');
                } else if (completedSessionId) {
                  // Different session - save the background session from storage
                  saveCompletedBackgroundSession(completedSessionId, botDiv);
                  console.log('[STREAM] ✅ Auto-saved background session:', completedSessionId);
                } else {
                  console.warn('[STREAM] ⚠️ No sessionId found on botDiv, falling back to current session save');
                  saveCurrentSession();
                }
                /* ================================ */
                
                return;
              } else if (data.type === 'error') {
                throw new Error(data.error);
              }
            } catch (e) {
              console.error("Error parsing streaming data:", e);
            }
          }
        }
      }
      
    } catch (error) {
      console.error("Error sending message:", error);
      botDiv.innerHTML = "Sorry, there was an error. Please try again.";
      
      // ✅ CORRECTION 2: Always clean up on error
      // Re-enable send buttons after error
      setSessionGenerating(sessionId!, false);
      
      /* ================================
         PHASE 2.5.3 FINAL FIX – STREAM-SAFE PERSISTENCE
         Mark message as complete and save the CORRECT session even on error
         ================================ */
      botDiv.dataset.generating = 'false';
      
      // Check which session this message belongs to
      const completedSessionId = botDiv.dataset.sessionId;
      
      // ✅ FIX 2 (Error Handler): Clear generating flag for the completed session
      if (completedSessionId) {
        setSessionGenerating(completedSessionId, false);
      }
      
      if (completedSessionId === sessionId) {
        // Still on this session - save normally from DOM
        saveCurrentSession();
        console.log('[STREAM] ✅ Auto-saved current session after error');
      } else if (completedSessionId) {
        // Different session - save the background session from storage
        saveCompletedBackgroundSession(completedSessionId, botDiv);
        console.log('[STREAM] ✅ Auto-saved background session after error:', completedSessionId);
      } else {
        console.warn('[STREAM] ⚠️ No sessionId found on botDiv after error, falling back to current session save');
        saveCurrentSession();
      }
      /* ================================ */
    }
  }

  function copyMessage(button: HTMLElement) {
    const messageDiv = button.closest('.message.bot');
    const contentDiv = messageDiv!.querySelector('.message-content') as HTMLElement;
    
    // Copy HTML content to preserve formatting (bold, underline, strikethrough, etc.)
    // This way, when pasted into rich text editors, all formatting is maintained
    const htmlToCopy = contentDiv!.innerHTML;
    
    // Use the Clipboard API to copy both HTML and plain text
    const blob = new Blob([htmlToCopy], { type: 'text/html' });
    const richTextItem = new ClipboardItem({
      'text/html': blob,
      'text/plain': new Blob([contentDiv!.innerText || contentDiv!.textContent || ''], { type: 'text/plain' })
    });
    
    navigator.clipboard.write([richTextItem]).then(() => {
      console.log('[COPY] Message copied successfully with formatting');
      const originalHTML = button.innerHTML;
      
      // Change to checkmark icon
      button.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10a37f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      button.classList.add('copied');
      button.title = 'Copied!';
      
      // Show toast notification
      try {
        showToast('Copied to clipboard');
      } catch (e) {
        console.error('[TOAST] Error showing toast:', e);
      }
      
      setTimeout(() => {
        button.innerHTML = originalHTML;
        button.classList.remove('copied');
        button.title = 'Copy message';
      }, 2000);
    }).catch(err => {
      console.error('[COPY] Failed to copy text:', err);
      // Fallback to plain text copy
      navigator.clipboard.writeText(contentDiv!.innerText || contentDiv!.textContent || '').catch(fallbackErr => {
        console.error('[COPY] Fallback copy also failed:', fallbackErr);
      });
    });
  }

  function askRecommendedQuestion(button: HTMLElement) {
    const question = button.getAttribute('data-question');
    if (!question) {
      console.warn('[RECOMMENDED] No question found on button');
      return;
    }
    
    // ✅ FIX: Ensure sessionId exists
    if (!sessionId) {
      console.error('[RECOMMENDED] No sessionId available');
      return;
    }
    
    // ✅ FIX: Clear any stale generating state before checking
    // This prevents blocking if a previous response finished but flag wasn't cleared
    const currentGenerating = isSessionGenerating(sessionId);
    if (currentGenerating) {
      console.log('[RECOMMENDED] Session is currently generating, waiting...');
      // Force clear if it's been generating for too long (might be stuck)
      const botMessages = messagesDiv!.querySelectorAll('.message.bot');
      const lastBotMessage = botMessages[botMessages.length - 1] as HTMLElement | null;
      if (lastBotMessage && lastBotMessage.dataset.generating === 'true') {
        // Check if it's been generating for more than 30 seconds (likely stuck)
        // ✅ FIX: Use type assertion and getAttribute fallback to avoid TypeScript errors
        const generatingTime = parseInt(
          (lastBotMessage.dataset as any).generatingStartTime || 
          lastBotMessage.getAttribute('data-generating-start-time') || 
          '0', 
          10
        );
        if (generatingTime && Date.now() - generatingTime > 30000) {
          console.warn('[RECOMMENDED] Clearing stuck generating state');
          setSessionGenerating(sessionId, false);
          lastBotMessage.dataset.generating = 'false';
        } else {
          console.log('[RECOMMENDED] Previous response still generating, please wait');
          return;
        }
      } else {
        // State mismatch - DOM shows not generating but flag says generating
        // This can happen legitimately when:
        // 1. Response just finished (DOM updated to generating='false')
        // 2. But setSessionGenerating(false) hasn't been called yet (race condition)
        // 3. Or user clicks recommended question very quickly after response completes
        // 
        // Silently fix the mismatch - this is expected behavior, not an error
        setSessionGenerating(sessionId, false);
      }
    }
    
    console.log('[RECOMMENDED] Processing recommended question:', question);
    
    // Remove ALL previous recommended questions from the DOM
    const allRecommendations = messagesDiv!.querySelectorAll('.recommended-questions');
    allRecommendations.forEach(rec => rec.remove());
    
    // Add user message to chat FIRST (so it displays immediately)
    addMessage(question, "user");
    
    // Clear input fields
    if (input) {
      input.value = "";
      input.style.height = '24px';
    }
    if (inputEmptyState) {
      inputEmptyState.value = "";
      inputEmptyState.style.height = '24px';
    }
    
    // Then send the question to get bot response
    console.log('[RECOMMENDED] Sending question to backend...');
    sendMessageText(question);
  }

  async function submitFeedback(button: HTMLElement, rating: string) {
    try {
      const messageDiv = button.closest('.message.bot') as HTMLElement;
      if (!messageDiv) {
        console.error('[FEEDBACK] Could not find message div');
        return;
      }
      
      const traceId =
        messageDiv.dataset.traceId ||
        messageDiv.dataset.traceid ||
        (button as HTMLElement).dataset.traceId ||
        button.getAttribute('data-trace-id') ||
        (button.closest('[data-trace-id]') as HTMLElement | null)?.dataset.traceId ||
        '';
      
      if (messageDiv.dataset.feedbackSubmitted === 'true') {
        console.log('[FEEDBACK] Feedback already submitted for this message');
        return;
      }
      
      // If thumbs down, show detailed feedback modal
      if (rating === 'thumbs_down') {
        showFeedbackModal(messageDiv, traceId || '');
        return;
      }
      
      // For thumbs up, submit immediately
      const feedbackButtons = messageDiv.querySelectorAll('.feedback-btn');
      feedbackButtons.forEach((btn) => {
        const buttonEl = btn as HTMLButtonElement;
        buttonEl.disabled = true;
        buttonEl.style.cursor = 'not-allowed';
        buttonEl.style.opacity = '0.5';
      });
      
      // Show loading state
      const feedbackText = messageDiv.querySelector('.feedback-text') as HTMLElement;
      if (feedbackText) {
        feedbackText.textContent = 'Submitting...';
        feedbackText.style.color = '#6b7280';
      }
      
      // ✅ STRICT VALIDATION: trace_id is REQUIRED (no fallback)
      if (!traceId || traceId.trim() === '') {
        console.error('[FEEDBACK] ✗ Cannot submit feedback: trace_id is missing');
        // Re-enable buttons
        feedbackButtons.forEach((btn) => {
          const buttonEl = btn as HTMLButtonElement;
          buttonEl.disabled = false;
          buttonEl.style.cursor = 'pointer';
          buttonEl.style.opacity = '1';
        });
        if (feedbackText) {
          feedbackText.textContent = 'Feedback unavailable: trace_id missing';
          (feedbackText as HTMLElement).style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            (feedbackText as HTMLElement).style.color = '';
          }, 5000);
        }
        return;
      }
      
      // ✅ REJECT fallback trace_ids
      if (traceId.startsWith('feedback_fallback_')) {
        console.error('[FEEDBACK] ✗ Cannot submit feedback: invalid fallback trace_id');
        if (feedbackText) {
          feedbackText.textContent = 'Invalid trace_id. Please refresh and try again.';
          (feedbackText as HTMLElement).style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            (feedbackText as HTMLElement).style.color = '';
          }, 5000);
        }
        return;
      }
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch('/feedback', {
        method: "POST",
        body: JSON.stringify({
          trace_id: traceId,  // ✅ Always use real trace_id (no fallback)
          rating: rating,
          comment: "",
          categories: []
        }),
      });
      
      if (response.ok) {
        messageDiv.dataset.feedbackSubmitted = 'true';
        messageDiv.dataset.feedbackRating = 'thumbs_up';
        feedbackButtons.forEach((btn) => btn.classList.remove('selected'));
        button.classList.add('selected');
        
        if (feedbackText) {
          feedbackText.textContent = 'Thanks for your feedback!';
          (feedbackText as HTMLElement).style.color = '#10a37f';
          
          setTimeout(() => {
            feedbackText.textContent = '';
            (feedbackText as HTMLElement).style.color = '';
          }, 3000);
        }
        
        console.log('[FEEDBACK] ✓ Feedback submitted successfully');
        // Persist feedback state to session storage
        saveCurrentSession();
      } else {
        // API error - re-enable buttons
        const errorText = await response.text().catch(() => 'Unknown error');
        console.error('[FEEDBACK] API error:', response.status, errorText);
        
        feedbackButtons.forEach((btn) => {
          const buttonEl = btn as HTMLButtonElement;
          buttonEl.disabled = false;
          buttonEl.style.cursor = 'pointer';
          buttonEl.style.opacity = '1';
        });
        
        if (feedbackText) {
          feedbackText.textContent = 'Failed to submit. Try again.';
          (feedbackText as HTMLElement).style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            (feedbackText as HTMLElement).style.color = '';
          }, 3000);
        }
        
        showToast('Failed to submit feedback. Please try again.');
      }
    } catch (error) {
      console.error("Error submitting feedback:", error);
      
      // Re-enable buttons on error
      const messageDiv = button.closest('.message.bot') as HTMLElement;
      if (messageDiv) {
        const feedbackButtons = messageDiv.querySelectorAll('.feedback-btn');
        feedbackButtons.forEach((btn) => {
          const buttonEl = btn as HTMLButtonElement;
          buttonEl.disabled = false;
          buttonEl.style.cursor = 'pointer';
          buttonEl.style.opacity = '1';
        });
        
        const feedbackText = messageDiv.querySelector('.feedback-text') as HTMLElement;
        if (feedbackText) {
          feedbackText.textContent = 'Network error. Try again.';
          feedbackText.style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            feedbackText.style.color = '';
          }, 3000);
        }
      }
      
      showToast('Network error. Please check your connection and try again.');
    }
  }

  function showFeedbackModal(messageDiv: HTMLElement, traceId: string) {
    const modal = document.getElementById('feedback-modal');
    if (!modal) {
      console.error('[FEEDBACK] Feedback modal not found in DOM');
      return;
    }
    
    // ✅ STRICT VALIDATION: Check if traceId is available
    const finalTraceId = messageDiv.dataset.traceId || traceId || '';
    if (!finalTraceId || finalTraceId.trim() === '' || finalTraceId.startsWith('feedback_fallback_')) {
      console.error('[FEEDBACK] ✗ Cannot show feedback modal: trace_id is missing or invalid');
      const feedbackText = messageDiv.querySelector('.feedback-text') as HTMLElement;
      if (feedbackText) {
        feedbackText.textContent = 'Feedback unavailable: trace_id missing';
        feedbackText.style.color = '#dc3545';
        setTimeout(() => {
          feedbackText.textContent = '';
          feedbackText.style.color = '';
        }, 5000);
      }
      return;
    }
    
    // Check if feedback already submitted
    if (messageDiv.dataset.feedbackSubmitted === 'true') {
      console.log('[FEEDBACK] Feedback already submitted for this message');
      return;
    }
    
    // Store reference to message div using a unique identifier
    const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    messageDiv.dataset.feedbackMessageId = messageId;
    
    // Store reference to message for later submission
    modal.dataset.messageId = messageId;
    modal.dataset.traceId = finalTraceId;  // ✅ Use validated trace_id
    
    // Reset modal state - clear all category selections
    const categoryBtns = modal.querySelectorAll('.feedback-category-btn');
    categoryBtns.forEach(btn => btn.classList.remove('active'));
    
    // Clear comment textarea
    const commentTextarea = document.getElementById('feedback-comment') as HTMLTextAreaElement;
    if (commentTextarea) {
      commentTextarea.value = '';
    }
    
    // Show modal
    modal.style.display = 'flex';
  }

  async function submitDetailedFeedback() {
    const modal = document.getElementById('feedback-modal');
    if (!modal) {
      console.error('[FEEDBACK] Feedback modal not found');
      return;
    }
    
    // Find message div using the stored message ID
    const messageId = modal.dataset.messageId || '';
    let messageDiv: HTMLElement | null = null;
    
    if (messageId) {
      messageDiv = document.querySelector(`[data-feedback-message-id="${messageId}"]`) as HTMLElement;
    }
    
    // Fallback: try to find by trace ID if message ID not found
    if (!messageDiv) {
      const traceId = modal.dataset.traceId || '';
      if (traceId) {
        // Try both camelCase and kebab-case selectors
        messageDiv = document.querySelector(`[data-trace-id="${traceId}"]`) as HTMLElement ||
                     document.querySelector(`[data-traceId="${traceId}"]`) as HTMLElement;
      }
    }
    
    // Last resort: find the most recent bot message
    if (!messageDiv) {
      const allBotMessages = document.querySelectorAll('.message.bot');
      if (allBotMessages.length > 0) {
        messageDiv = allBotMessages[allBotMessages.length - 1] as HTMLElement;
        console.warn('[FEEDBACK] Using fallback: found message by position');
      }
    }
    
    if (!messageDiv) {
      console.error('[FEEDBACK] Could not find message div for feedback submission');
        showToast('Error: Could not submit feedback. Please try again.');
      return;
    }
    
    // Check if feedback already submitted
    if (messageDiv.dataset.feedbackSubmitted === 'true') {
      console.log('[FEEDBACK] Feedback already submitted for this message');
      modal.style.display = 'none';
      return;
    }
    
    // Get selected categories
    const selectedCategories: string[] = [];
    const categoryBtns = modal.querySelectorAll('.feedback-category-btn.active');
    categoryBtns.forEach(btn => {
      const category = btn.getAttribute('data-category');
      if (category) {
        selectedCategories.push(category);
      }
    });
    
    // Get comment
    const commentTextarea = document.getElementById('feedback-comment') as HTMLTextAreaElement;
    const comment = commentTextarea ? commentTextarea.value.trim() : '';
    
    // Close modal immediately for better UX
    modal.style.display = 'none';
    
    // Disable buttons while submitting
    const feedbackButtons = messageDiv.querySelectorAll('.feedback-btn');
    feedbackButtons.forEach((btn) => {
      const buttonEl = btn as HTMLButtonElement;
      buttonEl.disabled = true;
      buttonEl.style.cursor = 'not-allowed';
      buttonEl.style.opacity = '0.5';
    });
    
    // Show loading state
    const feedbackText = messageDiv.querySelector('.feedback-text') as HTMLElement;
    if (feedbackText) {
      feedbackText.textContent = 'Submitting feedback...';
      feedbackText.style.color = '#6b7280';
    }
    
    // Submit feedback
    try {
      const traceId = modal.dataset.traceId || messageDiv.dataset.traceId || messageDiv.dataset.traceid || '';
      
      // ✅ STRICT VALIDATION: trace_id is REQUIRED (no fallback)
      if (!traceId || traceId.trim() === '') {
        console.error('[FEEDBACK] ✗ Cannot submit feedback: trace_id is missing');
        // Re-enable buttons
        feedbackButtons.forEach((btn) => {
          const buttonEl = btn as HTMLButtonElement;
          buttonEl.disabled = false;
          buttonEl.style.cursor = 'pointer';
          buttonEl.style.opacity = '1';
        });
        if (feedbackText) {
          feedbackText.textContent = 'Feedback unavailable: trace_id missing';
          feedbackText.style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            feedbackText.style.color = '';
          }, 5000);
        }
        return;
      }
      
      // ✅ REJECT fallback trace_ids
      if (traceId.startsWith('feedback_fallback_')) {
        console.error('[FEEDBACK] ✗ Cannot submit feedback: invalid fallback trace_id');
        if (feedbackText) {
          feedbackText.textContent = 'Invalid trace_id. Please refresh and try again.';
          feedbackText.style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            feedbackText.style.color = '';
          }, 5000);
        }
        return;
      }
      
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch('/feedback', {
        method: "POST",
        body: JSON.stringify({
          trace_id: traceId,  // ✅ Always use real trace_id (no fallback)
          rating: 'thumbs_down',
          comment: comment,
          categories: selectedCategories
        }),
      });
      
      if (response.ok) {
        // Success - update UI
        feedbackButtons.forEach((btn) => {
          const buttonEl = btn as HTMLButtonElement;
          buttonEl.disabled = true;
          buttonEl.style.cursor = 'not-allowed';
          buttonEl.style.opacity = '0.5';
          btn.classList.remove('selected');
        });
        
        const thumbsDownBtn = messageDiv.querySelector('.feedback-btn.thumbs-down');
        if (thumbsDownBtn) {
          thumbsDownBtn.classList.add('selected');
        }
        
        messageDiv.dataset.feedbackSubmitted = 'true';
        messageDiv.dataset.feedbackRating = 'thumbs_down';
        
        if (feedbackText) {
          feedbackText.textContent = 'Thanks! We\'ll improve.';
          // Match thumbs-down brand color for clarity
          feedbackText.style.color = '#ef4444';
          
          setTimeout(() => {
            feedbackText.textContent = '';
            feedbackText.style.color = '';
          }, 3000);
        }
        
        console.log('[FEEDBACK] ✓ Feedback submitted successfully');
        // Persist feedback state to session storage
        saveCurrentSession();
      } else {
        // API error - re-enable buttons and show error
        const errorText = await response.text().catch(() => 'Unknown error');
        console.error('[FEEDBACK] API error:', response.status, errorText);
        
        feedbackButtons.forEach((btn) => {
          const buttonEl = btn as HTMLButtonElement;
          buttonEl.disabled = false;
          buttonEl.style.cursor = 'pointer';
          buttonEl.style.opacity = '1';
        });
        
        if (feedbackText) {
          feedbackText.textContent = 'Failed to submit. Please try again.';
          feedbackText.style.color = '#dc3545';
          setTimeout(() => {
            feedbackText.textContent = '';
            feedbackText.style.color = '';
          }, 5000);
        }
        
        showToast('Failed to submit feedback. Please try again.');
      }
    } catch (error) {
      console.error("[FEEDBACK] Error submitting detailed feedback:", error);
      
      // Re-enable buttons on error
      feedbackButtons.forEach((btn) => {
        const buttonEl = btn as HTMLButtonElement;
        buttonEl.disabled = false;
        buttonEl.style.cursor = 'pointer';
        buttonEl.style.opacity = '1';
      });
      
      if (feedbackText) {
        feedbackText.textContent = 'Network error. Please try again.';
        feedbackText.style.color = '#dc3545';
        setTimeout(() => {
          feedbackText.textContent = '';
          feedbackText.style.color = '';
        }, 5000);
      }
      
      showToast('Network error. Please check your connection and try again.');
    }
  }

  function copyUserMessage(button: HTMLElement) {
    const wrapper = button.closest('.user-message-wrapper');
    if (!wrapper) return;
    
    const messageDiv = wrapper.querySelector('.message.user') as HTMLElement;
    if (!messageDiv) return;
    
    const text = messageDiv.textContent || '';
    navigator.clipboard.writeText(text).then(() => {
      console.log('[COPY USER] User message copied successfully');
      const originalHTML = button.innerHTML;
      
      // Change to checkmark icon
      button.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10a37f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      `;
      button.title = 'Copied!';
      
      // Show toast notification
      try {
        showToast('Copied to clipboard');
      } catch (e) {
        console.error('[TOAST] Error showing toast:', e);
      }
      
      setTimeout(() => {
        button.innerHTML = originalHTML;
        button.title = 'Copy message';
      }, 2000);
    }).catch(err => {
      console.error('[COPY USER] Failed to copy text:', err);
    });
  }

  function editMessage(button: HTMLElement) {
    const wrapper = button.closest('.user-message-wrapper');
    if (!wrapper) return;
    
    const messageDiv = wrapper.querySelector('.message.user') as HTMLElement;
    const editContainer = wrapper.querySelector('.edit-button-container');
    
    if (!messageDiv || !editContainer) return;
    
    const originalText = messageDiv.textContent || '';
    
    // Add editing class to wrapper
    wrapper.classList.add('editing');
    
    // Replace message with textarea
    messageDiv.innerHTML = `
      <textarea class="edit-textarea" rows="1">${originalText}</textarea>
      <div class="edit-actions">
        <button class="edit-action-btn edit-cancel-btn" data-action="cancel-edit">Cancel</button>
        <button class="edit-action-btn edit-save-btn" data-action="save-edit" title="Send">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a1 1 0 011 1v10.586l2.293-2.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L7 12.586V2a1 1 0 011-1z" transform="rotate(180 8 8)"/>
          </svg>
        </button>
      </div>
    `;
    
    // Clear the edit container since we moved buttons inside messageDiv
    editContainer.innerHTML = ``;
    
    // Store original text for cancel
    wrapper.setAttribute('data-original-text', originalText);
    
    // Focus the textarea and set up auto-resize
    const textarea = messageDiv.querySelector('.edit-textarea') as HTMLTextAreaElement;
    if (textarea) {
      // Auto-resize functionality
      const autoResize = () => {
        textarea.style.height = '24px';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
      };
      
      textarea.addEventListener('input', autoResize);
      
      // Enter key to save (without Shift)
      textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          const saveBtn = messageDiv.querySelector('.edit-save-btn') as HTMLButtonElement;
          if (saveBtn) saveBtn.click();
        }
      });
      
      autoResize(); // Initial resize
      
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }
  }

  function cancelEdit(button: HTMLElement) {
    const wrapper = button.closest('.user-message-wrapper');
    if (!wrapper) return;
    
    const messageDiv = wrapper.querySelector('.message.user') as HTMLElement;
    const editContainer = wrapper.querySelector('.edit-button-container');
    const originalText = wrapper.getAttribute('data-original-text') || '';
    
    if (!messageDiv || !editContainer) return;
    
    // Remove editing class from wrapper
    wrapper.classList.remove('editing');
    
    // Restore original message
    messageDiv.innerHTML = originalText;
    
    // Restore original buttons
    editContainer.innerHTML = `
      <button class="copy-button-user" data-action="copy-user-message" title="Copy message">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
      <button class="edit-btn" data-action="edit-message" title="Edit message">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
        </svg>
      </button>
    `;
    
    wrapper.removeAttribute('data-original-text');
  }

  function saveEdit(button: HTMLElement) {
    // ✅ PHASE-1: Check per-session state
    if (!sessionId || isSessionGenerating(sessionId)) return;
    
    const wrapper = button.closest('.user-message-wrapper');
    if (!wrapper) return;
    
    const messageDiv = wrapper.querySelector('.message.user') as HTMLElement;
    const editContainer = wrapper.querySelector('.edit-button-container');
    const textarea = messageDiv?.querySelector('.edit-textarea') as HTMLTextAreaElement;
    
    if (!textarea || !messageDiv || !editContainer) return;
    
    const newText = textarea.value.trim();
    
    if (!newText) {
      alert('Message cannot be empty');
      return;
    }
    
    // Remove editing class from wrapper
    wrapper.classList.remove('editing');
    
    // Find all messages after this one and remove them
    let nextElement = wrapper.nextElementSibling;
    while (nextElement) {
      const toRemove = nextElement;
      nextElement = nextElement.nextElementSibling;
      toRemove.remove();
    }
    
    // Update the message
    messageDiv.innerHTML = newText;
    
    // Restore original buttons
    editContainer.innerHTML = `
      <button class="copy-button-user" data-action="copy-user-message" title="Copy message">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
      <button class="edit-btn" data-action="edit-message" title="Edit message">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
        </svg>
      </button>
    `;
    
    wrapper.removeAttribute('data-original-text');
    
    // Send the edited message to get a new response
    sendMessageText(newText);
  }

  // Expose ALL functions to window for onclick handlers
  (window as any).copyMessage = copyMessage;
  (window as any).copyUserMessage = copyUserMessage;
  (window as any).submitFeedback = submitFeedback;
  (window as any).editMessage = editMessage;
  (window as any).cancelEdit = cancelEdit;
  (window as any).saveEdit = saveEdit;
  (window as any).askRecommendedQuestion = askRecommendedQuestion;
  (window as any).showFeedbackModal = showFeedbackModal;
  (window as any).submitDetailedFeedback = submitDetailedFeedback;

  // ============================================================================
  // DYNAMIC SUGGESTED QUESTIONS SYSTEM
  // ============================================================================
  
  // Fetch suggested questions from API
  async function loadSuggestedQuestions() {
    try {
      // Check if questions already exist in DOM (don't reload if they're already there)
      const emptyContainer = document.getElementById('suggested-questions-empty');
      const mainContainer = document.getElementById('suggested-questions-main');
      
      // If containers exist and have content, skip reloading
      if (emptyContainer && emptyContainer.children.length > 0) {
        console.log('[QUESTIONS] Questions already loaded, skipping reload');
        return;
      }
      if (mainContainer && mainContainer.children.length > 0) {
        console.log('[QUESTIONS] Questions already loaded, skipping reload');
        return;
      }
      
      console.log('[QUESTIONS] Loading dynamic suggested questions...');
      // ✅ Use apiFetch for all backend calls
      const response = await apiFetch('/api/suggested-questions/?limit=4');
      
      if (!response.ok) {
        console.error('[QUESTIONS] Failed to load questions:', response.status);
        return;
      }
      
      // 🔒 CRITICAL FIX: Defensive check for response data with type guards
      let questions: SuggestedQuestion[] = [];
      try {
        const data = await response.json();
        
        // Type guard function to validate SuggestedQuestion
        const isValidQuestion = (q: any): q is SuggestedQuestion => 
          q && 
          typeof q === 'object' && 
          typeof q.id === 'string' && 
          typeof q.question_text === 'string';
        
        // Backend returns array directly (from MongoDB via QuestionResponse)
        if (Array.isArray(data)) {
          // Filter and validate each item (backend may include extra fields like category, priority)
          questions = data.filter(isValidQuestion);
        } else if (data && typeof data === 'object') {
          // Fallback: try to extract from object (shouldn't happen, but defensive)
          const questionsData = data.questions || data.data || [];
          if (Array.isArray(questionsData)) {
            questions = questionsData.filter(isValidQuestion);
          }
        }
      } catch (parseError) {
        console.error('[QUESTIONS] Failed to parse response:', parseError);
        return;
      }
      
      // Final safety check
      if (!Array.isArray(questions)) {
        console.warn('[QUESTIONS] Questions is not an array:', questions);
        questions = [];
      }
      
      console.log('[QUESTIONS] Loaded', questions.length, 'questions');
      updateSuggestedQuestions(questions);
    } catch (error) {
      console.error('[QUESTIONS] Error loading questions:', error);
    }
  }
  
  // Update both suggested questions containers
  function updateSuggestedQuestions(questions: SuggestedQuestion[]) {
    const containers = [
      document.getElementById('suggested-questions-empty'),
      document.getElementById('suggested-questions-main')
    ];
    
    containers.forEach(container => {
      if (!container || !questions || questions.length === 0) return;
      
      const html = questions.map((q: SuggestedQuestion) => `
        <button class="suggested-question-btn" 
                data-question="${q.question_text.replace(/"/g, '&quot;')}"
                data-question-id="${q.id}">
          ${q.question_text}
        </button>
      `).join('');
      
      container.innerHTML = html;
    });
    
    // Re-attach event listeners for new buttons
    attachSuggestedQuestionListeners();
  }
  
  // Attach click handlers to suggested question buttons
  function attachSuggestedQuestionListeners() {
    const buttons = document.querySelectorAll('.suggested-question-btn');
    
    buttons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const button = e.target as HTMLButtonElement;
        const question = button.getAttribute('data-question');
        const questionId = button.getAttribute('data-question-id');
        
        if (question) {
          // Track click for analytics
          if (questionId) {
            trackQuestionClick(questionId);
          }
          
          // Remove all previous recommended questions
          const allRecommendations = messagesDiv!.querySelectorAll('.recommended-questions');
          allRecommendations.forEach(rec => rec.remove());
          
          // Add user message to chat
          addMessage(question, "user");
          
          // Clear input fields
          if (input) {
            input.value = "";
            input.style.height = '24px';
          }
          if (inputEmptyState) {
            inputEmptyState.value = "";
            inputEmptyState.style.height = '24px';
          }
          
          // Send the question
          sendMessageText(question);
        }
      });
    });
  }
  
  // Track question click for analytics (optional - silently fails if endpoint not available)
  function trackQuestionClick(questionId: string) {
    // Disabled for now - analytics endpoint not implemented yet
    // fetch(`${getApiBase()}/api/suggested-questions/analytics`, {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify({
    //     action: 'click',
    //     question_id: questionId
    //   })
    // }).catch(err => console.error('[ANALYTICS] Failed to track click:', err));
    console.log('[ANALYTICS] Question clicked:', questionId);
  }
  
  // ============================================================================
  // AUTHENTICATION & INITIALIZATION
  // ============================================================================
  
  // Initialize auth - simplified since auth check is done at component level
  async function initAuth() {
    // ✅ FIX 2: Session-based auth - check user exists (no token needed)
    const user = getCurrentUser();
    
    // User is already authenticated at this point (checked in component)
    // Just load user info and chat history
    if (user) {
      // ✅ User type is compatible - no token fields needed
      updateUserInfo(user as any);
      
      // If switching sessions, skip full reload and only reload session data
      if (isSwitchingSession) {
        console.log('[CHAT] Session switch detected - reloading only session data');
        
        /* ================================
           PHASE 2.5.1 – CRITICAL FIX #2
           Save current session before switching away to prevent data loss
           
           At this point:
           - currentInitializedSessionId = OLD session ID (still in DOM)
           - sessionId = NEW session ID (from URL)
           - DOM still contains OLD session's messages
           
           We need to save the OLD session before loading the NEW session
           ================================ */
        try {
          const newSessionId = sessionId;  // Save the new session ID
          sessionId = currentInitializedSessionId;  // Temporarily restore old session ID
          
          // Now saveCurrentSession() will use the correct (old) session ID
          // It reads messages from DOM (which still has old session's messages)
          // and saves them with the old session ID
          if (typeof saveCurrentSession === 'function') {
            saveCurrentSession();
            console.log('[CHAT] ✅ Saved previous session before switch:', currentInitializedSessionId);
          }
          
          sessionId = newSessionId;  // Restore new session ID for upcoming logic
        } catch (err) {
          console.error('[CHAT] Failed to save session before switch:', err);
        }
        /* ================================ */
        
        // Update sidebar active state (lightweight, no re-render)
        updateSidebarActiveState(initialSessionId || null);
        
        // Load the new session
        if (initialSessionId) {
          // Check if this is an Others Chat (conversation_id format or legacy user_chat_ format)
          const isConversationId = /^[0-9a-fA-F]{24}$/.test(initialSessionId);
          const isLegacyOthersChat = initialSessionId.startsWith('user_chat_');
          
          if (isConversationId || isLegacyOthersChat) {
            console.log('[SESSION] Loading Others Chat from backend:', initialSessionId);
            loadOthersSession(initialSessionId);
          } else {
            // This is user's own chat - load from localStorage
            const sessions = getAllSessions();
            const currentSession = sessions.find(s => s.id === sessionId);
            if (currentSession) {
              console.log('[SESSION] Loading session for switch:', sessionId);
              // Always reload session when switching (clear existing messages first)
              if (messagesDiv) {
                messagesDiv.innerHTML = '';
              }
              loadSession(currentSession);
            } else {
              console.log('[SESSION] Session not found in localStorage:', sessionId);
              // Clear messages if session not found
              if (messagesDiv) {
                messagesDiv.innerHTML = '';
              }
              updateEmptyState();
            }
          }
        } else {
          // New chat mode - clear messages
          if (messagesDiv) {
            messagesDiv.innerHTML = '';
          }
          updateEmptyState();

          // Reload suggested questions for fresh chat start
          const emptyContainer = document.getElementById('suggested-questions-empty');
          const mainContainer = document.getElementById('suggested-questions-main');
          if (emptyContainer) emptyContainer.innerHTML = '';
          if (mainContainer) mainContainer.innerHTML = '';
          loadSuggestedQuestions();
        }
        
        // Update initialization state after session switch
        currentInitializedSessionId = initialSessionId || null;
        return;
      }
      
      // Full initialization (first time only)
      // Add test data for UI testing (DISABLED IN PRODUCTION)
      // addTestSessions();
      
      // Remove any existing test sessions (production cleanup)
      removeTestSessions();
      
      // ✅ IMPORTANT: Fetch and merge sessions from backend BEFORE rendering sidebar
      // This ensures chats saved on other devices/browsers are available
      console.log('[SESSIONS] Fetching sessions from backend for cross-device sync...');
      try {
        await fetchAndMergeUserSessions();
        console.log('[SESSIONS] Backend sync complete');
      } catch (error) {
        console.error('[SESSIONS] Failed to fetch sessions from backend:', error);
        // Continue even if backend fetch fails (use local sessions)
      }
      
      // Load dynamic suggested questions (only on first initialization)
      loadSuggestedQuestions();
      
      // Load session history in sidebar (async) - now includes backend sessions
      renderSessionHistory().catch(err => console.error('[SESSION] Failed to render history:', err));
      
      // Load current session if it exists in localStorage
      // BUT only if we're on /chat/[sessionId] route (not /chat/new)
      if (initialSessionId) {
        // Check if this is an Others Chat (conversation_id format or legacy user_chat_ format)
        const isConversationId = /^[0-9a-fA-F]{24}$/.test(initialSessionId);
        const isLegacyOthersChat = initialSessionId.startsWith('user_chat_');
        
        if (isConversationId || isLegacyOthersChat) {
          console.log('[SESSION] Loading Others Chat from backend:', initialSessionId);
          loadOthersSession(initialSessionId);
        } else {
          // This is user's own chat
          // Use preloaded session if available (from shared chat or session page)
          if (preloadedSession && preloadedSession.messages && preloadedSession.messages.length > 0) {
            console.log('[SESSION] Loading preloaded session with', preloadedSession.messages.length, 'messages');
            loadSession(preloadedSession);
          } else {
            // Fall back to localStorage
            const sessions = getAllSessions();
            const currentSession = sessions.find(s => s.id === sessionId);
            if (currentSession && messagesDiv!.children.length === 0) {
              console.log('[SESSION] Loading existing session from localStorage');
              loadSession(currentSession);
            } else if (!currentSession) {
              console.log('[SESSION] Session not found in localStorage or preloaded');
            }
          }
        }
      } else {
        console.log('[SESSION] New chat mode - not loading any existing session');
      }
      
      // Mark as initialized
      isAppInitialized = true;
      currentInitializedSessionId = initialSessionId || null;
    }
  }

  interface User {
    id: string;
    name: string;
    email: string;
    access_token: string;
    refresh_token: string;
  }

  function updateUserInfo(user: User) {
    const userName = document.getElementById('userName');
    const userAvatar = document.getElementById('userAvatar');
    const userEmail = document.getElementById('userEmail');
    const userEmailSidebar = document.getElementById('userEmailSidebar');
    
    if (user) {
      userName!.textContent = user.name || 'User';
      userAvatar!.textContent = (user.name || 'U').charAt(0).toUpperCase();
      userEmail!.textContent = user.email || '';
      if (userEmailSidebar) {
        userEmailSidebar.textContent = user.email || '';
      }
    }
  }

  // ❌ DEPRECATED: Legacy function - use session-based auth instead
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async function loadUserChatHistory(userId: string, accessToken: string) {
    console.warn('[AUTH] loadUserChatHistory() is deprecated - use session-based auth');
    try {
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch(`/chat/history/${userId}`, {
        method: 'GET'
      });
      
      if (response.ok) {
        const data = await response.json();
        const history = data.history || [];
        
        if (history.length > 0) {
          messagesDiv!.innerHTML = '';
          
          for (let i = 0; i < history.length; i++) {
            const message = history[i];
            const sender = message.role === 'user' ? 'user' : 'bot';
            
            if (sender === 'bot') {
              // For bot messages, check if we have saved recommendations
              const savedRecommendations = loadRecommendedQuestions(i);
              const recommendedQuestionsHTML = buildRecommendedQuestionsHTML(savedRecommendations);
              
              // Create bot message with recommendations
              const div = document.createElement("div");
              div.className = "message bot";
              // Render markdown and add UTM parameters to all links
              const renderedMarkdown = renderMarkdown(message.content);
              const contentWithLinks = linkifyText(renderedMarkdown);
              div.innerHTML = `
                <div class="message-content">${contentWithLinks}</div>
                <div class="feedback-buttons">
                  <button class="copy-button" data-action="copy-message" title="Copy message">
                    <img src="/images/copy-icon.svg?v=2" alt="Copy" width="16" height="16">
                  </button>
                  <button class="feedback-btn thumbs-up" data-action="feedback" data-rating="thumbs_up" title="Good response">
                    <img src="/images/thumbs-up-icon.svg?v=2" alt="Thumbs up" width="16" height="16">
                  </button>
                  <button class="feedback-btn thumbs-down" data-action="feedback" data-rating="thumbs_down" title="Bad response">
                    <img src="/images/thumbs-down-icon.svg?v=2" alt="Thumbs down" width="16" height="16">
                  </button>
                  <span class="feedback-text"></span>
                </div>
                ${recommendedQuestionsHTML}
              `;
              messagesDiv!.appendChild(div);
            } else {
              addMessage(message.content, sender);
            }
          }
          
          scrollToBottom();
        }
      }
    } catch (error) {
      console.error('[HISTORY] Failed to load chat history:', error);
    }
  }

  async function handleNewChat() {
    console.log('[NEW CHAT] Starting new chat...');
    
    // Reset read-only mode when creating new chat
    isReadOnlyMode = false;
    
    // If router is available, ALWAYS navigate to /chat/new
    if (router) {
      // Save current session before navigating
      if (messagesDiv!.children.length > 0) {
        saveCurrentSession();
      }
      
      // REQUIRED: Always force route change to /chat/new
      // Don't check current path - always navigate
      console.log('[NEW CHAT] Navigating to /chat/new');
      router.push('/chat/new');
      return;
    }
    
    // Fallback to old behavior if no router
    const newChatBtn = document.getElementById('newChatBtn') as HTMLElement;
    
    // Show loading state
    if (newChatBtn) {
      console.log('[NEW CHAT] Showing loading state');
      newChatBtn.innerHTML = `
        <svg class="loading-spinner" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" opacity="0.25"/>
          <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/>
        </svg>
        <span class="btn-text">Loading...</span>
      `;
      newChatBtn.style.pointerEvents = 'none';
    }
    
    // Save current session before creating new one
    if (messagesDiv!.children.length > 0) {
      saveCurrentSession();
    }
    
    // ✅ Session-based auth - session_id cookie sent automatically via proxy
    try {
      await apiFetch(`/chat/history/${getCurrentUser()?.id || ''}`, {
        method: "DELETE"
      });
    } catch (error) {
      console.error('Failed to clear chat history:', error);
    }
    
    // Clear old recommended questions
    clearRecommendedQuestions();
    
    // Create new session
    sessionId = createNewSession();
    activeSessionId = sessionId;
    currentSessionTitle = '';
    localStorage.setItem(getUserStorageKey('chatbot_session_id'), sessionId);
    
    // Clear messages
    messagesDiv!.innerHTML = '';
    updateEmptyState();
    
    // Update sidebar to show new session is active (async with error handling)
    renderSessionHistory().catch(err => console.error('[SESSION] Failed to render history:', err));
    
    // Show success state briefly with visual feedback
    if (newChatBtn) {
      console.log('[NEW CHAT] Showing success state');
      newChatBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10a37f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <span class="btn-text">New chat</span>
      `;
      
      // Show toast notification
      try {
        showToast('Started new chat');
      } catch (e) {
        console.error('[TOAST] Error showing toast:', e);
      }
      
      setTimeout(() => {
        console.log('[NEW CHAT] Resetting to normal state');
        newChatBtn.innerHTML = `
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          <span class="btn-text">New chat</span>
        `;
        newChatBtn.style.pointerEvents = 'auto';
      }, 800);
    }
  }

  // ✅ NEW: Handle logout (session-based auth)
  async function handleLogout() {
    try {
      // ✅ Session-based auth - session_id cookie sent automatically via proxy
      const response = await apiFetch('/auth/logout', {
        method: 'POST'
      });
      
      if (response.ok) {
        console.log('[AUTH] ✅ Logged out successfully');
      } else {
        console.warn('[AUTH] Logout endpoint failed, clearing local data anyway');
      }
    } catch (error) {
      console.error('[AUTH] Logout error:', error);
    } finally {
      // ✅ Clear all user-specific localStorage data (must be before removing 'user')
      clearUserLocalStorage();
      
      // ✅ Always clear user data (must be last to allow clearUserLocalStorage to get userId)
      localStorage.removeItem('user');
      
      // 🔒 CRITICAL: Clear session expiration flag on manual logout
      // This prevents showing "session expired" error when user manually logs out
      sessionStorage.removeItem('session_expired');
      // Set manual logout flag to prevent error message
      sessionStorage.setItem('manual_logout', 'true');
      window.location.href = "/login";
    }
  }

  function toggleDropdown() {
    const dropdown = document.getElementById('userDropdown');
    dropdown!.classList.toggle('show');
  }

  // Event listeners for regular input (bottom)
  // ✅ MOBILE FIX: Add multiple event types for better mobile support
  if (sendBtn) {
    // Handle click events (desktop and mobile)
    sendBtn.addEventListener("click", sendMessage);
    
    // ✅ MOBILE FIX: Add touch events for better mobile reliability
    let touchStartTime = 0;
    let touchStartY = 0;
    
    sendBtn.addEventListener("touchstart", (e) => {
      touchStartTime = Date.now();
      // Store Y position to detect scrolling
      touchStartY = (e.touches[0] || e.changedTouches[0]).clientY;
      // Don't preventDefault here - allow scrolling if user drags
    }, { passive: true });
    
    sendBtn.addEventListener("touchend", (e) => {
      const touchEndY = (e.changedTouches[0]).clientY;
      const touchDuration = Date.now() - touchStartTime;
      const touchDistance = Math.abs(touchEndY - touchStartY);
      
      // Only trigger if:
      // 1. Quick tap (< 500ms)
      // 2. Minimal movement (< 10px) - not a scroll
      if (touchDuration < 500 && touchDistance < 10) {
        e.preventDefault();
        e.stopPropagation();
        sendMessage();
      }
    }, { passive: false });
  }
  
  if (input) {
    // Auto-expand textarea and handle character validation
    input.addEventListener("input", (e) => {
      const target = e.target as HTMLTextAreaElement;
      target.style.height = '24px';
      target.style.height = Math.min(target.scrollHeight, 200) + 'px';
      
      // Character counter and button validation
      const counter = document.getElementById('char-counter');
      const sendButton = document.getElementById('send-btn') as HTMLButtonElement;
      const tooltip = document.getElementById('tooltip-main');
      const length = target.value.length;
      const exceeded = length >= MAX_PROMPT_LENGTH;
      
      // Show counter when approaching limit
      if (counter && length >= WARN_PROMPT_LENGTH) {
        counter.textContent = `${length.toLocaleString()} / ${MAX_PROMPT_LENGTH.toLocaleString()}`;
        counter.style.display = 'block';
        // Color coding: red when exceeded, orange when close, gray otherwise
        counter.style.color = exceeded ? '#ef4444' : (length > 18000 ? '#f59e0b' : '#6b7280');
      } else if (counter) {
        counter.style.display = 'none';
      }
      
      // Disable button if limit exceeded
      if (sendButton) {
        sendButton.disabled = exceeded;
        sendButton.style.opacity = exceeded ? '0.5' : '1';
        sendButton.style.cursor = exceeded ? 'not-allowed' : 'pointer';
        sendButton.style.backgroundColor = exceeded ? '#9ca3af' : '';
        
        // Show tooltip on hover when disabled
        if (exceeded) {
          sendButton.onmouseenter = () => { if (tooltip) tooltip.style.display = 'block'; };
          sendButton.onmouseleave = () => { if (tooltip) tooltip.style.display = 'none'; };
        } else {
          sendButton.onmouseenter = null;
          sendButton.onmouseleave = null;
          if (tooltip) tooltip.style.display = 'none';
        }
      }
    });
    
    // Handle Enter key
    input.addEventListener("keydown", (e) => { 
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const btn = document.getElementById('send-btn') as HTMLButtonElement;
        if (btn && !btn.disabled) {
          btn.click();
        }
      }
    });
  }

  // Event listeners for empty state input (center)
  // ✅ MOBILE FIX: Add multiple event types for better mobile support
  if (sendBtnEmptyState) {
    const handleEmptyStateSend = () => {
      // ✅ PHASE-1: Check per-session state
      if (!sessionId || isSessionGenerating(sessionId)) return;
      
      if (inputEmptyState) {
        const question = inputEmptyState.value.trim();
        if (question) {
          // Validate prompt length
          if (question.length > MAX_PROMPT_LENGTH) {
            const tokens = Math.round(question.length / 4);
            alert(`G��n+� Message is too long!\n\nYour message: ~${tokens.toLocaleString()} tokens (${question.length.toLocaleString()} characters)\nMaximum allowed: 5,000 tokens (20,000 characters)\n\nPlease shorten your message or split it into multiple parts.`);
            return;
          }
          
          // Show warning for large prompts
          if (question.length > WARN_PROMPT_LENGTH) {
            const tokens = Math.round(question.length / 4);
            const proceed = confirm(`G��n+� Large Message Warning\n\nYour message is approximately ${tokens.toLocaleString()} tokens (${question.length.toLocaleString()} characters).\n\nLarge messages may:\nG�� Take longer to process\nG�� Produce less focused responses\n\nDo you want to continue?`);
            if (!proceed) return;
          }
          
          addMessage(question, "user");
          inputEmptyState.value = "";
          inputEmptyState.style.height = '24px';
          
          // Hide character counter after sending
          const counter = document.getElementById('char-counter-empty');
          if (counter) counter.style.display = 'none';
          
          sendMessageText(question);
        }
      }
    };
    
    // Handle click events (desktop and mobile)
    sendBtnEmptyState.addEventListener("click", handleEmptyStateSend);
    
    // ✅ MOBILE FIX: Add touch events for better mobile reliability
    let emptyStateTouchStartTime = 0;
    let emptyStateTouchStartY = 0;
    
    sendBtnEmptyState.addEventListener("touchstart", (e) => {
      emptyStateTouchStartTime = Date.now();
      // Store Y position to detect scrolling
      emptyStateTouchStartY = (e.touches[0] || e.changedTouches[0]).clientY;
      // Don't preventDefault here - allow scrolling if user drags
    }, { passive: true });
    
    sendBtnEmptyState.addEventListener("touchend", (e) => {
      const touchEndY = (e.changedTouches[0]).clientY;
      const touchDuration = Date.now() - emptyStateTouchStartTime;
      const touchDistance = Math.abs(touchEndY - emptyStateTouchStartY);
      
      // Only trigger if:
      // 1. Quick tap (< 500ms)
      // 2. Minimal movement (< 10px) - not a scroll
      if (touchDuration < 500 && touchDistance < 10) {
        e.preventDefault();
        e.stopPropagation();
        handleEmptyStateSend();
      }
    }, { passive: false });
  }
  
  if (inputEmptyState) {
    // Auto-expand textarea and handle character validation
    inputEmptyState.addEventListener("input", (e) => {
      const target = e.target as HTMLTextAreaElement;
      target.style.height = '24px';
      target.style.height = Math.min(target.scrollHeight, 200) + 'px';
      
      // Character counter and button validation
      const counter = document.getElementById('char-counter-empty');
      const sendButton = document.getElementById('send-btn-empty') as HTMLButtonElement;
      const tooltip = document.getElementById('tooltip-empty');
      const length = target.value.length;
      const exceeded = length >= MAX_PROMPT_LENGTH;
      
      // Show counter when approaching limit
      if (counter && length >= WARN_PROMPT_LENGTH) {
        counter.textContent = `${length.toLocaleString()} / ${MAX_PROMPT_LENGTH.toLocaleString()}`;
        counter.style.display = 'block';
        // Color coding: red when exceeded, orange when close, gray otherwise
        counter.style.color = exceeded ? '#ef4444' : (length > 18000 ? '#f59e0b' : '#6b7280');
      } else if (counter) {
        counter.style.display = 'none';
      }
      
      // Disable button if limit exceeded
      if (sendButton) {
        sendButton.disabled = exceeded;
        sendButton.style.opacity = exceeded ? '0.5' : '1';
        sendButton.style.cursor = exceeded ? 'not-allowed' : 'pointer';
        sendButton.style.backgroundColor = exceeded ? '#9ca3af' : '';
        
        // Show tooltip on hover when disabled
        if (exceeded) {
          sendButton.onmouseenter = () => { if (tooltip) tooltip.style.display = 'block'; };
          sendButton.onmouseleave = () => { if (tooltip) tooltip.style.display = 'none'; };
        } else {
          sendButton.onmouseenter = null;
          sendButton.onmouseleave = null;
          if (tooltip) tooltip.style.display = 'none';
        }
      }
    });
    
    // Handle Enter key
    inputEmptyState.addEventListener("keydown", (e) => { 
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const btn = sendBtnEmptyState as HTMLButtonElement;
        if (btn && !btn.disabled) {
          btn.click();
        }
      }
    });
  }
  
  // Event listeners for suggested question buttons
  const suggestedQuestionBtns = document.querySelectorAll('.suggested-question-btn');
  suggestedQuestionBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
      // ✅ PHASE-1: Check per-session state
      if (!sessionId || isSessionGenerating(sessionId)) return;
      
      const button = e.target as HTMLButtonElement;
      const question = button.getAttribute('data-question');
      if (question) {
        // Remove all previous recommended questions when user clicks a suggested question
        const allRecommendations = messagesDiv!.querySelectorAll('.recommended-questions');
        allRecommendations.forEach(rec => rec.remove());
        
        // Add user message to chat
        addMessage(question, "user");
        
        // Clear input fields
        if (input) {
          input.value = "";
          input.style.height = '24px';
        }
        if (inputEmptyState) {
          inputEmptyState.value = "";
          inputEmptyState.style.height = '24px';
        }
        
        // Send the question
        sendMessageText(question);
      }
    });
  });
  
  const newChatBtn = document.getElementById('newChatBtn');
  if (newChatBtn) {
    newChatBtn.addEventListener('click', handleNewChat);
  }
  
  const userMenu = document.getElementById('userMenu');
  if (userMenu) {
    // Support both click and hover to open the user dropdown
    userMenu.addEventListener('click', toggleDropdown);
    userMenu.addEventListener('mouseenter', () => {
      const dropdown = document.getElementById('userDropdown');
      if (dropdown) dropdown.classList.add('show');
    });
    userMenu.addEventListener('mouseleave', () => {
      const dropdown = document.getElementById('userDropdown');
      if (dropdown) dropdown.classList.remove('show');
    });
  }
  
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', handleLogout);
  }
  
  // Scroll to bottom button functionality
  const scrollToBottomBtn = document.getElementById('scroll-to-bottom-btn');
  const messagesContainer = document.querySelector('.messages-container') as HTMLElement;
  
  // Helper function to check if user is near bottom
  function checkScrollPosition() {
    if (!scrollToBottomBtn || !messagesContainer) return;
    
    const threshold = 150; // Show button when more than 150px from bottom
    const isNearBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < threshold;
    
    if (isNearBottom) {
      scrollToBottomBtn.classList.remove('show');
    } else {
      scrollToBottomBtn.classList.add('show');
    }
  }
  
  if (scrollToBottomBtn && messagesContainer) {
    scrollToBottomBtn.addEventListener('click', () => {
      scrollToBottom();
      // Hide button immediately after clicking
      scrollToBottomBtn.classList.remove('show');
    });
    
    // Show/hide scroll to bottom button based on scroll position
    messagesContainer.addEventListener('scroll', checkScrollPosition);
    
    // Also check when content changes (new messages added)
    const observer = new MutationObserver(checkScrollPosition);
    observer.observe(messagesDiv!, { childList: true, subtree: true });
    
    // Initially hide the button
    scrollToBottomBtn.classList.remove('show');
  }
  
  document.addEventListener('click', (event) => {
    const userMenu = document.getElementById('userMenu');
    const dropdown = document.getElementById('userDropdown');
    const target = event.target as HTMLElement;
    
    // Don't close if clicking on admin menu items
    const adminItems = document.querySelectorAll('.admin-submenu .admin-item');
    let isAdminItemClick = false;
    adminItems.forEach(item => {
      if (item.contains(target as Node)) {
        isAdminItemClick = true;
      }
    });
    
    // Don't close if clicking inside dropdown or admin items
    if (userMenu && !userMenu.contains(event.target as Node)) {
      if (dropdown && !dropdown.contains(event.target as Node) && !isAdminItemClick) {
        dropdown.classList.remove('show');
      }
    }
    
    // Close history item dropdowns when clicking outside
    if (!target.closest('.history-item-menu') && !target.closest('.history-item-dropdown')) {
      document.querySelectorAll('.history-item-dropdown').forEach(dropdown => {
        (dropdown as HTMLElement).style.display = 'none';
      });
    }
  });

  // Feedback modal event listeners
  const feedbackModal = document.getElementById('feedback-modal');
  const feedbackModalClose = document.getElementById('feedback-modal-close');
  const feedbackSubmitBtn = document.getElementById('feedback-submit-btn');
  
  // Close modal when clicking X button
  if (feedbackModalClose) {
    feedbackModalClose.addEventListener('click', () => {
      if (feedbackModal) {
        feedbackModal.style.display = 'none';
      }
    });
  }
  
  // Close modal when clicking outside
  if (feedbackModal) {
    feedbackModal.addEventListener('click', (e) => {
      if (e.target === feedbackModal) {
        feedbackModal.style.display = 'none';
      }
    });
  }
  
  // Toggle category selection
  const categoryBtns = document.querySelectorAll('.feedback-category-btn');
  categoryBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      btn.classList.toggle('active');
    });
  });
  
  // Submit detailed feedback
  if (feedbackSubmitBtn) {
    feedbackSubmitBtn.addEventListener('click', submitDetailedFeedback);
  }

  // ============================================================================
  // GLOBAL EVENT LISTENERS (SET UP ONCE)
  // ============================================================================
  
  // Handle Yes/No button clicks for delete confirmation (dropdown appended to body)
  document.body.addEventListener('click', async (e) => {
    const target = e.target as HTMLElement;
    
    // Check if clicked on YES button
    const yesBtn = target.closest('.confirm-yes-option') as HTMLElement;
    if (yesBtn) {
      e.stopPropagation();
      e.preventDefault();
      const sid = yesBtn.dataset.sessionId;
      console.log('[DELETE] YES clicked - deleting session:', sid);
      // ✅ Await backend deletion
      await deleteSession(sid!);
      // Remove dropdown
      document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());
      return;
    }
    
    // Check if clicked on NO button
    const noBtn = target.closest('.confirm-no-option') as HTMLElement;
    if (noBtn) {
      e.stopPropagation();
      e.preventDefault();
      const sid = noBtn.dataset.sessionId;
      console.log('[DELETE] NO clicked - cancelled delete for session:', sid);
      // Remove dropdown
      document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());
      return;
    }
  });
  
  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    if (!target.closest('.history-item-dropdown') && !target.closest('.history-item-menu')) {
      document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());
    }
  });

  // ============================================================================
  // MOBILE-FRIENDLY EVENT DELEGATION FOR BUTTONS
  // ============================================================================
  // Use event delegation to handle all button clicks, including dynamically created ones
  // This ensures buttons work on mobile devices where inline onclick handlers can fail
  // ============================================================================
  
  function setupButtonEventDelegation() {
    let lastTouchTime = 0;
    // Use capture phase and handle both click and touch events for better mobile support
    const handleButtonAction = (e: Event) => {
      const isTouchEvent =
        e.type === 'touchend' ||
        (e.type === 'pointerup' && (e as PointerEvent).pointerType === 'touch');
      if (isTouchEvent) {
        lastTouchTime = Date.now();
      } else if (e.type === 'click' && Date.now() - lastTouchTime < 500) {
        // Skip synthetic click right after touch to avoid double handling
        return;
      }

      const target = e.target as HTMLElement;
      // Find the button element (might be clicking on an icon inside the button)
      const button = target.closest('[data-action]') as HTMLElement;
      if (!button) return;
      
      const action = button.getAttribute('data-action');
      if (!action) return;
      
      // Prevent default and stop propagation to avoid double-firing
      if (e.cancelable) {
        e.preventDefault();
      }
      e.stopPropagation();
      
      // Handle different button actions
      switch (action) {
        case 'copy-message':
          copyMessage(button);
          break;
        case 'copy-user-message':
          copyUserMessage(button);
          break;
        case 'feedback':
          const rating = button.getAttribute('data-rating');
          if (rating) {
            submitFeedback(button, rating);
          }
          break;
        case 'edit-message':
          editMessage(button);
          break;
        case 'cancel-edit':
          cancelEdit(button);
          break;
        case 'save-edit':
          saveEdit(button);
          break;
        case 'continue-thread':
          continueInThisThread();
          break;
        case 'share-chat':
          shareChat();
          break;
        case 'ask-recommended-question':
          const question = button.getAttribute('data-question');
          console.log('[EVENT] Recommended question clicked:', question);
          if (question) {
            askRecommendedQuestion(button);
          } else {
            console.warn('[EVENT] No question attribute found on recommended question button');
          }
          break;
      }
    };
    
    // Add listeners for click and touch/pointer events for better mobile support
    // Use capture phase to ensure we catch events before they bubble
    document.addEventListener('click', handleButtonAction, true);
    document.addEventListener('pointerup', handleButtonAction, { capture: true, passive: false });
    document.addEventListener('touchend', handleButtonAction, { capture: true, passive: false });
  }
  
  // Set up event delegation immediately
  setupButtonEventDelegation();

  initAuth();
}
