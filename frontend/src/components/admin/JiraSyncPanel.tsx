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
      const response = await fetch("/api/proxy/jira/sync/status", {
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
      const response = await fetch("/api/proxy/jira/sync", {
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

  if (isLoading) {
    return (
      <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6 text-white">
        <p>Loading sync status...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Alerts Section */}
      {syncStatus?.has_alerts && syncStatus.alerts && syncStatus.alerts.length > 0 && (
        <div className="space-y-3">
          {syncStatus.alerts.map((alert, index) => (
            <div
              key={index}
              className={`p-4 rounded-lg border ${
                alert.type === "error"
                  ? "bg-red-500/20 border-red-500"
                  : "bg-yellow-500/20 border-yellow-500"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl">
                  {alert.type === "error" ? "❌" : "⚠️"}
                </span>
                <div className="flex-1">
                  <div className="font-bold text-white mb-1">
                    {alert.message}
                  </div>
                  <div className="text-sm text-gray-300 mb-2">
                    {alert.details}
                  </div>
                  {alert.last_attempt && (
                    <div className="text-xs text-gray-400">
                      Last attempt: {alert.last_attempt}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Sync Status Card */}
      <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6">
        <h2 className="text-2xl font-bold text-white mb-4">Sync Status</h2>

        {/* Message */}
        {message && (
          <div
            className={`mb-4 p-4 rounded-lg ${
              message.type === "success"
                ? "bg-green-500/20 border border-green-500 text-green-100"
                : message.type === "error"
                ? "bg-red-500/20 border border-red-500 text-red-100"
                : "bg-blue-500/20 border border-blue-500 text-blue-100"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-sm text-gray-400 mb-1">Vectorstore Status</div>
            <div
              className={`text-2xl font-bold ${
                syncStatus?.status === "active"
                  ? "text-green-400"
                  : "text-red-400"
              }`}
            >
              {syncStatus?.status === "active" ? "Active" : "Inactive"}
            </div>
          </div>

          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-sm text-gray-400 mb-1">Last Sync</div>
            <div className="text-2xl font-bold text-white">
              {syncStatus?.last_sync || "Never"}
            </div>
          </div>

          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-sm text-gray-400 mb-1">Total Tickets</div>
            <div className="text-2xl font-bold text-purple-400">
              {syncStatus?.total_documents?.toLocaleString() || "0"}
            </div>
          </div>
        </div>

        {/* Sync Button */}
        <button
          onClick={handleSync}
          disabled={isSyncing}
          className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 disabled:from-gray-600 disabled:to-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-all font-semibold text-lg shadow-lg"
        >
          {isSyncing ? (
            <>
              <span className="inline-block animate-spin mr-2">⟳</span>
              Syncing...
            </>
          ) : (
            "Trigger Manual Sync"
          )}
        </button>

        <p className="text-sm text-gray-400 mt-3 text-center">
          This will fetch all new and updated tickets since the last sync
        </p>
      </div>

      {/* Sync History */}
      {syncStatus?.sync_history && syncStatus.sync_history.length > 0 && (
        <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6">
          <h3 className="text-xl font-bold text-white mb-4">Sync History</h3>

          <div className="space-y-2">
            {syncStatus.sync_history.slice(0, 10).map((entry, index) => (
              <div
                key={index}
                className="bg-white/5 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        entry.status === "success"
                          ? "bg-green-400"
                          : entry.status === "no_updates"
                          ? "bg-blue-400"
                          : "bg-red-400"
                      }`}
                    />
                    <div>
                      <div className="text-white font-medium">
                        {new Date(entry.timestamp).toLocaleString()}
                      </div>
                      <div className="text-sm text-gray-400">
                        {entry.documents_added > 0
                          ? `Added ${entry.documents_added} documents`
                          : entry.status === "no_updates"
                          ? "No new tickets"
                          : "Sync failed"}
                      </div>
                    </div>
                  </div>
                  <div
                    className={`px-3 py-1 rounded-full text-xs font-semibold ${
                      entry.status === "success"
                        ? "bg-green-500/20 text-green-300"
                        : entry.status === "no_updates"
                        ? "bg-blue-500/20 text-blue-300"
                        : "bg-red-500/20 text-red-300"
                    }`}
                  >
                    {entry.status}
                  </div>
                </div>
                {entry.error && (
                  <div className="ml-6 mt-2 text-xs text-red-300 bg-red-500/10 p-2 rounded">
                    Error: {entry.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Stats */}
      <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6">
        <h3 className="text-xl font-bold text-white mb-4">Quick Info</h3>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Sync Type:</span>
            <span className="text-white font-medium">Incremental</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Project Keys:</span>
            <span className="text-white font-medium">PRI, QAB</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Status Filter:</span>
            <span className="text-white font-medium">
              Resolved, Resolved-, Closed
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Automatic Sync:</span>
            <span className="text-yellow-400 font-medium">
              Coming Soon (Scheduled)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
