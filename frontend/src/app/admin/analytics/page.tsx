'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getCurrentUser } from '@/lib/session-utils';
import { getApiBase } from '@/lib/api';
import { isAdminEmail } from '@/constants/admins';
import { colorPalette } from '@/constants/colors';

interface UserAnalytics {
  user_id: string;
  email: string;
  name: string;
  total_questions: number;
  first_question_at: string;
  last_question_at: string;
  top_questions: Array<{ question: string; count: number }>;
}

interface TopQuestion {
  question: string;
  times_asked: number;
}

interface MostActiveUser {
  user_id: string;
  email: string;
  name: string;
  questions_asked: number;
}

interface DashboardSummary {
  total_users: number;
  total_questions: number;
  unique_questions: number;
  average_questions_per_user: number;
}

type TimeFilter = 'today' | 'yesterday' | 'this_week' | 'last_week' | 'last_7_days' | 'this_month' | 'all';

const TIME_FILTERS: { value: TimeFilter; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'this_week', label: 'This Week' },
  { value: 'last_week', label: 'Last Week' },
  { value: 'last_7_days', label: 'Last 7 Days' },
  { value: 'this_month', label: 'This Month' },
  { value: 'all', label: 'All' },
];

type DashboardTab = 'overview' | 'users' | 'questions';
const TAB_OPTIONS: DashboardTab[] = ['overview', 'users', 'questions'];

export default function AdminLangfuseAnalyticsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('today');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [users, setUsers] = useState<UserAnalytics[]>([]);
  const [topQuestions, setTopQuestions] = useState<TopQuestion[]>([]);
  const [mostActiveUsers, setMostActiveUsers] = useState<MostActiveUser[]>([]);
  const [lastFetchTime, setLastFetchTime] = useState<number | null>(null);

  // Check admin access on mount
  useEffect(() => {
    function checkAuth() {
      try {
        const user = getCurrentUser(); // NOT async!
        if (!user || !isAdminEmail(user.email)) {
          router.push('/login');
          return;
        }
      } catch (err) {
        console.error('Auth check failed:', err);
        router.push('/login');
      } finally {
        setLoading(false);
      }
    }
    checkAuth();
  }, [router]);

  // Fetch all analytics data
  const fetchAnalytics = useCallback(
    async (filter: string) => {
      setFetching(true);
      setError(null);

      try {
        const user = getCurrentUser(); // NOT async!
        if (!user) {
          setError('Not authenticated');
          console.error('[Analytics] No user found in localStorage');
          return;
        }

        const apiBase = getApiBase();
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };

        const fetchOptions = {
          headers,
          credentials: 'include' as const,
          signal: AbortSignal.timeout(90000), // 90 second timeout
        };

        // Fetch summary
        const summaryUrl = `${apiBase}/analytics/langfuse/dashboard-summary?time_filter=${filter}`;
        console.log('[Analytics Fetch] Summary URL:', summaryUrl);
        
        const summaryRes = await fetch(summaryUrl, fetchOptions);

        if (summaryRes.ok) {
          const data = await summaryRes.json();
          if (data.status === 'success') {
            setSummary(data.summary);
            setMostActiveUsers(data.most_active_users || []);
            setTopQuestions(data.top_questions || []);
          }
        }

        // Fetch users
        const usersUrl = `${apiBase}/analytics/langfuse/users?time_filter=${filter}`;
        const usersRes = await fetch(usersUrl, fetchOptions);

        if (usersRes.ok) {
          const data = await usersRes.json();
          if (data.status === 'success') {
            setUsers(data.users || []);
          }
        }

        setLastFetchTime(Date.now());
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch analytics';
        setError(message);
        console.error('Analytics fetch error:', err);
      } finally {
        setFetching(false);
      }
    },
    []
  );

  // Handle filter change
  const handleFilterChange = (filter: TimeFilter) => {
    setTimeFilter(filter);
  };

  // Handle apply button click
  const handleApplyClick = () => {
    fetchAnalytics(timeFilter);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', fontSize: '18px' }}>
        Checking access...
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '24px',
        maxWidth: '1400px',
        margin: '0 auto',
        backgroundColor: colorPalette.background.page,
        color: colorPalette.typography.primary,
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: '700', marginBottom: '8px' }}>Langfuse Analytics</h1>
        <p style={{ color: colorPalette.typography.secondary, fontSize: '16px' }}>Track user questions and analytics</p>
      </div>

      {/* Filter Buttons */}
      <div style={{ marginBottom: '24px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        {TIME_FILTERS.map((filter) => {
          const isActive = timeFilter === filter.value;
          return (
            <button
              key={filter.value}
              onClick={() => handleFilterChange(filter.value)}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: isActive
                  ? `2px solid ${colorPalette.dashboard.filterBorder}`
                  : `1px solid ${colorPalette.background.border}`,
                background: isActive ? colorPalette.brand.primary : colorPalette.background.panel,
                color: isActive ? colorPalette.dashboard.filterActiveText : colorPalette.dashboard.filterInactiveText,
                cursor: 'pointer',
                fontWeight: isActive ? '600' : '500',
                fontSize: '14px',
                transition: 'all 0.2s ease',
              }}
            >
              {filter.label}
            </button>
          );
        })}

        {/* Apply Button */}
        <button
          onClick={handleApplyClick}
          disabled={fetching}
          style={{
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            background: fetching ? colorPalette.dashboard.applyDisabled : colorPalette.dashboard.apply,
            color: colorPalette.typography.inverse,
            cursor: fetching ? 'not-allowed' : 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s ease',
            marginLeft: '12px',
          }}
        >
          {fetching ? 'Fetching...' : 'Apply'}
        </button>
      </div>

      {/* Fetch Time */}
      {lastFetchTime && (
        <div style={{ marginBottom: '16px', fontSize: '12px', color: colorPalette.typography.muted }}>
          Last updated: {new Date(lastFetchTime).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'rgba(255,31,31,0.08)',
            border: '1px solid rgba(255,31,31,0.45)',
            borderRadius: '8px',
            color: colorPalette.status.error,
            marginBottom: '24px',
          }}
        >
          Error: {error}
        </div>
      )}

      {/* Loading State */}
      {fetching && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'rgba(63,214,241,0.16)',
            border: `1px solid ${colorPalette.brand.secondary}`,
            borderRadius: '8px',
            color: colorPalette.status.info,
            marginBottom: '24px',
          }}
        >
          Loading analytics...
        </div>
      )}

      {/* Summary Cards */}
      {summary && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
            marginBottom: '32px',
          }}
        >
          {[
            { label: 'Total Users', value: summary.total_users },
            { label: 'Total Questions', value: summary.total_questions },
            { label: 'Unique Questions', value: summary.unique_questions },
            {
              label: 'Avg per User',
              value: summary.average_questions_per_user.toFixed(2),
            },
          ].map((card) => (
            <div
              key={card.label}
              style={{
                padding: '16px',
                border: `1px solid ${colorPalette.background.border}`,
                borderRadius: '8px',
                backgroundColor: colorPalette.background.panel,
              }}
            >
              <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '4px' }}>
                {card.label}
              </div>
              <div style={{ fontSize: '28px', fontWeight: '700' }}>{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', borderBottom: `1px solid ${colorPalette.background.border}` }}>
        {TAB_OPTIONS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '12px 0',
              borderBottom: activeTab === tab ? `2px solid ${colorPalette.brand.primary}` : 'none',
              background: 'none',
              border: 'none',
              color: activeTab === tab ? colorPalette.brand.primary : colorPalette.typography.secondary,
              cursor: 'pointer',
              fontWeight: activeTab === tab ? '600' : '500',
              fontSize: '14px',
            }}
          >
            {tab === 'overview' ? 'Overview' : tab === 'users' ? 'Top Users' : 'Top Questions'}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && mostActiveUsers.length > 0 && (
        <div style={{ border: `1px solid ${colorPalette.background.border}`, borderRadius: '8px', overflow: 'hidden' }}>
          <div
            style={{
              padding: '16px',
              backgroundColor: colorPalette.background.soft,
              borderBottom: `1px solid ${colorPalette.background.border}`,
            }}
          >
            <h2 style={{ fontSize: '18px', fontWeight: '600' }}>Most Active Users</h2>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: colorPalette.background.muted, borderBottom: `1px solid ${colorPalette.background.border}` }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Rank</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Email</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Questions</th>
                </tr>
              </thead>
              <tbody>
                {mostActiveUsers.map((user, idx) => (
                  <tr
                    key={user.user_id}
                    style={{
                      borderBottom: `1px solid ${colorPalette.background.border}`,
                      backgroundColor: idx % 2 === 0 ? colorPalette.background.panel : colorPalette.background.soft,
                    }}
                  >
                    <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: '500' }}>{idx + 1}</td>
                    <td style={{ padding: '12px 16px', fontSize: '14px' }}>{user.email}</td>
                    <td
                      style={{
                        padding: '12px 16px',
                        fontSize: '14px',
                        textAlign: 'center',
                        fontWeight: '600',
                      }}
                    >
                      {user.questions_asked}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Users Tab */}
      {activeTab === 'users' && users.length > 0 && (
        <div style={{ border: `1px solid ${colorPalette.background.border}`, borderRadius: '8px', overflow: 'hidden' }}>
          <div
            style={{
              padding: '16px',
              backgroundColor: colorPalette.background.soft,
              borderBottom: `1px solid ${colorPalette.background.border}`,
            }}
          >
            <h2 style={{ fontSize: '18px', fontWeight: '600' }}>All Users</h2>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: colorPalette.background.muted, borderBottom: `1px solid ${colorPalette.background.border}` }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Email</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Questions</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Last Asked</th>
                </tr>
              </thead>
              <tbody>
                {users.slice(0, 20).map((user, idx) => (
                  <tr
                    key={user.user_id}
                    style={{
                      borderBottom: `1px solid ${colorPalette.background.border}`,
                      backgroundColor: idx % 2 === 0 ? colorPalette.background.panel : colorPalette.background.soft,
                    }}
                  >
                    <td style={{ padding: '12px 16px', fontSize: '14px' }}>{user.email}</td>
                    <td
                      style={{
                        padding: '12px 16px',
                        fontSize: '14px',
                        textAlign: 'center',
                        fontWeight: '500',
                      }}
                    >
                      {user.total_questions}
                    </td>
                    <td style={{ padding: '12px 16px', fontSize: '14px', color: colorPalette.typography.secondary }}>
                      {new Date(user.last_question_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Questions Tab */}
      {activeTab === 'questions' && topQuestions.length > 0 && (
        <div style={{ border: `1px solid ${colorPalette.background.border}`, borderRadius: '8px', overflow: 'hidden' }}>
          <div
            style={{
              padding: '16px',
              backgroundColor: colorPalette.background.soft,
              borderBottom: `1px solid ${colorPalette.background.border}`,
            }}
          >
            <h2 style={{ fontSize: '18px', fontWeight: '600' }}>Top Questions</h2>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: colorPalette.background.muted, borderBottom: `1px solid ${colorPalette.background.border}` }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Rank</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Question</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Times Asked</th>
                </tr>
              </thead>
              <tbody>
                {topQuestions.map((q, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: `1px solid ${colorPalette.background.border}`,
                      backgroundColor: idx % 2 === 0 ? colorPalette.background.panel : colorPalette.background.soft,
                    }}
                  >
                    <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: '500' }}>{idx + 1}</td>
                    <td style={{ padding: '12px 16px', fontSize: '14px' }}>{q.question.substring(0, 100)}</td>
                    <td
                      style={{
                        padding: '12px 16px',
                        fontSize: '14px',
                        textAlign: 'center',
                        fontWeight: '600',
                      }}
                    >
                      {q.times_asked}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!fetching && !summary && !error && (
        <div style={{ padding: '32px', textAlign: 'center', color: colorPalette.typography.secondary }}>
          No data available for the selected period.
        </div>
      )}
    </div>
  );
}
