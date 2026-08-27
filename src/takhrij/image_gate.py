"""Fail-closed corpus checks executed while constructing a Docker image."""

from __future__ import annotations

import argparse
from pathlib import Path

from takhrij.index import CorpusIndex
from takhrij.index_builder import (
    APPROVED_SCOPE,
    APPROVED_STATUS,
    FIXTURE_SCOPE,
)
from takhrij.manifest import APPROVED_KIND, FIXTURE_KIND

APPROVED_IMAGE_OPT_IN = "written_permission_granted"
FIXTURE_RELEASE = "FIXTURE-ONLY"


def verify_image_database(database_path: Path, approved_image_opt_in: str) -> dict[str, str]:
    metadata = CorpusIndex(database_path).metadata()
    content_kind = metadata.get("content_kind", "")
    if content_kind == FIXTURE_KIND:
        if metadata.get("release") != FIXTURE_RELEASE:
            raise PermissionError("fixture image database has an invalid release label")
        if metadata.get("delivery_scope") != FIXTURE_SCOPE:
            raise PermissionError("fixture image database requires delivery_scope=fixture_only")
        return metadata
    if content_kind != APPROVED_KIND:
        raise PermissionError("image database has an unknown content_kind")
    if metadata.get("approval_status") != APPROVED_STATUS:
        raise PermissionError(
            f"approved image database requires approval_status={APPROVED_STATUS}"
        )
    if metadata.get("delivery_scope") != APPROVED_SCOPE:
        raise PermissionError(
            "approved image database requires delivery_scope=distribution_approved"
        )
    if approved_image_opt_in != APPROVED_IMAGE_OPT_IN:
        raise PermissionError(
            "approved image database requires explicit Docker build opt-in"
        )
    approval_reference = metadata.get("approval_reference", "").strip()
    if not approval_reference or "REPLACE_WITH" in approval_reference.upper():
        raise PermissionError("approved image database requires an approval reference")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("approved_image_opt_in")
    args = parser.parse_args()
    metadata = verify_image_database(args.database, args.approved_image_opt_in)
    print(
        "image corpus gate: "
        f"{metadata['content_kind']} / {metadata['release']} / {metadata['approval_status']}"
    )


if __name__ == "__main__":
    main()
