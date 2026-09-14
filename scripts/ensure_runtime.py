#!/usr/bin/env python3
"""Ensure the local handraw-style runtime library is complete before routing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from update_style_library import DEFAULT_REVISION, _resolve_latest, update_library


MIN_ROUTEABLE_STYLES = 5
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def default_runtime_dir() -> Path:
    """Resolve the runtime directory from this script, not from the shell CWD."""
    return Path(__file__).resolve().parents[1] / ".runtime" / "style-library"


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _valid_png(path: Path) -> bool:
    try:
        if path.stat().st_size <= len(PNG_SIGNATURE):
            return False
        with path.open("rb") as handle:
            return handle.read(len(PNG_SIGNATURE)) == PNG_SIGNATURE
    except OSError:
        return False


def inspect_runtime(runtime_dir: Path) -> dict[str, Any]:
    """Return a machine-readable readiness report without changing files."""
    profile_path = runtime_dir / "style-profiles.json"
    source_path = runtime_dir / "source.json"
    preview_dir = runtime_dir / "previews"
    profiles_payload = _read_json(profile_path)
    source_payload = _read_json(source_path)
    problems: list[str] = []

    styles = profiles_payload.get("styles") if isinstance(profiles_payload, dict) else None
    if not isinstance(styles, list):
        problems.append("style-profiles.json 缺失或格式无效")
        styles = []

    routeable_styles = [
        style
        for style in styles
        if isinstance(style, dict) and style.get("status") not in {"disabled", "gallery_only"}
    ]
    if len(routeable_styles) < MIN_ROUTEABLE_STYLES:
        problems.append(f"可路由风格少于 {MIN_ROUTEABLE_STYLES} 个")

    if not isinstance(source_payload, dict):
        problems.append("source.json 缺失或格式无效")
    elif not source_payload.get("images_downloaded"):
        problems.append("示意图尚未完成下载")

    valid_previews = {
        preview.stem
        for preview in preview_dir.glob("*.png")
        if _valid_png(preview)
    } if preview_dir.exists() else set()
    if len(valid_previews) < MIN_ROUTEABLE_STYLES:
        problems.append(f"有效示意图少于 {MIN_ROUTEABLE_STYLES} 张")

    missing_previews = [
        str(style.get("style_id", "")).zfill(3)
        for style in routeable_styles
        if str(style.get("style_id", "")).zfill(3) not in valid_previews
    ]
    if missing_previews:
        problems.append(f"仍有 {len(missing_previews)} 个可路由风格缺少示意图")

    return {
        "ready": not problems,
        "runtime_dir": str(runtime_dir),
        "style_count": len(styles),
        "routeable_count": len(routeable_styles),
        "preview_count": len(valid_previews),
        "problems": problems,
    }


def ensure_runtime(
    runtime_dir: Path,
    *,
    revision: str = DEFAULT_REVISION,
    latest: bool = False,
) -> dict[str, Any]:
    """Check the runtime and initialize it once when it is absent or incomplete."""
    status = inspect_runtime(runtime_dir)
    if status["ready"]:
        print(f"runtime ready: {runtime_dir}")
        return status

    print("本地风格库未初始化或不完整，开始首次同步 261+ 个示意图。", file=sys.stderr)
    print("同步完成后，Skill 才会继续执行主题路由。", file=sys.stderr)
    selected_revision = _resolve_latest() if latest else revision
    update_library(
        runtime_dir,
        revision=selected_revision,
        with_images=True,
    )

    final_status = inspect_runtime(runtime_dir)
    if not final_status["ready"]:
        details = "；".join(final_status["problems"])
        raise RuntimeError(f"风格库同步结束，但仍未达到运行条件：{details}")
    print(f"runtime initialized: {runtime_dir}")
    return final_status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the handraw-style runtime library exists before routing"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_runtime_dir(),
        help="Runtime library directory (default: skill/.runtime/style-library)",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Use the current upstream master instead of the pinned revision",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only report readiness; never download files",
    )
    args = parser.parse_args()

    if args.check_only:
        status = inspect_runtime(args.output)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["ready"] else 1

    try:
        ensure_runtime(args.output, latest=args.latest)
    except Exception as exc:  # pragma: no cover - network/dependency failures vary by host
        print(f"无法初始化 handraw-style 风格库：{exc}", file=sys.stderr)
        print(
            "可先运行 `python -m pip install -r requirements.txt`，"
            "再检查网络后重试。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
