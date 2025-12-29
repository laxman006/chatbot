'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '@/lib/api';
import { getCurrentUser } from '@/lib/session-utils';
import { isAdminEmail, ADMIN_EMAILS } from '@/constants/admins';
import { User } from '@/types/chat';
import DateRangeFilterDropdown, { DateRange } from '@/components/DateRangeFilterDropdown';
import DeveloperExclusionFilterDropdown from '@/components/DeveloperExclusionFilterDropdown';
import {
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell
} from 'recharts';

type TeamStat = {
  team_name: string;
  lead: string | null;
  lead_email: string | null;
  color: string;
  description: string;
  total_messages: number;
  active_members_count: number;
  member_count: number;
};

type TeamsStatsResponse = {
  teams: TeamStat[];
  total_teams: number;
  generated_at: string;
  filters_applied?: {
    excluded_users_count?: number;
  };
  data_source?: string;
};

const COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#6366f1', '#ef4444', '#14b8a6', '#f97316', '#06b6d4'];

export default function TeamsDashboardPage() {
  const router = useRouter();
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [teamStats, setTeamStats] = useState<TeamStat[]>([]);
  const [totalTeams, setTotalTeams] = useState<number>(0);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  
  // Filter states
  const [dateRange, setDateRange] = useState<DateRange>({ startDate: null, endDate: null });
  const [excludedUsers, setExcludedUsers] = useState<string[]>([]);

  // Verify admin access on mount
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

  const fetchTeamStats = useCallback(async (user: User, startDate?: string | null, endDate?: string | null, excludeUsers?: string[]) => {
    setFetching(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (startDate) {
        // Extract YYYY-MM-DD format from ISO string if needed
        const dateOnly = startDate.includes('T') ? startDate.split('T')[0] : startDate;
        params.append('from_date', dateOnly);
      }
      if (endDate) {
        // Extract YYYY-MM-DD format from ISO string if needed
        const dateOnly = endDate.includes('T') ? endDate.split('T')[0] : endDate;
        params.append('to_date', dateOnly);
      }
      if (excludeUsers && excludeUsers.length > 0) {
        params.append('exclude_users', excludeUsers.join(','));
      }
      
      const url = `/admin/teams/summary${params.toString() ? `?${params.toString()}` : ''}`;
      console.log('[TEAMS DASHBOARD] Fetching from:', url);
      
      const response = await apiFetch(url, {
        method: 'GET'
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error((payload as any).detail || (payload as any).error || 'Failed to load team statistics');
      }

      const statsResponse = payload as TeamsStatsResponse;
      console.log('[TEAMS DASHBOARD] Response:', {
        total_teams: statsResponse.total_teams,
        teams_count: (statsResponse.teams || []).length
      });
      
      setTeamStats(statsResponse.teams || []);
      setTotalTeams(statsResponse.total_teams || 0);
      setGeneratedAt(statsResponse.generated_at || null);
      
      if ((statsResponse.teams || []).length === 0) {
        console.warn('[TEAMS DASHBOARD] No teams found. Check if user_activity collection has team_name data.');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setFetching(false);
    }
  }, []);

  // Fetch data when filters change (with debouncing)
  useEffect(() => {
    if (!authUser) return;
    
    // Debounce API calls to prevent excessive requests when filters change rapidly
    const timeout = setTimeout(() => {
      fetchTeamStats(
        authUser, 
        dateRange.startDate || undefined, 
        dateRange.endDate || undefined, 
        excludedUsers.length > 0 ? excludedUsers : undefined
      );
    }, 300); // 300ms debounce delay

    // Cleanup: cancel timeout if filters change again before delay completes
    return () => clearTimeout(timeout);
  }, [
    authUser,
    dateRange.startDate,
    dateRange.endDate,
    excludedUsers.join(','), // Use join for proper array comparison
    fetchTeamStats
  ]);

  // Format local time
  const formatLocalTime = useCallback((utcTime: string | null) => {
    if (!utcTime) return '—';
    try {
      const date = new Date(utcTime);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (error) {
      console.error('[TEAMS DASHBOARD] Error formatting date:', utcTime, error);
      return utcTime;
    }
  }, []);

  const formatLocalDate = useCallback((utcTime: string | null) => {
    if (!utcTime) return '—';
    try {
      const date = new Date(utcTime);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    } catch (error) {
      console.error('[TEAMS DASHBOARD] Error formatting date:', utcTime, error);
      return utcTime;
    }
  }, []);

  // Top 5 teams
  const top5Teams = useMemo(() => {
    return teamStats.slice(0, 5);
  }, [teamStats]);

  // Pie chart data
  const pieChartData = useMemo(() => {
    const top5 = teamStats.slice(0, 5);
    const total = top5.reduce((sum, team) => sum + team.total_messages, 0);
    return top5.map(team => ({
      name: team.team_name,
      value: team.total_messages,
      percentage: total > 0 ? ((team.total_messages / total) * 100).toFixed(1) : '0'
    }));
  }, [teamStats]);

  // Bar chart data
  const messagesBarData = useMemo(() => {
    return teamStats.slice(0, 10).map(team => ({
      name: team.team_name.length > 15 ? team.team_name.substring(0, 15) + '...' : team.team_name,
      messages: team.total_messages,
      activeMembers: team.active_members_count
    }));
  }, [teamStats]);

  if (loading) {
    return (
      <div style={{ padding: '32px', textAlign: 'center' }}>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px', maxWidth: '1600px', margin: '0 auto', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ marginBottom: '24px' }}>
        {/* Header with title and filters */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
          paddingBottom: '16px',
          borderBottom: '1px solid #e1e5e9'
        }}>
          <div>
            <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '6px', color: '#323130' }}>Team Leaderboard</h1>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <DateRangeFilterDropdown onFilterChange={setDateRange} />
            <DeveloperExclusionFilterDropdown onExclusionChange={setExcludedUsers} />
            <button
              onClick={() => router.push('/admin/top-questions')}
              style={{
                padding: '8px 16px',
                borderRadius: '4px',
                border: '1px solid #c8c6c4',
                background: '#ffffff',
                cursor: 'pointer',
                color: '#323130',
                fontWeight: 500,
                fontSize: '14px',
                transition: 'all 0.15s',
                fontFamily: 'inherit'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = '#8a8886';
                e.currentTarget.style.backgroundColor = '#faf9f8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = '#c8c6c4';
                e.currentTarget.style.backgroundColor = '#ffffff';
              }}
            >
              Top Questions
            </button>
            <button
              onClick={() => router.push('/chat/new')}
              style={{
                padding: '8px 16px',
                borderRadius: '4px',
                border: '1px solid #c8c6c4',
                background: '#ffffff',
                cursor: 'pointer',
                color: '#323130',
                fontWeight: 500,
                fontSize: '14px',
                transition: 'all 0.15s',
                fontFamily: 'inherit'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = '#8a8886';
                e.currentTarget.style.backgroundColor = '#faf9f8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = '#c8c6c4';
                e.currentTarget.style.backgroundColor = '#ffffff';
              }}
            >
              Back to chats
            </button>
          </div>
        </div>
      </div>

      {generatedAt && (
        <div style={{ marginBottom: '12px', color: '#6b7280', fontSize: '13px' }}>
          Last updated: <strong style={{ color: '#111827' }}>{formatLocalDate(generatedAt)}</strong>
          {' • '}
          Total teams: <strong style={{ color: '#111827' }}>{totalTeams}</strong>
          {dateRange.startDate || dateRange.endDate ? (
            <>
              {' • '}
              <span style={{ color: '#059669', fontWeight: 500 }}>
                Date Range: {dateRange.startDate ? formatLocalTime(dateRange.startDate).split(',')[0] : 'All'} - {dateRange.endDate ? formatLocalTime(dateRange.endDate).split(',')[0] : 'All'}
              </span>
            </>
          ) : (
            <>
              {' • '}
              <span style={{ color: '#059669', fontWeight: 500 }}>All-Time Statistics (MongoDB)</span>
            </>
          )}
        </div>
      )}

      {error && (
        <div style={{ background: '#fef2f2', color: '#b91c1c', padding: '12px 14px', borderRadius: '10px', marginBottom: '12px', border: '1px solid #fecdd3' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {!error && teamStats.length === 0 && !fetching && (
        <div style={{ 
          background: '#f0f9ff', 
          color: '#0369a1', 
          padding: '16px 18px', 
          borderRadius: '10px', 
          marginBottom: '16px', 
          border: '1px solid #bae6fd' 
        }}>
          <div style={{ fontWeight: 600, marginBottom: '8px' }}>No data available</div>
          <div style={{ fontSize: '14px', lineHeight: '1.6' }}>
            {dateRange.startDate || dateRange.endDate ? (
              <>
                <strong>Date-based view:</strong> No messages found for the selected date range. 
                This is normal if the <code>message_events</code> collection is empty (new system).
                <br />
                <strong>Tip:</strong> Try switching to <strong>"All Time"</strong> to see data from the <code>user_activity</code> collection,
                or ensure messages are being logged to <code>message_events</code>.
              </>
            ) : (
              <>
                <strong>All-time view:</strong> No teams found in the <code>user_activity</code> collection.
                <br />
                <strong>Tip:</strong> Ensure users have completed the onboarding process and selected their team.
                Also, send some messages to populate user activity.
              </>
            )}
          </div>
        </div>
      )}

      {/* Top 5 Teams Section */}
      {top5Teams.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '16px', color: '#111827' }}>
            Top 5 Teams
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            {top5Teams.map((team, idx) => (
              <div
                key={team.team_name}
                style={{
                  padding: '20px',
                  background: idx === 0 
                    ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                    : idx === 1 
                    ? 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
                    : idx === 2 
                    ? 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)'
                    : idx === 3 
                    ? 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)'
                    : idx === 4 
                    ? 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'
                    : '#f9fafb',
                  borderRadius: '12px',
                  border: '1px solid #e5e7eb',
                  color: idx < 5 ? 'white' : '#111827',
                  textAlign: 'center'
                }}
              >
                <div style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>
                  #{idx + 1}
                </div>
                <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                  {team.team_name}
                </div>
                <div style={{ fontSize: '12px', opacity: 0.9, marginBottom: '12px' }}>
                  {team.description || team.team_name}
                </div>
                <div style={{ fontSize: '14px', marginBottom: '4px' }}>
                  <strong>{team.total_messages.toLocaleString()}</strong> messages
                </div>
                <div style={{ fontSize: '14px' }}>
                  <strong>{team.active_members_count}</strong> active members
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Charts Section */}
      {teamStats.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '16px', color: '#111827' }}>
            Visualizations
          </h2>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '24px', marginBottom: '24px' }}>
            {/* Pie Chart */}
            {pieChartData.length > 0 && (
              <div style={{ padding: '20px', background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: '#111827' }}>
                  Message Distribution (Top 5)
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={pieChartData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percentage }) => {
                        return `${name}: ${percentage}%`;
                      }}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {pieChartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Messages Bar Chart */}
            {messagesBarData.length > 0 && (
              <div style={{ padding: '20px', background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: '#111827' }}>
                  Top Teams by Messages
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={messagesBarData}>
                    <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={12} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="messages" fill="#3b82f6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Teams Table */}
      <div style={{
        background: 'white',
        borderRadius: '12px',
        border: '1px solid #e5e7eb',
        overflow: 'hidden'
      }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '0.5fr 2fr 1.5fr 1fr 1fr 1.5fr',
          padding: '12px 14px',
          background: '#f9fafb',
          borderBottom: '2px solid #e5e7eb',
          fontWeight: 600,
          color: '#374151',
          fontSize: '13px',
          gap: '12px',
          alignItems: 'center'
        }}>
          <div>Rank</div>
          <div>Team Name</div>
          <div>Lead</div>
          <div style={{ textAlign: 'right' }}>Messages</div>
          <div style={{ textAlign: 'right' }}>Active Members</div>
          <div style={{ textAlign: 'right' }}>Total Members</div>
        </div>

        {teamStats.length === 0 ? (
          <div style={{ padding: '16px', color: '#6b7280' }}>No data available.</div>
        ) : (
          teamStats.map((team, idx) => (
            <div
              key={team.team_name || idx}
              style={{
                display: 'grid',
                gridTemplateColumns: '0.5fr 2fr 1.5fr 1fr 1fr 1.5fr',
                padding: '12px 14px',
                borderTop: '1px solid #e5e7eb',
                background: idx % 2 === 0 ? 'white' : '#f9fafb',
                gap: '12px',
                alignItems: 'center'
              }}
            >
              <div style={{ color: '#111827', fontWeight: 700 }}>
                {idx + 1}
              </div>
              <div style={{ color: '#111827', fontWeight: 600 }}>
                {team.team_name || '—'}
              </div>
              <div style={{ color: '#6b7280', fontSize: '13px' }}>
                {team.lead || '—'}
              </div>
              <div style={{ color: '#111827', textAlign: 'right', fontWeight: 600 }}>
                {team.total_messages?.toLocaleString() || '0'}
              </div>
              <div style={{ color: '#111827', textAlign: 'right' }}>
                {team.active_members_count?.toLocaleString() || '0'}
              </div>
              <div style={{ color: '#6b7280', fontSize: '13px', textAlign: 'right' }}>
                {team.member_count?.toLocaleString() || '0'}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

