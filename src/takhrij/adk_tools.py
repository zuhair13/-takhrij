"""Deterministic functions exposed as an auditable ADK tool registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from takhrij.config import Settings
from takhrij.index import CorpusIndex
from takhrij.models import Variant
from takhrij.normalization import (
    expand_orthographic_variants as expand_spellings,
)
from takhrij.normalization import (
    normalize_token,
)
from takhrij.normalization import (
    validate_variants as validate_variant_forms,
)
from takhrij.serde import plain


@dataclass(frozen=True, slots=True)
class ToolRegistry:
    normalize: Any
    expand_orthographic_variants: Any
    validate_variants: Any
    retrieve: Any
    extract_quote: Any
    verify_span: Any
    adk_tools: tuple[Any, ...]


def build_tool_registry(index: CorpusIndex, settings: Settings) -> ToolRegistry:
    from google.adk.tools import FunctionTool

    def normalize(form: str) -> dict[str, str]:
        """Return the documented non-destructive retrieval normalization of one token."""
        return {"normalized_form": normalize_token(form)}

    def expand_orthographic_variants(form: str) -> dict[str, list[str]]:
        """Enumerate documented orthographic spellings; never merge grammatical letters."""
        return {"variants": expand_spellings(form, max_variants=settings.max_variants)}

    def validate_variants(forms: list[str]) -> dict[str, list[str]]:
        """Reject malformed, multi-token, or excessive candidate variants."""
        return {"variants": validate_variant_forms(forms, max_variants=settings.max_variants)}

    def retrieve(
        forms: list[str], book_ids: list[str], max_hits: int | None = None
    ) -> dict[str, object]:
        """Retrieve every exact normalized token match up to the declared safety bound."""
        if not set(book_ids).issubset(set(settings.corpus_book_ids)):
            raise ValueError("requested books fall outside the server-declared corpus")
        limit = settings.max_matches if max_hits is None else int(max_hits)
        if not 0 <= limit <= settings.max_matches:
            raise ValueError("max_hits falls outside the server-declared safety bound")
        variants = [Variant(form, "tool") for form in validate_variants(forms)["variants"]]
        hits, total, truncated = index.search(
            variants,
            book_ids=tuple(book_ids),
            max_hits=limit,
        )
        return {"hits": plain(hits), "total_hits": total, "truncated": truncated}

    def extract_quote(doc_id: str, raw_start: int, raw_end: int) -> dict[str, str]:
        """Extract a raw quote at trusted Unicode code-point offsets."""
        document = index.get_document(doc_id)
        if document is None:
            raise ValueError("unknown source document")
        return {"quote": document.raw_text[raw_start:raw_end]}

    def verify_span(doc_id: str, raw_start: int, raw_end: int, expected: str) -> dict[str, bool]:
        """Verify that the exact UTF-8 bytes occur at the recorded code-point span."""
        document = index.get_document(doc_id)
        actual = document.raw_text[raw_start:raw_end] if document else ""
        return {
            "verified": actual.encode("utf-8") == expected.encode("utf-8")
            and index.verify_raw_span(doc_id, raw_start, raw_end, expected)
        }

    functions = (
        normalize,
        expand_orthographic_variants,
        validate_variants,
        retrieve,
        extract_quote,
        verify_span,
    )
    adk_tools = tuple(FunctionTool(func=function) for function in functions)
    tools_by_name = {tool.name: tool for tool in adk_tools}
    return ToolRegistry(
        normalize=tools_by_name["normalize"],
        expand_orthographic_variants=tools_by_name["expand_orthographic_variants"],
        validate_variants=tools_by_name["validate_variants"],
        retrieve=tools_by_name["retrieve"],
        extract_quote=tools_by_name["extract_quote"],
        verify_span=tools_by_name["verify_span"],
        adk_tools=adk_tools,
    )
