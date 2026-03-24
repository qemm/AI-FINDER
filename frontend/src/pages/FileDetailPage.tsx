import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchFile } from "../api/client";
import { RuleBadge } from "../components/RuleBadge";

export function FileDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const fileId = Number(id);

  const { data, isLoading, error } = useQuery({
    queryKey: ["file", fileId],
    queryFn: () => fetchFile(fileId),
    enabled: !isNaN(fileId),
  });

  if (isLoading) return <p style={msgStyle}>Loading…</p>;
  if (error || !data) return <p style={{ ...msgStyle, color: "#f38ba8" }}>File not found.</p>;

  return (
    <div style={pageStyle}>
      <button onClick={() => navigate(-1)} style={backBtn}>← Back</button>
      <h1 style={h1Style}>File #{data.id}</h1>

      <table style={metaTable}>
        <tbody>
          <MetaRow label="URL" value={<a href={data.url} target="_blank" rel="noopener noreferrer" style={{ color: "#89b4fa" }}>{data.url}</a>} />
          <MetaRow label="Platform" value={data.platform} />
          <MetaRow label="Indexed" value={data.indexed_at} />
          <MetaRow label="Tags" value={data.tags || "—"} />
          <MetaRow label="Hash" value={<code style={{ fontSize: "0.75rem", color: "#a6e3a1" }}>{data.content_hash}</code>} />
        </tbody>
      </table>

      {data.secrets.length > 0 && (
        <>
          <h2 style={h2Style}>Secrets ({data.secrets.length})</h2>
          <table style={tableStyle}>
            <thead>
              <tr>
                <Th>Rule</Th>
                <Th>Line</Th>
                <Th>Redacted</Th>
                <Th>Context</Th>
              </tr>
            </thead>
            <tbody>
              {data.secrets.map((s) => (
                <tr key={s.id}>
                  <Td><RuleBadge ruleName={s.rule_name} /></Td>
                  <Td>{s.line_number ?? "—"}</Td>
                  <Td><code style={{ fontSize: "0.75rem", color: "#f38ba8" }}>{s.redacted}</code></Td>
                  <Td><pre style={preStyle}>{s.context}</pre></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {data.raw_content && (
        <>
          <h2 style={h2Style}>Raw Content</h2>
          <pre style={rawStyle}>{data.raw_content}</pre>
        </>
      )}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <tr>
      <td style={{ color: "#a6adc8", fontSize: "0.8rem", padding: "0.3rem 0.8rem 0.3rem 0", whiteSpace: "nowrap", verticalAlign: "top" }}>{label}</td>
      <td style={{ padding: "0.3rem 0", fontSize: "0.85rem", color: "#cdd6f4" }}>{value}</td>
    </tr>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th style={{ textAlign: "left", padding: "0.4rem 0.8rem", color: "#a6adc8", fontSize: "0.8rem" }}>{children}</th>;
}

function Td({ children }: { children: React.ReactNode }) {
  return <td style={{ padding: "0.4rem 0.8rem", fontSize: "0.82rem", borderTop: "1px solid #313244", verticalAlign: "top" }}>{children}</td>;
}

const pageStyle: React.CSSProperties = { padding: "1.5rem 2rem", maxWidth: "1000px" };
const h1Style: React.CSSProperties = { fontSize: "1.4rem", margin: "0.75rem 0", color: "#cdd6f4" };
const h2Style: React.CSSProperties = { fontSize: "1rem", color: "#a6adc8", margin: "1.5rem 0 0.5rem" };
const msgStyle: React.CSSProperties = { padding: "2rem", color: "#a6adc8" };
const backBtn: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "#89b4fa",
  cursor: "pointer",
  fontSize: "0.85rem",
  padding: 0,
};
const metaTable: React.CSSProperties = { borderCollapse: "collapse", marginBottom: "0.5rem" };
const tableStyle: React.CSSProperties = { borderCollapse: "collapse", width: "100%", background: "#313244", borderRadius: "8px", overflow: "hidden" };
const preStyle: React.CSSProperties = { fontSize: "0.72rem", whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0, maxWidth: "400px" };
const rawStyle: React.CSSProperties = {
  background: "#181825",
  border: "1px solid #313244",
  borderRadius: "6px",
  padding: "1rem",
  fontSize: "0.78rem",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
  maxHeight: "500px",
  overflowY: "auto",
};
