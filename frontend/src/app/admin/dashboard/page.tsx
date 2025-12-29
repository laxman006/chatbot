


'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { getApiBase, apiFetch } from '@/lib/api';
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

type UserStat = {
  user_id: string;
  user_email: string;
  user_name: string;
  total_messages: number;
  total_sessions?: number; // All-time sessions (from user_activity)
  sessions?: number; // Date-based sessions (from message_events aggregation)
  avg_messages_per_session?: number; // Optional - only available for all-time stats
  last_active?: string;
};

type UserStatsResponse = {
  users: UserStat[];
  total_users: number;
  generated_at: string;
  filters_applied?: {
    start_date?: string;
    end_date?: string;
    excluded_users_count?: number;
  };
  data_source?: string;
  time_range?: string;
};

type RankersResponse = {
  rankers: UserStat[];
  total_rankers: number;
  generated_at: string;
  filters_applied?: {
    from_date?: string;
    to_date?: string;
    excluded_users_count?: number;
  };
  data_source?: string;
  time_range?: string;
};

const COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#6366f1', '#ef4444', '#14b8a6', '#f97316', '#06b6d4'];

export default function AdminDashboardPage() {
  const router = useRouter();
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [userStats, setUserStats] = useState<UserStat[]>([]);
  const [totalUsers, setTotalUsers] = useState<number>(0);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  
  // Filter states
  const [dateRange, setDateRange] = useState<DateRange>({ startDate: null, endDate: null });
  const [excludedUsers, setExcludedUsers] = useState<string[]>([]); // Default: no exclusions (opt-in)

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

  const fetchUserStats = useCallback(async (user: User, startDate?: string | null, endDate?: string | null, excludeUsers?: string[]) => {
    setFetching(true);
    setError(null);

    try {
      let url: string;
      let payload: UserStatsResponse | RankersResponse;

      // Determine which API to use based on date filter
      if (!startDate && !endDate) {
        // All-time stats: use /admin/users/summary
        const params = new URLSearchParams();
        if (excludeUsers && excludeUsers.length > 0) {
          params.append('exclude_users', excludeUsers.join(','));
          console.log('[DASHBOARD] Excluding users (all-time):', excludeUsers);
        } else {
          console.log('[DASHBOARD] No exclusions (all-time)');
        }
        url = `/admin/users/summary${params.toString() ? `?${params.toString()}` : ''}`;
        console.log('[DASHBOARD] Fetching all-time stats from:', url);
        
        const response = await apiFetch(url, {
          method: 'GET',
        });

        payload = await response.json();

        if (!response.ok) {
          throw new Error((payload as any).detail || (payload as any).error || 'Failed to load user statistics');
        }

        // Transform response to match UserStatsResponse format
        const statsResponse = payload as UserStatsResponse;
        console.log('[DASHBOARD] All-time stats response:', {
          total_users: statsResponse.total_users,
          users_count: (statsResponse.users || []).length,
          user_emails: (statsResponse.users || []).map(u => u.user_email)
        });
        
        setUserStats(statsResponse.users || []);
        setTotalUsers(statsResponse.total_users || 0);
        setGeneratedAt(statsResponse.generated_at || null);
        
        // Show helpful message if no data
        if ((statsResponse.users || []).length === 0) {
          console.warn('[DASHBOARD] No users found. Check if user_activity collection has data.');
        }
      } else {
        // Date-based rankers: use /admin/rankers
        const params = new URLSearchParams();
        if (startDate) params.append('from_date', startDate);
        if (endDate) params.append('to_date', endDate);
        if (excludeUsers && excludeUsers.length > 0) {
          params.append('exclude_users', excludeUsers.join(','));
          console.log('[DASHBOARD] Excluding users (date-based):', excludeUsers);
        } else {
          console.log('[DASHBOARD] No exclusions (date-based)');
        }
        params.append('limit', '100'); // Get top 100 rankers
        
        url = `/admin/rankers?${params.toString()}`;
        
        console.log('[DASHBOARD] Fetching rankers from:', url);
        
        const response = await apiFetch(url, {
          method: 'GET',
        });

        payload = await response.json();

        if (!response.ok) {
          throw new Error((payload as any).detail || (payload as any).error || 'Failed to load rankers');
        }

        // Transform rankers response to match UserStat format
        const rankersResponse = payload as RankersResponse;
        console.log('[DASHBOARD] Rankers response:', {
          total_rankers: rankersResponse.total_rankers,
          rankers_count: (rankersResponse.rankers || []).length,
          ranker_emails: (rankersResponse.rankers || []).map(r => r.user_email),
          excluded_count: rankersResponse.filters_applied?.excluded_users_count || 0
        });
        
        setUserStats(rankersResponse.rankers || []);
        setTotalUsers(rankersResponse.total_rankers || 0);
        setGeneratedAt(rankersResponse.generated_at || null);
        
        // Show helpful message if no data
        if ((rankersResponse.rankers || []).length === 0) {
          console.warn('[DASHBOARD] No rankers found for date range. This is normal if message_events collection is empty.');
        }
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setFetching(false);
    }
  }, []);

  // ✅ Fetch data automatically when filters change (with debouncing)
  // FIX: Removed manual refresh button - filters now trigger automatic refresh
  useEffect(() => {
    if (!authUser) return;
    
    // DEBUG: Log exclusion changes
    console.log('[DASHBOARD] Filters changed, will fetch data:', {
      startDate: dateRange.startDate,
      endDate: dateRange.endDate,
      excludedUsers: excludedUsers,
      excludedCount: excludedUsers.length
    });
    
    // Debounce API calls to prevent excessive requests when filters change rapidly
    const timeout = setTimeout(() => {
      fetchUserStats(authUser, dateRange.startDate || undefined, dateRange.endDate || undefined, excludedUsers);
    }, 300); // 300ms debounce delay

    // Cleanup: cancel timeout if filters change again before delay completes
    return () => clearTimeout(timeout);
  }, [
    authUser,
    dateRange.startDate,
    dateRange.endDate,
    excludedUsers.join(','), // Use join for proper array comparison
    fetchUserStats
  ]);

  // ✅ SINGLE SOURCE OF TRUTH: formatLocalTime helper (used everywhere)
  // FIX: Properly format Last Active timestamps from UTC to IST
  const formatLocalTime = (utcTime?: string) => {
    if (!utcTime) return '—';
    try {
      const date = new Date(utcTime);
      // Validate date
      if (isNaN(date.getTime())) {
        console.warn('[DASHBOARD] Invalid date:', utcTime);
        return '—';
      }
      // CRITICAL FIX: Explicitly convert UTC to IST (Asia/Kolkata)
      // Backend stores everything in UTC, but UI should display in local timezone
      return date.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata', // Explicitly set to IST
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true, // Use 12-hour format (am/pm)
        timeZoneName: 'short' // Shows timezone abbreviation (IST)
      });
    } catch (error) {
      console.error('[DASHBOARD] Error formatting date:', utcTime, error);
      return '—';
    }
  };

  // Format date only (without time) for "Last updated" display
  const formatLocalDate = (utcTime?: string) => {
    if (!utcTime) return '—';
    try {
      const date = new Date(utcTime);
      // Validate date
      if (isNaN(date.getTime())) {
        console.warn('[DASHBOARD] Invalid date:', utcTime);
        return '—';
      }
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    } catch (error) {
      console.error('[DASHBOARD] Error formatting date:', utcTime, error);
      return '—';
    }
  };

  // ✅ SINGLE SOURCE OF TRUTH: All derived data from userStats using useMemo
  // Top 5 rankers (for cards)
  const top5Rankers = useMemo(() => {
    return userStats.slice(0, 5);
  }, [userStats]);

  // Top 10 users (for charts)
  const top10Users = useMemo(() => {
    return userStats.slice(0, 10);
  }, [userStats]);

  // ✅ Pie chart data (derived, always fresh, shows percentages)
  // FIX: Use decimals instead of rounding to ensure percentages sum to exactly 100%
  const pieChartData = useMemo(() => {
    if (!top10Users.length) return [];

    const total = top10Users.reduce(
      (sum, user) => sum + user.total_messages,
      0
    );

    if (total === 0) return [];

    return top10Users.map(user => ({
      name: user.user_name || user.user_email.split('@')[0],
      value: user.total_messages,
      percentage: (user.total_messages / total) * 100 // Use decimal, not rounded
    }));
  }, [top10Users]);

  // ✅ Messages bar chart data (derived, always fresh)
  const messagesBarData = useMemo(() => {
    return top10Users.map(user => ({
      name: user.user_name || user.user_email.split('@')[0],
      messages: user.total_messages
    }));
  }, [top10Users]);

  // ✅ Sessions bar chart data (derived, always fresh)
  // FIX: Sessions available for both all-time (total_sessions) and date-based (sessions) views
  const hasSessionData = useMemo(() => {
    if (userStats.length === 0) return false;
    // Check if any user has session data (either total_sessions for all-time or sessions for date-based)
    return userStats.some(user => 
      user.total_sessions !== undefined || user.sessions !== undefined
    );
  }, [userStats]);
  
  // Helper: Get session count for a user (handles both all-time and date-based)
  const getSessionCount = useCallback((user: UserStat): number => {
    // For date-based views, use 'sessions' field
    // For all-time views, use 'total_sessions' field
    return user.sessions !== undefined ? user.sessions : (user.total_sessions || 0);
  }, []);
  
  // Helper: Calculate avg messages per session
  const getAvgMessagesPerSession = useCallback((user: UserStat): number => {
    const sessions = getSessionCount(user);
    if (sessions === 0) return 0;
    return user.total_messages / sessions;
  }, [getSessionCount]);

  const sessionsBarData = useMemo(() => {
    if (!hasSessionData) return [];
    return top10Users.map(user => ({
      name: user.user_name || user.user_email.split('@')[0],
      sessions: getSessionCount(user)
    }));
  }, [top10Users, hasSessionData, getSessionCount]);

  if (loading) {
    return (
      <div style={{ padding: '40px', fontFamily: 'Inter, system-ui, sans-serif' }}>
        <p style={{ color: '#6b7280' }}>Checking admin access...</p>
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
            <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '6px', color: '#323130' }}>User Leaderboard</h1>
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
            {/* Refresh button removed - data refreshes automatically when filters change */}
          </div>
        </div>
      </div>

      {generatedAt && (
        <div style={{ marginBottom: '12px', color: '#6b7280', fontSize: '13px' }}>
          Last updated: <strong style={{ color: '#111827' }}>{formatLocalDate(generatedAt)}</strong>
          {' • '}
          Total users: <strong style={{ color: '#111827' }}>{totalUsers}</strong>
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
              <span style={{ color: '#059669', fontWeight: 500 }}>All-Time Statistics</span>
            </>
          )}
        </div>
      )}

      {error && (
        <div style={{ background: '#fef2f2', color: '#b91c1c', padding: '12px 14px', borderRadius: '10px', marginBottom: '12px', border: '1px solid #fecdd3' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Helpful message when no data */}
      {!error && userStats.length === 0 && !fetching && (
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
                or send some messages first to populate event tracking.
              </>
            ) : (
              <>
                <strong>All-time view:</strong> No users found in the <code>user_activity</code> collection.
                <br />
                <strong>Tip:</strong> If you have existing chat data, you may need to run the migration endpoint: 
                <code style={{ background: '#e0f2fe', padding: '2px 6px', borderRadius: '4px', marginLeft: '4px' }}>
                  POST /admin/user-stats/migrate
                </code>
              </>
            )}
          </div>
        </div>
      )}

      {/* Top 5 Rankers Section */}
      {top5Rankers.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '16px', color: '#111827' }}>
            Top 5 Rankers
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            {top5Rankers.map((user, idx) => (
              <div
                key={user.user_id}
                style={{
                  padding: '20px',
                  background: idx === 0 
                    ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'  // #1: Purple
                    : idx === 1 
                    ? 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'  // #2: Pink
                    : idx === 2 
                    ? 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)'  // #3: Blue
                    : idx === 3 
                    ? 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)'  // #4: Green
                    : idx === 4 
                    ? 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'  // #5: Orange-Yellow
                    : '#f9fafb',  // Fallback for any beyond top 5
                  borderRadius: '12px',
                  border: '1px solid #e5e7eb',
                  color: idx < 5 ? 'white' : '#111827',  // White text for all top 5 rankers with gradients
                  textAlign: 'center'
                }}
              >
                <div style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>
                  #{idx + 1}
                </div>
                <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                  {user.user_name || user.user_email.split('@')[0]}
                </div>
                <div style={{ fontSize: '12px', opacity: 0.9, marginBottom: '12px' }}>
                  {user.user_email}
                </div>
                <div style={{ fontSize: '14px', marginBottom: '4px' }}>
                  <strong>{user.total_messages.toLocaleString()}</strong> messages
                </div>
                {(user.total_sessions !== undefined || user.sessions !== undefined) && (
                  <div style={{ fontSize: '14px' }}>
                    <strong>{getSessionCount(user).toLocaleString()}</strong> sessions
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Charts Section */}
      {userStats.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '16px', color: '#111827' }}>
            Visualizations
          </h2>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '24px', marginBottom: '24px' }}>
            {/* Pie Chart */}
            {pieChartData.length > 0 && (
              <div style={{ padding: '20px', background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: '#111827' }}>
                  Message Distribution (Top 10)
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={pieChartData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => {
                        // Format to 1 decimal place for accuracy (ensures sum = 100%)
                        const percentage = (percent * 100).toFixed(1);
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
                  Top Users by Messages
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

          {/* Sessions Bar Chart - Only shown for all-time stats */}
          {hasSessionData && sessionsBarData.length > 0 && (
            <div style={{ padding: '20px', background: 'white', borderRadius: '12px', border: '1px solid #e5e7eb' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: '#111827' }}>
                Top Users by Sessions
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={sessionsBarData}>
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={12} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="sessions" fill="#8b5cf6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Full User List Table */}
      <div
        style={{
          border: '1px solid #e5e7eb',
          borderRadius: '12px',
          overflow: 'hidden'
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: hasSessionData 
              ? '0.5fr 2fr 2fr 1fr 1fr 1.2fr 1.5fr'
              : '0.5fr 2fr 2fr 1fr 1.5fr',
            background: '#f9fafb',
            padding: '12px 14px',
            fontWeight: 700,
            color: '#111827',
            fontSize: '14px',
            gap: '12px',
            alignItems: 'center'
          }}
        >
          <div>Rank</div>
          <div>User Name</div>
          <div>Email</div>
          <div style={{ textAlign: 'right' }}>Messages</div>
          {hasSessionData && (
            <>
              <div style={{ textAlign: 'right' }}>Sessions</div>
              <div style={{ textAlign: 'right' }}>Avg/Session</div>
            </>
          )}
          <div>Last Active</div>
        </div>

        {userStats.length === 0 ? (
          <div style={{ padding: '16px', color: '#6b7280' }}>No data available.</div>
        ) : (
          userStats.map((user, idx) => (
            <div
              key={user.user_id || idx}
              style={{
                display: 'grid',
                gridTemplateColumns: hasSessionData 
                  ? '0.5fr 2fr 2fr 1fr 1fr 1.2fr 1.5fr'
                  : '0.5fr 2fr 2fr 1fr 1.5fr',
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
                {user.user_name || '—'}
              </div>
              <div style={{ color: '#6b7280', fontSize: '13px' }}>
                {user.user_email || '—'}
              </div>
              <div style={{ color: '#111827', textAlign: 'right', fontWeight: 600 }}>
                {user.total_messages.toLocaleString()}
              </div>
              {hasSessionData && (
                <>
                  <div style={{ color: '#111827', textAlign: 'right' }}>
                    {getSessionCount(user).toLocaleString()}
                  </div>
                  <div style={{ color: '#6b7280', textAlign: 'right' }}>
                    {getAvgMessagesPerSession(user).toFixed(1)}
                  </div>
                </>
              )}
              <div style={{ color: '#6b7280', fontSize: '13px' }}>
                {formatLocalTime(user.last_active)}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
