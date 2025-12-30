'use client';

import { useEffect, useCallback, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { ChatSession, OtherUserChat, User } from '@/types/chat';
import {
  getAllSessions,
  fetchAllUsersChats,
  getCurrentUser,
  deleteSession as deleteSessionUtil,
  saveAllSessions,
  setCurrentSessionId
} from '@/lib/session-utils';
import { isAdminEmail } from '@/constants/admins';
import { apiFetch } from '@/lib/api';

interface ChatSidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onLoadSession?: (session: ChatSession, isReadOnly: boolean) => void;
  activeSessionId?: string;
}

export default function ChatSidebar({
  isOpen,
  onToggle,
  onNewChat,
  onLoadSession,
  activeSessionId
}: ChatSidebarProps) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [showLogoutModal, setShowLogoutModal] = useState<boolean>(false);
  const [adminSubmenuOpen, setAdminSubmenuOpen] = useState<boolean>(false);
  const hasRenderedHistoryRef = useRef(false);
  const adminSubmenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const currentUser = getCurrentUser();
    setUser(currentUser);
    setIsAdmin(isAdminEmail(currentUser?.email));
  }, []);

  // Render session history
  const renderSessionHistory = useCallback(async (forceFullRender = false) => {
    const sidebarHistory = document.getElementById('sidebar-history');
    if (!sidebarHistory) return;
    const othersHistory = document.getElementById('others-history');

    // If we've already rendered once and not forcing, just update active state to avoid refetch/re-render
    if (hasRenderedHistoryRef.current && !forceFullRender) {
      const allHistoryItems = [
        ...(sidebarHistory ? Array.from(sidebarHistory.querySelectorAll('.history-item')) : []),
        ...(othersHistory ? Array.from(othersHistory.querySelectorAll('.history-item')) : [])
      ];
      allHistoryItems.forEach(item => {
        const sessionEl = item as HTMLElement;
        const sid = sessionEl.dataset.sessionId;
        if (sid === activeSessionId) {
          sessionEl.classList.add('active');
        } else {
          sessionEl.classList.remove('active');
        }
      });
      return;
    }

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
    let othersHtml = '';

    const othersChats = await fetchAllUsersChats();
    if (othersChats.length > 0) {
      othersChats.forEach((chat: OtherUserChat) => {
        const displayTitle = chat.title.length > 40 ? chat.title.substring(0, 40) + '...' : chat.title;
        const isActive = chat.session_id === activeSessionId;
        othersHtml += `
          <div class="history-item others-item ${isActive ? 'active' : ''}" data-session-id="${chat.session_id}" data-is-others="true">
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

    // Add click handlers for history items
    const allHistoryItems = [...Array.from(sidebarHistory.querySelectorAll('.history-item')),
    ...(othersHistory ? Array.from(othersHistory.querySelectorAll('.history-item')) : [])];

    allHistoryItems.forEach(item => {
      const sessionEl = item as HTMLElement;
      const sid = sessionEl.dataset.sessionId;
      const isOthers = sessionEl.dataset.isOthers === 'true';

      // Remove existing listeners by cloning
      const newItem = sessionEl.cloneNode(true) as HTMLElement;
      sessionEl.parentNode?.replaceChild(newItem, sessionEl);

      newItem.addEventListener('click', (e) => {
        const target = e.target as HTMLElement;
        // Don't navigate if clicking on menu button, dropdown, or toggle button
        if (target.closest('.history-item-menu') ||
          target.closest('.history-item-dropdown') ||
          target.closest('.section-toggle-btn')) {
          return;
        }

        allHistoryItems.forEach(item => {
          (item as HTMLElement).classList.remove('active');
        });
        newItem.classList.add('active');

        // Navigate based on chat type
        // NOTE: Sidebar will remain open during navigation (no onToggle called)
        if (isOthers) {
          // Client-side load for others' session (read-only) - no page reload
          if (typeof (window as any).loadOthersSession === 'function') {
            (window as any).loadOthersSession(sid);
            // Update URL without page reload
            window.history.pushState({}, '', `/chat/others/${sid}`);
          } else {
            // Fallback to router if function not available
            router.push(`/chat/others/${sid}`);
          }
        } else {
          // Navigate to own session
          // Sidebar stays open
          router.push(`/chat/${sid}`);
        }
      });
    });

    hasRenderedHistoryRef.current = true;
  }, [activeSessionId, router]);

  // Handle delete confirmation clicks globally
  useEffect(() => {
    const handleGlobalClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;

      // Handle Yes button
      const yesBtn = target.closest('.confirm-yes-option') as HTMLElement;
      if (yesBtn) {
        e.preventDefault();
        e.stopPropagation();
        const sid = yesBtn.dataset.sessionId;

        if (sid) {
          // Preserve current section states before deletion
          const sidebarHistory = document.getElementById('sidebar-history');
          const sectionStates: Record<string, boolean> = {};
          if (sidebarHistory) {
            const sections = sidebarHistory.querySelectorAll('.history-section-content');
            sections.forEach(section => {
              const sectionId = section.getAttribute('data-section-id');
              if (sectionId) {
                const isCollapsed = section.classList.contains('collapsed');
                sectionStates[sectionId] = isCollapsed;
                // Update localStorage to ensure state is preserved
                if (isCollapsed) {
                  localStorage.setItem(`section_collapsed_${sectionId}`, 'true');
                } else {
                  localStorage.removeItem(`section_collapsed_${sectionId}`);
                }
              }
            });
          }

          deleteSessionUtil(sid);

          // Remove delete-active class from all items
          document.querySelectorAll('.history-item').forEach(item => {
            item.classList.remove('delete-active');
          });

          // Remove dropdown
          document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());

          // If deleted current session, navigate to new chat
          if (sid === activeSessionId) {
            router.push('/chat/new');
          }

          // Re-render history (section states are preserved in localStorage)
          // Don't manually remove items - let re-render handle it to preserve section states
          renderSessionHistory(true);
        }
        return;
      }

      // Handle No button
      const noBtn = target.closest('.confirm-no-option') as HTMLElement;
      if (noBtn) {
        e.preventDefault();
        e.stopPropagation();
        
        // Remove delete-active class from all items
        document.querySelectorAll('.history-item').forEach(item => {
          item.classList.remove('delete-active');
        });
        
        document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());
        return;
      }

      // Close dropdown when clicking outside
      if (!target.closest('.history-item-dropdown') && !target.closest('.history-item-menu')) {
        // Remove delete-active class from all items
        document.querySelectorAll('.history-item').forEach(item => {
          item.classList.remove('delete-active');
        });
        
        document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());
      }
    };

    document.addEventListener('click', handleGlobalClick, true); // Use capture phase for better reliability
    return () => document.removeEventListener('click', handleGlobalClick, true);
  }, [activeSessionId, router, renderSessionHistory]);

  // Set up event delegation for sidebar interactions (only once)
  useEffect(() => {
    const sidebarHistory = document.getElementById('sidebar-history');
    if (!sidebarHistory) return;

    // Combined click handler for all sidebar interactions
    const handleSidebarClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;

      // Check for section toggle button first
      const toggleBtn = target.closest('.section-toggle-btn') as HTMLElement;
      if (toggleBtn) {
        e.preventDefault();
        e.stopPropagation();
        const sectionId = toggleBtn.dataset.sectionId;
        if (!sectionId) return;

        const content = sidebarHistory.querySelector(`.history-section-content[data-section-id="${sectionId}"]`);
        const icon = toggleBtn.querySelector('.toggle-icon');

        if (content && icon) {
          const isCollapsed = content.classList.contains('collapsed');

          if (isCollapsed) {
            content.classList.remove('collapsed');
            icon.classList.remove('collapsed');
            localStorage.removeItem(`section_collapsed_${sectionId}`);
            toggleBtn.setAttribute('title', 'Collapse');
          } else {
            content.classList.add('collapsed');
            icon.classList.add('collapsed');
            localStorage.setItem(`section_collapsed_${sectionId}`, 'true');
            toggleBtn.setAttribute('title', 'Expand');
          }
        }
        return;
      }

      // Check for delete menu button
      const menuBtn = target.closest('.history-item-menu') as HTMLElement;
      if (menuBtn) {
        e.preventDefault();
        e.stopPropagation();
        const sid = menuBtn.dataset.sessionId;

        // Find the parent history item
        const historyItem = menuBtn.closest('.history-item') as HTMLElement;
        
        // Remove delete-active class from all items
        document.querySelectorAll('.history-item').forEach(item => {
          item.classList.remove('delete-active');
        });
        
        // Add delete-active class to the clicked item to keep delete icon visible
        if (historyItem) {
          historyItem.classList.add('delete-active');
        }

        // Close all other dropdowns
        document.querySelectorAll('.history-item-dropdown').forEach(d => d.remove());

        // Create dropdown
        const dropdown = document.createElement('div');
        dropdown.className = 'history-item-dropdown';
        dropdown.dataset.sessionId = sid!;
        dropdown.innerHTML = `
          <div class="delete-confirmation-text">Delete this chat?</div>
          <div class="delete-confirmation-buttons">
            <button class="confirm-yes-option" data-session-id="${sid}" type="button">
              <span>Yes</span>
            </button>
            <button class="confirm-no-option" data-session-id="${sid}" type="button">
              <span>No</span>
            </button>
          </div>
        `;

        document.body.appendChild(dropdown);

        // Position dropdown
        const rect = menuBtn.getBoundingClientRect();
        const dropdownWidth = 160;
        const dropdownHeight = 75;
        let top = rect.bottom + 4;
        let left = rect.right - dropdownWidth + 145;

        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;

        if (spaceBelow < dropdownHeight + 10 && spaceAbove > dropdownHeight + 10) {
          top = rect.top - dropdownHeight - 4;
        }

        if (left + dropdownWidth > window.innerWidth - 10) {
          left = window.innerWidth - dropdownWidth - 10;
        }
        if (left < 10) left = 10;
        if (top < 10) top = 10;
        if (top + dropdownHeight > window.innerHeight - 10) {
          top = window.innerHeight - dropdownHeight - 10;
        }

        dropdown.style.top = `${top}px`;
        dropdown.style.left = `${left}px`;
        return;
      }
    };

    // Handle scroll
    const handleScroll = () => {
      // Remove delete-active class from all items
      document.querySelectorAll('.history-item').forEach(item => {
        item.classList.remove('delete-active');
      });
      document.querySelectorAll('.history-item-dropdown').forEach(dropdown => dropdown.remove());
    };

    sidebarHistory.addEventListener('click', handleSidebarClick);
    sidebarHistory.addEventListener('scroll', handleScroll);

    return () => {
      sidebarHistory.removeEventListener('click', handleSidebarClick);
      sidebarHistory.removeEventListener('scroll', handleScroll);
    };
  }, []);

  // Render session history on mount and when activeSessionId changes
  useEffect(() => {
    renderSessionHistory(!hasRenderedHistoryRef.current);
  }, [renderSessionHistory]);

  // Close submenu when dropdown closes
  useEffect(() => {
    const dropdown = document.getElementById('userDropdown');
    if (!dropdown) return;

    const observer = new MutationObserver(() => {
      if (!dropdown.classList.contains('show')) {
        setAdminSubmenuOpen(false);
      }
    });

    observer.observe(dropdown, {
      attributes: true,
      attributeFilter: ['class']
    });

    return () => observer.disconnect();
  }, []);

  // Show logout confirmation modal
  const handleLogoutClick = () => {
    setShowLogoutModal(true);
    // Close the dropdown
    const dropdown = document.getElementById('userDropdown');
    if (dropdown) {
      dropdown.classList.remove('show');
    }
  };

  // ✅ NEW: Handle logout confirmation (session-based auth)
  const handleLogoutConfirm = async () => {
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
      // Always clear local data
      localStorage.removeItem('user');
      // 🔒 CRITICAL: Clear session expiration flag on manual logout
      // This prevents showing "session expired" error when user manually logs out
      sessionStorage.removeItem('session_expired');
      // Set manual logout flag to prevent error message
      sessionStorage.setItem('manual_logout', 'true');
      router.replace('/login');
    }
  };

  // Handle logout cancel
  const handleLogoutCancel = () => {
    setShowLogoutModal(false);
  };

  // Toggle user dropdown
  const toggleUserDropdown = () => {
    const dropdown = document.getElementById('userDropdown');
    if (dropdown) {
      dropdown.classList.toggle('show');
    }
  };

  // Handle admin menu navigation
  const handleAdminNavigation = (path: string, e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
    }
    console.log('[Admin Nav] Navigating to:', path);
    const dropdown = document.getElementById('userDropdown');
    if (dropdown) {
      dropdown.classList.remove('show');
    }
    setAdminSubmenuOpen(false);
    // Use window.location for more reliable navigation
    setTimeout(() => {
      window.location.href = path;
    }, 10);
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const dropdown = document.getElementById('userDropdown');
      const userMenu = document.getElementById('userMenu');
      const adminSubmenu = document.querySelector('.admin-submenu');
      const adminItems = document.querySelectorAll('.admin-submenu .admin-item');

      if (dropdown && userMenu) {
        const target = e.target as Node;
        // Check if click is on an admin menu item - if so, don't close
        let isAdminItemClick = false;
        adminItems.forEach(item => {
          if (item.contains(target)) {
            isAdminItemClick = true;
          }
        });
        
        // Don't close if clicking inside userMenu, dropdown, admin-submenu, or admin items
        if (!userMenu.contains(target) && !dropdown.contains(target) && 
            !(adminSubmenu && adminSubmenu.contains(target)) && !isAdminItemClick) {
          // Use setTimeout to let click handlers fire first
          setTimeout(() => {
            dropdown.classList.remove('show');
            setAdminSubmenuOpen(false);
          }, 0);
        }
      }
    };

    // Use bubble phase (not capture) so click handlers fire first
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  // Handle Escape key to close logout modal and disable background interactions
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && showLogoutModal) {
        setShowLogoutModal(false);
      }
    };

    const handleTab = (e: KeyboardEvent) => {
      if (!showLogoutModal) return;
      
      const modal = document.querySelector('.logout-modal');
      if (!modal) return;
      
      const focusableElements = modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const firstElement = focusableElements[0] as HTMLElement;
      const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    if (showLogoutModal) {
      document.addEventListener('keydown', handleEscape);
      document.addEventListener('keydown', handleTab);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
      // Disable pointer events on main content to make background inactive
      const mainContent = document.querySelector('.chatgpt-main');
      const sidebar = document.querySelector('.chatgpt-sidebar');
      const container = document.querySelector('.chatgpt-container');
      const headerContainer = document.getElementById('chat-header-container');
      const chatHeader = document.querySelector('.chat-header');
      
      if (container) {
        container.classList.add('modal-open');
      }
      if (mainContent) {
        (mainContent as HTMLElement).style.pointerEvents = 'none';
      }
      if (sidebar) {
        (sidebar as HTMLElement).style.pointerEvents = 'none';
      }
      if (headerContainer) {
        (headerContainer as HTMLElement).style.pointerEvents = 'none';
      }
      if (chatHeader) {
        (chatHeader as HTMLElement).style.pointerEvents = 'none';
      }

      // Focus the confirm button after a brief delay for smooth animation
      setTimeout(() => {
        const confirmBtn = document.querySelector('.logout-confirm-btn') as HTMLElement;
        if (confirmBtn) {
          confirmBtn.focus();
        }
      }, 100);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.removeEventListener('keydown', handleTab);
      document.body.style.overflow = '';
      // Re-enable pointer events on main content
      const mainContent = document.querySelector('.chatgpt-main');
      const sidebar = document.querySelector('.chatgpt-sidebar');
      const container = document.querySelector('.chatgpt-container');
      const headerContainer = document.getElementById('chat-header-container');
      const chatHeader = document.querySelector('.chat-header');
      
      if (container) {
        container.classList.remove('modal-open');
      }
      if (mainContent) {
        (mainContent as HTMLElement).style.pointerEvents = '';
      }
      if (sidebar) {
        (sidebar as HTMLElement).style.pointerEvents = '';
      }
      if (headerContainer) {
        (headerContainer as HTMLElement).style.pointerEvents = '';
      }
      if (chatHeader) {
        (chatHeader as HTMLElement).style.pointerEvents = '';
      }
    };
  }, [showLogoutModal]);

  return (
    <aside className={`chatgpt-sidebar ${isOpen ? 'open' : 'closed'}`}>
      <div className="sidebar-header">
        <div className="sidebar-top-row">
          <button
            className="sidebar-icon"
            onClick={() => router.push('/chat/new')}
            title="New chat"
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
          >
            {isOpen ? (
              <Image
                src="/images/CloudFuze Horizontal Logo.svg"
                alt="CloudFuze"
                width={200}
                height={52}
                priority
              />
            ) : (
              <Image
                src="/images/CloudFuze-icon-64x64.png"
                alt="CloudFuze"
                width={42}
                height={42}
                priority
              />
            )}
          </button>
          <button
            className="sidebar-toggle-btn-new"
            onClick={onToggle}
            title={isOpen ? "Close sidebar" : "Open sidebar"}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
          </button>
        </div>

        <button className="new-chat-btn-sidebar" onClick={onNewChat} title="New chat">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span className="btn-text">New chat</span>
        </button>
      </div>

      <div className="sidebar-content-wrapper">
        <div className="my-chats-section">
          <div className="section-label">My Chats</div>
          <div id="sidebar-history" className="sidebar-history">
            {/* Chat history will be populated here */}
          </div>
        </div>

        <div className="others-chats-section">
          <div className="section-label">Others Chats</div>
          <div id="others-history" className="sidebar-history">
            {/* Others' chats will be populated here */}
          </div>
        </div>

      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user" id="userMenu" onClick={toggleUserDropdown}>
          <div className="user-avatar" id="userAvatar">
            {user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
          </div>
          <div className="user-details">
            <span className="user-name" id="userName">{user?.name || 'User'}</span>
            <span className="user-email-small" id="userEmailSidebar">{user?.email || ''}</span>
          </div>
          <div className="user-dropdown-sidebar" id="userDropdown">
            <div className="dropdown-item" id="userEmail">{user?.email || ''}</div>
            {isAdmin && (
              <>
                <div 
                  className="dropdown-item admin-parent" 
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    // Ensure dropdown stays open when toggling submenu
                    const dropdown = document.getElementById('userDropdown');
                    if (dropdown && !dropdown.classList.contains('show')) {
                      dropdown.classList.add('show');
                    }
                    setAdminSubmenuOpen(!adminSubmenuOpen);
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <path d="M3 9h18M9 21V9" />
                  </svg>
                  <span>Admin</span>
                  <svg 
                    width="16" 
                    height="16" 
                    viewBox="0 0 24 24" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="2"
                    style={{ 
                      marginLeft: 'auto',
                      transform: adminSubmenuOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease'
                    }}
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </div>
                {adminSubmenuOpen && (
                  <div 
                    ref={adminSubmenuRef}
                    className="admin-submenu" 
                    style={{ pointerEvents: 'auto', position: 'relative', zIndex: 10000 }}
                  >
                    <div 
                      className="dropdown-item admin-item" 
                      onMouseDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Team Analytics clicked - mousedown');
                        handleAdminNavigation('/admin/teams', e);
                      }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Team Analytics clicked - click');
                        handleAdminNavigation('/admin/teams', e);
                      }}
                      style={{ cursor: 'pointer', pointerEvents: 'auto', position: 'relative', zIndex: 10000 }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm9 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
                      </svg>
                      <span>Team Analytics</span>
                    </div>
                    <div 
                      className="dropdown-item admin-item" 
                      onMouseDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Team Leaderboard clicked - mousedown');
                        handleAdminNavigation('/admin/teams-dashboard', e);
                      }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Team Leaderboard clicked - click');
                        handleAdminNavigation('/admin/teams-dashboard', e);
                      }}
                      style={{ cursor: 'pointer', pointerEvents: 'auto', position: 'relative', zIndex: 10000 }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M3 3h18v18H3V3zm2 2v14h14V5H5zm2 2h10v2H7V7zm0 4h10v2H7v-2zm0 4h7v2H7v-2z" />
                      </svg>
                      <span>Team Leaderboard</span>
                    </div>
                    <div 
                      className="dropdown-item admin-item" 
                      onMouseDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Langfuse Analytics clicked - mousedown');
                        handleAdminNavigation('/admin/analytics', e);
                      }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Langfuse Analytics clicked - click');
                        handleAdminNavigation('/admin/analytics', e);
                      }}
                      style={{ cursor: 'pointer', pointerEvents: 'auto', position: 'relative', zIndex: 10000 }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M3 3v18h18M3 15l4-4 3 3 5-5 6 6M9 7h6M9 7v2" />
                      </svg>
                      <span>Langfuse Analytics</span>
                    </div>
                    <div 
                      className="dropdown-item admin-item" 
                      onMouseDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Most Asked Questions clicked - mousedown');
                        handleAdminNavigation('/admin/top-questions', e);
                      }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.nativeEvent.stopImmediatePropagation();
                        console.log('[Admin Nav] Most Asked Questions clicked - click');
                        handleAdminNavigation('/admin/top-questions', e);
                      }}
                      style={{ cursor: 'pointer', pointerEvents: 'auto', position: 'relative', zIndex: 10000 }}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M3 13h2v-2H3v2Zm4 0h2v-2H7v2Zm4 0h2v-2h-2v2Zm4 0h2v-2h-2v2Zm4 0h2v-2h-2v2ZM5 21h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2-3h-4l-2 3H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2Z" />
                      </svg>
                      <span>Most Asked Questions</span>
                    </div>
                  </div>
                )}
              </>
            )}
            <div className="dropdown-item logout" onClick={handleLogoutClick}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M3.50171 12.6663V7.33333C3.50171 6.64424 3.50106 6.08728 3.53784 5.63704C3.57525 5.17925 3.65463 4.77342 3.84644 4.39681L3.96851 4.17806C4.2726 3.68235 4.70919 3.2785 5.23023 3.01302L5.3728 2.94661C5.7091 2.80238 6.06981 2.73717 6.47046 2.70443C6.9207 2.66764 7.47766 2.66829 8.16675 2.66829H9.16675L9.30054 2.68197C9.60367 2.7439 9.83179 3.0119 9.83179 3.33333C9.83179 3.65476 9.60367 3.92277 9.30054 3.9847L9.16675 3.99837H8.16675C7.45571 3.99837 6.96238 3.99926 6.57886 4.0306C6.297 4.05363 6.10737 4.09049 5.96362 4.14193L5.83374 4.19857C5.53148 4.35259 5.27861 4.58671 5.1023 4.87435L5.03198 5.00032C4.95147 5.15833 4.89472 5.36974 4.86401 5.74544C4.83268 6.12896 4.83179 6.6223 4.83179 7.33333V12.6663C4.83179 13.3772 4.8327 13.8707 4.86401 14.2542C4.8947 14.6298 4.95153 14.8414 5.03198 14.9993L5.1023 15.1263C5.27861 15.4137 5.53163 15.6482 5.83374 15.8021L5.96362 15.8577C6.1074 15.9092 6.29691 15.947 6.57886 15.9701C6.96238 16.0014 7.45571 16.0013 8.16675 16.0013H9.16675L9.30054 16.015C9.6036 16.0769 9.83163 16.345 9.83179 16.6663C9.83179 16.9877 9.60363 17.2558 9.30054 17.3177L9.16675 17.3314H8.16675C7.47766 17.3314 6.9207 17.332 6.47046 17.2952C6.06978 17.2625 5.70912 17.1973 5.3728 17.0531L5.23023 16.9867C4.70911 16.7211 4.27261 16.3174 3.96851 15.8216L3.84644 15.6038C3.65447 15.2271 3.57526 14.8206 3.53784 14.3626C3.50107 13.9124 3.50171 13.3553 3.50171 12.6663ZM13.8035 13.804C13.5438 14.0634 13.1226 14.0635 12.863 13.804C12.6033 13.5443 12.6033 13.1223 12.863 12.8626L13.8035 13.804ZM12.863 6.19661C13.0903 5.96939 13.4409 5.94126 13.699 6.11165L13.8035 6.19661L17.1375 9.52962C17.3969 9.78923 17.3968 10.2104 17.1375 10.4701L13.8035 13.804L13.3337 13.3333L12.863 12.8626L15.0603 10.6654H9.16675C8.79959 10.6654 8.50189 10.3674 8.50171 10.0003C8.50171 9.63306 8.79948 9.33529 9.16675 9.33529H15.0613L12.863 7.13704L12.7781 7.03255C12.6077 6.77449 12.6359 6.42386 12.863 6.19661Z" />
              </svg>
              <span>Log out</span>
            </div>
          </div>
        </div>
      </div>

      {/* Logout Confirmation Modal */}
      {showLogoutModal && (
        <>
          <div 
            className="logout-modal-overlay" 
            onClick={handleLogoutCancel}
          />
          <div className="logout-modal" onClick={(e) => e.stopPropagation()}>
            <div className="logout-modal-content">
              <h3 className="logout-modal-title">Are you sure you want to log out?</h3>
              <p className="logout-modal-message">
                Log out of ai.cloudfuze as {user?.email || 'user'}?
              </p>
              <div className="logout-modal-buttons">
                <button 
                  className="logout-modal-btn logout-cancel-btn" 
                  onClick={(e) => {
                    e.stopPropagation();
                    handleLogoutCancel();
                  }}
                >
                  Cancel
                </button>
                <button 
                  className="logout-modal-btn logout-confirm-btn" 
                  onClick={(e) => {
                    e.stopPropagation();
                    handleLogoutConfirm();
                  }}
                  autoFocus
                >
                  Log out
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}

