#!/usr/bin/env python3
"""Fail when disallowed runtime provider names appear in repository text files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISALLOWED = ("open" + "ai", "g" + "pt", "anth" + "ropic")
SKIP_PARTS = {".git", ".venv", "__pycache__", "data"}
TEXT_SUFFIXES = {
    "",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def main() -> None:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in DISALLOWED:
            if term in text:
                findings.append(f"{path.relative_to(ROOT)}: contains disallowed runtime term")
    if findings:
        raise SystemExit("\n".join(findings))
    print("runtime provider scan: clean")


if __name__ == "__main__":
    main()
