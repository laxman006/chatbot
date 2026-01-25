"use client";

import { useState, useEffect } from "react";

interface SyncStatus {
  status: string;
  last_sync: string;
  last_attempt?: string;
  last_status?: string;
  total_documents: number;
  consecutive_failures?: number;
  has_alerts?: boolean;
  alerts?: Array<{
    type: "error" | "warning";
    message: string;
    details: string;
    last_attempt?: string;
  }>;
  sync_history: Array<{
    timestamp: string;
    documents_added: number;
    status: string;
    error?: string;
  }>;
}

export default function JiraSyncPanel() {
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error" | "info";
    text: string;
  } | null>(null);

  useEffect(() => {
    loadStatus();
    // Auto-refresh status every 30 seconds
    const interval = setInterval(loadStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadStatus = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/proxy/api/jira/sync/status", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error("Failed to load sync status");

      const data = await response.json();
      setSyncStatus(data);
    } catch (error) {
      console.error("Failed to load status:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSync = async () => {
    setIsSyncing(true);
    setMessage(null);

    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/proxy/api/jira/sync", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error("Sync failed");

      const data = await response.json();

      if (data.status === "success") {
        setMessage({
          type: "success",
          text: `✓ ${data.message}. Added ${data.new_tickets} new tickets.`,
        });
      } else if (data.status === "no_updates") {
        setMessage({
          type: "info",
          text: "ℹ No new tickets to sync. All tickets are up to date.",
        });
      }

      // Reload status after sync
      setTimeout(() => loadStatus(), 1000);
    } catch (error: any) {
      setMessage({
        type: "error",
        text: `✗ Sync failed: ${error.message}`,
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const formatDate = (dateString: string | null): string => {
    if (!dateString || dateString === 'Never') return 'Never';
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return dateString; // Return original string if invalid date
      }
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

  if (isLoading) {
    return (
      <div style={{ padding: '20px', backgroundColor: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '10px', color: '#1d4ed8', textAlign: 'center' }}>
        Loading sync status...
      </div>
    );
  }

  return (
    <div>
      {/* Alerts Section */}
      {syncStatus?.has_alerts && syncStatus.alerts && syncStatus.alerts.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          {syncStatus.alerts.map((alert, index) => (
            <div
              key={index}
              style={{
                padding: '12px 16px',
                backgroundColor: alert.type === "error" ? '#fef2f2' : '#fffbeb',
                border: `1px solid ${alert.type === "error" ? '#fecdd3' : '#fde68a'}`,
                borderRadius: '10px',
                color: alert.type === "error" ? '#b91c1c' : '#92400e',
                marginBottom: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'start', gap: '12px' }}>
                <span style={{ fontSize: '20px' }}>
                  {alert.type === "error" ? "❌" : "⚠️"}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                    {alert.message}
                  </div>
                  <div style={{ fontSize: '13px', marginBottom: '4px' }}>
                    {alert.details}
                  </div>
                  {alert.last_attempt && (
                    <div style={{ fontSize: '12px', color: '#6b7280' }}>
                      Last attempt: {alert.last_attempt}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Trigger Sync Button Section */}
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
            Trigger Jira Sync
          </h2>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>
            Manually trigger a Jira sync to fetch new and updated tickets from Jira.
          </p>
        </div>

        {/* Message */}
        {message && (
          <div
            style={{
              padding: '12px 16px',
              backgroundColor:
                message.type === "success"
                  ? '#f0fdf4'
                  : message.type === "error"
                  ? '#fef2f2'
                  : '#eff6ff',
              border: `1px solid ${
                message.type === "success"
                  ? '#bbf7d0'
                  : message.type === "error"
                  ? '#fecdd3'
                  : '#bfdbfe'
              }`,
              borderRadius: '10px',
              color:
                message.type === "success"
                  ? '#166534'
                  : message.type === "error"
                  ? '#b91c1c'
                  : '#1d4ed8',
              marginBottom: '16px',
            }}
          >
            {message.text}
          </div>
        )}

        <button
          onClick={handleSync}
          disabled={isSyncing}
          style={{
            padding: '14px 28px',
            borderRadius: '10px',
            border: 'none',
            background: isSyncing ? '#9ca3af' : '#0129ac',
            color: 'white',
            cursor: isSyncing ? 'not-allowed' : 'pointer',
            fontWeight: 700,
            fontSize: '16px',
            minWidth: '200px',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            if (!isSyncing) {
              e.currentTarget.style.background = '#011a8a';
            }
          }}
          onMouseLeave={(e) => {
            if (!isSyncing) {
              e.currentTarget.style.background = '#0129ac';
            }
          }}
        >
          {isSyncing ? 'Syncing...' : 'Trigger Manual Sync'}
        </button>
        <p style={{ color: '#6b7280', fontSize: '13px', marginTop: '12px' }}>
          This will fetch all new and updated tickets since the last sync
        </p>
      </div>

      {/* Status Cards */}
      {syncStatus && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          {/* Vectorstore Status Card */}
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
                  backgroundColor: syncStatus.status === "active" ? '#10b981' : '#ef4444',
                  marginRight: '8px',
                }}
              />
              <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#111827' }}>
                Vectorstore Status
              </h3>
            </div>
            <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
              <div>
                <strong>Status:</strong>{' '}
                <span style={{ color: syncStatus.status === "active" ? '#10b981' : '#ef4444' }}>
                  {syncStatus.status === "active" ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          </div>

          {/* Last Sync Card */}
          <div
            style={{
              padding: '20px',
              border: '1px solid #e5e7eb',
              borderRadius: '12px',
              backgroundColor: 'white',
            }}
          >
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', marginBottom: '12px' }}>
              Last Sync
            </h3>
            <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
              <div>
                <strong>Time:</strong> {syncStatus.last_sync === 'Never' || !syncStatus.last_sync ? 'Never' : formatDate(syncStatus.last_sync)}
              </div>
              {syncStatus.last_status && syncStatus.last_status !== 'unknown' && (
                <div style={{ marginTop: '8px' }}>
                  <strong>Status:</strong>{' '}
                  <span style={{ color: syncStatus.last_status === "success" ? '#10b981' : syncStatus.last_status === "no_updates" ? '#3b82f6' : '#ef4444' }}>
                    {syncStatus.last_status}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Total Tickets Card */}
          <div
            style={{
              padding: '20px',
              border: '1px solid #e5e7eb',
              borderRadius: '12px',
              backgroundColor: 'white',
            }}
          >
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#111827', marginBottom: '12px' }}>
              Total Tickets
            </h3>
            <div style={{ fontSize: '14px', color: '#6b7280', lineHeight: '1.6' }}>
              <div>
                <strong>Documents:</strong>{' '}
                <span style={{ color: '#111827', fontWeight: 600, fontSize: '18px' }}>
                  {syncStatus.total_documents?.toLocaleString() || "0"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sync History */}
      {syncStatus?.sync_history && syncStatus.sync_history.length > 0 && (
        <div
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            overflow: 'hidden',
            backgroundColor: 'white',
            marginBottom: '24px',
            width: '50%',
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
              Sync History
            </h2>
          </div>
          <div 
            style={{ 
              padding: '20px',
              maxHeight: '400px',
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[...syncStatus.sync_history].reverse().slice(0, 10).map((entry, index) => (
                <div
                  key={index}
                  style={{
                    padding: '16px',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    backgroundColor: '#f9fafb',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div
                        style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          backgroundColor:
                            entry.status === "success"
                              ? '#10b981'
                              : entry.status === "no_updates"
                              ? '#3b82f6'
                              : '#ef4444',
                        }}
                      />
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: '#111827' }}>
                          {formatDate(entry.timestamp)}
                        </div>
                        <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>
                          {entry.documents_added > 0
                            ? `Added ${entry.documents_added} documents`
                            : entry.status === "no_updates"
                            ? "No new tickets"
                            : "Sync failed"}
                        </div>
                      </div>
                    </div>
                    <div
                      style={{
                        padding: '4px 12px',
                        borderRadius: '12px',
                        fontSize: '12px',
                        fontWeight: 600,
                        backgroundColor:
                          entry.status === "success"
                            ? '#d1fae5'
                            : entry.status === "no_updates"
                            ? '#dbeafe'
                            : '#fee2e2',
                        color:
                          entry.status === "success"
                            ? '#065f46'
                            : entry.status === "no_updates"
                            ? '#1e40af'
                            : '#991b1b',
                      }}
                    >
                      {entry.status}
                    </div>
                  </div>
                  {entry.error && (
                    <div style={{ marginLeft: '20px', marginTop: '8px', fontSize: '12px', color: '#b91c1c', backgroundColor: '#fef2f2', padding: '8px', borderRadius: '6px' }}>
                      Error: {entry.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Quick Info */}
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
            Quick Info
          </h2>
        </div>
        <div style={{ padding: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Sync Type</div>
              <div style={{ fontSize: '14px', color: '#111827', fontWeight: 600 }}>Incremental</div>
            </div>
            <div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Project Keys</div>
              <div style={{ fontSize: '14px', color: '#111827', fontWeight: 600 }}>PRI</div>
            </div>
            <div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Status Filter</div>
              <div style={{ fontSize: '14px', color: '#111827', fontWeight: 600 }}>
                Resolved, Resolved-, Closed
              </div>
            </div>
            <div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginBottom: '4px' }}>Automatic Sync</div>
              <div style={{ fontSize: '14px', color: '#111827', fontWeight: 600 }}>
                Scheduled (Daily)
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
