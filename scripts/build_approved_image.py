#!/usr/bin/env python3
"""Build a corpus-baked image only from a written-permission manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from takhrij.index_builder import APPROVED_STATUS, build_index
from takhrij.manifest import APPROVED_KIND, CorpusManifest, load_manifest

BUILD_FILES = ("Dockerfile", "LICENSE", "README.md", "pyproject.toml")
BUILD_DIRECTORIES = ("src", "static", "templates")


def _repository_root(manifest_path: Path) -> Path:
    for candidate in (manifest_path.resolve().parent, *manifest_path.resolve().parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ValueError("approved manifest must be located within the TAKHRIJ repository")


def _approved_manifest(manifest_path: Path, *, allow_approved_corpus_image: bool) -> CorpusManifest:
    if not allow_approved_corpus_image:
        raise PermissionError(
            "approved image build requires the explicit --allow-approved-corpus-image flag"
        )
    manifest = load_manifest(manifest_path)
    if manifest.content_kind != APPROVED_KIND:
        raise PermissionError("approved image build requires an approved_corpus manifest")
    if manifest.approval.status != APPROVED_STATUS:
        raise PermissionError(
            f"approved image build blocked: approval.status must be {APPROVED_STATUS}"
        )
    return manifest


def _copy_application_context(repository_root: Path, context_root: Path) -> None:
    for name in BUILD_FILES:
        shutil.copy2(repository_root / name, context_root / name)
    for name in BUILD_DIRECTORIES:
        shutil.copytree(repository_root / name, context_root / name)
    (context_root / "data").mkdir()


def build_approved_image(
    manifest_path: Path,
    image_tag: str,
    *,
    allow_approved_corpus_image: bool = False,
) -> dict[str, Any]:
    """Build an image from an isolated context containing only the derived database."""
    manifest_path = manifest_path.resolve()
    manifest = _approved_manifest(
        manifest_path,
        allow_approved_corpus_image=allow_approved_corpus_image,
    )
    repository_root = _repository_root(manifest_path)
    with tempfile.TemporaryDirectory(prefix="takhrij-approved-image-") as directory:
        context_root = Path(directory).resolve()
        if context_root == repository_root or repository_root in context_root.parents:
            raise PermissionError("approved image build context must be outside the repository")
        _copy_application_context(repository_root, context_root)
        database_path = context_root / "data" / "takhrij.db"
        result = build_index(
            manifest_path,
            database_path,
            allow_approved_corpus=True,
        )
        subprocess.run(
            [
                "docker",
                "build",
                "--build-arg",
                "ALLOW_APPROVED_CORPUS_IMAGE=written_permission_granted",
                "--tag",
                image_tag,
                ".",
            ],
            cwd=context_root,
            check=True,
        )
        return {
            **result,
            "image": image_tag,
            "delivery": "baked_read_only_database",
            "approval_status": manifest.approval.status,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("image_tag")
    parser.add_argument(
        "--allow-approved-corpus-image",
        action="store_true",
        help="confirm that the written permission covers building a corpus-containing image",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            build_approved_image(
                args.manifest,
                args.image_tag,
                allow_approved_corpus_image=args.allow_approved_corpus_image,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
