import { useState } from "react";
import { startCrawlJob, startScanJob } from "../api/client";
import { useJobStream } from "../api/sse";
import type { JobStatus } from "../types";

type Mode = "crawl" | "scan";

export function NewJob() {
  const [mode, setMode] = useState<Mode>("crawl");
  const [urlsText, setUrlsText] = useState("");
  const [engines, setEngines] = useState("duckduckgo,google,bing");
  const [maxQueries, setMaxQueries] = useState(20);
  const [maxWebDorks, setMaxWebDorks] = useState(20);
  const [depth, setDepth] = useState(2);
  const [useGithub, setUseGithub] = useState(true);
  const [useGitlab, setUseGitlab] = useState(false);
  const [useWebSearch, setUseWebSearch] = useState(true);

  const [job, setJob] = useState<JobStatus | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { events, status, stats, error: streamError } = useJobStream(job?.job_id ?? null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    try {
      let created: JobStatus;
      if (mode === "scan") {
        const urls = urlsText
          .split(/\n|,/)
          .map((u) => u.trim())
          .filter(Boolean);
        created = await startScanJob({ urls });
      } else {
        created = await startCrawlJob({
          use_github: useGithub,
          use_gitlab: useGitlab,
          use_web_search: useWebSearch,
          engines: engines.split(",").map((e) => e.trim()).filter(Boolean),
          max_web_dorks: maxWebDorks,
          max_queries: maxQueries,
          depth,
        });
      }
      setJob(created);
    } catch (err) {
      setSubmitError(String(err));
    }
  }

  return (
    <div style={pageStyle}>
      <h1 style={h1Style}>New Job</h1>

      {/* Mode selector */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        {(["crawl", "scan"] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{ ...btnStyle, background: mode === m ? "#cba6f7" : "#313244", color: mode === m ? "#1e1e2e" : "#cdd6f4" }}
          >
            {m === "crawl" ? "Crawl (discover)" : "Scan (URLs list)"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} style={formStyle}>
        {mode === "scan" ? (
          <>
            <Label>URLs (one per line or comma-separated)</Label>
            <textarea
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              rows={6}
              style={inputStyle}
              placeholder="https://github.com/user/repo/blob/main/agent.yaml"
            />
          </>
        ) : (
          <>
            <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
              <Checkbox label="GitHub" checked={useGithub} onChange={setUseGithub} />
              <Checkbox label="GitLab" checked={useGitlab} onChange={setUseGitlab} />
              <Checkbox label="Web Search" checked={useWebSearch} onChange={setUseWebSearch} />
            </div>

            <Label>Engines (comma-separated)</Label>
            <input value={engines} onChange={(e) => setEngines(e.target.value)} style={inputStyle} />

            <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
              <div style={{ flex: 1 }}>
                <Label>Max queries (GitHub/GitLab)</Label>
                <input
                  type="number"
                  value={maxQueries}
                  onChange={(e) => setMaxQueries(Number(e.target.value))}
                  style={inputStyle}
                  min={1}
                />
              </div>
              <div style={{ flex: 1 }}>
                <Label>Max web dorks</Label>
                <input
                  type="number"
                  value={maxWebDorks}
                  onChange={(e) => setMaxWebDorks(Number(e.target.value))}
                  style={inputStyle}
                  min={1}
                />
              </div>
              <div style={{ flex: 1 }}>
                <Label>Depth</Label>
                <input
                  type="number"
                  value={depth}
                  onChange={(e) => setDepth(Number(e.target.value))}
                  style={inputStyle}
                  min={1}
                  max={5}
                />
              </div>
            </div>
          </>
        )}

        <button type="submit" style={{ ...btnStyle, background: "#a6e3a1", color: "#1e1e2e", marginTop: "0.5rem" }}>
          Start
        </button>
        {submitError && <p style={{ color: "#f38ba8", fontSize: "0.85rem" }}>{submitError}</p>}
      </form>

      {/* Live feed */}
      {job && (
        <div style={{ marginTop: "2rem" }}>
          <h2 style={{ fontSize: "1rem", color: "#a6adc8" }}>
            Job <code style={{ color: "#cba6f7" }}>{job.job_id}</code> — {status ?? "pending"}
          </h2>
          {streamError && <p style={{ color: "#f38ba8" }}>{streamError}</p>}
          <div style={statsRow}>
            {Object.entries(stats).map(([k, v]) => (
              <span key={k} style={statChip}>
                {k}: <strong>{v}</strong>
              </span>
            ))}
          </div>
          <div style={logBox}>
            {events.slice(-100).map((ev, i) => (
              <div key={i} style={{ fontSize: "0.78rem", lineHeight: 1.5 }}>
                <span style={{ color: "#a6adc8" }}>[{ev.type}]</span>{" "}
                {JSON.stringify(ev.data)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label style={{ fontSize: "0.8rem", color: "#a6adc8", marginBottom: "0.25rem", display: "block" }}>{children}</label>;
}

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ fontSize: "0.85rem", color: "#cdd6f4", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

const pageStyle: React.CSSProperties = { padding: "1.5rem 2rem", maxWidth: "700px" };
const h1Style: React.CSSProperties = { fontSize: "1.4rem", marginBottom: "1rem", color: "#cdd6f4" };
const formStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "0.75rem" };
const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
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
  cursor: "pointer",
  fontWeight: 600,
  fontSize: "0.85rem",
};
const statsRow: React.CSSProperties = { display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" };
const statChip: React.CSSProperties = {
  background: "#313244",
  borderRadius: "4px",
  padding: "0.2rem 0.6rem",
  fontSize: "0.78rem",
  color: "#cdd6f4",
};
const logBox: React.CSSProperties = {
  background: "#181825",
  border: "1px solid #313244",
  borderRadius: "6px",
  padding: "0.75rem",
  maxHeight: "340px",
  overflowY: "auto",
  fontFamily: "monospace",
};
