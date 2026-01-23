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
      const response = await fetch("/api/proxy/jira/config", {
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
      const response = await fetch("/api/proxy/jira/config/test", {
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
      const response = await fetch("/api/proxy/jira/config", {
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
      <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6 text-white">
        <p>Loading configuration...</p>
      </div>
    );
  }

  return (
    <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-4">
          Jira Configuration
        </h2>
        <p className="text-gray-300 text-sm">
          Configure your Jira connection details. The API token will be
          encrypted when saved.
        </p>
      </div>

      {/* Message */}
      {message && (
        <div
          className={`p-4 rounded-lg ${
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

      {/* Form */}
      <div className="space-y-4">
        {/* Server URL */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Jira Server URL *
          </label>
          <input
            type="url"
            value={config.server}
            onChange={(e) => setConfig({ ...config, server: e.target.value })}
            placeholder="https://yourcompany.atlassian.net"
            className="w-full px-4 py-2 bg-white/5 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            required
          />
        </div>

        {/* Email */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Email *
          </label>
          <input
            type="email"
            value={config.email}
            onChange={(e) => setConfig({ ...config, email: e.target.value })}
            placeholder="user@example.com"
            className="w-full px-4 py-2 bg-white/5 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            required
          />
        </div>

        {/* API Token */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            API Token *
          </label>
          <div className="relative">
            <input
              type={showToken ? "text" : "password"}
              value={config.api_token}
              onChange={(e) =>
                setConfig({ ...config, api_token: e.target.value })
              }
              placeholder={tokenPlaceholder}
              className="w-full px-4 py-2 bg-white/5 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-12"
              required
            />
            <button
              type="button"
              onClick={() => setShowToken(!showToken)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300"
            >
              {showToken ? "👁️" : "👁️‍🗨️"}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Get your API token from Jira: Account Settings → Security → API
            Tokens
          </p>
        </div>

        {/* Project Keys */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Project Keys *
          </label>
          <input
            type="text"
            value={config.project_keys.join(", ")}
            onChange={(e) => handleProjectKeysChange(e.target.value)}
            placeholder="PRI, QAB"
            className="w-full px-4 py-2 bg-white/5 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            required
          />
          <p className="text-xs text-gray-400 mt-1">
            Comma-separated project keys (e.g., PRI, QAB)
          </p>
        </div>

        {/* Max Issues */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Maximum Issues to Fetch
          </label>
          <input
            type="number"
            value={config.max_issues}
            onChange={(e) =>
              setConfig({ ...config, max_issues: parseInt(e.target.value) || 10000 })
            }
            className="w-full px-4 py-2 bg-white/5 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        {/* Date Filter (Optional) */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Date Filter (Optional)
          </label>
          <input
            type="text"
            value={config.date_filter}
            onChange={(e) =>
              setConfig({ ...config, date_filter: e.target.value })
            }
            placeholder="Leave empty for all tickets"
            className="w-full px-4 py-2 bg-white/5 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <p className="text-xs text-gray-400 mt-1">
            Example: "3months" - Leave empty to fetch all tickets
          </p>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-4 pt-4">
        <button
          onClick={handleTest}
          disabled={isTesting || !config.server || !config.email || !config.api_token}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-semibold"
        >
          {isTesting ? "Testing..." : "Test Connection"}
        </button>

        <button
          onClick={handleSave}
          disabled={isSaving || !config.server || !config.email || !config.api_token}
          className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors font-semibold"
        >
          {isSaving ? "Saving..." : "Save Configuration"}
        </button>
      </div>
    </div>
  );
}
