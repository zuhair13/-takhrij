"""Source-format adapters that preserve Arabic content and deterministic offsets."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

OPENITI_MAGIC = "######OpenITI#"
OPENITI_HEADER_END = "#META#Header#End#"
PAGE_MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])PageV\d{2,3}P\d{3,4}(?![A-Za-z0-9_])")
MILESTONE_RE = re.compile(r"(?<![A-Za-z0-9_])ms[A-Z]?\d+(?![A-Za-z0-9_])")
LINE_PREFIX_RE = re.compile(r"^[ \t]*(?:###\s*(?:\|+\s*)?|#\s*(?:\|\s*)?|~~\s?)")


class IngestionError(ValueError):
    """Raised when a source cannot be ingested without guessing."""


@dataclass(frozen=True, slots=True)
class IngestedText:
    raw_text: str
    source_sha256: str
    raw_text_sha256: str
    source_format: str
    parser_version: str


def _decode_utf8(source_bytes: bytes, path: Path) -> str:
    try:
        return source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionError(f"source is not valid UTF-8: {path}") from exc


def _strip_token_without_joining_words(text: str, pattern: re.Pattern[str]) -> str:
    def replacement(match: re.Match[str]) -> str:
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        return " " if before.isalpha() and after.isalpha() else ""

    return pattern.sub(replacement, text)


def strip_openiti_markup(source_text: str) -> str:
    """Remove supported OpenITI mARkdown controls without normalizing Arabic.

    The returned string is the canonical raw text stored in SQLite. All posting
    offsets refer to Unicode code points in this exact string. Unsupported or
    malformed headers fail closed instead of triggering heuristic deletion.
    """
    if not source_text.startswith(OPENITI_MAGIC):
        raise IngestionError("openiti_mARkdown source is missing the OpenITI magic header")
    lines = source_text.splitlines(keepends=True)
    header_end = next(
        (index for index, line in enumerate(lines) if line.strip() == OPENITI_HEADER_END),
        None,
    )
    if header_end is None:
        raise IngestionError("openiti_mARkdown source is missing #META#Header#End#")

    output: list[str] = []
    for line in lines[header_end + 1 :]:
        newline = ""
        body = line
        if body.endswith("\r\n"):
            body, newline = body[:-2], "\r\n"
        elif body.endswith(("\r", "\n")):
            body, newline = body[:-1], body[-1:]
        body = LINE_PREFIX_RE.sub("", body, count=1)
        body = body.replace("%~%", " ")
        body = _strip_token_without_joining_words(body, PAGE_MARKER_RE)
        body = _strip_token_without_joining_words(body, MILESTONE_RE)
        output.append(body + newline)
    return "".join(output)


def ingest_source(path: Path, source_format: str, expected_sha256: str) -> IngestedText:
    """Read, hash, parse, and verify one explicitly declared UTF-8 source."""
    source_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if source_sha256 != expected_sha256:
        raise IngestionError(
            f"source SHA-256 mismatch for {path}: expected {expected_sha256}, got {source_sha256}"
        )
    source_text = _decode_utf8(source_bytes, path)
    if source_format == "plain_text":
        raw_text = source_text
        parser_version = "plain_text:v1"
    elif source_format == "openiti_mARkdown":
        raw_text = strip_openiti_markup(source_text)
        parser_version = "openiti_mARkdown:v1"
    else:
        raise IngestionError(f"unsupported source format: {source_format}")
    if not raw_text.strip():
        raise IngestionError(f"ingestion produced an empty document: {path}")
    return IngestedText(
        raw_text=raw_text,
        source_sha256=source_sha256,
        raw_text_sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        source_format=source_format,
        parser_version=parser_version,
    )
