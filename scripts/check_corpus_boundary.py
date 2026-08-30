#!/usr/bin/env python3
"""Fail if corpus content or derived databases cross repository/build boundaries."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from takhrij.index_builder import build_index, logical_database_sha256

ROOT = Path(__file__).resolve().parents[1]
SQLITE_MAGIC = b"SQLite format 3\x00"
OPENITI_MAGIC = b"######OpenITI#"
SKIP_DIRECTORIES = {".git", ".venv", "__pycache__", "build", "dist", "htmlcov"}
ALLOWED_OPENITI_SHAPED_FIXTURES = {
    Path("tests/fixtures/corpus/openiti-synthetic.txt"),
}
ALLOWED_NON_CORPUS_SQLITE = {Path(".coverage")}
FIXTURE_DATABASE = Path("data/takhrij.db")
FORBIDDEN_TRACKED_PREFIXES = (
    "corpus/",
    "approved-corpus/",
    ".corpus-approval/",
)
FORBIDDEN_TRACKED_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".mARkdown", ".completed")
REQUIRED_GITIGNORE = {
    "/corpus/",
    "/approved-corpus/",
    "/.corpus-approval/",
    "/data/*",
    "*.db",
    "*.sqlite*",
    "*.mARkdown",
    "*.completed",
    "/config/corpus_manifest.approved.json",
    "!/data/takhrij.db",
}
REQUIRED_DOCKERIGNORE = {
    "corpus",
    "approved-corpus",
    ".corpus-approval",
    "data/*",
    "*.db",
    "*.sqlite*",
    "*.mARkdown",
    "*.completed",
    "config/corpus_manifest.approved.json",
    "!data/takhrij.db",
}
REQUIRED_MANIFEST_RULES = {
    "prune corpus",
    "prune approved-corpus",
    "prune .corpus-approval",
    "prune data",
    "global-exclude *.db",
    "global-exclude *.sqlite",
    "global-exclude *.sqlite3",
    "global-exclude *.mARkdown",
    "global-exclude *.completed",
    "exclude config/corpus_manifest.approved.json",
}


def _tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        path
        for item in result.stdout.split(b"\x00")
        if item
        for path in (Path(item.decode("utf-8")),)
        if (root / path).is_file()
    ]


def fixture_database_is_reproducible(root: Path, database_path: Path) -> bool:
    manifest = root / "config" / "corpus_manifest.fixture.json"
    if not manifest.is_file() or not database_path.is_file():
        return False
    with tempfile.TemporaryDirectory(prefix="takhrij-boundary-") as directory:
        rebuilt = Path(directory) / "takhrij.db"
        build_index(manifest, rebuilt)
        return logical_database_sha256(database_path) == logical_database_sha256(rebuilt)


def find_workspace_leaks(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(
            part in SKIP_DIRECTORIES for part in path.relative_to(root).parts
        ):
            continue
        relative = path.relative_to(root)
        try:
            with path.open("rb") as stream:
                prefix = stream.read(max(len(SQLITE_MAGIC), len(OPENITI_MAGIC)))
        except OSError as exc:
            findings.append(f"{relative}: cannot inspect file: {exc}")
            continue
        if (
            prefix == SQLITE_MAGIC
            and relative not in ALLOWED_NON_CORPUS_SQLITE
            and (
                relative != FIXTURE_DATABASE
                or not fixture_database_is_reproducible(root, path)
            )
        ):
            findings.append(f"{relative}: SQLite database inside repository workspace")
        if relative not in ALLOWED_OPENITI_SHAPED_FIXTURES and prefix.startswith(OPENITI_MAGIC):
            findings.append(f"{relative}: OpenITI content inside repository workspace")
    return findings


def find_tracked_leaks(root: Path) -> list[str]:
    findings: list[str] = []
    for path in _tracked_files(root):
        normalized = path.as_posix()
        if normalized.startswith(FORBIDDEN_TRACKED_PREFIXES):
            findings.append(f"{normalized}: forbidden corpus/approval path is tracked")
        if normalized == FIXTURE_DATABASE.as_posix():
            if not fixture_database_is_reproducible(root, root / path):
                findings.append(f"{normalized}: tracked fixture database is not reproducible")
        elif normalized.lower().endswith(
            tuple(item.lower() for item in FORBIDDEN_TRACKED_SUFFIXES)
        ):
            findings.append(f"{normalized}: corpus or derived-data file type is tracked")
    return findings


def _missing_lines(path: Path, required: set[str]) -> list[str]:
    lines = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return sorted(required - lines)


def find_build_context_gaps(root: Path) -> list[str]:
    findings: list[str] = []
    for item in _missing_lines(root / ".gitignore", REQUIRED_GITIGNORE):
        findings.append(f".gitignore: missing {item}")
    for item in _missing_lines(root / ".dockerignore", REQUIRED_DOCKERIGNORE):
        findings.append(f".dockerignore: missing {item}")
    for item in _missing_lines(root / "MANIFEST.in", REQUIRED_MANIFEST_RULES):
        findings.append(f"MANIFEST.in: missing {item}")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8").lower()
    for instruction in ("add data", "copy corpus", "add corpus"):
        if instruction in dockerfile:
            findings.append(f"Dockerfile: forbidden instruction contains {instruction!r}")
    if "copy data/takhrij.db ./data/takhrij.db" not in dockerfile:
        findings.append("Dockerfile: exact baked fixture database COPY is missing")
    if "chmod 0444 /app/data/takhrij.db" not in dockerfile:
        findings.append("Dockerfile: baked database is not made read-only")
    if "arg allow_approved_corpus_image=fixture_only" not in dockerfile:
        findings.append("Dockerfile: approved corpus image opt-in ARG is missing")
    if "python -m takhrij.image_gate" not in dockerfile:
        findings.append("Dockerfile: image corpus gate is missing")
    if "/corpus" in dockerfile or "volume [" in dockerfile:
        findings.append("Dockerfile: runtime-mounted corpus path is forbidden")
    return findings


def main() -> None:
    findings = [
        *find_workspace_leaks(ROOT),
        *find_tracked_leaks(ROOT),
        *find_build_context_gaps(ROOT),
    ]
    if findings:
        raise SystemExit("\n".join(findings))
    print("corpus boundary scan: clean")


if __name__ == "__main__":
    main()
