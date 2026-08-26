from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.adk.tools import FunctionTool
from google.adk.workflow import node

from takhrij.agent import _build_gemini_model, build_workflow, run_claim
from takhrij.config import Settings
from takhrij.index import CorpusIndex
from takhrij.index_builder import build_index

ROOT = Path(__file__).resolve().parents[1]


def fake_llm_agent(*, name, **_kwargs):
    @node(name=f"fake_{name}")
    def fake(node_input):
        if name == "morphologist":
            return {"forms": [], "rationale": "fixture"}
        if name == "assessor":
            return {
                "decisions": [
                    {
                        "hit_key": hit["hit_key"],
                        "classification": "target_use",
                        "reason": "synthetic fixture",
                        "confidence": 1.0,
                    }
                    for hit in node_input["hits"]
                ]
            }
        if name == "devils_advocate":
            return {
                "completed": True,
                "findings": [
                    {
                        "kind": "missing_variant",
                        "rationale": "attached clitic",
                        "missing_variant": "بالتخريج",
                    }
                ],
            }
        raise AssertionError(name)

    return fake


class AgentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "fixture.db"
        build_index(ROOT / "config" / "corpus_manifest.fixture.json", db_path)
        self.settings = Settings(
            corpus_db_path=db_path,
            corpus_release="FIXTURE-ONLY",
            corpus_book_ids=("fixture-early", "fixture-late"),
            pubsub_audience="http://local/worker",
            pubsub_service_account="local@example.invalid",
        )
        self.index = CorpusIndex(db_path)
        self.claim = {
            "form": "تخريج",
            "target_sense": "دليل يُستند إليه في الاستدلال",
            "cutoff_year_ah": 500,
            "corpus_release": "FIXTURE-ONLY",
            "book_ids": ["fixture-early", "fixture-late"],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_registered_tool_surface_is_exact(self):
        bundle = build_workflow(self.index, self.settings)
        self.assertEqual(bundle.root_agent.name, "takhrij_root_agent")
        self.assertEqual(
            [tool.name for tool in bundle.tools.adk_tools],
            [
                "normalize",
                "expand_orthographic_variants",
                "validate_variants",
                "retrieve",
                "extract_quote",
                "verify_span",
            ],
        )

    def test_gemini_model_retries_transient_capacity_errors(self):
        model = _build_gemini_model(self.settings)
        self.assertEqual(model.model, "gemini-3.5-flash")
        self.assertEqual(model.retry_options.attempts, 5)
        self.assertEqual(model.retry_options.initial_delay, 1.0)
        self.assertEqual(model.retry_options.max_delay, 16.0)
        self.assertEqual(
            model.retry_options.http_status_codes,
            [408, 429, 500, 502, 503, 504],
        )

    def test_actual_adk_runner_executes_reversal_and_gate(self):
        progress = []
        tool_calls = []
        original_run_async = FunctionTool.run_async

        async def track_tool(tool, **kwargs):
            tool_calls.append(tool.name)
            return await original_run_async(tool, **kwargs)

        with (
            patch("google.adk.agents.LlmAgent", side_effect=fake_llm_agent),
            patch.object(FunctionTool, "run_async", track_tool),
        ):
            dossier = asyncio.run(
                run_claim(
                    self.index,
                    self.settings,
                    self.claim,
                    lambda stage, details: progress.append((stage, details)),
                )
            )
        self.assertEqual(dossier["provisional_verdict"], "NO_EARLIER_MATCH_IN_DECLARED_CORPUS")
        self.assertEqual(dossier["verdict"], "EARLIER_MATCH_FOUND")
        self.assertTrue(dossier["gate_passed"])
        self.assertEqual([stage for stage, _ in progress], ["provisional", "devils_advocate"])
        self.assertEqual(
            [item["surface_form"] for item in dossier["variants"]],
            ["تخريج", "بالتخريج"],
        )
        self.assertEqual(
            set(tool_calls),
            {
                "normalize",
                "expand_orthographic_variants",
                "validate_variants",
                "retrieve",
                "extract_quote",
                "verify_span",
            },
        )


if __name__ == "__main__":
    unittest.main()
