# AI-FINDER

An OSINT / Cyber-Intelligence engine that discovers, extracts, and classifies AI agent configuration files exposed in public repositories (GitHub, GitLab, Bitbucket) and open S3 buckets.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          AI-FINDER Engine                          │
│                                                                    │
│  ┌──────────────┐   queries   ┌──────────────┐   URLs             │
│  │  Discovery   │ ──────────► │  Extractor   │ ──────────────┐    │
│  │  Module      │             │  (aiohttp)   │               │    │
│  └──────────────┘             └──────────────┘               │    │
│   Google Dorks                  BeautifulSoup                 │    │
│   GitHub API                    Regex patterns                │    │
│   GitLab API                    GitLab/Bitbucket              ▼    │
│   S3 Dorks                      URL conversion     ┌──────────────┐│
│                                                    │  Processor   ││
│                                                    │  (Classify)  ││
│                                                    └──────────────┘│
│                                                     Platform DNA    │
│                                                     Tech Stack      │
│                                                     Constraints     │
│                                                           │         │
│                                                    ┌──────▼───────┐│
│                                                    │   Scanner    ││
│                                                    │  (Secrets)   ││
│                                                    └──────────────┘│
│                                                     API keys        │
│                                                     Tokens          │
│                                                           │         │
│                                                    ┌──────▼───────┐│
│                                                    │   Storage    ││
│                                                    │  SQLite+JSON ││
│                                                    └──────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

### Modules

| Module | File | Responsibility |
|--------|------|----------------|
| **Discovery** | `ai_finder/discovery.py` | Generate Google dorks, GitHub/GitLab API queries, and S3 bucket dorks targeting AI config files |
| **Extractor** | `ai_finder/extractor.py` | Async HTTP fetching (aiohttp), URL normalisation for GitHub/GitLab/Bitbucket, system-prompt block extraction with regex + BeautifulSoup |
| **Processor** | `ai_finder/processor.py` | Platform classification (Claude, OpenAI, Cursor, …) and "Model DNA" extraction (persona, tech stack, ethical constraints) |
| **Scanner** | `ai_finder/scanner.py` | Secret / API-key leak detection using rule-based regex patterns |
| **Storage** | `ai_finder/storage.py` | SQLite persistence (deduplication by content hash) and JSON export |

---

## Target File Patterns

The engine searches for the following file names and content signatures:

### File names
- `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `CURSOR.md`, `.clinerules`
- `COPILOT.md`, `.github/copilot-instructions.md`
- `system_prompt.md`, `system_prompt.txt`
- `langchain_config.{py,yaml,json}`, `crewai_config.{yaml,json}`
- `agent_config.{json,yaml}`, `openai_config.json`, `.env.agents`

### Content signatures (for dorking)
- `"Assistant is a large language model trained by Anthropic"`
- `"You are an expert developer"`
- `"Rules for the agent"`
- `## Instructions`, `## Rules`, `SYSTEM PROMPT`
- Framework identifiers: `langchain`, `crewai`, `openai.api_key`

---

## Search Dorks & Queries

### Google Dorks (examples)

```
intitle:"CLAUDE.md" site:github.com
intitle:"AGENTS.md" site:github.com
intitle:".cursorrules" site:github.com
"Assistant is a large language model trained by Anthropic" (filetype:md OR filetype:txt OR filetype:yaml OR filetype:json) site:github.com
"You are an expert developer" (filetype:md OR filetype:txt ...) site:github.com
inurl:".github/" site:github.com (filetype:md OR filetype:txt)
intitle:"CLAUDE.md" "Rules for the agent" site:github.com
```

### S3 Bucket Discovery Dorks (examples)

```
site:s3.amazonaws.com "CLAUDE.md"
site:*.s3.amazonaws.com "system_prompt"
s3.amazonaws.com "AGENTS.md" site:github.com
```

### GitHub Code Search API (examples)

```
filename:CLAUDE.md
filename:AGENTS.md
"Assistant is a large language model trained by Anthropic"
"Rules for the agent"
path:.github/
filename:CLAUDE.md "You are"
extension:md "system prompt"
```

### GitLab Search API (examples)

```
CLAUDE.md          (scope: blobs)
AGENTS.md          (scope: blobs)
You are Claude     (scope: blobs)
Rules for the agent (scope: blobs)
```

---

## Installation

```bash
pip install -r requirements.txt
```

**Dependencies:** `aiohttp`, `beautifulsoup4`, `lxml`, `aiosqlite`

---

## Usage

### List all dorks and queries

```bash
# Google dorks
python poc.py --list-dorks

# S3 discovery dorks
python poc.py --list-s3-dorks

# GitHub Code Search queries
python poc.py --list-github-queries

# GitLab Search queries
python poc.py --list-gitlab-queries
```

### Scan a list of URLs

```bash
# Create a file with one URL per line
echo "https://github.com/user/repo/blob/main/CLAUDE.md" > urls.txt

python poc.py --urls urls.txt --db results.db --json results.json
```

### Use GitHub / GitLab search APIs

```bash
# GitHub (token strongly recommended to avoid rate limits)
python poc.py --github-search --token ghp_YOUR_TOKEN --db results.db

# GitLab
python poc.py --gitlab-search --gitlab-token glpat_YOUR_TOKEN --db results.db

# Both at once
python poc.py --github-search --token GH_TOKEN \
              --gitlab-search --gitlab-token GL_TOKEN \
              --db results.db --json results.json --verbose
```

### Run the built-in demo

```bash
python poc.py --demo --verbose
```

---

## Output

Each discovered file is stored in SQLite with:

| Field | Description |
|-------|-------------|
| `url` | Original URL of the file |
| `content_hash` | SHA-256 of the raw content (used for deduplication) |
| `platform` | Detected AI platform (`claude`, `openai`, `cursor`, …) |
| `indexed_at` | ISO-8601 timestamp |
| `raw_content` | Full file text |
| `tags` | Comma-separated tags (platform, tech stack, trait flags) |
| `has_secrets` | `1` if leaked credentials were detected |

JSON export example:

```json
{
  "exported_at": "2025-01-01T00:00:00+00:00",
  "total_files": 3,
  "files": [
    {
      "url": "https://...",
      "content_hash": "abc123...",
      "platform": "claude",
      "indexed_at": "2025-01-01T00:00:00+00:00",
      "tags": "claude,has-persona,python",
      "has_secrets": 0
    }
  ],
  "secret_findings": []
}
```

---

## Secret Detection Rules

The scanner applies the following regex rules to every fetched file:

| Rule | Pattern description |
|------|---------------------|
| `openai_api_key` | `sk-` prefixed keys ≥ 20 chars |
| `anthropic_api_key` | `sk-ant-` prefixed keys |
| `github_token` | `gh[pousr]_` prefixed tokens |
| `aws_access_key` | `AKIA` prefixed 20-char keys |
| `aws_secret_key` | `aws_secret_key = ...` assignments |
| `google_api_key` | `AIza` prefixed 35-char keys |
| `huggingface_token` | `hf_` prefixed tokens |
| `hardcoded_api_key_assignment` | Generic `api_key = "..."` patterns |
| `placeholder_leak` | Unfilled `{{OPENAI_API_KEY}}` placeholders |
| `env_var_exposure` | `os.environ["SECRET_KEY"]` exposures |

---

## Supported Platforms (Classification)

| Platform label | Detection signals |
|----------------|-------------------|
| `claude` | `anthropic`, `claude`, `CLAUDE.md`, `claude.ai` |
| `openai` | `openai`, `gpt-3/4`, `chatgpt`, `OPENAI_API_KEY` |
| `cursor` | `.cursorrules`, `cursorai`, `cursor.sh` |
| `copilot` | `github copilot`, `copilot-instructions` |
| `langchain` | `langchain`, `LLMChain`, `AgentExecutor` |
| `crewai` | `crewai`, `CrewAI`, `crew.kickoff` |
| `cline` | `.clinerules`, `cline` |
| `gemini` | `gemini`, `google.generativeai`, `bard` |

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

