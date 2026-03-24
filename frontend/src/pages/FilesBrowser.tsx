import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFiles } from "../api/client";
import { useNavigate } from "react-router-dom";

export function FilesBrowser() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [platform, setPlatform] = useState("");
  const [hasSecrets, setHasSecrets] = useState<boolean | undefined>(undefined);
  const PAGE_SIZE = 50;

  const { data, isLoading } = useQuery({
    queryKey: ["files", page, platform, hasSecrets],
    queryFn: () => fetchFiles({ page, page_size: PAGE_SIZE, platform: platform || undefined, has_secrets: hasSecrets }),
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1;

  return (
    <div style={pageStyle}>
      <h1 style={h1Style}>Files</h1>

      {/* Filters */}
      <div style={filterRow}>
        <input
          placeholder="Filter by platform"
          value={platform}
          onChange={(e) => { setPlatform(e.target.value); setPage(1); }}
          style={inputStyle}
        />
        <select
          value={hasSecrets === undefined ? "" : String(hasSecrets)}
          onChange={(e) => {
            setHasSecrets(e.target.value === "" ? undefined : e.target.value === "true");
            setPage(1);
          }}
          style={inputStyle}
        >
          <option value="">All files</option>
          <option value="true">With secrets</option>
          <option value="false">Without secrets</option>
        </select>
      </div>

      {isLoading ? (
        <p style={msgStyle}>Loading…</p>
      ) : (
        <>
          <table style={tableStyle}>
            <thead>
              <tr>
                <Th>ID</Th>
                <Th>URL</Th>
                <Th>Platform</Th>
                <Th>Indexed</Th>
                <Th>Secrets</Th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((f) => (
                <tr
                  key={f.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/files/${f.id}`)}
                >
                  <Td>{f.id}</Td>
                  <Td><span title={f.url}>{f.url.length > 60 ? `${f.url.slice(0, 60)}…` : f.url}</span></Td>
                  <Td>{f.platform}</Td>
                  <Td>{f.indexed_at.slice(0, 10)}</Td>
                  <Td>
                    {f.has_secrets ? (
                      <span style={{ color: "#f38ba8", fontWeight: 700 }}>YES</span>
                    ) : (
                      <span style={{ color: "#a6adc8" }}>—</span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div style={pagination}>
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} style={pageBtnStyle}>
              ← Prev
            </button>
            <span style={{ color: "#a6adc8", fontSize: "0.85rem" }}>
              Page {page} / {totalPages} ({data?.total ?? 0} total)
            </span>
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={pageBtnStyle}>
              Next →
            </button>
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
  return <td style={{ padding: "0.4rem 0.8rem", fontSize: "0.82rem", borderTop: "1px solid #313244" }}>{children}</td>;
}

const pageStyle: React.CSSProperties = { padding: "1.5rem 2rem" };
const h1Style: React.CSSProperties = { fontSize: "1.4rem", marginBottom: "1rem", color: "#cdd6f4" };
const msgStyle: React.CSSProperties = { color: "#a6adc8", padding: "1rem 0" };
const filterRow: React.CSSProperties = { display: "flex", gap: "0.75rem", marginBottom: "1rem", flexWrap: "wrap" };
const inputStyle: React.CSSProperties = {
  padding: "0.4rem 0.75rem",
  borderRadius: "6px",
  border: "1px solid #45475a",
  background: "#181825",
  color: "#cdd6f4",
  fontSize: "0.85rem",
};
const tableStyle: React.CSSProperties = {
  borderCollapse: "collapse",
  width: "100%",
  background: "#313244",
  borderRadius: "8px",
  overflow: "hidden",
};
const pagination: React.CSSProperties = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  gap: "1rem",
  marginTop: "1rem",
};
const pageBtnStyle: React.CSSProperties = {
  padding: "0.35rem 0.9rem",
  borderRadius: "6px",
  border: "1px solid #45475a",
  background: "#313244",
  color: "#cdd6f4",
  cursor: "pointer",
  fontSize: "0.82rem",
};
