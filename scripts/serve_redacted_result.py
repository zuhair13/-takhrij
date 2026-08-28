#!/usr/bin/env python3
"""Serve one Gate-issued redacted local-run dossier through the existing TAKHRIJ UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from flask import Flask, Response, render_template

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TEXT_KEYS = {
    "match",
    "prefix",
    "quote",
    "rationale",
    "raw_form",
    "raw_text",
    "reason",
    "suffix",
}


def _reject_unredacted_keys(value: Any, location: str = "dossier") -> None:
    if isinstance(value, dict):
        exposed = FORBIDDEN_TEXT_KEYS.intersection(value)
        if exposed:
            names = ", ".join(sorted(exposed))
            raise ValueError(f"unredacted fields at {location}: {names}")
        for key, nested in value.items():
            _reject_unredacted_keys(nested, f"{location}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_unredacted_keys(nested, f"{location}[{index}]")


def load_redacted_result(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("result must be a readable UTF-8 JSON file") from exc
    if not isinstance(result, dict):
        raise ValueError("result must be a JSON object")
    run_policy = result.get("run_policy")
    corpus = result.get("corpus")
    dossier = result.get("dossier")
    if not all(isinstance(item, dict) for item in (run_policy, corpus, dossier)):
        raise ValueError("result is missing run_policy, corpus, or dossier")
    if run_policy.get("delivery_scope") != "local_only":
        raise ValueError("viewer accepts only local_only results")
    if run_policy.get("corpus_text") != "redacted":
        raise ValueError("run policy does not confirm corpus-text redaction")
    if dossier.get("gate_passed") is not True or dossier.get("gate_errors"):
        raise ValueError("viewer accepts only a clean Gate-issued dossier")
    display_policy = dossier.get("display_policy")
    if not isinstance(display_policy, dict):
        raise ValueError("dossier is missing its display policy")
    if display_policy.get("corpus_text") != "redacted":
        raise ValueError("dossier does not confirm corpus-text redaction")
    if display_policy.get("assessment_rationales") != "redacted":
        raise ValueError("dossier does not confirm rationale redaction")
    _reject_unredacted_keys(dossier)
    return result


def create_result_app(result_path: Path) -> Flask:
    result = load_redacted_result(result_path)
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )

    @app.after_request
    def no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.get("/")
    def home() -> str:
        return render_template(
            "result.html",
            run_policy=result["run_policy"],
            corpus=result["corpus"],
            dossier=result["dossier"],
        )

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    try:
        app = create_result_app(args.result)
    except ValueError as exc:
        parser.error(str(exc))
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
