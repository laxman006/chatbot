'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getCurrentUser } from '@/lib/session-utils';
import { getApiBase } from '@/lib/api';
import { isAdminEmail, ADMIN_EMAILS } from '@/constants/admins';
import { User } from '@/types/chat';

type QuestionStat = {
  question: string;
  count: number;
  last_asked?: string;
};

export default function AdminTopQuestionsPage() {
  const router = useRouter();
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);
  const [questions, setQuestions] = useState<QuestionStat[]>([]);
  const [usedSource, setUsedSource] = useState<string>('auto');
  const [source, setSource] = useState<string>('auto');
  const [limit, setLimit] = useState<number>(15);

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

  const fetchQuestions = useCallback(
    async (user: User, selectedSource?: string, selectedLimit?: number) => {
      setFetching(true);
      setError(null);
      setNotes(null);

      const src = (selectedSource || source).toLowerCase();
      const lim = selectedLimit || limit;

      try {
        const response = await fetch(
          `${getApiBase()}/admin/top-questions?limit=${lim}&source=${src}`,
          {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json'
            },
            credentials: 'include'
          }
        );

        const payload = await response.json();

        if (!response.ok) {
          throw new Error(payload.detail || payload.error || 'Failed to load most asked questions');
        }

        setQuestions(payload.questions || []);
        setUsedSource(payload.used_source || src);

        if (payload.errors && payload.errors.length > 0) {
          setNotes(payload.errors.join('; '));
        } else if (!payload.questions || payload.questions.length === 0) {
          setNotes('No questions found in the selected source.');
        } else {
          setNotes(null);
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setFetching(false);
      }
    },
    [limit, source]
  );

  // Fetch data after authentication
  useEffect(() => {
    if (!authUser) return;
    fetchQuestions(authUser);
  }, [authUser, fetchQuestions]);

  const handleRefresh = () => {
    if (!authUser) return;
    fetchQuestions(authUser);
  };

  if (loading) {
    return (
      <div style={{ padding: '40px', fontFamily: 'Inter, system-ui, sans-serif' }}>
        <p style={{ color: '#6b7280' }}>Checking admin access...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px', maxWidth: '1080px', margin: '0 auto', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '6px' }}>Most Asked Questions</h1>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => router.push('/admin/dashboard')}
            style={{
              padding: '10px 14px',
              borderRadius: '10px',
              border: '1px solid #d1d5db',
              background: 'white',
              cursor: 'pointer',
              color: '#111827',
              fontWeight: 600
            }}
          >
            Dashboard
          </button>
          <button
            onClick={() => router.push('/chat/new')}
            style={{
              padding: '10px 14px',
              borderRadius: '10px',
              border: '1px solid #d1d5db',
              background: 'white',
              cursor: 'pointer',
              color: '#111827',
              fontWeight: 600
            }}
          >
            Back to chats
          </button>
          <button
            onClick={handleRefresh}
            disabled={fetching}
            style={{
              padding: '10px 14px',
              borderRadius: '10px',
              border: 'none',
              background: '#0129ac',
              color: 'white',
              cursor: fetching ? 'not-allowed' : 'pointer',
              fontWeight: 700
            }}
          >
            {fetching ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          gap: '12px',
          marginBottom: '16px',
          alignItems: 'center',
          flexWrap: 'wrap'
        }}
      >
        <label style={{ fontSize: '14px', color: '#374151' }}>
          Source:&nbsp;
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            style={{ padding: '8px 10px', borderRadius: '8px', border: '1px solid #d1d5db' }}
          >
            <option value="auto">Auto (chat_sessions → conversations)</option>
            <option value="chat_sessions">chat_sessions (saved sessions)</option>
            <option value="conversations">conversations (recent memory)</option>
          </select>
        </label>

        <label style={{ fontSize: '14px', color: '#374151' }}>
          Limit:&nbsp;
          <input
            type="number"
            min={1}
            max={200}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            style={{ width: '80px', padding: '8px 10px', borderRadius: '8px', border: '1px solid #d1d5db' }}
          />
        </label>

        <button
          onClick={() => authUser && fetchQuestions(authUser, source, limit)}
          disabled={fetching}
          style={{
            padding: '9px 14px',
            borderRadius: '10px',
            border: '1px solid #0129ac',
            background: '#0129ac',
            color: 'white',
            cursor: fetching ? 'not-allowed' : 'pointer',
            fontWeight: 600
          }}
        >
          {fetching ? 'Loading...' : 'Run query'}
        </button>
      </div>

      {usedSource && (
        <div style={{ marginBottom: '12px', color: '#6b7280', fontSize: '13px' }}>
          Data source: <strong style={{ color: '#111827' }}>{usedSource}</strong>
        </div>
      )}

      {error && (
        <div style={{ background: '#fef2f2', color: '#b91c1c', padding: '12px 14px', borderRadius: '10px', marginBottom: '12px', border: '1px solid #fecdd3' }}>
          {error}
        </div>
      )}

      {notes && (
        <div style={{ background: '#eff6ff', color: '#1d4ed8', padding: '12px 14px', borderRadius: '10px', marginBottom: '12px', border: '1px solid #bfdbfe' }}>
          {notes}
        </div>
      )}

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
            gridTemplateColumns: '3fr 0.7fr 1.2fr',
            background: '#f9fafb',
            padding: '12px 14px',
            fontWeight: 700,
            color: '#111827',
            fontSize: '14px'
          }}
        >
          <div>Question</div>
          <div>Count</div>
          <div>Last asked</div>
        </div>

        {questions.length === 0 ? (
          <div style={{ padding: '16px', color: '#6b7280' }}>No data available.</div>
        ) : (
          questions.map((item, idx) => (
            <div
              key={`${item.question}-${idx}`}
              style={{
                display: 'grid',
                gridTemplateColumns: '3fr 0.7fr 1.2fr',
                padding: '12px 14px',
                borderTop: '1px solid #e5e7eb',
                background: idx % 2 === 0 ? 'white' : '#f9fafb'
              }}
            >
              <div style={{ color: '#111827', fontWeight: 600 }}>{item.question}</div>
              <div style={{ color: '#111827' }}>{item.count}</div>
              <div style={{ color: '#6b7280' }}>{item.last_asked || '—'}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}


