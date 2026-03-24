import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSecrets, fetchSecretsStats } from "../api/client";
import { RuleBadge } from "../components/RuleBadge";
import { useNavigate } from "react-router-dom";

export function SecretsPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [ruleName, setRuleName] = useState("");
  const [platform, setPlatform] = useState("");
  const PAGE_SIZE = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["secrets", page, ruleName, platform],
    queryFn: () =>
      fetchSecrets({ page, page_size: PAGE_SIZE, rule_name: ruleName || undefined, platform: platform || undefined }),
  });

  const { data: stats } = useQuery({
    queryKey: ["secrets-stats"],
    queryFn: fetchSecretsStats,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <div style={pageStyle}>
      <h1 style={h1Style}>Secrets</h1>

      {/* Rule breakdown */}
      {stats && (
        <div style={statsBand}>
          {stats.map((s) => (
            <button
              key={s.rule_name}
              onClick={() => { setRuleName(ruleName === s.rule_name ? "" : s.rule_name); setPage(1); }}
              style={{
                ...statBtn,
                outline: ruleName === s.rule_name ? "2px solid #cba6f7" : "none",
              }}
            >
              <RuleBadge ruleName={s.rule_name} />
              <span style={{ marginLeft: "0.35rem", fontWeight: 700 }}>{s.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={filterRow}>
        <input
          placeholder="Filter by platform"
          value={platform}
          onChange={(e) => { setPlatform(e.target.value); setPage(1); }}
          style={inputStyle}
        />
        <input
          placeholder="Filter by rule"
          value={ruleName}
          onChange={(e) => { setRuleName(e.target.value); setPage(1); }}
          style={inputStyle}
        />
      </div>

      {isLoading ? (
        <p style={msgStyle}>Loading…</p>
      ) : (
        <>
          <table style={tableStyle}>
            <thead>
              <tr>
                <Th>Rule</Th>
                <Th>File</Th>
                <Th>Platform</Th>
                <Th>Line</Th>
                <Th>Redacted</Th>
                <Th>Context</Th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((s) => (
                <tr key={s.id} style={{ cursor: "pointer" }} onClick={() => navigate(`/files/${s.file_id}`)}>
                  <Td><RuleBadge ruleName={s.rule_name} /></Td>
                  <Td><span style={{ color: "#89b4fa" }}>#{s.file_id}</span></Td>
                  <Td>{s.platform ?? "—"}</Td>
                  <Td>{s.line_number ?? "—"}</Td>
                  <Td><code style={{ fontSize: "0.75rem", color: "#f38ba8" }}>{s.redacted}</code></Td>
                  <Td><pre style={preStyle}>{s.context}</pre></Td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={pagination}>
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} style={pageBtnStyle}>← Prev</button>
            <span style={{ color: "#a6adc8", fontSize: "0.85rem" }}>
              Page {page} / {totalPages} ({data?.total ?? 0} total)
            </span>
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={pageBtnStyle}>Next →</button>
          </div>
        </>
      )}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ textAlign: "left", padding: "0.4rem 0.8rem", color: "#a6adc8", fontSize: "0.8rem" }}>{children}</th>;
}

function Td({ children }: { children: React.ReactNode }) {
  return <td style={{ padding: "0.4rem 0.8rem", fontSize: "0.82rem", borderTop: "1px solid #313244", verticalAlign: "top" }}>{children}</td>;
}

const pageStyle: React.CSSProperties = { padding: "1.5rem 2rem" };
const h1Style: React.CSSProperties = { fontSize: "1.4rem", marginBottom: "1rem", color: "#cdd6f4" };
const msgStyle: React.CSSProperties = { color: "#a6adc8", padding: "1rem 0" };
const statsBand: React.CSSProperties = { display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" };
const statBtn: React.CSSProperties = {
  background: "#313244",
  border: "none",
  borderRadius: "6px",
  padding: "0.35rem 0.6rem",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  color: "#cdd6f4",
  fontSize: "0.82rem",
};
const filterRow: React.CSSProperties = { display: "flex", gap: "0.75rem", marginBottom: "1rem" };
const inputStyle: React.CSSProperties = {
  padding: "0.4rem 0.75rem",
  borderRadius: "6px",
  border: "1px solid #45475a",
  background: "#181825",
  color: "#cdd6f4",
  fontSize: "0.85rem",
};
const tableStyle: React.CSSProperties = { borderCollapse: "collapse", width: "100%", background: "#313244", borderRadius: "8px", overflow: "hidden" };
const preStyle: React.CSSProperties = { fontSize: "0.72rem", whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0, maxWidth: "300px" };
const pagination: React.CSSProperties = { display: "flex", justifyContent: "center", alignItems: "center", gap: "1rem", marginTop: "1rem" };
const pageBtnStyle: React.CSSProperties = {
  padding: "0.35rem 0.9rem",
  borderRadius: "6px",
  border: "1px solid #45475a",
  background: "#313244",
  color: "#cdd6f4",
  cursor: "pointer",
  fontSize: "0.82rem",
};
