'use client';

import { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ChatSidebar from '@/components/ChatSidebar';
import SessionCard from '@/components/SessionCard';
import { getCurrentUser, checkSession, getAllSessions, fetchAndMergeUserSessions } from '@/lib/session-utils';
import { ChatSession } from '@/types/chat';

export default function ChatsPage() {
  const router = useRouter();
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
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [filteredSessions, setFilteredSessions] = useState<ChatSession[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const authCheckRef = useRef<boolean>(false);

  // Save sidebar state to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('sidebarOpen', String(isSidebarOpen));
    }
  }, [isSidebarOpen]);

  // Authentication check BEFORE rendering
  useEffect(() => {
    if (authCheckRef.current) {
      console.log('[AUTH] Auth check already in progress, skipping');
      return;
    }
    
    authCheckRef.current = true;
    
    const checkAuth = async () => {
      try {
        const sessionValid = await checkSession();
        if (!sessionValid) {
          console.log('[AUTH] Session invalid or expired, redirecting to login');
          localStorage.removeItem('user');
          router.replace('/login?error=session_expired');
          return;
        }

        const user = getCurrentUser();
        if (!user || !user.email || !user.email.endsWith('@cloudfuze.com')) {
          console.log('[AUTH] Invalid user data, redirecting to login');
          localStorage.removeItem('user');
          router.replace('/login?error=unauthorized_domain&email=' + encodeURIComponent(user?.email || ''));
          return;
        }

        console.log('[AUTH] User authenticated successfully:', user.email);
        setIsAuthenticated(true);
        setIsLoading(false);
        
      } catch (error) {
        console.error('[AUTH] Authentication check failed:', error);
        localStorage.removeItem('user');
        router.replace('/login?error=verification_failed');
      } finally {
        authCheckRef.current = false;
      }
    };

    checkAuth();
  }, [router]);

  // Load sessions after authentication
  useEffect(() => {
    if (isAuthenticated) {
      loadSessions();
    }
  }, [isAuthenticated]);

  const loadSessions = async () => {
    try {
      // Fetch and merge sessions from backend
      await fetchAndMergeUserSessions();
      
      // Get all sessions from localStorage
      const allSessions = getAllSessions();
      
      // Sort by timestamp (most recent first)
      allSessions.sort((a, b) => b.timestamp - a.timestamp);
      
      setSessions(allSessions);
      setFilteredSessions(allSessions);
      
      console.log('[CHATS] Loaded', allSessions.length, 'sessions');
    } catch (error) {
      console.error('[CHATS] Failed to load sessions:', error);
    }
  };

  // Filter sessions based on search query
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredSessions(sessions);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = sessions.filter(session => {
        return (
          session.title.toLowerCase().includes(query) ||
          session.messages.some(msg => msg.content.toLowerCase().includes(query))
        );
      });
      setFilteredSessions(filtered);
    }
  }, [searchQuery, sessions]);

  const handleNewChat = () => {
    // REQUIRED: Always navigate to /chat/new
    router.push('/chat/new');
  };

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
          Loading chats...
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
    <div className="chatgpt-container">
      <ChatSidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        onNewChat={handleNewChat}
      />
      
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
      
      <main className="chatgpt-main" style={{ padding: '40px' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ marginBottom: '32px' }}>
            <h1 style={{
              fontSize: '32px',
              fontWeight: '700',
              color: '#111827',
              marginBottom: '12px'
            }}>
              All Chats
            </h1>
            <p style={{
              fontSize: '16px',
              color: '#6b7280'
            }}>
              Browse and search through your chat history
            </p>
          </div>

          {/* Search Bar */}
          <div style={{ marginBottom: '32px' }}>
            <div style={{
              position: 'relative',
              maxWidth: '500px'
            }}>
              <svg 
                width="20" 
                height="20" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="#9ca3af" 
                strokeWidth="2"
                style={{
                  position: 'absolute',
                  left: '16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  pointerEvents: 'none'
                }}
              >
                <circle cx="11" cy="11" r="8"></circle>
                <path d="m21 21-4.35-4.35"></path>
              </svg>
              <input
                type="text"
                placeholder="Search chats..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px 16px 12px 48px',
                  fontSize: '15px',
                  border: '1px solid #d1d5db',
                  borderRadius: '12px',
                  outline: 'none',
                  transition: 'border-color 0.2s'
                }}
                onFocus={(e) => e.target.style.borderColor = '#0129ac'}
                onBlur={(e) => e.target.style.borderColor = '#d1d5db'}
              />
            </div>
          </div>

          {/* Sessions Grid */}
          {filteredSessions.length === 0 ? (
            <div style={{
              textAlign: 'center',
              padding: '60px 20px',
              color: '#9ca3af'
            }}>
              <svg 
                width="64" 
                height="64" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="currentColor" 
                strokeWidth="1.5"
                style={{ margin: '0 auto 16px' }}
              >
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              <p style={{ fontSize: '18px', fontWeight: '500', marginBottom: '8px' }}>
                {searchQuery ? 'No chats found' : 'No chats yet'}
              </p>
              <p style={{ fontSize: '14px' }}>
                {searchQuery ? 'Try a different search term' : 'Start a new conversation to see it here'}
              </p>
              {!searchQuery && (
                <button
                  onClick={handleNewChat}
                  style={{
                    marginTop: '24px',
                    padding: '12px 24px',
                    fontSize: '15px',
                    fontWeight: '500',
                    color: 'white',
                    backgroundColor: '#0129ac',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    transition: 'background-color 0.2s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#010f5e'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#0129ac'}
                >
                  Start New Chat
                </button>
              )}
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: '20px'
            }}>
              {filteredSessions.map((session) => (
                <SessionCard key={session.id} session={session} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

