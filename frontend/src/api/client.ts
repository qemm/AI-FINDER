import type {
  CrawlJobRequest,
  DashboardStats,
  FileDetail,
  FileRecord,
  JobStatus,
  Page,
  PlatformStat,
  ScanJobRequest,
  SecretFinding,
  SecretRuleStat,
  SemanticSearchResult,
} from "../types";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Stats / Dashboard
// ---------------------------------------------------------------------------
export const fetchStats = (): Promise<DashboardStats> =>
  apiFetch<DashboardStats>("/stats");

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------
export const startCrawlJob = (req: CrawlJobRequest): Promise<JobStatus> =>
  apiFetch<JobStatus>("/jobs/crawl", {
    method: "POST",
    body: JSON.stringify(req),
  });

export const startScanJob = (req: ScanJobRequest): Promise<JobStatus> =>
  apiFetch<JobStatus>("/jobs/scan", {
    method: "POST",
    body: JSON.stringify(req),
  });

export const fetchJob = (jobId: string): Promise<JobStatus> =>
  apiFetch<JobStatus>(`/jobs/${jobId}`);

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------
export const fetchFiles = (
  params: { platform?: string; has_secrets?: boolean; page?: number; page_size?: number } = {}
): Promise<Page<FileRecord>> => {
  const qs = new URLSearchParams();
  if (params.platform) qs.set("platform", params.platform);
  if (params.has_secrets !== undefined) qs.set("has_secrets", String(params.has_secrets));
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  return apiFetch<Page<FileRecord>>(`/files?${qs}`);
};

export const fetchFile = (id: number): Promise<FileDetail> =>
  apiFetch<FileDetail>(`/files/${id}`);

export const fetchFileSecrets = (id: number): Promise<SecretFinding[]> =>
  apiFetch<SecretFinding[]>(`/files/${id}/secrets`);

// ---------------------------------------------------------------------------
// Secrets
// ---------------------------------------------------------------------------
export const fetchSecrets = (
  params: { rule_name?: string; platform?: string; page?: number; page_size?: number } = {}
): Promise<Page<SecretFinding>> => {
  const qs = new URLSearchParams();
  if (params.rule_name) qs.set("rule_name", params.rule_name);
  if (params.platform) qs.set("platform", params.platform);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  return apiFetch<Page<SecretFinding>>(`/secrets?${qs}`);
};

export const fetchSecretsStats = (): Promise<SecretRuleStat[]> =>
  apiFetch<SecretRuleStat[]>("/secrets/stats");

// re-export for convenience
export type { PlatformStat, SecretRuleStat, SemanticSearchResult };

// ---------------------------------------------------------------------------
// Semantic Search
// ---------------------------------------------------------------------------
export const semanticSearch = (q: string, n = 10): Promise<SemanticSearchResult[]> => {
  const qs = new URLSearchParams({ q, n: String(n) });
  return apiFetch<SemanticSearchResult[]>(`/search/semantic?${qs}`);
};
