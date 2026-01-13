'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getCurrentUser } from '@/lib/session-utils';
import { getApiBase } from '@/lib/api';
import { isAdminEmail } from '@/constants/admins';
import { colorPalette } from '@/constants/colors';

interface TeamStats {
  team_name: string;
  lead: string | null;
  lead_email: string | null;
  member_count: number;
  active_members_count: number;
  color: string;
  total_questions: number;
  unique_questions: number;
  top_questions: Array<{ question: string; count: number }>;
}

interface TeamMember {
  name: string;
  email: string;
  is_lead: boolean;
  total_questions: number;
  top_questions: Array<{ question: string; count: number }>;
}

interface TeamDetails {
  team_name: string;
  lead: string;
  lead_email: string;
  color: string;
  members: TeamMember[];
  total_members: number;
  active_members: number;
  team_total_questions: number;
  team_unique_questions: number;
}

interface AggregatedTopQuestion {
  question: string;
  count: number;
  teams: string[];
}

const PieDonut = ({
  value,
  total,
  color,
  label,
}: {
  value: number;
  total: number;
  color: string;
  label: string;
}) => {
  const radius = 52;
  const strokeWidth = 10;
  const circumference = 2 * Math.PI * radius;
  const normalizedValue = total ? Math.min(100, (value / total) * 100) : 0;

  const dashArray = `${(normalizedValue / 100) * circumference} ${circumference}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
      <svg width="140" height="140">
        <circle
          cx="70"
          cy="70"
          r={radius}
          stroke={colorPalette.background.border}
          strokeWidth={strokeWidth}
          fill="none"
        />
        <circle
          cx="70"
          cy="70"
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={dashArray}
          strokeDashoffset={circumference * 0.25}
          strokeLinecap="round"
          fill="none"
          transform={`rotate(-90 70 70)`}
        />
      </svg>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '18px', fontWeight: '700' }}>{normalizedValue.toFixed(0)}%</div>
        <div style={{ fontSize: '12px', color: colorPalette.typography.muted }}>{label}</div>
      </div>
    </div>
  );
};

export default function TeamsAnalyticsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [teams, setTeams] = useState<TeamStats[]>([]);
  const [selectedTeamDetails, setSelectedTeamDetails] = useState<TeamDetails | null>(null);
  const [showTeamDetails, setShowTeamDetails] = useState<boolean>(false);

  const [selectedFilter, setSelectedFilter] = useState<string>('this_week'); // Filter selected by user
  const [appliedFilter, setAppliedFilter] = useState<string>('this_week'); // Filter actually applied/fetched
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

  // Fetch teams analytics
  const fetchTeamsAnalytics = useCallback(async (filter: string) => {
    try {
      setFetching(true);
      setError(null);

      console.log('[Teams Fetch] Starting fetch with filter:', filter);
      
      const user = getCurrentUser(); // NOT async!
      console.log('[Teams Fetch] Got user:', user?.email);
      
      if (!user) {
        setError('Not authenticated');
        console.error('[Teams Fetch] No user found');
        return;
      }

      const apiBase = getApiBase();
      console.log('[Teams Fetch] API Base:', apiBase);
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      const url = `${apiBase}/analytics/langfuse/teams/summary?time_filter=${filter}`;
      console.log('[Teams Fetch] Attempting to fetch from:', url);
      console.log('[Teams Fetch] Headers:', headers);

      try {
        const controller = new AbortController();
        let timeoutId: NodeJS.Timeout | null = null;
        
        try {
          // Adaptive timeout based on time filter - longer periods need more time
          // Backend optimization should make this faster, but keeping longer timeout as safety net
          const timeoutDuration = filter === 'today' || filter === 'yesterday' 
            ? 90000   // 90 seconds for short periods
            : 120000; // 120 seconds (2 minutes) for longer periods (this_week, last_week, etc.)
          
          timeoutId = setTimeout(() => {
            console.warn(`[Teams Fetch] Request timeout after ${timeoutDuration/1000} seconds, aborting...`);
            controller.abort();
          }, timeoutDuration);

          const response = await fetch(url, {
            method: 'GET',
            headers,
            credentials: 'include',
            signal: controller.signal,
          });

          // Clear timeout on successful response
          if (timeoutId) {
            clearTimeout(timeoutId);
            timeoutId = null;
          }
          
          console.log('[Teams Fetch] Response status:', response.status);

          if (!response.ok) {
            const errorText = await response.text();
            console.error('[Teams Fetch] Error response:', errorText);
            throw new Error(`HTTP ${response.status}: ${errorText.substring(0, 200)}`);
          }

          const contentType = response.headers.get('content-type');
          if (!contentType || !contentType.includes('application/json')) {
            console.error('[Teams Fetch] Invalid content type:', contentType);
            throw new Error(`Invalid response type: ${contentType}`);
          }

          const data = await response.json();
          console.log('[Teams Fetch] Success! Data:', data);
          
          if (!data.teams && !Array.isArray(data)) {
            console.error('[Teams Fetch] Invalid response format:', data);
            throw new Error('Invalid response format from server');
          }
          
          setTeams(data.teams || data || []);
          setLastFetchTime(Date.now());
        } catch (fetchErr: unknown) {
          // Clear timeout in case of error
          if (timeoutId) {
            clearTimeout(timeoutId);
            timeoutId = null;
          }
          
          // Handle AbortError specifically
          const error = fetchErr as Error & { name?: string };
          if (error.name === 'AbortError' || error.message === 'signal is aborted without reason' || error.message?.includes('aborted')) {
            console.error('[Teams Fetch] Request was aborted (timeout or cancelled)');
            throw new Error('Request timed out. The data may be too large. Please try a different time filter or contact support.');
          }
          
          if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            console.error('[Teams Fetch] Network error (CORS or connection issue):', error);
            throw new Error('Failed to connect to server. Check if backend is running and CORS is configured correctly.');
          }
          console.error('[Teams Fetch] Network error:', error);
          throw error;
        }
      } catch (fetchErr) {
        // This catch is for the outer try-catch
        throw fetchErr;
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch team analytics';
      setError(message);
      console.error('Teams analytics fetch error:', err);
    } finally {
      setFetching(false);
    }
  }, []);

  // Fetch team details
  const fetchTeamDetails = useCallback(async (teamName: string) => {
    try {
      const user = getCurrentUser(); // NOT async!
      if (!user) return;

      const apiBase = getApiBase();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

      const response = await fetch(
        `${apiBase}/analytics/langfuse/teams/details/${encodeURIComponent(teamName)}?time_filter=${appliedFilter}`,
        {
          method: 'GET',
          headers,
          credentials: 'include',
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSelectedTeamDetails(data);
        setShowTeamDetails(true);
      }
    } catch (err) {
      console.error('Team details fetch error:', err);
    }
  }, [appliedFilter]);

  // Handle filter selection (doesn't fetch, just updates selection)
  const handleFilterChange = (filter: string) => {
    setSelectedFilter(filter);
  };

  // Handle apply button click (fetches with selected filter)
  const handleApplyFilter = () => {
    setAppliedFilter(selectedFilter);
    fetchTeamsAnalytics(selectedFilter);
  };

  // NO automatic fetching - only fetch when Apply button is clicked

  const totalQuestions = teams.reduce((sum, team) => sum + (team.total_questions || 0), 0);
  const totalUniqueQuestions = teams.reduce((sum, team) => sum + (team.unique_questions || 0), 0);
  const totalMembers = teams.reduce((sum, team) => sum + (team.member_count || 0), 0);
  const totalActiveMembers = teams.reduce((sum, team) => sum + (team.active_members_count || 0), 0);
  const activeTeamsCount = teams.filter((team) => (team.total_questions || 0) > 0).length;
  const averageQuestionsPerTeam = teams.length ? totalQuestions / teams.length : 0;
  const questionCoverage = totalQuestions ? (totalUniqueQuestions / totalQuestions) * 100 : 0;
  const activeMemberRatio = totalMembers
    ? Math.min(100, (totalActiveMembers / totalMembers) * 100)
    : 0;
  const repeatedQuestions = Math.max(0, totalQuestions - totalUniqueQuestions);
  const donutTotalMembers = totalMembers || 1;
  const donutTotalQuestions = totalQuestions || 1;
  const sortedPerformanceTeams = [...teams]
    .sort((a, b) => (b.total_questions || 0) - (a.total_questions || 0))
    .slice(0, 6);
  const maxQuestions = Math.max(1, ...teams.map((team) => team.total_questions || 0));
  const leaderboardTeams = [...teams].sort(
    (a, b) => (b.total_questions || 0) - (a.total_questions || 0)
  );
  const topFiveTeams = leaderboardTeams.slice(0, 5);
  const topFiveTotalQuestions = topFiveTeams.reduce(
    (sum, team) => sum + (team.total_questions || 0),
    0
  );
  const gradientBackgrounds = [
    'linear-gradient(135deg, #1d53ff, #0066ff)',
    'linear-gradient(135deg, #9c47ff, #ff3fdc)',
    'linear-gradient(135deg, #0d8eea, #37c1ff)',
    'linear-gradient(135deg, #16c79a, #4ce6c5)',
    'linear-gradient(135deg, #fe7c00, #ffd55f)',
  ];
  const messageDistribution = topFiveTeams.map((team, index) => ({
    name: team.team_name,
    value: team.total_questions || 0,
    percentage: topFiveTotalQuestions
      ? ((team.total_questions || 0) / topFiveTotalQuestions) * 100
      : 0,
    color: gradientBackgrounds[index % gradientBackgrounds.length],
  }));
  const topFiveBarMax = Math.max(1, ...topFiveTeams.map((team) => team.total_questions || 0));
  const aggregatedTopQuestionMap = new Map<
    string,
    { question: string; count: number; teams: Set<string> }
  >();
  teams.forEach((team) => {
    (team.top_questions || []).forEach(({ question, count }) => {
      const normalized = question.trim();
      if (!normalized) return;
      const existing = aggregatedTopQuestionMap.get(normalized);
      if (existing) {
        existing.count += count;
        existing.teams.add(team.team_name);
        return;
      }

      aggregatedTopQuestionMap.set(normalized, {
        question: normalized,
        count,
        teams: new Set([team.team_name]),
      });
    });
  });
  const aggregatedTopQuestions: AggregatedTopQuestion[] = Array.from(
    aggregatedTopQuestionMap.values()
  )
    .map((item) => ({
      question: item.question,
      count: item.count,
      teams: Array.from(item.teams),
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  const summaryCards = [
    { label: 'Total Questions', value: totalQuestions.toLocaleString() },
    { label: 'Total Teams', value: teams.length },
    { label: 'Active Teams', value: activeTeamsCount },
    {
      label: 'Avg Questions / Team',
      value: averageQuestionsPerTeam ? averageQuestionsPerTeam.toFixed(1) : '0.0',
    },
  ];

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', fontSize: '18px' }}>
        Checking access...
      </div>
    );
  }

  const handleBackClick = () => {
    router.back();
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <button
          onClick={handleBackClick}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            padding: '6px 12px',
            borderRadius: '999px',
            border: `1px solid ${colorPalette.background.border}`,
            backgroundColor: colorPalette.background.panel,
            color: colorPalette.typography.primary,
            fontSize: '14px',
            fontWeight: '600',
            cursor: 'pointer',
            marginBottom: '12px',
            transition: 'all 0.2s ease',
          }}
        >
          ← Back
        </button>
        <h1 style={{ fontSize: '32px', fontWeight: '700', marginBottom: '8px' }}>Team Analytics</h1>
        <p style={{ color: colorPalette.typography.muted, fontSize: '16px' }}>Track team performance and questions</p>
      </div>

      {/* Filter Buttons */}
      <div style={{ marginBottom: '24px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        {['today', 'yesterday', 'this_week', 'last_week', 'last_7_days', 'this_month', 'all'].map((filter) => {
          const isSelected = selectedFilter === filter;
          const isApplied = appliedFilter === filter;
          const getLabel = (f: string) => {
            if (f === 'this_week') return 'This Week';
            if (f === 'last_week') return 'Last Week';
            if (f === 'last_7_days') return 'Last 7 Days';
            if (f === 'this_month') return 'This Month';
            return f.charAt(0).toUpperCase() + f.slice(1);
          };
          return (
            <button
              key={filter}
              onClick={() => handleFilterChange(filter)}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: isSelected ? `2px solid ${colorPalette.brand.primary}` : isApplied ? `2px solid ${colorPalette.status.success}` : `1px solid ${colorPalette.background.border}`,
                background: isSelected ? colorPalette.brand.primary : isApplied ? colorPalette.background.glow : colorPalette.background.panel,
                color: isSelected ? colorPalette.typography.inverse : isApplied ? colorPalette.status.success : colorPalette.dashboard.filterInactiveText,
                cursor: 'pointer',
                fontWeight: isSelected ? '600' : isApplied ? '600' : '500',
                fontSize: '14px',
                transition: 'all 0.2s ease',
              }}
            >
              {getLabel(filter)}
            </button>
          );
        })}
        <button
          onClick={handleApplyFilter}
          disabled={fetching}
          style={{
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            background: fetching ? colorPalette.dashboard.applyDisabled : colorPalette.brand.primary,
            color: colorPalette.typography.inverse,
            cursor: fetching ? 'not-allowed' : 'pointer',
            fontWeight: '600',
            fontSize: '14px',
            transition: 'all 0.2s ease',
            opacity: fetching ? 0.6 : 1,
          }}
        >
          {fetching ? 'Loading...' : 'Apply'}
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
        <div style={{
          padding: '12px 16px',
          backgroundColor: colorPalette.background.glow,
          border: `1px solid ${colorPalette.status.error}`,
          borderRadius: '8px',
          color: colorPalette.status.error,
          marginBottom: '24px'
        }}>
          Error: {error}
        </div>
      )}

      {/* Loading State */}
      {fetching && (
        <div style={{
          padding: '12px 16px',
          backgroundColor: colorPalette.background.glow,
          border: `1px solid ${colorPalette.brand.secondary}`,
          borderRadius: '8px',
          color: colorPalette.brand.primary,
          marginBottom: '24px'
        }}>
          Loading team data...
        </div>
      )}

      {/* Analytics Visuals */}
      {teams.length > 0 ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '32px' }}>
            {summaryCards.map((card) => (
              <div
                key={card.label}
                style={{
                  padding: '18px',
                  borderRadius: '12px',
                  border: `1px solid ${colorPalette.background.border}`,
                  backgroundColor: colorPalette.background.soft,
                  boxShadow: '0 4px 12px rgba(15,23,42,0.04)',
                }}
              >
                <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '6px' }}>{card.label}</div>
                <div style={{ fontSize: '28px', fontWeight: '700' }}>{card.value}</div>
              </div>
            ))}
          </div>

          <section
            style={{
              padding: '24px',
              borderRadius: '16px',
              border: `1px solid ${colorPalette.background.border}`,
              backgroundColor: colorPalette.background.panel,
              marginBottom: '32px',
              boxShadow: '0 10px 25px rgba(15,23,42,0.06)',
              display: 'flex',
              flexDirection: 'column',
              gap: '18px',
            }}
          >
            <div style={{ display: 'flex', gap: '28px', flexWrap: 'wrap', justifyContent: 'center' }}>
              <PieDonut
                value={totalActiveMembers}
                total={donutTotalMembers}
                color={colorPalette.status.success}
                label="Active Member Engagement"
              />
              <PieDonut
                value={totalUniqueQuestions}
                total={donutTotalQuestions}
                color={colorPalette.chart.combos[2]}
                label="Unique Question Share"
              />
            </div>
            <p style={{ margin: 0, fontSize: '14px', color: colorPalette.typography.secondary, textAlign: 'center' }}>
              {repeatedQuestions.toLocaleString()} repeated questions detected across teams ({questionCoverage.toFixed(1)}% unique coverage).
            </p>
          </section>

          <section
            style={{
              padding: '20px',
              borderRadius: '16px',
              border: `1px solid ${colorPalette.background.border}`,
              backgroundColor: colorPalette.background.panel,
              boxShadow: '0 4px 20px rgba(15,23,42,0.05)',
              marginBottom: '32px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700' }}>Team Performance Snapshot</h2>
              <span style={{ fontSize: '12px', color: colorPalette.typography.muted }}>Top {sortedPerformanceTeams.length} teams</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {sortedPerformanceTeams.map((team) => {
                const widthPercent = Math.min(
                  100,
                  Math.max(8, ((team.total_questions || 0) / maxQuestions) * 100)
                );
                return (
                  <div key={team.team_name} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '14px', fontWeight: '600', color: colorPalette.typography.primary }}>
                      <span>{team.team_name}</span>
                      <span>{team.total_questions || 0} Qs</span>
                    </div>
                    <div style={{ height: '10px', borderRadius: '999px', backgroundColor: colorPalette.background.border, overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${widthPercent}%`,
                          height: '100%',
                          borderRadius: '999px',
                          backgroundColor: team.color || colorPalette.brand.primary,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '16px',
              marginBottom: '32px',
            }}
          >
            <div
              style={{
                padding: '20px',
                borderRadius: '16px',
                border: `1px solid ${colorPalette.background.border}`,
                backgroundColor: colorPalette.background.soft,
                minHeight: '160px',
              }}
            >
              <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '6px' }}>Active Members</div>
              <div style={{ fontSize: '24px', fontWeight: '700' }}>
                {totalActiveMembers}/{totalMembers || 1}
              </div>
              <div
                style={{
                  marginTop: '10px',
                  height: '8px',
                  borderRadius: '999px',
                  backgroundColor: colorPalette.background.border,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${activeMemberRatio}%`,
                    height: '100%',
                    borderRadius: '999px',
                    backgroundColor: colorPalette.status.success,
                  }}
                />
              </div>
              <p style={{ marginTop: '8px', fontSize: '12px', color: colorPalette.typography.muted }}>
                {activeMemberRatio.toFixed(0)}% of configured members engaged.
              </p>
            </div>
            <div
              style={{
                padding: '20px',
                borderRadius: '16px',
                border: `1px solid ${colorPalette.background.border}`,
                backgroundColor: colorPalette.background.panel,
                minHeight: '160px',
              }}
            >
              <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '6px' }}>Unique Coverage</div>
              <div style={{ fontSize: '24px', fontWeight: '700' }}>{questionCoverage.toFixed(1)}%</div>
              <div
                style={{
                  marginTop: '10px',
                  height: '8px',
                  borderRadius: '999px',
                  backgroundColor: colorPalette.background.border,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${Math.min(Math.max(questionCoverage, 0), 100)}%`,
                    height: '100%',
                    borderRadius: '999px',
                    backgroundColor: colorPalette.chart.combos[2],
                  }}
                />
              </div>
              <p style={{ marginTop: '8px', fontSize: '12px', color: colorPalette.typography.muted }}>Unique questions vs total volume.</p>
            </div>
            <div
              style={{
                padding: '20px',
                borderRadius: '16px',
                border: `1px solid ${colorPalette.background.border}`,
                backgroundColor: colorPalette.background.soft,
                minHeight: '160px',
              }}
            >
              <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '6px' }}>Avg Questions / Team</div>
              <div style={{ fontSize: '24px', fontWeight: '700' }}>
                {averageQuestionsPerTeam ? averageQuestionsPerTeam.toFixed(1) : '0.0'}
              </div>
              <p style={{ marginTop: '8px', fontSize: '12px', color: colorPalette.typography.muted }}>
                Based on {teams.length} teams and {totalQuestions} questions.
              </p>
            </div>
          </section>

          <section
            style={{
              border: `1px solid ${colorPalette.background.border}`,
              borderRadius: '16px',
              padding: '20px',
              marginBottom: '32px',
              backgroundColor: colorPalette.background.panel,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700' }}>Top Questions Across Teams</h2>
              <span style={{ fontSize: '12px', color: colorPalette.typography.muted }}>
                {aggregatedTopQuestions.length} tracked
              </span>
            </div>
            {aggregatedTopQuestions.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {aggregatedTopQuestions.map((item, idx) => (
                  <div
                    key={`${item.question}-${idx}`}
                    style={{
                      padding: '14px',
                      borderRadius: '12px',
                      border: `1px solid ${colorPalette.background.border}`,
                      backgroundColor: colorPalette.background.soft,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontWeight: '600', color: colorPalette.typography.primary }}>
                        {idx + 1}. {item.question}
                      </span>
                      <span style={{ fontWeight: '700', color: colorPalette.brand.primary }}>{item.count} q</span>
                    </div>
                    <p style={{ margin: 0, fontSize: '12px', color: colorPalette.typography.muted }}>Teams: {item.teams.join(', ')}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: '14px', color: colorPalette.typography.muted }}>No aggregated top questions yet.</p>
            )}
          </section>

          <section
            style={{
              marginBottom: '32px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700' }}>Team Snapshots</h2>
              <span style={{ fontSize: '12px', color: colorPalette.typography.muted }}>Click a team to explore more</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
              {teams.map((team) => {
                const activeMemberRatio = team.member_count
                  ? Math.min(100, ((team.active_members_count || 0) / team.member_count) * 100)
                  : 0;
                const topQuestion =
                  team.top_questions && team.top_questions.length > 0
                    ? team.top_questions[0].question
                    : 'Top question will appear here.';
                const topQuestionPreview =
                  topQuestion.length > 90 ? `${topQuestion.slice(0, 90)}...` : topQuestion;

                return (
                  <article
                    key={team.team_name}
                    style={{
                      border: `1px solid ${colorPalette.background.border}`,
                      borderRadius: '16px',
                      padding: '18px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '10px',
                      backgroundColor: colorPalette.background.panel,
                      boxShadow: '0 10px 20px rgba(15,23,42,0.06)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          width: '20px',
                          height: '20px',
                          borderRadius: '6px',
                          backgroundColor: team.color || colorPalette.brand.primary,
                          display: 'inline-block',
                        }}
                      />
                      <span style={{ fontSize: '16px', fontWeight: '600' }}>{team.team_name}</span>
                    </div>
                    <div style={{ display: 'none', fontSize: '12px', color: colorPalette.typography.muted }}>Lead: {team.lead || 'Unassigned'}</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '14px', fontWeight: '600' }}>
                      <div>Members {team.active_members_count}/{team.member_count}</div>
                      <div>{team.total_questions || 0} Qs</div>
                    </div>
                    <div style={{ height: '6px', borderRadius: '999px', backgroundColor: colorPalette.background.border, overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${Math.min(Math.max(activeMemberRatio, 0), 100)}%`,
                          height: '100%',
                          backgroundColor: team.color || colorPalette.brand.primary,
                          borderRadius: '999px',
                        }}
                      />
                    </div>
                    <div style={{ fontSize: '12px', color: colorPalette.typography.muted }}>Unique questions: {team.unique_questions || 0}</div>
                    <p style={{ margin: 0, fontSize: '13px', color: colorPalette.typography.secondary }}>{topQuestionPreview}</p>
                    <button
                      onClick={() => fetchTeamDetails(team.team_name)}
                      style={{
                        marginTop: 'auto',
                        padding: '8px 12px',
                        borderRadius: '10px',
                        border: 'none',
                        backgroundColor: colorPalette.brand.primary,
                        color: colorPalette.typography.inverse,
                        fontWeight: '600',
                        cursor: 'pointer',
                      }}
                    >
                      View Details
                    </button>
                  </article>
                );
              })}
            </div>
          </section>

          <div style={{ border: `1px solid ${colorPalette.background.border}`, borderRadius: '16px', overflow: 'hidden', backgroundColor: colorPalette.background.panel }}>
            <div style={{ padding: '20px', borderBottom: `1px solid ${colorPalette.background.border}` }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700' }}>Team Leaderboard</h2>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: colorPalette.background.muted, borderBottom: `1px solid ${colorPalette.background.border}` }}>
                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Rank</th>
                    <th style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Team</th>
                    <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Total Questions</th>
                    <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Unique</th>
                    <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Active Members</th>
                    <th style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', fontWeight: '600', color: colorPalette.typography.muted }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboardTeams.map((team, idx) => (
                    <tr key={team.team_name} style={{ borderBottom: `1px solid ${colorPalette.background.border}`, backgroundColor: idx % 2 === 0 ? colorPalette.background.panel : colorPalette.background.soft }}>
                      <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: '500' }}>{idx + 1}</td>
                      <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: '500' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span
                            style={{
                              display: 'inline-block',
                              width: '12px',
                              height: '12px',
                              borderRadius: '3px',
                              backgroundColor: team.color,
                            }}
                          />
                          <span>{team.team_name}</span>
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '14px', textAlign: 'center', fontWeight: '600' }}>
                        {team.total_questions || 0}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '14px', textAlign: 'center' }}>
                        {team.unique_questions || 0}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '14px', textAlign: 'center' }}>
                        {team.active_members_count}/{team.member_count}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '14px', textAlign: 'center' }}>
                        <button
                          onClick={() => fetchTeamDetails(team.team_name)}
                          style={{
                            padding: '6px 10px',
                            backgroundColor: colorPalette.brand.primary,
                            color: colorPalette.typography.inverse,
                            border: 'none',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '12px',
                            fontWeight: '600',
                          }}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {topFiveTeams.length > 0 && (
            <section
              style={{
                marginTop: '32px',
                padding: '24px',
                border: `1px solid ${colorPalette.background.border}`,
                borderRadius: '16px',
                backgroundColor: colorPalette.background.panel,
                boxShadow: '0 8px 20px rgba(15,23,42,0.06)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: '12px', marginBottom: '18px' }}>
                <h2 style={{ fontSize: '20px', fontWeight: '700' }}>Top 5 Teams Overview</h2>
                <span style={{ fontSize: '12px', color: colorPalette.typography.muted }}>Live data from the leaderboard</span>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: '14px',
                }}
              >
                {topFiveTeams.map((team, idx) => (
                  <article
                    key={`top-${team.team_name}-${idx}`}
                    style={{
                      padding: '16px',
                      borderRadius: '16px',
                      color: '#fff',
                      backgroundImage: gradientBackgrounds[idx % gradientBackgrounds.length],
                      minHeight: '170px',
                      boxShadow: '0 6px 18px rgba(15,23,42,0.25)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                    }}
                  >
                    <span style={{ fontSize: '14px', fontWeight: '600' }}>#{idx + 1}</span>
                    <span style={{ fontSize: '18px', fontWeight: '700' }}>{team.team_name}</span>
                    <span style={{ fontSize: '16px', fontWeight: '600' }}>{team.total_questions || 0} messages</span>
                    <span style={{ fontSize: '12px', fontWeight: '500', opacity: 0.85 }}>
                      {team.active_members_count}/{team.member_count} active members
                    </span>
                  </article>
                ))}
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: '20px',
                  marginTop: '28px',
                }}
              >
                <div
                  style={{
                    padding: '18px',
                    borderRadius: '16px',
                    border: `1px solid ${colorPalette.background.border}`,
                    backgroundColor: colorPalette.background.panel,
                    minHeight: '220px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '700' }}>Message Distribution</h3>
                    <span style={{ fontSize: '12px', color: colorPalette.typography.muted }}>Top {topFiveTeams.length}</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    {messageDistribution.map((item, idx) => (
                      <div key={`dist-${item.name}-${idx}`} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', fontWeight: '600' }}>
                          <span>{item.name}</span>
                          <span>{item.percentage.toFixed(1)}%</span>
                        </div>
                        <div
                          style={{
                            height: '8px',
                            borderRadius: '999px',
                            backgroundColor: colorPalette.background.border,
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${Math.min(Math.max(item.percentage, 3), 100)}%`,
                              height: '100%',
                              borderRadius: '999px',
                              backgroundImage: item.color,
                              boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div
                  style={{
                    padding: '18px',
                    borderRadius: '16px',
                    border: `1px solid ${colorPalette.background.border}`,
                    backgroundColor: colorPalette.background.panel,
                    minHeight: '220px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '700' }}>Top Teams by Messages</h3>
                    <span style={{ fontSize: '12px', color: colorPalette.typography.muted }}>{topFiveTeams.length} teams</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {topFiveTeams.map((team) => {
                      const widthPercent = topFiveBarMax
                        ? Math.min(100, ((team.total_questions || 0) / topFiveBarMax) * 100)
                        : 0;
                      return (
                        <div key={`bar-${team.team_name}`} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', fontWeight: '600' }}>
                            <span>{team.team_name}</span>
                            <span>{team.total_questions || 0} msgs</span>
                          </div>
                          <div
                            style={{
                              height: '8px',
                              borderRadius: '999px',
                              backgroundColor: colorPalette.background.border,
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${Math.max(widthPercent, 5)}%`,
                                height: '100%',
                                borderRadius: '999px',
                                backgroundColor: team.color || colorPalette.brand.primary,
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      ) : !fetching && !error ? (
        <div style={{ padding: '32px', textAlign: 'center', color: colorPalette.typography.muted }}>
          No team data available for the selected period.
        </div>
      ) : null}

      {/* Team Details Modal */}
      {showTeamDetails && selectedTeamDetails && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000
        }}>
          <div style={{
            backgroundColor: colorPalette.background.panel,
            borderRadius: '8px',
            padding: '24px',
            maxWidth: '700px',
            width: '90%',
            maxHeight: '80vh',
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700' }}>{selectedTeamDetails.team_name}</h2>
              <button
                onClick={() => setShowTeamDetails(false)}
                style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: colorPalette.typography.primary }}
              >
                ×
              </button>
            </div>

            <div style={{ marginBottom: '20px', paddingBottom: '20px', borderBottom: `1px solid ${colorPalette.background.border}` }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                <div>
                  <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '4px' }}>Lead</div>
                  <div style={{ fontSize: '14px', fontWeight: '600' }}>{selectedTeamDetails.lead}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '4px' }}>Total Members</div>
                  <div style={{ fontSize: '14px', fontWeight: '600' }}>{selectedTeamDetails.total_members}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '4px' }}>Active Members</div>
                  <div style={{ fontSize: '14px', fontWeight: '600' }}>{selectedTeamDetails.active_members}</div>
                </div>
                <div>
                  <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginBottom: '4px' }}>Total Questions</div>
                  <div style={{ fontSize: '14px', fontWeight: '600' }}>{selectedTeamDetails.team_total_questions}</div>
                </div>
              </div>
            </div>

            <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '12px' }}>Members</h3>
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {selectedTeamDetails.members.map((member, idx) => (
                <div key={idx} style={{
                  padding: '12px',
                  backgroundColor: colorPalette.background.soft,
                  borderRadius: '4px',
                  marginBottom: '8px'
                }}>
                  <div style={{ fontSize: '14px', fontWeight: '500' }}>
                    {member.name}
                    {member.is_lead && <span style={{ marginLeft: '8px', fontSize: '12px', backgroundColor: colorPalette.background.glow, color: colorPalette.brand.primary, padding: '2px 6px', borderRadius: '3px' }}>Lead</span>}
                  </div>
                  <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginTop: '4px' }}>{member.email}</div>
                  <div style={{ fontSize: '12px', color: colorPalette.typography.muted, marginTop: '4px' }}>Questions: {member.total_questions}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
