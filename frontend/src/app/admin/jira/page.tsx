"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import JiraConfigPanel from "@/components/admin/JiraConfigPanel";
import JiraSyncPanel from "@/components/admin/JiraSyncPanel";

export default function JiraAdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"config" | "sync">("config");
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    // Check if user is admin
    const checkAuth = async () => {
      try {
        const token = localStorage.getItem("authToken");
        if (!token) {
          router.push("/login");
          return;
        }

        // Verify admin status
        const response = await fetch("/api/proxy/verify-admin", {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          router.push("/login");
          return;
        }

        setIsAuthenticated(true);
      } catch (error) {
        console.error("Auth check failed:", error);
        router.push("/login");
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, [router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
        <div className="text-white text-lg">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            Jira Integration Management
          </h1>
          <p className="text-gray-300">
            Configure and manage Jira ticket synchronization
          </p>
        </div>

        {/* Navigation Tabs */}
        <div className="flex gap-4 mb-6 border-b border-gray-700">
          <button
            onClick={() => setActiveTab("config")}
            className={`px-6 py-3 font-semibold transition-colors ${
              activeTab === "config"
                ? "text-white border-b-2 border-purple-500"
                : "text-gray-400 hover:text-gray-300"
            }`}
          >
            Configuration
          </button>
          <button
            onClick={() => setActiveTab("sync")}
            className={`px-6 py-3 font-semibold transition-colors ${
              activeTab === "sync"
                ? "text-white border-b-2 border-purple-500"
                : "text-gray-400 hover:text-gray-300"
            }`}
          >
            Sync & Status
          </button>
        </div>

        {/* Content */}
        <div className="space-y-6">
          {activeTab === "config" && <JiraConfigPanel />}
          {activeTab === "sync" && <JiraSyncPanel />}
        </div>

        {/* Back Button */}
        <div className="mt-8">
          <button
            onClick={() => router.push("/admin/dashboard")}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
