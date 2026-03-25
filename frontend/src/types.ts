// ---------------------------------------------------------------------------
// Generic pagination
// ---------------------------------------------------------------------------
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------
export interface FileRecord {
  id: number;
  url: string;
  content_hash: string;
  platform: string;
  indexed_at: string;
  tags: string;
  has_secrets: boolean;
}

export interface SecretFinding {
  id: number;
  file_id: number;
  rule_name: string;
  line_number: number | null;
  redacted: string;
  context: string;
  url?: string;
  platform?: string;
  indexed_at?: string;
}

export interface FileDetail extends FileRecord {
  raw_content: string | null;
  secrets: SecretFinding[];
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------
export interface CrawlJobRequest {
  use_github?: boolean;
  use_gitlab?: boolean;
  use_web_search?: boolean;
  engines?: string[];
  web_dork_sources?: "all" | "web" | "github";
  max_web_dorks?: number;
  target_url?: string;
  max_queries?: number;
  depth?: number;
  github_token?: string;
  gitlab_token?: string;
}

export interface ScanJobRequest {
  urls: string[];
}

export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  stats: Record<string, number>;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Secrets
// ---------------------------------------------------------------------------
export interface SecretRuleStat {
  rule_name: string;
  count: number;
}

export interface PlatformStat {
  platform: string;
  count: number;
}

export interface DashboardStats {
  total_files: number;
  total_secrets: number;
  files_with_secrets: number;
  platforms: PlatformStat[];
  secrets_by_rule: SecretRuleStat[];
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
export interface SemanticSearchResult {
  url: string;
  platform: string;
  tags: string;
  score: number;
  snippet: string;
}
