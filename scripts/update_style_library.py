#!/usr/bin/env python3
"""Explicitly fetch and prepare the handraw-style runtime library."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_style_profiles import build_profiles


UPSTREAM_REPOSITORY = "yang0/handraw-style"
DEFAULT_REVISION = "58dee6151874c6fc381e6a0d97430f1c275c1696"
STYLES_PATH = "handdraw-style-prompter/references/styles.json"
IMAGE_TEMPLATE = "images/individual/{bucket}/{number}.png"


def _request(url: str, *, accept: str = "application/octet-stream") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "handraw-style-router/0.1", "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _resolve_latest() -> str:
    payload = json.loads(
        _request(
            "https://api.github.com/repos/yang0/handraw-style/git/ref/heads/master",
            accept="application/vnd.github+json",
        ).decode("utf-8")
    )
    return str(payload["object"]["sha"])


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _image_path(number: str) -> str:
    bucket = "001-200" if int(number) <= 200 else "201-400"
    return IMAGE_TEMPLATE.format(bucket=bucket, number=number)


def _merge_review_status(profiles_payload: dict[str, Any], previous_path: Path) -> dict[str, Any]:
    """Keep reviewed states and quarantine new or changed entries in the gallery."""
    if not previous_path.exists():
        return profiles_payload
    try:
        previous_payload = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return profiles_payload
    previous_by_id = {
        str(profile.get("style_id")): profile
        for profile in previous_payload.get("styles", [])
        if isinstance(profile, dict) and profile.get("style_id") is not None
    }
    for profile in profiles_payload.get("styles", []):
        style_id = str(profile.get("style_id"))
        previous = previous_by_id.get(style_id)
        if previous is None:
            profile["status"] = "gallery_only"
            continue
        old_traits = previous.get("visual_facts", {}).get("traits")
        new_traits = profile.get("visual_facts", {}).get("traits")
        if old_traits != new_traits:
            profile["status"] = "gallery_only"
        else:
            profile["status"] = previous.get("status", profile.get("status", "heuristic_pending_review"))
    statuses = {str(profile.get("status")) for profile in profiles_payload.get("styles", [])}
    if statuses == {"reviewed"}:
        profiles_payload["profile_status"] = "reviewed"
    elif "gallery_only" in statuses or "disabled" in statuses:
        profiles_payload["profile_status"] = "mixed_review_state"
    else:
        profiles_payload["profile_status"] = "heuristic_pending_review"
    return profiles_payload


def update_library(output_dir: Path, *, revision: str, with_images: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_profiles_path = output_dir / "style-profiles.json"
    base = f"https://raw.githubusercontent.com/{UPSTREAM_REPOSITORY}/{revision}"
    styles_url = f"{base}/{STYLES_PATH}"
    styles = json.loads(_request(styles_url).decode("utf-8"))
    if not isinstance(styles, list) or not styles:
        raise RuntimeError("upstream styles.json is not a non-empty JSON array")

    preview_dir = output_dir / "previews"
    existing_preview_files = list(preview_dir.glob("*.png")) if preview_dir.exists() else []
    source = {
        "repository": UPSTREAM_REPOSITORY,
        "revision": revision,
        "styles_url": styles_url,
        "image_template": f"{base}/images/individual/{{bucket}}/{{number}}.png",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "style_count": len(styles),
        "images_downloaded": bool(with_images or existing_preview_files),
    }
    catalog_path = output_dir / "catalog" / "styles.json"
    source_path = output_dir / "source.json"
    _write_json(catalog_path, styles)
    _write_json(source_path, source)

    if with_images:
        preview_dir.mkdir(parents=True, exist_ok=True)
        for index, style in enumerate(styles, start=1):
            number = str(style["number"]).zfill(3)
            url = f"{base}/{_image_path(number)}"
            destination = preview_dir / f"{number}.png"
            destination.write_bytes(_request(url))
            if index % 25 == 0 or index == len(styles):
                print(f"downloaded previews: {index}/{len(styles)}", file=sys.stderr)

    preview_available = preview_dir.exists() and any(preview_dir.glob("*.png"))
    profiles = build_profiles(
        styles,
        source=source,
        preview_dir=str(preview_dir) if preview_available else None,
    )
    profiles = _merge_review_status(profiles, previous_profiles_path)
    _write_json(output_dir / "style-profiles.json", profiles)
    print(f"synced {len(styles)} styles at {revision} -> {output_dir}")
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicitly sync the handraw-style runtime library")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".runtime" / "style-library",
        help="Runtime library directory (default: .runtime/style-library)",
    )
    revision_group = parser.add_mutually_exclusive_group()
    revision_group.add_argument("--revision", default=DEFAULT_REVISION, help="Pinned upstream commit or ref")
    revision_group.add_argument("--latest", action="store_true", help="Resolve upstream master now and pin its commit")
    parser.add_argument("--with-images", action="store_true", help="Also download the 261+ single-image previews")
    args = parser.parse_args()

    revision = _resolve_latest() if args.latest else args.revision
    update_library(args.output, revision=revision, with_images=args.with_images)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
