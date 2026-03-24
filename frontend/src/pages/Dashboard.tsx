import { useQuery } from "@tanstack/react-query";
import { fetchStats } from "../api/client";
import { RuleBadge } from "../components/RuleBadge";

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    refetchInterval: 15_000,
  });

  if (isLoading) return <p style={msgStyle}>Loading stats…</p>;
  if (error) return <p style={{ ...msgStyle, color: "#f38ba8" }}>Failed to load stats.</p>;
  if (!data) return null;

  return (
    <div style={pageStyle}>
      <h1 style={h1Style}>Dashboard</h1>

      {/* KPI cards */}
      <div style={cardsRow}>
        <KpiCard label="Total Files" value={data.total_files} />
        <KpiCard label="Total Secrets" value={data.total_secrets} accent="#f38ba8" />
        <KpiCard label="Files with Secrets" value={data.files_with_secrets} accent="#fab387" />
      </div>

      {/* Platforms */}
      <Section title="Platforms">
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th>Platform</Th>
              <Th>Files</Th>
            </tr>
          </thead>
          <tbody>
            {data.platforms.map((p) => (
              <tr key={p.platform}>
                <Td>{p.platform}</Td>
                <Td>{p.count}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {/* Secrets by rule */}
      <Section title="Secrets by Rule">
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th>Rule</Th>
              <Th>Count</Th>
            </tr>
          </thead>
          <tbody>
            {data.secrets_by_rule.map((r) => (
              <tr key={r.rule_name}>
                <Td>
                  <RuleBadge ruleName={r.rule_name} />
                </Td>
                <Td>{r.count}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function KpiCard({ label, value, accent = "#cba6f7" }: { label: string; value: number; accent?: string }) {
  return (
    <div style={{ ...cardStyle, borderTop: `3px solid ${accent}` }}>
      <div style={{ fontSize: "2rem", fontWeight: 700, color: accent }}>{value}</div>
      <div style={{ fontSize: "0.85rem", color: "#a6adc8" }}>{label}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: "2rem" }}>
      <h2 style={{ fontSize: "1rem", color: "#a6adc8", marginBottom: "0.5rem" }}>{title}</h2>
      {children}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ textAlign: "left", padding: "0.4rem 0.8rem", color: "#a6adc8", fontSize: "0.8rem" }}>{children}</th>;
}

function Td({ children }: { children: React.ReactNode }) {
  return <td style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }}>{children}</td>;
}

const pageStyle: React.CSSProperties = { padding: "1.5rem 2rem", maxWidth: "900px" };
const h1Style: React.CSSProperties = { fontSize: "1.4rem", marginBottom: "1.5rem", color: "#cdd6f4" };
const msgStyle: React.CSSProperties = { padding: "2rem", color: "#a6adc8" };
const cardsRow: React.CSSProperties = { display: "flex", gap: "1rem", flexWrap: "wrap" };
const cardStyle: React.CSSProperties = {
  flex: "1 1 160px",
  background: "#313244",
  borderRadius: "8px",
  padding: "1rem 1.25rem",
  minWidth: "140px",
};
const tableStyle: React.CSSProperties = {
  borderCollapse: "collapse",
  width: "100%",
  background: "#313244",
  borderRadius: "8px",
  overflow: "hidden",
};
