"""Shared pytest hooks for acceptance suites."""

from __future__ import annotations

import os

import pytest

_INVALID_DATABASE_URLS = frozenset(
    {
        "postgresql://...",
        "postgres://...",
        "postgresql://",
        "postgres://",
    }
)


def _looks_like_placeholder(url: str) -> bool:
    if url in _INVALID_DATABASE_URLS or url.endswith("://..."):
        return True
    for prefix in ("postgresql://", "postgres://"):
        if not url.startswith(prefix):
            continue
        remainder = url[len(prefix) :]
        host_part = remainder.split("/", 1)[0]
        if "@" in host_part:
            host_part = host_part.rsplit("@", 1)[-1]
        host = host_part.split(":", 1)[0]
        if host in {"", "..."}:
            return True
    return False


def pytest_configure(config: pytest.Config) -> None:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return
    if _looks_like_placeholder(url):
        pytest.exit(
            "\nDATABASE_URL looks like a placeholder, not a real Postgres connection string.\n"
            "\n"
            "Start Postgres (Docker):\n"
            "  docker compose up -d\n"
            "\n"
            "Then in PowerShell:\n"
            "  $env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5433/dpdp'\n"
            "  uv run pytest tests/ -v\n",
            returncode=1,
        )
