"""Load-bearing ADK 2.x dynamic workflow for TAKHRIJ."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from takhrij.adk_tools import ToolRegistry, build_tool_registry
from takhrij.config import Settings
from takhrij.gate import IssuanceGate
from takhrij.index import CorpusIndex
from takhrij.models import AuditReport, Claim, RetrievalHit, SearchPass, Variant
from takhrij.pipeline import (
    apply_classifications,
    assemble_dossier,
    merge_hits,
    parse_audit,
)
from takhrij.serde import (
    claim_from_dict,
    hit_from_dict,
    plain,
    search_pass_from_dict,
    variant_from_dict,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimInput(StrictModel):
    form: str
    target_sense: str
    cutoff_year_ah: int


class MorphologyOutput(StrictModel):
    forms: list[str] = Field(default_factory=list, max_length=20)
    rationale: str = Field(max_length=800)


class HitContext(StrictModel):
    hit_key: str
    prefix: str
    match: str
    suffix: str
    title: str
    author: str
    comparison_year_ah: int | None
    date_basis: str | None


class AssessmentInput(StrictModel):
    form: str
    target_sense: str
    cutoff_year_ah: int
    audit_notes: list[str] = Field(default_factory=list)
    hits: list[HitContext]


class MatchDecision(StrictModel):
    hit_key: str
    classification: Literal["target_use", "homograph", "quotation", "uncertain"]
    reason: str = Field(max_length=700)
    confidence: float = Field(ge=0.0, le=1.0)


class AssessmentOutput(StrictModel):
    decisions: list[MatchDecision]


class AuditInput(StrictModel):
    form: str
    target_sense: str
    cutoff_year_ah: int
    searched_variants: list[str]
    provisional_verdict: str
    classification_notes: list[str]
    corpus_time_summary: list[str]


class AuditFindingModel(StrictModel):
    kind: Literal[
        "missing_variant",
        "thin_time_slice",
        "weak_classification",
        "metadata_conflict",
        "other",
    ]
    rationale: str = Field(max_length=700)
    missing_variant: str | None = None


class AuditOutput(StrictModel):
    # google-genai only supports string-valued JSON Schema literals.  Keep
    # this a normal boolean; the deterministic Issuance Gate rejects false.
    completed: bool
    findings: list[AuditFindingModel] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True, slots=True)
class WorkflowBundle:
    root_agent: Any
    tools: ToolRegistry


def _build_gemini_model(settings: Settings) -> Any:
    """Create the pinned ADK Gemini model with bounded transient retries."""
    from google.adk.models import Gemini
    from google.genai import types

    return Gemini(
        model=settings.model_id,
        retry_options=types.HttpRetryOptions(
            attempts=5,
            initial_delay=1.0,
            max_delay=16.0,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        ),
    )


def _runner_input_payload(value: Any) -> str | dict[str, Any]:
    """Unwrap the Content object passed by Runner to a function-workflow root."""
    if isinstance(value, (str, dict)):
        return value
    parts = getattr(value, "parts", None)
    if parts is not None:
        text = "".join(str(part.text) for part in parts if getattr(part, "text", None))
        if text:
            return text
    raise ValueError("workflow input must contain a JSON text part")


async def _variants_via_tools(
    ctx: Any,
    tools: ToolRegistry,
    original: str,
    morphological_forms: list[str],
    *,
    max_variants: int,
) -> list[Variant]:
    validated_output = await ctx.run_node(
        tools.validate_variants,
        node_input={"forms": [original, *morphological_forms]},
    )
    validated = validated_output["variants"]
    variants: list[Variant] = []
    seen: set[str] = set()
    for form in validated:
        source = "input" if form == original else "morphologist"
        spelling_output = await ctx.run_node(
            tools.expand_orthographic_variants,
            node_input={"form": form},
        )
        spellings = spelling_output["variants"]
        for spelling in spellings:
            normalized_output = await ctx.run_node(
                tools.normalize,
                node_input={"form": spelling},
            )
            normalized = normalized_output["normalized_form"]
            if not normalized:
                raise ValueError("variant normalized to an empty token")
            if spelling in seen:
                continue
            seen.add(spelling)
            variants.append(
                Variant(
                    spelling,
                    source if spelling == form else "orthographic",
                    form,
                )
            )
            if len(variants) > max_variants:
                raise ValueError(f"expanded variant count exceeds MAX_VARIANTS={max_variants}")
    return variants


async def _retrieve_via_tools(
    ctx: Any,
    tools: ToolRegistry,
    claim: Claim,
    variants: list[Variant],
    *,
    pass_name: str,
    max_hits: int,
) -> tuple[list[RetrievalHit], SearchPass]:
    response = await ctx.run_node(
        tools.retrieve,
        node_input={
            "forms": [variant.surface_form for variant in variants],
            "book_ids": list(claim.book_ids),
            "max_hits": max_hits,
        },
    )
    hits = [hit_from_dict(item) for item in response["hits"]]
    for hit in hits:
        quote_output = await ctx.run_node(
            tools.extract_quote,
            node_input={
                "doc_id": hit.doc_id,
                "raw_start": hit.raw_start,
                "raw_end": hit.raw_end,
            },
        )
        verified_output = await ctx.run_node(
            tools.verify_span,
            node_input={
                "doc_id": hit.doc_id,
                "raw_start": hit.raw_start,
                "raw_end": hit.raw_end,
                "expected": hit.raw_form,
            },
        )
        quote = quote_output["quote"]
        verified = verified_output["verified"]
        if quote != hit.raw_form or not verified:
            raise ValueError(f"deterministic span verification failed: {hit.key}")
    search_pass = SearchPass(
        name=pass_name,
        variants=tuple(variants),
        hit_keys=tuple(hit.key for hit in hits),
        total_hits=int(response["total_hits"]),
        truncated=bool(response["truncated"]),
    )
    return hits, search_pass


def _assessment_payload(
    claim: dict[str, Any], hits: list[dict[str, Any]], audit_notes: list[str]
) -> dict[str, Any]:
    return {
        "form": claim["form"],
        "target_sense": claim["target_sense"],
        "cutoff_year_ah": claim["cutoff_year_ah"],
        "audit_notes": audit_notes,
        "hits": [
            {
                "hit_key": f"{hit['doc_id']}:{hit['raw_start']}:{hit['raw_end']}",
                "prefix": hit["prefix"],
                "match": hit["match"],
                "suffix": hit["suffix"],
                "title": hit["title"],
                "author": hit["author"],
                "comparison_year_ah": (
                    hit["provenance"].get("composition_date_ah")
                    or hit["provenance"].get("author_death_year_ah")
                ),
                "date_basis": (
                    "composition_date_ah"
                    if hit["provenance"].get("composition_date_ah") is not None
                    else "author_death_year_ah"
                    if hit["provenance"].get("author_death_year_ah") is not None
                    else None
                ),
            }
            for hit in hits
        ],
    }


def build_workflow(
    index: CorpusIndex,
    settings: Settings,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> WorkflowBundle:
    """Create one isolated ADK workflow and its deterministic tool registry."""
    from google.adk import Context, Event, Workflow
    from google.adk.agents import LlmAgent
    from google.adk.workflow import node
    from google.genai import types

    tool_registry = build_tool_registry(index, settings)
    generation = types.GenerateContentConfig(temperature=0, max_output_tokens=16384)
    gemini_model = _build_gemini_model(settings)

    morphologist = LlmAgent(
        name="morphologist",
        model=gemini_model,
        input_schema=ClaimInput,
        output_schema=MorphologyOutput,
        include_contents="none",
        mode="single_turn",
        generate_content_config=generation,
        instruction=(
            "You are the Morphologist for an Arabic historical-linguistics audit. "
            "Propose only inflectional or cliticized single-token surface forms "
            "of the same lexeme and the exact target sense. Do not propose "
            "derivational relatives merely sharing a root. Do not expand spelling "
            "variants; deterministic code does that. Return at most 20 forms, "
            "excluding an exact duplicate of the input form. If uncertain, return fewer forms."
        ),
    )
    assessor = LlmAgent(
        name="assessor",
        model=gemini_model,
        input_schema=AssessmentInput,
        output_schema=AssessmentOutput,
        include_contents="none",
        mode="single_turn",
        generate_content_config=generation,
        instruction=(
            "Classify every supplied hit exactly once. target_use means the "
            "highlighted form is used in the stated target sense. homograph means "
            "the same string is a different lexeme or sense. quotation means this "
            "passage attributes or quotes the wording from an earlier or external "
            "source. Use uncertain whenever context is insufficient. Never claim "
            "that a string exists outside the supplied hits. "
            "Keep reasons tied to visible context and preserve each hit_key exactly."
        ),
    )
    devils_advocate = LlmAgent(
        name="devils_advocate",
        model=gemini_model,
        input_schema=AuditInput,
        output_schema=AuditOutput,
        include_contents="none",
        mode="single_turn",
        generate_content_config=generation,
        instruction=(
            "Audit the supplied search TRACE, not the corpus. Look specifically "
            "for omitted inflectional or cliticized forms of the same lexeme, thin "
            "date coverage, weak classification reasons, and metadata conflicts. "
            "A missing_variant must be one Arabic single token and must preserve "
            "the stated lexeme and sense. Do not invent corpus attestations. Mark "
            "completed true even when there are no findings."
        ),
    )

    @node(name="prepare_claim", rerun_on_resume=True)
    async def prepare_claim(ctx: Context, node_input: Any):
        payload = _runner_input_payload(node_input)
        raw = json.loads(payload) if isinstance(payload, str) else payload
        claim = claim_from_dict(raw)
        await ctx.run_node(
            tool_registry.validate_variants,
            node_input={"forms": [claim.form]},
        )
        if not claim.target_sense.strip():
            raise ValueError("target_sense is required")
        if not 1 <= claim.cutoff_year_ah <= 1600:
            raise ValueError("cutoff_year_ah must be between 1 and 1600")
        if claim.corpus_release != settings.corpus_release:
            raise ValueError("claim corpus release differs from the deployed immutable index")
        if claim.book_ids != settings.corpus_book_ids:
            raise ValueError("claim book list differs from the deployed immutable index")
        return Event(output=plain(claim))

    @node(name="retrieve_initial", rerun_on_resume=True)
    async def retrieve_initial(ctx: Context, node_input: dict[str, Any]):
        claim = claim_from_dict(node_input["claim"])
        morphology = node_input["morphology"]
        variants = await _variants_via_tools(
            ctx,
            tool_registry,
            claim.form,
            list(morphology.get("forms", [])),
            max_variants=settings.max_variants,
        )
        hits, search_pass = await _retrieve_via_tools(
            ctx,
            tool_registry,
            claim,
            variants,
            pass_name="initial",
            max_hits=settings.max_matches,
        )
        return Event(
            output={
                "claim": plain(claim),
                "variants": plain(variants),
                "hits": plain(hits),
                "passes": [plain(search_pass)],
            }
        )

    @node(name="classify_initial")
    def classify_initial(node_input: dict[str, Any]):
        hits = [hit_from_dict(item) for item in node_input["trace"]["hits"]]
        classified = apply_classifications(hits, node_input["assessment"].get("decisions", []))
        result = dict(node_input["trace"])
        result["classified"] = plain(classified)
        return Event(output=result)

    @node(name="apply_audit", rerun_on_resume=True)
    async def apply_audit(ctx: Context, node_input: dict[str, Any]):
        trace = dict(node_input["trace"])
        claim = claim_from_dict(trace["claim"])
        audit = parse_audit(node_input["audit"])
        original_variants = [variant_from_dict(item) for item in trace["variants"]]
        requested = list(audit.proposed_variants)
        if requested:
            await ctx.run_node(
                tool_registry.validate_variants,
                node_input={"forms": requested},
            )
        all_morphological = [
            item.surface_form for item in original_variants if item.source == "morphologist"
        ] + requested
        all_variants = await _variants_via_tools(
            ctx,
            tool_registry,
            claim.form,
            all_morphological,
            max_variants=settings.max_variants,
        )
        seen = {item.surface_form for item in original_variants}
        new_variants = [item for item in all_variants if item.surface_form not in seen]
        all_hits = [hit_from_dict(item) for item in trace["hits"]]
        passes = [search_pass_from_dict(item) for item in trace["passes"]]
        if new_variants:
            remaining = max(0, settings.max_matches - len(all_hits))
            new_hits, search_pass = await _retrieve_via_tools(
                ctx,
                tool_registry,
                claim,
                new_variants,
                pass_name="devils_advocate_followup",
                max_hits=remaining,
            )
            all_hits = merge_hits(all_hits, new_hits)
            passes.append(search_pass)
        trace.update(
            variants=plain(all_variants),
            hits=plain(all_hits),
            passes=plain(passes),
            audit=plain(audit),
        )
        return Event(output=trace)

    @node(name="issue_dossier")
    def issue_dossier(node_input: dict[str, Any]):
        trace = node_input["trace"]
        claim = claim_from_dict(trace["claim"])
        hits = [hit_from_dict(item) for item in trace["hits"]]
        matches = apply_classifications(hits, node_input["assessment"].get("decisions", []))
        audit = parse_audit(trace["audit"])
        dossier = assemble_dossier(
            claim=claim,
            variants=[variant_from_dict(item) for item in trace["variants"]],
            matches=matches,
            passes=[search_pass_from_dict(item) for item in trace["passes"]],
            audit=audit,
        )
        IssuanceGate(index).issue(dossier)
        output = plain(dossier)
        return Event(output=output, message=json.dumps(output, ensure_ascii=False))

    @node(name="takhrij_orchestrator", rerun_on_resume=True)
    async def takhrij_orchestrator(ctx: Context, node_input: Any):
        claim = await ctx.run_node(prepare_claim, node_input=node_input)
        morphology = await ctx.run_node(
            morphologist,
            node_input={
                "form": claim["form"],
                "target_sense": claim["target_sense"],
                "cutoff_year_ah": claim["cutoff_year_ah"],
            },
        )
        trace = await ctx.run_node(
            retrieve_initial,
            node_input={"claim": claim, "morphology": plain(morphology)},
        )
        initial_assessment = await ctx.run_node(
            assessor,
            node_input=_assessment_payload(trace["claim"], trace["hits"], []),
        )
        trace = await ctx.run_node(
            classify_initial,
            node_input={"trace": trace, "assessment": plain(initial_assessment)},
        )
        classified = trace["classified"]
        provisional = assemble_dossier(
            claim=claim_from_dict(trace["claim"]),
            variants=[variant_from_dict(item) for item in trace["variants"]],
            matches=[
                apply_classifications(
                    [hit_from_dict(item["hit"])],
                    [
                        {
                            "hit_key": ":".join(
                                str(item["hit"][field])
                                for field in ("doc_id", "raw_start", "raw_end")
                            ),
                            "classification": item["classification"],
                            "reason": item["reason"],
                            "confidence": item["confidence"],
                        }
                    ],
                )[0]
                for item in classified
            ],
            passes=[search_pass_from_dict(item) for item in trace["passes"]],
            audit=AuditReport(completed=False),
        ).provisional_verdict.value
        if progress:
            progress(
                "provisional",
                {
                    "label": f"PROVISIONAL_{provisional}",
                    "verdict": provisional,
                    "searched_variants": len(trace["variants"]),
                    "matches": len(trace["hits"]),
                },
            )
        audit_input = {
            "form": trace["claim"]["form"],
            "target_sense": trace["claim"]["target_sense"],
            "cutoff_year_ah": trace["claim"]["cutoff_year_ah"],
            "searched_variants": [item["surface_form"] for item in trace["variants"]],
            "provisional_verdict": provisional,
            "classification_notes": [
                f"{item['classification']}: {item['reason']}" for item in classified
            ],
            "corpus_time_summary": [
                f"{item['name']}: total_hits={item['total_hits']}, truncated={item['truncated']}"
                for item in trace["passes"]
            ],
        }
        audit = await ctx.run_node(devils_advocate, node_input=audit_input)
        if progress:
            audit_plain = plain(audit)
            progress(
                "devils_advocate",
                {
                    "completed": audit_plain.get("completed", False),
                    "findings": len(audit_plain.get("findings", [])),
                },
            )
        audited_trace = await ctx.run_node(
            apply_audit,
            node_input={"trace": trace, "audit": plain(audit)},
        )
        audit_notes = [item["rationale"] for item in audited_trace["audit"]["findings"]]
        final_assessment = await ctx.run_node(
            assessor,
            node_input=_assessment_payload(
                audited_trace["claim"], audited_trace["hits"], audit_notes
            ),
        )
        return await ctx.run_node(
            issue_dossier,
            node_input={"trace": audited_trace, "assessment": plain(final_assessment)},
        )

    root_agent = Workflow(name="takhrij_root_agent", edges=[("START", takhrij_orchestrator)])
    return WorkflowBundle(root_agent=root_agent, tools=tool_registry)


async def run_claim(
    index: CorpusIndex,
    settings: Settings,
    claim: dict[str, Any],
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one isolated ADK invocation and return the Gate-issued dossier."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    bundle = build_workflow(index, settings, progress)
    session_service = InMemorySessionService()
    session_id = uuid.uuid4().hex
    user_id = "worker"
    app_name = "takhrij"
    await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
    runner = Runner(agent=bundle.root_agent, app_name=app_name, session_service=session_service)
    message = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(claim, ensure_ascii=False, separators=(",", ":")))],
    )
    final_output: dict[str, Any] | None = None
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        output = getattr(event, "output", None)
        if isinstance(output, dict) and output.get("gate_passed") is True:
            final_output = output
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    try:
                        candidate = json.loads(part.text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(candidate, dict) and candidate.get("gate_passed") is True:
                        final_output = candidate
    if final_output is None:
        raise RuntimeError("ADK workflow completed without a Gate-issued dossier")
    return final_output


def run_claim_sync(
    index: CorpusIndex,
    settings: Settings,
    claim: dict[str, Any],
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return asyncio.run(run_claim(index, settings, claim, progress))
