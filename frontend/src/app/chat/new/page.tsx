'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ChatSidebar from '@/components/ChatSidebar';
import ChatInterface from '@/components/ChatInterface';
import TokenMonitor from '@/components/TokenMonitor';
import { getCurrentUser, checkSession, createNewSessionId, setCurrentSessionId } from '@/lib/session-utils';

export default function NewChatPage() {
  const router = useRouter();
  
  // Hydration guard to avoid SSR/client HTML mismatch
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  // Always start with loading state to match server/client initial render
  // This prevents hydration mismatches
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  // Load sidebar state from localStorage, default to true if not set
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('sidebarOpen');
      return saved !== null ? saved === 'true' : true;
    }
    return true;
  });
  const authCheckRef = useRef<boolean>(false);

  // Save sidebar state to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('sidebarOpen', String(isSidebarOpen));
    }
  }, [isSidebarOpen]);

  // ✅ Simple session check (cookie-based auth only)
  useEffect(() => {
    if (authCheckRef.current) {
      console.log('[AUTH] Auth check already in progress, skipping');
      return;
    }
    
    authCheckRef.current = true;
    
    const checkAuth = async () => {
      try {
        // ✅ Simple session check - no token logic
        const isLoggedIn = await checkSession();
        
        if (!isLoggedIn) {
          console.log('[AUTH] No valid session, redirecting to login');
          localStorage.removeItem('user');
          setIsAuthenticated(false);
          setIsLoading(false);
          router.replace('/login');
          return;
        }

        // ✅ checkSession() now guarantees user exists (or fails)
        const currentUser = getCurrentUser();

        if (!currentUser) {
          console.error('[AUTH] Session valid but still no user found (unexpected). Redirecting...');
          localStorage.removeItem('user');
          setIsAuthenticated(false);
          setIsLoading(false);
          router.replace('/login');
          return;
        }

        console.log('[AUTH] ✅ Logged in user:', currentUser.email);
        
        setIsAuthenticated(true);
        setIsLoading(false);
        
      } catch (error) {
        console.error('[AUTH] Authentication check failed:', error);
        localStorage.removeItem('user');
        setIsAuthenticated(false);
        setIsLoading(false);
        router.replace('/login');
      } finally {
        authCheckRef.current = false;
      }
    };

    checkAuth();
  }, [router]);

  // Initialize chat app ONLY after authentication is confirmed
  useEffect(() => {
    if (isAuthenticated) {
      // Clear any stale chat state when mounting /chat/new
      // This ensures clean state even if user navigates here from another route
      if (typeof window !== 'undefined') {
        const messagesDiv = document.getElementById('messages');
        if (messagesDiv) {
          messagesDiv.innerHTML = '';
        }
        const emptyState = document.getElementById('empty-state');
        const inputSection = document.querySelector('.chatgpt-input-section') as HTMLElement;
        if (emptyState && inputSection && messagesDiv) {
          emptyState.style.display = 'flex';
          messagesDiv.style.display = 'none';
          inputSection.classList.remove('show');
        }
      }

      // Wait for marked.js to load
      const checkMarked = setInterval(() => {
        if (typeof window.marked !== 'undefined') {
          clearInterval(checkMarked);
          // Import and initialize the chat app
          import('@/lib/chat-initialization').then(({ initializeChatApp }) => {
            console.log('[CHAT] Initializing new chat page');
            // Pass router and null session ID (will create on first message)
            initializeChatApp({ router, initialSessionId: null });
          });
        }
      }, 100);

      return () => clearInterval(checkMarked);
    }
  }, [isAuthenticated, router]);

  const handleNewChat = () => {
    // REQUIRED: Always navigate to /chat/new to force route refresh
    // This ensures state is cleared even if URL was changed via window.history.replaceState()
    // Navigating to the same route forces Next.js to re-mount and clear state
    router.push('/chat/new');
  };

  // Avoid rendering until after hydration to prevent mismatches
  if (!hydrated) return null;

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'white',
        fontFamily: 'Arial, sans-serif'
      }}>
        <div style={{
          width: '50px',
          height: '50px',
          border: '4px solid #f3f3f3',
          borderTop: '4px solid #0129ac',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }}></div>
        <p style={{ 
          marginTop: '20px', 
          color: '#666',
          fontSize: '16px'
        }}>
          Verifying authentication...
        </p>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <>
      <TokenMonitor />
      <div className="chatgpt-container">
        {/* Mobile Sidebar Toggle Button - Shows when sidebar is closed */}
        {!isSidebarOpen && (
          <button
            className="mobile-sidebar-toggle"
            onClick={() => setIsSidebarOpen(true)}
            title="Open sidebar"
            aria-label="Open sidebar"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          </button>
        )}
        
        {/* Mobile Overlay - Closes sidebar when clicked */}
        {isSidebarOpen && (
          <div 
            className="sidebar-overlay show"
            onClick={() => setIsSidebarOpen(false)}
            aria-label="Close sidebar"
          />
        )}
        
        <ChatSidebar
          isOpen={isSidebarOpen}
          onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
          onNewChat={handleNewChat}
          activeSessionId={undefined}
        />
        <ChatInterface key="new" sessionId={undefined} />
      </div>
    </>
  );
}

