import { useState } from "react";
import { semanticSearch } from "../api/client";
import type { SemanticSearchResult } from "../types";

export function SemanticSearchPage() {
  const [query, setQuery] = useState("");
  const [n, setN] = useState(10);
  const [results, setResults] = useState<SemanticSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await semanticSearch(query.trim(), n);
      setResults(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={pageStyle}>
      <h1 style={h1Style}>Semantic Search</h1>

      <form onSubmit={handleSearch} style={formStyle}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. agent with bash execution permissions"
          style={{ ...inputStyle, flex: 1 }}
        />
        <input
          type="number"
          value={n}
          onChange={(e) => setN(Number(e.target.value))}
          min={1}
          max={100}
          style={{ ...inputStyle, width: "80px" }}
          title="Number of results"
        />
        <button type="submit" disabled={loading} style={btnStyle}>
          {loading ? "…" : "Search"}
        </button>
      </form>

      {error && <p style={{ color: "#f38ba8", marginTop: "0.75rem" }}>{error}</p>}

      {results.length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          {results.map((r, i) => (
            <div key={i} style={resultCard}>
              <div style={resultHeader}>
                <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ color: "#89b4fa", fontWeight: 600, fontSize: "0.9rem" }}>
                  {r.url}
                </a>
                <span style={scoreChip}>{(r.score * 100).toFixed(1)}%</span>
              </div>
              <div style={{ fontSize: "0.78rem", color: "#a6adc8", marginBottom: "0.4rem" }}>
                {r.platform} {r.tags ? `· ${r.tags}` : ""}
              </div>
              <pre style={snippetStyle}>{r.snippet}</pre>
            </div>
          ))}
        </div>
      )}

      {!loading && results.length === 0 && query && <p style={{ color: "#a6adc8", marginTop: "1rem" }}>No results.</p>}
    </div>
  );
}

const pageStyle: React.CSSProperties = { padding: "1.5rem 2rem", maxWidth: "900px" };
const h1Style: React.CSSProperties = { fontSize: "1.4rem", marginBottom: "1rem", color: "#cdd6f4" };
const formStyle: React.CSSProperties = { display: "flex", gap: "0.75rem", alignItems: "center" };
const inputStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderRadius: "6px",
  border: "1px solid #45475a",
  background: "#181825",
  color: "#cdd6f4",
  fontSize: "0.85rem",
};
const btnStyle: React.CSSProperties = {
  padding: "0.5rem 1.25rem",
  borderRadius: "6px",
  border: "none",
  background: "#cba6f7",
  color: "#1e1e2e",
  fontWeight: 700,
  cursor: "pointer",
  fontSize: "0.85rem",
};
const resultCard: React.CSSProperties = {
  background: "#313244",
  borderRadius: "8px",
  padding: "1rem",
  marginBottom: "0.75rem",
};
const resultHeader: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.3rem", gap: "1rem" };
const scoreChip: React.CSSProperties = {
  background: "#45475a",
  borderRadius: "4px",
  padding: "0.15rem 0.5rem",
  fontSize: "0.75rem",
  color: "#a6e3a1",
  whiteSpace: "nowrap",
};
const snippetStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  background: "#181825",
  borderRadius: "4px",
  padding: "0.5rem",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
  margin: 0,
  maxHeight: "160px",
  overflowY: "auto",
};
