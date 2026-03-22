#!/usr/bin/env python3
"""
poc.py — AI-FINDER Proof of Concept

Demonstrates the full pipeline:
  1. Generate search queries (dorks / GitHub API / GitLab API / S3).
  2. Fetch a list of URLs asynchronously.
  3. Extract system-prompt blocks.
  4. Classify the platform (Claude, OpenAI, Cursor, …).
  5. Scan for leaked secrets.
  6. Persist to SQLite and export to JSON.

Usage
-----
    # Search a list of known URLs (no token needed)
    python poc.py --urls urls.txt --db results.db --json results.json

    # Use GitHub Code Search API (token recommended)
    python poc.py --github-search --token <GITHUB_TOKEN> --db results.db

    # Use GitLab Search API (token recommended)
    python poc.py --gitlab-search --gitlab-token <GITLAB_TOKEN> --db results.db

    # Crawl GitHub/GitLab APIs and update urls.txt
    python poc.py --crawl --token <GITHUB_TOKEN> --urls-file urls.txt

    # Enumerate AI config paths on a specific domain (gobuster / wfuzz style)
    python poc.py --crawl --target https://example.com --no-github --no-gitlab --urls-file urls.txt

    # Combine API search with direct path enumeration
    python poc.py --crawl --token <GITHUB_TOKEN> --target https://example.com --urls-file urls.txt

    # Just print the generated dorks / queries
    python poc.py --list-dorks
    python poc.py --list-s3-dorks
    python poc.py --list-github-queries
    python poc.py --list-gitlab-queries
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ai_finder.discovery import GoogleDorkGenerator, GitHubQueryGenerator, GitLabQueryGenerator, S3DorkGenerator
from ai_finder.extractor import FileExtractor
from ai_finder.logger import configure_logging, get_logger
from ai_finder.processor import FileProcessor
from ai_finder.scanner import SecretScanner
from ai_finder.storage import Storage
from ai_finder.vector_store import VectorStore
from ai_finder.crawler import Crawler

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Demo URLs — a small set of real, publicly visible AI config files on GitHub
# ---------------------------------------------------------------------------

DEMO_URLS: list[str] = [
    # GitHub (raw content)
    "https://raw.githubusercontent.com/anthropics/anthropic-cookbook/main/README.md",
    "https://raw.githubusercontent.com/langchain-ai/langchain/master/README.md",
    "https://raw.githubusercontent.com/joaomdmoura/crewAI/main/README.md",
    # GitLab (blob URL — will be converted to raw by the extractor)
    "https://gitlab.com/gitlab-org/gitlab/-/blob/master/README.md",
]


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def print_dorks(args: argparse.Namespace) -> None:
    gen = GoogleDorkGenerator()
    dorks = gen.all_dorks()
    print(f"\n=== Google Dorks ({len(dorks)} total) ===\n")
    for d in dorks:
        print(f"[{d.tags[0] if d.tags else 'general'}] {d.query}")


def print_s3_dorks(args: argparse.Namespace) -> None:
    gen = S3DorkGenerator()
    dorks = gen.all_dorks()
    print(f"\n=== S3 Discovery Dorks ({len(dorks)} total) ===\n")
    for d in dorks:
        print(f"[{d.tags[0] if d.tags else 'general'}] {d.query}")


def print_github_queries(args: argparse.Namespace) -> None:
    gen = GitHubQueryGenerator()
    queries = gen.all_queries()
    print(f"\n=== GitHub Code Search Queries ({len(queries)} total) ===\n")
    for q in queries:
        print(f"[{q.tags[0] if q.tags else 'general'}] {q.query}")


def print_gitlab_queries(args: argparse.Namespace) -> None:
    gen = GitLabQueryGenerator()
    queries = gen.all_queries()
    print(f"\n=== GitLab Search Queries ({len(queries)} total) ===\n")
    for q in queries:
        print(f"[{q.tags[0] if q.tags else 'general'}] {q.query}")


async def run_crawl(args: argparse.Namespace) -> None:
    """Crawl GitHub/GitLab APIs and update the urls.txt file."""
    urls_file = args.urls_file or "urls.txt"
    print(f"[*] Crawling for AI agent config files…")
    print(f"    urls file : {urls_file}")
    if args.target:
        print(f"    target    : {args.target}")

    crawler = Crawler(
        github_token=args.token,
        gitlab_token=args.gitlab_token,
        captcha_pause=not args.no_captcha_pause,
    )

    new_urls = await crawler.crawl(
        urls_file=urls_file,
        target_url=args.target,
        use_github=not args.no_github,
        use_gitlab=not args.no_gitlab,
        max_queries=args.max_queries,
        check_reachability=not args.no_check,
    )

    if new_urls:
        print(f"\n[✓] {len(new_urls)} new URL(s) added to '{urls_file}':")
        for url in new_urls:
            print(f"    {url}")

        # Fetch content, classify, scan for secrets, store in DB + JSON.
        print(f"\n[*] Fetching & storing {len(new_urls)} discovered URL(s)…")
        await run_pipeline(
            urls=list(new_urls),
            db_path=args.db,
            json_path=args.json,
            github_token=args.token,
            github_search=False,   # already searched above
            gitlab_token=args.gitlab_token,
            gitlab_search=False,   # already searched above
            verbose=args.verbose,
            vector_db_path=args.vector_db,
            semantic_query=None,
        )
    else:
        print(f"\n[i] No new URLs found (file '{urls_file}' unchanged).")


# ---------------------------------------------------------------------------
# Main async pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(
    urls: list[str],
    db_path: str,
    json_path: str,
    github_token: str | None,
    github_search: bool,
    gitlab_token: str | None,
    gitlab_search: bool,
    verbose: bool,
    vector_db_path: str | None = None,
    semantic_query: str | None = None,
) -> None:
    storage = Storage(db_path)
    processor = FileProcessor()
    scanner = SecretScanner()

    # Initialise vector store if requested
    vector_store: VectorStore | None = None
    if vector_db_path is not None or semantic_query is not None:
        vdb_dir = vector_db_path or "vector_db"
        vector_store = VectorStore(persist_directory=vdb_dir)
        print(f"[i] Vector store initialised at '{vdb_dir}' "
              f"({vector_store.count()} documents already indexed).")

    # If a semantic query is provided without URLs, run search-only mode
    if semantic_query and not urls and not (github_search or gitlab_search):
        _run_semantic_search(vector_store, semantic_query, verbose)
        return

    async with FileExtractor(github_token=github_token) as extractor:
        # Optionally expand URL list via GitHub Code Search
        if github_search:
            print("\n[*] Searching GitHub for AI agent config files…")
            gh_gen = GitHubQueryGenerator()
            search_queries = gh_gen.all_queries()[:5]  # limit for demo
            for sq in search_queries:
                print(f"    Query: {sq.query}")
                found = await extractor.search_github(sq.query, per_page=5)
                urls.extend(found)
                print(f"    → {len(found)} URLs found")

        # Optionally expand URL list via GitLab Search API
        if gitlab_search:
            print("\n[*] Searching GitLab for AI agent config files…")
            gl_gen = GitLabQueryGenerator()
            gl_queries = gl_gen.all_queries()[:5]  # limit for demo
            for sq in gl_queries:
                print(f"    Query: {sq.query}")
                found = await extractor.search_gitlab(
                    sq.query, per_page=5, gitlab_token=gitlab_token
                )
                urls.extend(found)
                print(f"    → {len(found)} URLs found")

        urls = list(dict.fromkeys(urls))  # deduplicate, preserve order
        print(f"\n[*] Fetching {len(urls)} URL(s)…")

        extracted_files = await extractor.fetch_many(urls, concurrency=5)

    print(f"[*] Processing {len(extracted_files)} file(s)…\n")

    saved = 0
    for ef in extracted_files:
        if not ef.is_valid:
            print(f"  [SKIP] {ef.url} — {ef.error}")
            continue

        processed = processor.process(ef)
        secret_report = scanner.report(ef.raw_content, ef.url)

        row_id = storage.save(processed)
        if vector_store is not None:
            vector_store.index(processed)
        saved += 1

        print(f"  [OK] {ef.url}")
        print(f"       platform  : {processed.platform} (conf={processed.confidence:.0%})")
        print(f"       tags      : {', '.join(processed.tags) or '—'}")
        print(f"       hash      : {ef.content_hash[:16]}…")
        print(f"       db row id : {row_id}")

        if secret_report["has_secrets"]:
            print(f"       ⚠ SECRETS FOUND: {secret_report['secret_count']} finding(s)")
            for f in secret_report["findings"]:
                print(f"         • [{f['rule']}] line {f['line']}: {f['redacted']}")

        if verbose and processed.model_dna.persona:
            print(f"       persona   : {processed.model_dna.persona[:80]}…")
        if verbose and ef.system_prompt_blocks:
            print(f"       prompt blocks: {len(ef.system_prompt_blocks)}")

        print()

    print(f"[✓] Saved {saved}/{len(extracted_files)} file(s) to '{db_path}'.")

    if vector_store is not None:
        print(f"[✓] Vector store now contains {vector_store.count()} document(s).")
        if semantic_query:
            _run_semantic_search(vector_store, semantic_query, verbose)

    if json_path:
        storage.export_json(json_path)
        print(f"[✓] JSON export written to '{json_path}'.")

    total = storage.count()
    print(f"[i] Total records in database: {total}")


# ---------------------------------------------------------------------------
# Semantic search helper
# ---------------------------------------------------------------------------


def _run_semantic_search(
    vector_store: "VectorStore",
    query: str,
    verbose: bool,
) -> None:
    """Print semantic search results for *query* against *vector_store*."""
    print(f"\n[*] Semantic search: \"{query}\"")
    results = vector_store.search(query, n_results=10)
    if not results:
        print("    No results found (index may be empty).")
        return
    print(f"    {len(results)} result(s):\n")
    for i, r in enumerate(results, start=1):
        secrets_flag = " ⚠ [secrets]" if r["has_secrets"] else ""
        print(f"  {i}. [{r['platform']}]{secrets_flag} {r['url']}")
        print(f"     distance : {r['distance']}")
        if r["tags"]:
            print(f"     tags     : {r['tags']}")
        if verbose:
            excerpt = r["document"].replace("\n", " ")[:120]
            print(f"     excerpt  : {excerpt}…")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-FINDER PoC — discover AI agent config files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--urls",
        metavar="FILE",
        help="Path to a text file with one URL per line to process.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run against the built-in demo URL list.",
    )
    parser.add_argument(
        "--github-search",
        action="store_true",
        help="Expand URL list via GitHub Code Search API.",
    )
    parser.add_argument(
        "--token",
        metavar="GITHUB_TOKEN",
        help="GitHub personal access token (recommended for API search).",
    )
    parser.add_argument(
        "--gitlab-search",
        action="store_true",
        help="Expand URL list via GitLab Search API.",
    )
    parser.add_argument(
        "--gitlab-token",
        metavar="GITLAB_TOKEN",
        help="GitLab personal access token (recommended for GitLab search).",
    )
    parser.add_argument(
        "--db",
        default="ai_finder.db",
        metavar="FILE",
        help="SQLite database path (default: ai_finder.db).",
    )
    parser.add_argument(
        "--json",
        default="",
        metavar="FILE",
        help="Optional JSON export path.",
    )
    parser.add_argument(
        "--list-dorks",
        action="store_true",
        help="Print all generated Google dorks and exit.",
    )
    parser.add_argument(
        "--list-s3-dorks",
        action="store_true",
        help="Print all generated S3 discovery dorks and exit.",
    )
    parser.add_argument(
        "--list-github-queries",
        action="store_true",
        help="Print all generated GitHub search queries and exit.",
    )
    parser.add_argument(
        "--list-gitlab-queries",
        action="store_true",
        help="Print all generated GitLab search queries and exit.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print extra detail per file.",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help=(
            "Crawl GitHub and GitLab APIs to discover AI agent config URLs "
            "and update the urls file (see --urls-file)."
        ),
    )
    parser.add_argument(
        "--urls-file",
        metavar="FILE",
        default="urls.txt",
        help="Path to the URLs text file updated by --crawl (default: urls.txt).",
    )
    parser.add_argument(
        "--target",
        metavar="URL",
        default=None,
        help=(
            "Base URL of a target domain to enumerate AI config file paths "
            "against (e.g. https://example.com).  The crawler will probe "
            "each known AI config filename directly under this URL — similar "
            "to how gobuster or wfuzz discover paths — in addition to any "
            "GitHub/GitLab API search results.  Use with --crawl."
        ),
    )
    parser.add_argument(
        "--no-github",
        action="store_true",
        help="Skip GitHub Code Search during --crawl.",
    )
    parser.add_argument(
        "--no-gitlab",
        action="store_true",
        help="Skip GitLab blob search during --crawl.",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="Skip reachability check during --crawl (write all discovered URLs).",
    )
    parser.add_argument(
        "--no-captcha-pause",
        action="store_true",
        help=(
            "Disable interactive CAPTCHA handling during web search. "
            "When a search engine returns a CAPTCHA page the query is "
            "silently skipped instead of opening a browser and waiting "
            "for user input. Useful in headless / CI environments."
        ),
    )
    parser.add_argument(
        "--max-queries",
        metavar="N",
        type=int,
        default=None,
        help="Limit the number of search queries sent per platform during --crawl.",
    )
    parser.add_argument(
        "--vector-db",
        metavar="DIR",
        default=None,
        help="Directory for the ChromaDB vector store (enables indexing).",
    )
    parser.add_argument(
        "--semantic-search",
        metavar="QUERY",
        default=None,
        help=(
            "Run a semantic search against the vector store after indexing. "
            "Example: --semantic-search \"agents with bash execution permissions\""
        ),
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=(
            "Logging verbosity for the ai_finder package "
            "(default: INFO). Use DEBUG to see every HTTP call "
            "and search query."
        ),
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        default=None,
        help="Optional path to write log output to a file (in addition to stderr).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    configure_logging(level=args.log_level, log_file=args.log_file)
    log.debug("main  args=%s", args)

    if args.list_dorks:
        print_dorks(args)
        return

    if args.list_s3_dorks:
        print_s3_dorks(args)
        return

    if args.list_github_queries:
        print_github_queries(args)
        return

    if args.list_gitlab_queries:
        print_gitlab_queries(args)
        return

    if args.crawl:
        asyncio.run(run_crawl(args))
        return

    urls: list[str] = []

    if args.urls:
        path = Path(args.urls)
        if not path.exists():
            print(f"Error: file not found: {args.urls}", file=sys.stderr)
            sys.exit(1)
        urls = [line.strip() for line in path.read_text().splitlines() if line.strip()]

    if args.demo or not urls:
        print("[i] Using built-in demo URLs.")
        urls = list(DEMO_URLS)

    asyncio.run(
        run_pipeline(
            urls=urls,
            db_path=args.db,
            json_path=args.json,
            github_token=args.token,
            github_search=args.github_search,
            gitlab_token=args.gitlab_token,
            gitlab_search=args.gitlab_search,
            verbose=args.verbose,
            vector_db_path=args.vector_db,
            semantic_query=args.semantic_search,
        )
    )


if __name__ == "__main__":
    main()
