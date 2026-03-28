#!/usr/bin/env python3
"""
server.py — Web server entry point for AI-FINDER.

Starts the FastAPI application with Uvicorn.

Usage
-----
    python server.py [--host HOST] [--port PORT] [--reload]

Environment variables
---------------------
    DB_PATH        Path to the SQLite database (default: ai_finder.db).
    VECTOR_DB_PATH Directory for the ChromaDB vector store (optional).
    LOG_LEVEL      Logging verbosity (default: INFO).
"""

from __future__ import annotations

import argparse
import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-FINDER web server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="TCP port (default: 8000).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes (development mode).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
