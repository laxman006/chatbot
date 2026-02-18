'use client';

import { useEffect, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { apiFetch } from '@/lib/api';
import { getCurrentUser } from '@/lib/session-utils';
import { isAdminEmail } from '@/constants/admins';
import { User } from '@/types/chat';
import ChatSidebar from '@/components/ChatSidebar';

type UserSummary = {
  user_id: string;
  user_email: string;
  user_name: string;
  total_messages?: number;
  total_sessions?: number;
  avg_messages_per_session?: number;
  last_active?: string | null;
  role?: string | null;
  team_name?: string | null;
  manager_name?: string | null;
  is_active?: boolean;
};

type UsersSummaryResponse = {
  users: UserSummary[];
  total_users?: number;
  total_count?: number;
  generated_at?: string;
};

type TeamItem = {
  team_name: string;
  lead: string | null;
  lead_email: string | null;
  color?: string;
  description?: string;
  member_count: number;
};

type TeamsResponse = {
  teams: TeamItem[];
  total: number;
};

const ROLE_OPTIONS = [
  'Trainee',
  'Migration Engineer',
  'QA engineer',
  'software engineer',
  'Account Manager',
];

const AVATAR_BG = '#0129AC';

function getInitial(name: string | undefined, email: string): string {
  const n = (name || '').trim();
  if (n) return n.charAt(0).toUpperCase();
  const e = (email || '').trim();
  return e ? e.charAt(0).toUpperCase() : '?';
}

function getRoleBadgeStyle(role: string | null | undefined): { background: string; border: string; color: string } {
  // Match New chat button background (no hover): #f8fafc / #f1f5f9, border #e2e8f0
  const bg = 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)';
  const border = '1px solid #e2e8f0';
  const color = '#374151';
  return { background: bg, border, color };
}

export default function AdminUsersPage() {
  const router = useRouter();
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserSummary | null>(null);
  const [editRole, setEditRole] = useState('');
  const [editTeamName, setEditTeamName] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ email: string; action: 'deactivate' | 'activate' | 'remove' } | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [teamDropdownOpen, setTeamDropdownOpen] = useState(false);
  const [assignLeadDropdownOpen, setAssignLeadDropdownOpen] = useState(false);
  const [teamHoverKey, setTeamHoverKey] = useState<string | null>(null);
  const [assignLeadHoverKey, setAssignLeadHoverKey] = useState<string | null>(null);

  useEffect(() => {
    const user = getCurrentUser();
    if (!user) {
      router.replace('/login?error=admin_only');
      return;
    }
    if (!isAdminEmail(user.email)) {
      router.replace('/login?error=admin_only');
      return;
    }
    setAuthUser(user);
    setLoading(false);
  }, [router]);

  const fetchUsers = useCallback(async () => {
    if (!authUser) return;
    setFetching(true);
    setError(null);
    try {
      const res = await apiFetch('/admin/users/summary?include_inactive=true', { method: 'GET' });
      const data: UsersSummaryResponse = await res.json();
      if (!res.ok) {
        throw new Error((data as { detail?: string }).detail || 'Failed to load users');
      }
      setUsers(data.users || []);
      setTotalCount(data.total_count ?? data.total_users ?? (data.users || []).length);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setFetching(false);
    }
  }, [authUser]);

  const fetchTeams = useCallback(async () => {
    try {
      const res = await apiFetch('/admin/teams', { method: 'GET' });
      const data: TeamsResponse = await res.json();
      if (!res.ok) throw new Error((data as { detail?: string }).detail || 'Failed to load teams');
      setTeams(data.teams || []);
    } catch (e) {
      console.error('Failed to load teams:', e);
    }
  }, []);

  useEffect(() => {
    if (!authUser) return;
    fetchUsers();
    fetchTeams();
  }, [authUser, fetchUsers, fetchTeams]);

  const openEditModal = (u: UserSummary) => {
    setEditUser(u);
    setEditRole(u.role ?? '');
    setEditTeamName(u.team_name ?? '');
    setSaveError(null);
    setEditModalOpen(true);
  };

  const closeEditModal = () => {
    setEditModalOpen(false);
    setEditUser(null);
    setSaveError(null);
    setTeamDropdownOpen(false);
    setAssignLeadDropdownOpen(false);
    setTeamHoverKey(null);
    setAssignLeadHoverKey(null);
  };

  const handleSaveProfile = async () => {
    if (!editUser?.user_email) return;
    setSaving(true);
    setSaveError(null);
    try {
      const body: { role?: string; team_name?: string } = {};
      if (editRole !== (editUser.role ?? '')) body.role = editRole;
      if (editTeamName !== (editUser.team_name ?? '')) body.team_name = editTeamName || undefined;
      if (Object.keys(body).length === 0) {
        closeEditModal();
        return;
      }
      const res = await apiFetch(`/admin/users/${encodeURIComponent(editUser.user_email)}/profile`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error((data as { detail?: string }).detail || 'Failed to update profile');
      }
      setToast('Profile updated');
      setTimeout(() => setToast(null), 3000);
      closeEditModal();
      fetchUsers();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async (email: string) => {
    try {
      const res = await apiFetch(`/admin/users/${encodeURIComponent(email)}/deactivate`, { method: 'PUT' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error((data as { detail?: string }).detail || 'Failed to deactivate');
      }
      setToast('User deactivated');
      setTimeout(() => setToast(null), 3000);
      setConfirmAction(null);
      fetchUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to deactivate');
      setConfirmAction(null);
    }
  };

  const handleActivate = async (email: string) => {
    try {
      const res = await apiFetch(`/admin/users/${encodeURIComponent(email)}/activate`, { method: 'PUT' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error((data as { detail?: string }).detail || 'Failed to activate');
      }
      setToast('User activated');
      setTimeout(() => setToast(null), 3000);
      setConfirmAction(null);
      fetchUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to activate');
      setConfirmAction(null);
    }
  };

  const handleRemove = async (email: string) => {
    try {
      const res = await apiFetch(`/admin/users/${encodeURIComponent(email)}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error((data as { detail?: string }).detail || 'Failed to remove');
      }
      setToast('User removed');
      setTimeout(() => setToast(null), 3000);
      setConfirmAction(null);
      fetchUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove');
      setConfirmAction(null);
    }
  };

  const handleNewChat = useCallback(() => {
    router.push('/chat/new');
  }, [router]);

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <>
    <div className="chatgpt-container">
      {!isSidebarOpen && (
        <button
          className="mobile-sidebar-toggle"
          onClick={() => setIsSidebarOpen(true)}
          title="Open sidebar"
          aria-label="Open sidebar"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      )}
      {isSidebarOpen && (
        <div className="sidebar-overlay show" onClick={() => setIsSidebarOpen(false)} aria-label="Close sidebar" />
      )}
      <ChatSidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        onNewChat={handleNewChat}
        activeSessionId={undefined}
      />
    <div className="chatgpt-main admin-users-page" style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto', background: '#fff', overflow: 'auto' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem', color: '#1f2937' }}>User Management</h1>
      {toast && (
        <div
          role="alert"
          style={{
            position: 'fixed',
            top: '1rem',
            right: '1rem',
            padding: '0.75rem 1rem',
            background: '#10b981',
            color: 'white',
            borderRadius: '6px',
            zIndex: 10000,
          }}
        >
          {toast}
        </div>
      )}
      {error && (
        <div
          style={{
            padding: '0.75rem 1rem',
            marginBottom: '1rem',
            background: '#fef2f2',
            color: '#b91c1c',
            borderRadius: '6px',
          }}
        >
          {error}
        </div>
      )}
      {fetching && users.length === 0 ? (
        <p>Loading users...</p>
      ) : (
        <>
          <p style={{ marginBottom: '1rem', color: '#6b7280', fontSize: '0.875rem' }}>
            Total users: {totalCount}
          </p>
          <div style={{ overflowX: 'auto', background: 'white', borderRadius: '8px', border: '1px solid #e5e7eb', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 600, color: '#374151' }}>User</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 600, color: '#374151' }}>Role</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 600, color: '#374151' }}>Team Lead</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 600, color: '#374151' }}>Status</th>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600, color: '#374151' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_email} style={{ borderBottom: '1px solid #ececf1', background: 'white' }}>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <div
                          style={{
                            width: 40,
                            height: 40,
                            borderRadius: '50%',
                            background: AVATAR_BG,
                            color: 'white',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 600,
                            fontSize: '1rem',
                            flexShrink: 0,
                          }}
                          aria-hidden
                        >
                          {getInitial(u.user_name, u.user_email)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, color: '#1f2937' }}>{u.user_name || u.user_email}</div>
                          <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>{u.user_email}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      {u.role ? (
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '0.35rem 0.75rem',
                            borderRadius: '9999px',
                            fontSize: '0.8125rem',
                            fontWeight: 500,
                            ...getRoleBadgeStyle(u.role),
                          }}
                        >
                          {u.role}
                        </span>
                      ) : (
                        <span style={{ color: '#9ca3af' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '0.75rem 1rem', color: '#374151' }}>{u.manager_name ?? '—'}</td>
                    <td style={{ padding: '0.75rem 1rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.35rem 0.75rem',
                          borderRadius: '9999px',
                          fontSize: '0.8125rem',
                          fontWeight: 500,
                          background: u.is_active !== false ? '#C8E6C9' : '#FFCDD2',
                          color: u.is_active !== false ? '#2E7D32' : '#C62828',
                          border: u.is_active !== false ? '1px solid #A5D6A7' : '1px solid #EF9A9A',
                        }}
                      >
                        {u.is_active !== false ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                      <button
                        type="button"
                        onClick={() => openEditModal(u)}
                        style={{
                          marginRight: '0.5rem',
                          padding: '0.35rem',
                          border: 'none',
                          borderRadius: '6px',
                          background: 'transparent',
                          cursor: 'pointer',
                          color: '#6b7280',
                        }}
                        aria-label="Edit user"
                        title="Edit"
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                      {u.is_active !== false ? (
                        <>
                          <button
                            type="button"
                            onClick={() => setConfirmAction({ email: u.user_email, action: 'deactivate' })}
                            style={{
                              padding: '0.35rem',
                              border: 'none',
                              borderRadius: '6px',
                              background: 'transparent',
                              cursor: 'pointer',
                              color: '#dc2626',
                            }}
                            aria-label="Deactivate user"
                            title="Deactivate"
                          >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                              <circle cx="9" cy="7" r="4" />
                              <path d="M22 21v-2a4 4 0 0 0-3.5-3.97" />
                              <path d="M16 11.5a4 4 0 0 1 0-8" />
                              <line x1="18" y1="8" x2="23" y2="13" />
                              <line x1="23" y1="8" x2="18" y2="13" />
                            </svg>
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmAction({ email: u.user_email, action: 'remove' })}
                            style={{
                              padding: '0.35rem',
                              border: 'none',
                              borderRadius: '6px',
                              background: 'transparent',
                              cursor: 'pointer',
                              color: '#b91c1c',
                            }}
                            aria-label="Remove user"
                            title="Remove"
                          >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                              <line x1="10" y1="11" x2="10" y2="17" />
                              <line x1="14" y1="11" x2="14" y2="17" />
                            </svg>
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmAction({ email: u.user_email, action: 'activate' })}
                          style={{
                            padding: '0.35rem',
                            border: 'none',
                            borderRadius: '6px',
                            background: 'transparent',
                            cursor: 'pointer',
                            color: '#059669',
                          }}
                          aria-label="Activate user"
                          title="Activate"
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                            <circle cx="9" cy="7" r="4" />
                            <path d="M22 21v-2a4 4 0 0 0-3.5-3.97" />
                            <path d="M16 11.5a4 4 0 0 1 0-8" />
                            <polyline points="16 12 18 14 22 10" />
                          </svg>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

    </div>
    </div>

      {editModalOpen && editUser && typeof document !== 'undefined' && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-user-title"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '40px 20px 20px',
            overflow: 'auto',
          }}
          onClick={closeEditModal}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '12px',
              padding: '32px',
              maxWidth: '500px',
              width: '100%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
              position: 'relative',
              margin: '0 auto',
              zIndex: 10001,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="edit-user-title" style={{ fontSize: '24px', fontWeight: 600, marginBottom: '8px', color: '#111827' }}>
              Edit User Role
            </h2>
            <p style={{ fontSize: '14px', color: '#6B7280', marginBottom: '24px' }}>
              {editUser.user_name || editUser.user_email} ({editUser.user_email})
            </p>
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#374151', marginBottom: '8px' }}>
                Role
              </label>
              <input
                type="text"
                value={editRole}
                onChange={(e) => setEditRole(e.target.value)}
                list="edit-role-suggestions"
                placeholder="Type a role or choose from suggestions"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  fontSize: '14px',
                  backgroundColor: 'white',
                  color: '#111827',
                }}
                aria-label="Role"
              />
              <datalist id="edit-role-suggestions">
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r} />
                ))}
              </datalist>
            </div>
            <div style={{ marginBottom: '16px', position: 'relative' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#374151', marginBottom: '8px' }}>
                Team
              </label>
              <div
                role="combobox"
                aria-expanded={teamDropdownOpen}
                aria-haspopup="listbox"
                aria-label="Team"
                tabIndex={0}
                onClick={() => { setTeamDropdownOpen((v) => !v); setAssignLeadDropdownOpen(false); }}
                onKeyDown={(e) => { if (e.key === 'Escape') setTeamDropdownOpen(false); if (e.key === 'Enter' || e.key === ' ') e.preventDefault(); }}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  fontSize: '14px',
                  backgroundColor: 'white',
                  color: '#111827',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span>{editTeamName ? teams.find((t) => t.team_name === editTeamName)?.team_name ?? editTeamName : '—'}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, transform: teamDropdownOpen ? 'rotate(180deg)' : 'none' }}>
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
              {teamDropdownOpen && (
                <ul
                  role="listbox"
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    margin: 0,
                    marginTop: '4px',
                    padding: 0,
                    listStyle: 'none',
                    background: 'white',
                    border: '1px solid #D1D5DB',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                    maxHeight: '220px',
                    overflowY: 'auto',
                    zIndex: 10002,
                  }}
                >
                  <li
                    role="option"
                    aria-selected={!editTeamName}
                    onClick={() => { setEditTeamName(''); setTeamDropdownOpen(false); }}
                    onMouseEnter={() => setTeamHoverKey('')}
                    onMouseLeave={() => setTeamHoverKey(null)}
                    style={{
                      padding: '10px 12px',
                      cursor: 'pointer',
                      fontSize: '14px',
                      borderBottom: '1px solid #f3f4f6',
                      background: (teamHoverKey === '' || !editTeamName) ? '#dbeafe' : undefined,
                    }}
                  >
                    —
                  </li>
                  {teams.map((t) => {
                    const selected = editTeamName === t.team_name;
                    const hovered = teamHoverKey === t.team_name;
                    return (
                      <li
                        key={t.team_name}
                        role="option"
                        aria-selected={selected}
                        onClick={() => { setEditTeamName(t.team_name); setTeamDropdownOpen(false); }}
                        onMouseEnter={() => setTeamHoverKey(t.team_name)}
                        onMouseLeave={() => setTeamHoverKey(null)}
                        style={{
                          padding: '10px 12px',
                          cursor: 'pointer',
                          fontSize: '14px',
                          borderBottom: '1px solid #f3f4f6',
                          background: selected || hovered ? '#dbeafe' : undefined,
                        }}
                      >
                        {t.team_name}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <div style={{ marginBottom: '24px', position: 'relative' }}>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: 500, color: '#374151', marginBottom: '8px' }}>
                Assign Team Lead
              </label>
              <div
                role="combobox"
                aria-expanded={assignLeadDropdownOpen}
                aria-haspopup="listbox"
                aria-label="Assign Team Lead"
                tabIndex={0}
                onClick={() => { setAssignLeadDropdownOpen((v) => !v); setTeamDropdownOpen(false); }}
                onKeyDown={(e) => { if (e.key === 'Escape') setAssignLeadDropdownOpen(false); if (e.key === 'Enter' || e.key === ' ') e.preventDefault(); }}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  fontSize: '14px',
                  backgroundColor: 'white',
                  color: '#111827',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span>{editTeamName ? (teams.find((t) => t.team_name === editTeamName)?.lead || teams.find((t) => t.team_name === editTeamName)?.team_name) ?? '—' : '—'}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, transform: assignLeadDropdownOpen ? 'rotate(180deg)' : 'none' }}>
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
              {assignLeadDropdownOpen && (
                <ul
                  role="listbox"
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    margin: 0,
                    marginTop: '4px',
                    padding: 0,
                    listStyle: 'none',
                    background: 'white',
                    border: '1px solid #D1D5DB',
                    borderRadius: '8px',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                    maxHeight: '220px',
                    overflowY: 'auto',
                    zIndex: 10002,
                  }}
                >
                  <li
                    role="option"
                    aria-selected={!editTeamName}
                    onClick={() => { setEditTeamName(''); setAssignLeadDropdownOpen(false); }}
                    onMouseEnter={() => setAssignLeadHoverKey('')}
                    onMouseLeave={() => setAssignLeadHoverKey(null)}
                    style={{
                      padding: '10px 12px',
                      cursor: 'pointer',
                      fontSize: '14px',
                      borderBottom: '1px solid #f3f4f6',
                      background: (assignLeadHoverKey === '' || !editTeamName) ? '#dbeafe' : undefined,
                    }}
                  >
                    —
                  </li>
                  {teams.map((t) => {
                    const selected = editTeamName === t.team_name;
                    const hovered = assignLeadHoverKey === t.team_name;
                    return (
                      <li
                        key={t.team_name}
                        role="option"
                        aria-selected={selected}
                        onClick={() => { setEditTeamName(t.team_name); setAssignLeadDropdownOpen(false); }}
                        onMouseEnter={() => setAssignLeadHoverKey(t.team_name)}
                        onMouseLeave={() => setAssignLeadHoverKey(null)}
                        style={{
                          padding: '10px 12px',
                          cursor: 'pointer',
                          fontSize: '14px',
                          borderBottom: '1px solid #f3f4f6',
                          background: selected || hovered ? '#dbeafe' : undefined,
                        }}
                      >
                        {t.lead || t.team_name}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            {saveError && (
              <div style={{
                padding: '12px',
                backgroundColor: '#FEE2E2',
                border: '1px solid #FECACA',
                borderRadius: '8px',
                color: '#DC2626',
                fontSize: '14px',
                marginBottom: '20px',
              }}>
                {saveError}
              </div>
            )}
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={closeEditModal}
                style={{
                  padding: '12px 20px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  background: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveProfile}
                disabled={saving}
                style={{
                  padding: '12px 20px',
                  border: 'none',
                  borderRadius: '8px',
                  background: saving ? '#9CA3AF' : '#3B82F6',
                  color: 'white',
                  cursor: saving ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {confirmAction && typeof document !== 'undefined' && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '20px',
            overflow: 'auto',
          }}
          onClick={() => setConfirmAction(null)}
        >
          <div
            style={{
              backgroundColor: 'white',
              borderRadius: '12px',
              padding: '32px',
              maxWidth: '420px',
              width: '100%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
              position: 'relative',
              margin: 'auto',
              zIndex: 10001,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <p style={{ fontSize: '14px', color: '#374151', marginBottom: '24px' }}>
              {confirmAction.action === 'deactivate' && 'Deactivate this user? They will be marked inactive.'}
              {confirmAction.action === 'activate' && 'Activate this user?'}
              {confirmAction.action === 'remove' && 'Remove this user? They will be deactivated.'}
            </p>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => setConfirmAction(null)}
                style={{
                  padding: '12px 20px',
                  border: '1px solid #D1D5DB',
                  borderRadius: '8px',
                  background: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  color: '#374151',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (confirmAction.action === 'deactivate') {
                    handleDeactivate(confirmAction.email);
                  } else if (confirmAction.action === 'remove') {
                    handleRemove(confirmAction.email);
                  } else {
                    handleActivate(confirmAction.email);
                  }
                }}
                style={{
                  padding: '12px 20px',
                  border: 'none',
                  borderRadius: '8px',
                  background: confirmAction.action === 'activate' ? '#059669' : '#b91c1c',
                  color: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                }}
              >
                {confirmAction.action === 'activate' ? 'Activate' : confirmAction.action === 'remove' ? 'Remove' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
