'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '@/lib/api';
import AdminGuard from '@/components/AdminGuard';
import { useAuth } from '@/context/AuthContext';

type TimeFilter = 'today' | 'yesterday' | 'this_week' | 'last_week';

const TIME_FILTERS: { value: TimeFilter; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'this_week', label: 'This Week' },
  { value: 'last_week', label: 'Last Week' },
];

interface SiteAnalyticsSummary {
  time_filter: string;
  period: { label: string; start: string; end: string };
  total_page_views: number;
  total_events: number;
  unique_users: number;
  event_counts: Record<string, number>;
  per_endpoint: Record<string, number>;
  funnel: {
    entry: number;
    login_page: number;
    login_success: number;
    chat_start: number;
    conversion_rates: { entry_to_chat?: number };
  };
}

export default function SiteAnalyticsPage() {
  const router = useRouter();
  const { user: authUser } = useAuth();
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('today');
  const [data, setData] = useState<SiteAnalyticsSummary | null>(null);

  const fetchSummary = useCallback(async (filter: TimeFilter) => {
    setFetching(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/analytics/summary?time_filter=${filter}`);
      if (!res.ok) throw new Error(await res.text());
      const json = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load analytics');
      setData(null);
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (!authUser) {
      setLoading(false);
      return;
    }
    setLoading(false);
    fetchSummary(timeFilter);
  }, [authUser, timeFilter, fetchSummary]);

  if (loading) {
    return (
      <div style={{ padding: '32px', fontFamily: 'Inter, system-ui, sans-serif' }}>
        <p style={{ color: '#6b7280' }}>Loading...</p>
      </div>
    );
  }

  return (
    <AdminGuard>
      <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto', fontFamily: 'Inter, system-ui, sans-serif' }}>
        <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <h1 style={{ fontSize: '28px', fontWeight: 700, color: '#323130', margin: 0 }}>Site Analytics</h1>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <select
              value={timeFilter}
              onChange={(e) => setTimeFilter(e.target.value as TimeFilter)}
              style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '14px', background: '#fff' }}
            >
              {TIME_FILTERS.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => router.push('/admin/dashboard')}
              style={{ padding: '8px 16px', borderRadius: '4px', border: '1px solid #c8c6c4', background: '#fff', cursor: 'pointer', fontSize: '14px' }}
            >
              Dashboard
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: '12px', background: '#fef2f2', color: '#b91c1c', borderRadius: '6px', marginBottom: '16px' }}>
            {error}
          </div>
        )}

        {fetching && !data && <p style={{ color: '#6b7280' }}>Loading...</p>}

        {data && !fetching && (
          <>
            <p style={{ color: '#6b7280', marginBottom: '20px' }}>
              {data.period?.label} ({data.period?.start} – {data.period?.end})
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '16px', marginBottom: '24px' }}>
              <Card title="Page views" value={data.total_page_views} />
              <Card title="Unique users" value={data.unique_users} />
              <Card title="Total events" value={data.total_events} />
              {data.funnel?.entry != null && <Card title="Funnel: Entry" value={data.funnel.entry} />}
              {data.funnel?.login_page != null && <Card title="Funnel: Login page" value={data.funnel.login_page} />}
              {data.funnel?.login_success != null && <Card title="Funnel: Login success" value={data.funnel.login_success} />}
              {data.funnel?.chat_start != null && <Card title="Funnel: Chat start" value={data.funnel.chat_start} />}
              {data.funnel?.conversion_rates?.entry_to_chat != null && (
                <Card title="Conversion (entry → chat)" value={`${(data.funnel.conversion_rates.entry_to_chat * 100).toFixed(1)}%`} />
              )}
            </div>

            {data.event_counts && Object.keys(data.event_counts).length > 0 && (
              <section style={{ marginBottom: '24px' }}>
                <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '12px', color: '#323130' }}>Event counts</h2>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
                  {Object.entries(data.event_counts).map(([k, v]) => (
                    <span key={k} style={{ padding: '6px 12px', background: '#f3f4f6', borderRadius: '6px', fontSize: '14px' }}>
                      {k}: <strong>{v}</strong>
                    </span>
                  ))}
                </div>
              </section>
            )}

            {data.per_endpoint && Object.keys(data.per_endpoint).length > 0 && (
              <section>
                <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '12px', color: '#323130' }}>Page views by endpoint</h2>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px' }}>
                  {Object.entries(data.per_endpoint).map(([path, count]) => (
                    <span key={path} style={{ padding: '6px 12px', background: '#eff6ff', borderRadius: '6px', fontSize: '14px' }}>
                      {path}: <strong>{count}</strong>
                    </span>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </AdminGuard>
  );
}

function Card({ title, value }: { title: string; value: number | string }) {
  return (
    <div style={{ padding: '16px', background: '#f9fafb', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
      <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>{title}</div>
      <div style={{ fontSize: '24px', fontWeight: 700, color: '#323130' }}>{value}</div>
    </div>
  );
}
