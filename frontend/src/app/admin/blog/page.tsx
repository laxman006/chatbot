'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getCurrentUser } from '@/lib/session-utils';
import { apiFetch } from '@/lib/api';
import { isAdminEmail } from '@/constants/admins';
import { User } from '@/types/chat';

interface BlogStatus {
  polling_enabled: boolean;
  polling_interval_seconds: number;
  polling_interval_minutes: number;
  last_poll_file: string;
  last_poll_time: string | null;
  last_blog_poll: string | null;
  blog_post_count: number;
  last_blog_post_date: string | null;
  vectorstore_exists: boolean;
}

interface BlogStats {
  source_url: string;
  web_source_enabled: boolean;
  vectorstore_exists: boolean;
  blog_post_count: number;
  unique_blog_posts?: number;
  total_blog_chunks?: number;
  last_blog_poll: string | null;
  last_blog_post_date: string | null;
  last_blog_post_url?: string | null;
  last_blog_post_title?: string | null;
  oldest_post_date?: string | null;
  newest_post_date?: string | null;
  vectorstore_build_date?: string | null;
}

export default function AdminBlogPage() {
  const router = useRouter();
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [polling, setPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [status, setStatus] = useState<BlogStatus | null>(null);
  const [stats, setStats] = useState<BlogStats | null>(null);

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

  // Fetch status and stats
  const fetchData = useCallback(async () => {
    if (!authUser) return;

    setFetching(true);
    setError(null);
    setSuccess(null);

    try {
      // Fetch status
      const statusResponse = await apiFetch('/admin/blog/status', {
        method: 'GET',
      });

      if (!statusResponse.ok) {
        const statusData = await statusResponse.json();
        throw new Error(statusData.detail || 'Failed to fetch blog status');
      }

      const statusData: BlogStatus = await statusResponse.json();
      setStatus(statusData);

      // Fetch stats
      const statsResponse = await apiFetch('/admin/blog/stats', {
        method: 'GET',
      });

      if (!statsResponse.ok) {
        const statsData = await statsResponse.json();
        throw new Error(statsData.detail || 'Failed to fetch blog stats');
      }

      const statsData: BlogStats = await statsResponse.json();
      setStats(statsData);
    } catch (err) {
      setError((err as Error).message);
      console.error('Error fetching blog data:', err);
    } finally {
      setFetching(false);
    }
  }, [authUser]);

  // Fetch data after authentication
  useEffect(() => {
    if (!authUser) return;
    fetchData();
  }, [authUser, fetchData]);

  // Trigger blog poll
  const handleTriggerPoll = useCallback(async () => {
    if (!authUser || polling) return;

    setPolling(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await apiFetch('/admin/blog/poll', {
        method: 'POST',
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to trigger blog poll');
      }

      setSuccess('Blog poll completed successfully! New posts have been added to the vectorstore.');
      
      // Auto-refresh status after a short delay
      setTimeout(() => {
        fetchData();
      }, 2000);
    } catch (err) {
      setError((err as Error).message);
      console.error('Error triggering blog poll:', err);
    } finally {
      setPolling(false);
    }
  }, [authUser, polling, fetchData]);

  // Format interval for display
  const formatInterval = (seconds: number): string => {
    if (seconds < 60) return `${seconds} seconds`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} minutes`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} hours`;
    if (seconds < 604800) return `${Math.round(seconds / 86400)} days`;
    return `${Math.round(seconds / 604800)} weeks`;
  };

  // Format date for display
  const formatDate = (dateString: string | null): string => {
    if (!dateString) return 'Never';
    try {
      const date = new Date(dateString);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateString;
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '40px', fontFamily: 'Inter, system-ui, sans-serif' }}>
        <p style={{ color: '#6b7280' }}>Checking admin access...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto', fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '6px', color: '#111827' }}>
            Blog Management
          </h1>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>
            Manage blog polling and monitor blog post ingestion
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => router.push('/chat/new')}
            style={{
              padding: '10px 14px',
              borderRadius: '10px',
              border: '1px solid #d1d5db',
              background: 'white',
              cursor: 'pointer',
              color: '#111827',
              fontWeight: 600,
              fontSize: '14px',
            }}
          >
            Back to chats
          </button>
          <button
            onClick={fetchData}
            disabled={fetching}
            style={{
              padding: '10px 14px',
              borderRadius: '10px',
              border: 'none',
              background: '#0129ac',
              color: 'white',
              cursor: fetching ? 'not-allowed' : 'pointer',
              fontWeight: 700,
              fontSize: '14px',
            }}
          >
            {fetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecdd3',
            borderRadius: '10px',
            color: '#b91c1c',
            marginBottom: '20px',
          }}
        >
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Success Message */}
      {success && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '10px',
            color: '#166534',
            marginBottom: '20px',
          }}
        >
          <strong>Success:</strong> {success}
        </div>
      )}

      {/* Loading State */}
      {fetching && !status && (
        <div
          style={{
            padding: '20px',
            backgroundColor: '#eff6ff',
            border: '1px solid #bfdbfe',
            borderRadius: '10px',
            color: '#1d4ed8',
            marginBottom: '20px',
            textAlign: 'center',
          }}
        >
          Loading blog status...
        </div>
      )}

      {/* Trigger Poll Button Section */}
      <div
        style={{
          padding: '24px',
          border: '2px solid #e5e7eb',
          borderRadius: '12px',
          marginBottom: '24px',
          backgroundColor: '#f9fafb',
        }}
      >
        <div style={{ marginBottom: '16px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
            Trigger Blog Poll
          </h2>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>
            Manually trigger a blog poll to check for new posts and add them to the vectorstore.
          </p>
        </div>
        <button
          onClick={handleTriggerPoll}
          disabled={polling || !status?.polling_enabled}
          style={{
            padding: '14px 28px',
            borderRadius: '10px',
            border: 'none',
            background: polling || !status?.polling_enabled ? '#9ca3af' : '#0129ac',
            color: 'white',
            cursor: polling || !status?.polling_enabled ? 'not-allowed' : 'pointer',
            fontWeight: 700,
            fontSize: '16px',
            minWidth: '200px',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            if (!polling && status?.polling_enabled) {
              e.currentTarget.style.background = '#011a8a';
            }
          }}
          onMouseLeave={(e) => {
            if (!polling && status?.polling_enabled) {
              e.currentTarget.style.background = '#0129ac';
            }
          }}
        >
          {polling ? 'Polling...' : 'Trigger Blog Poll'}
        </button>
        {!status?.polling_enabled && (
          <p style={{ color: '#dc2626', fontSize: '13px', marginTop: '8px' }}>
            Blog polling is disabled. Enable it in your configuration.
          </p>
        )}
      </div>

      {/* Status Cards */}
      {status && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          {/* Polling Status Card */}
          <div
            style={{
              padding: '20px',
              border: '1px solid #e5e7eb',
              borderRadius: '12px',
              backgroundColor: 'white',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '12px' }}>
              <div
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  backgroundColor: status.polling_enabled ? '#10b981' : '#ef4444',
                  marginRight: '8px',
                }}
              />
              <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#111827' }}>
                Polling Status
              </h3>
            </div>
            <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
              <div style={{ marginBottom: '8px' }}>
                <strong>Status:</strong>{' '}
                <span style={{ color: status.polling_enabled ? '#10b981' : '#ef4444' }}>
                  {status.polling_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <strong>Interval:</strong> {formatInterval(status.polling_interval_seconds)}
              </div>
              <div>
                <strong>Last Poll:</strong> {formatDate(status.last_poll_time)}
              </div>
            </div>
          </div>

          {/* Blog Posts Card */}
          <div
            style={{
              padding: '20px',
              border: '1px solid #e5e7eb',
              borderRadius: '12px',
              backgroundColor: 'white',
            }}
          >
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', marginBottom: '12px' }}>
              Blog Posts
            </h3>
            <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
              <div style={{ marginBottom: '8px' }}>
                <strong>Total Posts:</strong>{' '}
                <span style={{ color: '#111827', fontWeight: 600, fontSize: '18px' }}>
                  {status.blog_post_count.toLocaleString()}
                </span>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <strong>Last Post Date:</strong> {formatDate(status.last_blog_post_date)}
              </div>
              {stats?.last_blog_post_url && (
                <div>
                  <strong>Last Post:</strong>{' '}
                  <a
                    href={stats.last_blog_post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: '#0129ac',
                      textDecoration: 'none',
                      wordBreak: 'break-all',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.textDecoration = 'underline';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.textDecoration = 'none';
                    }}
                  >
                    {stats.last_blog_post_title || stats.last_blog_post_url}
                  </a>
                </div>
              )}
            </div>
          </div>

          {/* Vectorstore Status Card */}
          <div
            style={{
              padding: '20px',
              border: '1px solid #e5e7eb',
              borderRadius: '12px',
              backgroundColor: 'white',
            }}
          >
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', marginBottom: '12px' }}>
              Vectorstore
            </h3>
            <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
              <div style={{ marginBottom: '8px' }}>
                <strong>Status:</strong>{' '}
                <span style={{ color: status.vectorstore_exists ? '#10b981' : '#ef4444' }}>
                  {status.vectorstore_exists ? 'Available' : 'Not Found'}
                </span>
              </div>
              {stats?.vectorstore_build_date && (
                <div>
                  <strong>Build Date:</strong> {formatDate(stats.vectorstore_build_date)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Detailed Statistics */}
      {stats && (
        <div
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            overflow: 'hidden',
            backgroundColor: 'white',
          }}
        >
          <div
            style={{
              padding: '16px 20px',
              backgroundColor: '#f9fafb',
              borderBottom: '1px solid #e5e7eb',
            }}
          >
            <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#111827' }}>
              Detailed Statistics
            </h2>
          </div>
          <div style={{ padding: '20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px' }}>
              <div>
                <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Source URL</div>
                <div style={{ fontSize: '14px', color: '#111827', wordBreak: 'break-all' }}>
                  {stats.source_url || 'N/A'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Web Source</div>
                <div style={{ fontSize: '14px', color: '#111827' }}>
                  {stats.web_source_enabled ? (
                    <span style={{ color: '#10b981' }}>Enabled</span>
                  ) : (
                    <span style={{ color: '#ef4444' }}>Disabled</span>
                  )}
                </div>
              </div>
              {stats.unique_blog_posts !== undefined && (
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Unique Posts</div>
                  <div style={{ fontSize: '14px', color: '#111827', fontWeight: 600 }}>
                    {stats.unique_blog_posts.toLocaleString()}
                  </div>
                </div>
              )}
              {stats.total_blog_chunks !== undefined && (
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Total Chunks</div>
                  <div style={{ fontSize: '14px', color: '#111827', fontWeight: 600 }}>
                    {stats.total_blog_chunks.toLocaleString()}
                  </div>
                </div>
              )}
              {stats.oldest_post_date && (
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Oldest Post</div>
                  <div style={{ fontSize: '14px', color: '#111827' }}>{formatDate(stats.oldest_post_date)}</div>
                </div>
              )}
              {stats.newest_post_date && (
                <div>
                  <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Newest Post</div>
                  <div style={{ fontSize: '14px', color: '#111827' }}>{formatDate(stats.newest_post_date)}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
