"use client";

import { useState, useEffect } from "react";

interface JiraConfig {
  server: string;
  email: string;
  api_token: string;
  project_keys: string[];
  max_issues: number;
  date_filter: string;
}

interface JiraConfigResponse extends Omit<JiraConfig, "api_token"> {
  api_token_masked: string;
  is_configured: boolean;
  last_test?: string;
  test_status?: string;
}

export default function JiraConfigPanel() {
  const [config, setConfig] = useState<JiraConfig>({
    server: "",
    email: "",
    api_token: "",
    project_keys: ["PRI", "QAB"],
    max_issues: 10000,
    date_filter: "",
  });

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [message, setMessage] = useState<{
    type: "success" | "error" | "info";
    text: string;
  } | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [tokenPlaceholder, setTokenPlaceholder] = useState("****");

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/proxy/api/jira/config", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error("Failed to load configuration");

      const data: JiraConfigResponse = await response.json();
      setConfig({
        server: data.server,
        email: data.email,
        api_token: "", // Don't populate token field for security
        project_keys: data.project_keys,
        max_issues: data.max_issues,
        date_filter: data.date_filter,
      });
      setTokenPlaceholder(data.api_token_masked);

      if (data.is_configured) {
        setMessage({
          type: "info",
          text: `Configuration loaded. Last test: ${
            data.last_test ? new Date(data.last_test).toLocaleString() : "Never"
          }`,
        });
      }
    } catch (error) {
      console.error("Failed to load config:", error);
      setMessage({
        type: "error",
        text: "Failed to load configuration",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    setMessage(null);

    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/proxy/api/jira/config/test", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(config),
      });

      const data = await response.json();

      if (data.status === "success") {
        setMessage({
          type: "success",
          text: `✓ ${data.message}`,
        });
      } else {
        setMessage({
          type: "error",
          text: `✗ ${data.message}`,
        });
      }
    } catch (error) {
      setMessage({
        type: "error",
        text: "Connection test failed",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setMessage(null);

    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/proxy/api/jira/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(config),
      });

      if (!response.ok) throw new Error("Failed to save configuration");

      const data = await response.json();
      setMessage({
        type: "success",
        text: "✓ Configuration saved successfully!",
      });

      // Reload to get masked token
      setTimeout(() => loadConfig(), 1000);
    } catch (error: any) {
      setMessage({
        type: "error",
        text: error.message || "Failed to save configuration",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleProjectKeysChange = (value: string) => {
    // Split by comma and trim whitespace
    const keys = value
      .split(",")
      .map((k) => k.trim())
      .filter((k) => k.length > 0);
    setConfig({ ...config, project_keys: keys });
  };

  if (isLoading) {
    return (
      <div style={{ padding: '20px', backgroundColor: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '10px', color: '#1d4ed8', textAlign: 'center' }}>
        Loading configuration...
      </div>
    );
  }

  return (
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
        <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#111827', marginBottom: '4px' }}>
          Jira Configuration
        </h2>
        <p style={{ fontSize: '14px', color: '#6b7280' }}>
          Configure your Jira connection details. The API token will be encrypted when saved.
        </p>
      </div>

      <div style={{ padding: '24px' }}>
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
              marginBottom: '24px',
            }}
          >
            {message.text}
          </div>
        )}

        {/* Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Server URL */}
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
              Jira Server URL *
            </label>
            <input
              type="url"
              value={config.server}
              onChange={(e) => setConfig({ ...config, server: e.target.value })}
              placeholder="https://yourcompany.atlassian.net"
              style={{
                width: '100%',
                padding: '10px 14px',
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                fontSize: '14px',
                color: '#111827',
                backgroundColor: 'white',
              }}
              required
            />
          </div>

          {/* Email */}
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
              Email *
            </label>
            <input
              type="email"
              value={config.email}
              onChange={(e) => setConfig({ ...config, email: e.target.value })}
              placeholder="user@example.com"
              style={{
                width: '100%',
                padding: '10px 14px',
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                fontSize: '14px',
                color: '#111827',
                backgroundColor: 'white',
              }}
              required
            />
          </div>

          {/* API Token */}
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
              API Token *
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showToken ? "text" : "password"}
                value={config.api_token}
                onChange={(e) =>
                  setConfig({ ...config, api_token: e.target.value })
                }
                placeholder={tokenPlaceholder}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  paddingRight: '48px',
                  border: '1px solid #d1d5db',
                  borderRadius: '8px',
                  fontSize: '14px',
                  color: '#111827',
                  backgroundColor: 'white',
                }}
                required
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                style={{
                  position: 'absolute',
                  right: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '18px',
                  color: '#6b7280',
                }}
              >
                {showToken ? "👁️" : "👁️‍🗨️"}
              </button>
            </div>
            <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '6px' }}>
              Get your API token from Jira: Account Settings → Security → API Tokens
            </p>
          </div>

          {/* Project Keys */}
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
              Project Keys *
            </label>
            <input
              type="text"
              value={config.project_keys.join(", ")}
              onChange={(e) => handleProjectKeysChange(e.target.value)}
              placeholder="PRI, QAB"
              style={{
                width: '100%',
                padding: '10px 14px',
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                fontSize: '14px',
                color: '#111827',
                backgroundColor: 'white',
              }}
              required
            />
            <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '6px' }}>
              Comma-separated project keys (e.g., PRI, QAB)
            </p>
          </div>

          {/* Max Issues */}
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
              Maximum Issues to Fetch
            </label>
            <input
              type="number"
              value={config.max_issues}
              onChange={(e) =>
                setConfig({ ...config, max_issues: parseInt(e.target.value) || 10000 })
              }
              style={{
                width: '100%',
                padding: '10px 14px',
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                fontSize: '14px',
                color: '#111827',
                backgroundColor: 'white',
              }}
            />
          </div>

          {/* Date Filter (Optional) */}
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827', marginBottom: '8px' }}>
              Date Filter (Optional)
            </label>
            <input
              type="text"
              value={config.date_filter}
              onChange={(e) =>
                setConfig({ ...config, date_filter: e.target.value })
              }
              placeholder="Leave empty for all tickets"
              style={{
                width: '100%',
                padding: '10px 14px',
                border: '1px solid #d1d5db',
                borderRadius: '8px',
                fontSize: '14px',
                color: '#111827',
                backgroundColor: 'white',
              }}
            />
            <p style={{ fontSize: '12px', color: '#6b7280', marginTop: '6px' }}>
              Example: "3months" - Leave empty to fetch all tickets
            </p>
          </div>
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '24px', paddingTop: '24px', borderTop: '1px solid #e5e7eb' }}>
          <button
            onClick={handleTest}
            disabled={isTesting || !config.server || !config.email || !config.api_token}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              background: isTesting || !config.server || !config.email || !config.api_token ? '#9ca3af' : '#0129ac',
              color: 'white',
              cursor: isTesting || !config.server || !config.email || !config.api_token ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              fontSize: '14px',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (!isTesting && config.server && config.email && config.api_token) {
                e.currentTarget.style.background = '#011a8a';
              }
            }}
            onMouseLeave={(e) => {
              if (!isTesting && config.server && config.email && config.api_token) {
                e.currentTarget.style.background = '#0129ac';
              }
            }}
          >
            {isTesting ? "Testing..." : "Test Connection"}
          </button>

          <button
            onClick={handleSave}
            disabled={isSaving || !config.server || !config.email || !config.api_token}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              background: isSaving || !config.server || !config.email || !config.api_token ? '#9ca3af' : '#10b981',
              color: 'white',
              cursor: isSaving || !config.server || !config.email || !config.api_token ? 'not-allowed' : 'pointer',
              fontWeight: 600,
              fontSize: '14px',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (!isSaving && config.server && config.email && config.api_token) {
                e.currentTarget.style.background = '#059669';
              }
            }}
            onMouseLeave={(e) => {
              if (!isSaving && config.server && config.email && config.api_token) {
                e.currentTarget.style.background = '#10b981';
              }
            }}
          >
            {isSaving ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </div>
    </div>
  );
}
