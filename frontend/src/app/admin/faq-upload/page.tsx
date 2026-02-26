"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import AdminGuard from "@/components/AdminGuard";
import { apiUrl } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UploadResult {
  status: string;
  file: string;
  combination: string;
  docs_added: number;
  total_in_db: number;
  all_combinations: string[];
}

interface CombinationsResult {
  combinations: string[];
  faq_combinations: string[];
  capability_combinations: string[];
  total_docs: number;
  faq_docs: number;
  capability_docs: number;
  db_exists: boolean;
}

type UploadStatus = "idle" | "uploading" | "success" | "error";

// ---------------------------------------------------------------------------
// Main content component (inside AdminGuard)
// ---------------------------------------------------------------------------

function FaqUploadContent() {
  const router = useRouter();

  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [combinations, setCombinations] = useState<CombinationsResult | null>(null);
  const [loadingCombinations, setLoadingCombinations] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchCombinations = useCallback(async () => {
    setLoadingCombinations(true);
    try {
      const res = await fetch(apiUrl("/admin/faq/combinations"), {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setCombinations(data);
      }
    } catch {
      // non-critical — just don't show the panel
    } finally {
      setLoadingCombinations(false);
    }
  }, []);

  useEffect(() => {
    fetchCombinations();
  }, [fetchCombinations]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setUploadStatus("idle");
    setUploadResult(null);
    setErrorMsg("");
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploadStatus("uploading");
    setUploadResult(null);
    setErrorMsg("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      // IMPORTANT: Do NOT set Content-Type header manually — browser must set
      // multipart/form-data boundary automatically when using FormData.
      const res = await fetch(apiUrl("/admin/faq/upload"), {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || `Upload failed (${res.status})`);
      }

      setUploadResult(data as UploadResult);
      setUploadStatus("success");
      // Refresh the combinations panel so new combination shows up immediately
      fetchCombinations();
      // Reset file input
      if (inputRef.current) inputRef.current.value = "";
      setFile(null);
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "Upload failed");
      setUploadStatus("error");
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files?.[0];
    if (dropped && (dropped.name.endsWith(".xlsx") || dropped.name.endsWith(".xls"))) {
      setFile(dropped);
      setUploadStatus("idle");
      setUploadResult(null);
      setErrorMsg("");
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  return (
    <div style={{ padding: "32px", maxWidth: "1000px", margin: "0 auto", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "28px", fontWeight: 700, marginBottom: "6px", color: "#111827" }}>
            FAQ Upload
          </h1>
          <p style={{ color: "#6b7280", fontSize: "14px" }}>
            Upload a Client FAQ Excel file to index it into the capabilities knowledge base.
          </p>
        </div>
        <button
          onClick={() => router.push("/admin/dashboard")}
          style={{
            padding: "10px 14px",
            borderRadius: "10px",
            border: "1px solid #d1d5db",
            background: "white",
            cursor: "pointer",
            color: "#111827",
            fontWeight: 600,
            fontSize: "14px",
          }}
        >
          Back to Dashboard
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>

        {/* ── Left: Upload Panel ── */}
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: "16px", padding: "28px" }}>
          <h2 style={{ fontSize: "16px", fontWeight: 700, marginBottom: "4px", color: "#111827" }}>
            Upload FAQ Excel
          </h2>
          <p style={{ fontSize: "13px", color: "#6b7280", marginBottom: "20px" }}>
            Column A: Question &nbsp;·&nbsp; Column B: Answer
            <br />
            File name sets the combination, e.g. &ldquo;Gmail to Outlook FAQ&apos;s.xlsx&rdquo;
          </p>

          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() => inputRef.current?.click()}
            style={{
              border: `2px dashed ${file ? "#6366f1" : "#d1d5db"}`,
              borderRadius: "12px",
              padding: "36px 24px",
              textAlign: "center",
              cursor: "pointer",
              background: file ? "#f5f3ff" : "#f9fafb",
              transition: "all 0.2s",
              marginBottom: "20px",
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={handleFileChange}
              style={{ display: "none" }}
            />
            {file ? (
              <>
                <div style={{ fontSize: "32px", marginBottom: "8px" }}>📄</div>
                <div style={{ fontWeight: 600, color: "#4f46e5", fontSize: "14px" }}>{file.name}</div>
                <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "4px" }}>
                  {(file.size / 1024).toFixed(1)} KB — click to change
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: "32px", marginBottom: "8px" }}>📤</div>
                <div style={{ fontWeight: 600, color: "#374151", fontSize: "14px" }}>
                  Drop your Excel file here
                </div>
                <div style={{ fontSize: "12px", color: "#9ca3af", marginTop: "4px" }}>
                  or click to browse — .xlsx, .xls accepted
                </div>
              </>
            )}
          </div>

          {/* Upload button */}
          <button
            onClick={handleUpload}
            disabled={!file || uploadStatus === "uploading"}
            style={{
              width: "100%",
              padding: "12px",
              borderRadius: "10px",
              border: "none",
              background: !file || uploadStatus === "uploading" ? "#e5e7eb" : "#4f46e5",
              color: !file || uploadStatus === "uploading" ? "#9ca3af" : "white",
              cursor: !file || uploadStatus === "uploading" ? "not-allowed" : "pointer",
              fontWeight: 700,
              fontSize: "15px",
              transition: "background 0.2s",
            }}
          >
            {uploadStatus === "uploading" ? "Indexing…" : "Upload & Index"}
          </button>

          {/* Status messages */}
          {uploadStatus === "uploading" && (
            <div style={{ marginTop: "16px", padding: "12px", background: "#eff6ff", borderRadius: "8px", fontSize: "13px", color: "#1d4ed8" }}>
              Uploading and indexing FAQ entries into the knowledge base…
            </div>
          )}

          {uploadStatus === "success" && uploadResult && (
            <div style={{ marginTop: "16px", padding: "14px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "10px" }}>
              <div style={{ fontWeight: 700, color: "#15803d", fontSize: "14px", marginBottom: "6px" }}>
                ✓ Indexed successfully
              </div>
              <div style={{ fontSize: "13px", color: "#166534" }}>
                <strong>Combination:</strong> {uploadResult.combination}
              </div>
              <div style={{ fontSize: "13px", color: "#166534" }}>
                <strong>FAQ entries added:</strong> {uploadResult.docs_added}
              </div>
              <div style={{ fontSize: "13px", color: "#166534" }}>
                <strong>Total docs in DB:</strong> {uploadResult.total_in_db}
              </div>
            </div>
          )}

          {uploadStatus === "error" && (
            <div style={{ marginTop: "16px", padding: "14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "10px" }}>
              <div style={{ fontWeight: 700, color: "#dc2626", fontSize: "14px", marginBottom: "4px" }}>
                Upload failed
              </div>
              <div style={{ fontSize: "13px", color: "#b91c1c" }}>{errorMsg}</div>
            </div>
          )}

          {/* Format guide */}
          <div style={{ marginTop: "20px", padding: "14px", background: "#f8fafc", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
            <div style={{ fontWeight: 600, fontSize: "12px", color: "#475569", marginBottom: "8px" }}>
              EXPECTED FORMAT
            </div>
            <table style={{ width: "100%", fontSize: "12px", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "4px 8px", background: "#e2e8f0", borderRadius: "4px", color: "#374151" }}>Column A — Client FAQ</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", background: "#e2e8f0", borderRadius: "4px", color: "#374151" }}>Column B — Response</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: "4px 8px", color: "#6b7280" }}>Will the folder structure be preserved?</td>
                  <td style={{ padding: "4px 8px", color: "#6b7280" }}>Yes, folder structure is preserved.</td>
                </tr>
                <tr>
                  <td style={{ padding: "4px 8px", color: "#6b7280" }}>Are attachments migrated?</td>
                  <td style={{ padding: "4px 8px", color: "#6b7280" }}>Yes, attachments are migrated.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Right: Indexed Combinations Panel ── */}
        <div style={{ background: "white", border: "1px solid #e5e7eb", borderRadius: "16px", padding: "28px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
            <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#111827" }}>
              Indexed Combinations
            </h2>
            <button
              onClick={fetchCombinations}
              disabled={loadingCombinations}
              style={{
                padding: "6px 12px",
                borderRadius: "8px",
                border: "1px solid #d1d5db",
                background: "white",
                cursor: loadingCombinations ? "not-allowed" : "pointer",
                fontSize: "12px",
                color: "#374151",
              }}
            >
              {loadingCombinations ? "Loading…" : "Refresh"}
            </button>
          </div>

          {combinations && (
            <div style={{ display: "flex", gap: "12px", marginBottom: "20px" }}>
              {[
                { label: "Total Docs", value: combinations.total_docs },
                { label: "FAQ Docs", value: combinations.faq_docs },
                { label: "Capability Docs", value: combinations.capability_docs },
              ].map((stat) => (
                <div
                  key={stat.label}
                  style={{
                    flex: 1,
                    background: "#f9fafb",
                    border: "1px solid #e5e7eb",
                    borderRadius: "10px",
                    padding: "12px",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: "22px", fontWeight: 700, color: "#4f46e5" }}>{stat.value}</div>
                  <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "2px" }}>{stat.label}</div>
                </div>
              ))}
            </div>
          )}

          {loadingCombinations && !combinations && (
            <div style={{ padding: "24px", textAlign: "center", color: "#9ca3af", fontSize: "14px" }}>
              Loading…
            </div>
          )}

          {combinations && combinations.combinations.length === 0 && (
            <div style={{ padding: "24px", textAlign: "center", color: "#9ca3af", fontSize: "14px" }}>
              No combinations indexed yet. Upload a FAQ Excel to get started.
            </div>
          )}

          {combinations && combinations.combinations.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "16px", maxHeight: "380px", overflowY: "auto" }}>

              {/* FAQ-uploaded combinations */}
              {combinations.faq_combinations.length > 0 && (
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#059669", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>
                    📋 FAQ Uploaded ({combinations.faq_combinations.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {combinations.faq_combinations.map((combo) => (
                      <div
                        key={combo}
                        style={{
                          padding: "9px 13px",
                          background: "#f0fdf4",
                          border: "1px solid #bbf7d0",
                          borderRadius: "8px",
                          fontSize: "13px",
                          color: "#15803d",
                          fontWeight: 500,
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span style={{ fontSize: "15px" }}>🔀</span>
                        {combo}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Capability/limitation combinations */}
              {combinations.capability_combinations.length > 0 && (
                <div>
                  <div style={{ fontSize: "11px", fontWeight: 700, color: "#6366f1", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "8px" }}>
                    ⚡ Capabilities ({combinations.capability_combinations.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {combinations.capability_combinations.map((combo) => (
                      <div
                        key={combo}
                        style={{
                          padding: "9px 13px",
                          background: "#f5f3ff",
                          border: "1px solid #ede9fe",
                          borderRadius: "8px",
                          fontSize: "13px",
                          color: "#4338ca",
                          fontWeight: 500,
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span style={{ fontSize: "15px" }}>🔀</span>
                        {combo}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!combinations?.db_exists && (
            <div style={{ marginTop: "12px", padding: "10px", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: "8px", fontSize: "12px", color: "#92400e" }}>
              Capabilities DB does not exist yet. Upload a FAQ file or run the capabilities ingest script first.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export — wrapped in AdminGuard
// ---------------------------------------------------------------------------

export default function FaqUploadPage() {
  return (
    <AdminGuard>
      <FaqUploadContent />
    </AdminGuard>
  );
}
