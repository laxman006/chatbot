"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { User } from "@/types/chat";
import JiraConfigPanel from "@/components/admin/JiraConfigPanel";
import JiraSyncPanel from "@/components/admin/JiraSyncPanel";
import AdminGuard from "@/components/AdminGuard";
import { useAuth } from "@/context/AuthContext";

function JiraAdminContent() {
  const router = useRouter();
  const { user: authUser } = useAuth();
  const [activeTab, setActiveTab] = useState<"config" | "sync">("config");

  return (
    <div style={{ padding: '32px', maxWidth: '1200px', margin: '0 auto', fontFamily: 'Inter, system-ui, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '6px', color: '#111827' }}>
            Jira Integration Management
          </h1>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>
            Configure and manage Jira ticket synchronization
          </p>
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
              fontWeight: 600,
              fontSize: '14px',
            }}
          >
            Back to Dashboard
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', borderBottom: '1px solid #e5e7eb' }}>
        <button
          onClick={() => setActiveTab("config")}
          style={{
            padding: '12px 24px',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            color: activeTab === "config" ? '#111827' : '#6b7280',
            fontWeight: 600,
            fontSize: '14px',
            borderBottom: activeTab === "config" ? '2px solid #111827' : '2px solid transparent',
            marginBottom: '-1px',
          }}
        >
          Configuration
        </button>
        <button
          onClick={() => setActiveTab("sync")}
          style={{
            padding: '12px 24px',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            color: activeTab === "sync" ? '#111827' : '#6b7280',
            fontWeight: 600,
            fontSize: '14px',
            borderBottom: activeTab === "sync" ? '2px solid #111827' : '2px solid transparent',
            marginBottom: '-1px',
          }}
        >
          Sync & Status
        </button>
      </div>

      {/* Content */}
      <div>
        {activeTab === "config" && <JiraConfigPanel />}
        {activeTab === "sync" && <JiraSyncPanel />}
      </div>
    </div>
  );
}

export default function JiraAdminPage() {
  return (
    <AdminGuard>
      <JiraAdminContent />
    </AdminGuard>
  );
}
