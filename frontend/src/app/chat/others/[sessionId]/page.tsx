'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import ChatSidebar from '../../../../components/ChatSidebar';
import ChatInterface from '../../../../components/ChatInterface';
import { initializeChatApp } from '../../../../lib/chat-initialization';
import { User } from '../../../../types/chat';
import { getCurrentUser, checkSession } from '../../../../lib/session-utils';

export default function OthersSessionChatPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = params.sessionId as string;
  
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

        // Get user info for UI (optional - session is validated by cookie)
        const currentUser = getCurrentUser();
        if (currentUser) {
          console.log('[AUTH] ✅ User authenticated via session:', currentUser.email);
        }
        
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

  useEffect(() => {
    if (isAuthenticated && sessionId) {
      const checkMarked = setInterval(() => {
        if (typeof window.marked !== 'undefined') {
          clearInterval(checkMarked);
          console.log('[CHAT] Initializing others chat page for session:', sessionId);
          initializeChatApp({ router, initialSessionId: sessionId }); // Pass sessionId for Others Chat
        }
      }, 100);
      return () => clearInterval(checkMarked);
    }
  }, [isAuthenticated, router, sessionId]);

  // Avoid rendering until after hydration to prevent mismatches
  if (!hydrated) return null;

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'white', fontFamily: 'Arial, sans-serif' }}>
        <div style={{ width: '50px', height: '50px', border: '4px solid #f3f3f3', borderTop: '4px solid #0129ac', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
        <p style={{ marginTop: '20px', color: '#666', fontSize: '16px' }}>Verifying authentication...</p>
        <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const handleNewChat = () => {
    router.push('/chat/new');
  };

  return (
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
        activeSessionId={sessionId}
      />
      <ChatInterface sessionId={sessionId} />
    </div>
  );
}

