#!/usr/bin/env python3
"""Repair known upstream preview-splitting defects without changing upstream files."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Callable, Mapping


# 046.png in the pinned upstream commit is a malformed individual export: it
# contains part of 046 and the neighbouring 047 tile. The source contact sheet
# has an irregular five-cell third row, so this rule uses the verified pixel
# boundary instead of the upstream splitter's 4x4 assumption.
KNOWN_ASSET_REPAIRS: dict[str, dict[str, Any]] = {
    "046": {
        "source_path": "images/B_036-048.png",
        "expected_source_sha256": "ccb6580124b895b321ae24a56de7e76d26efba6363057e334768f338655859ea",
        "crop_box": [527, 630, 730, 960],
        "output_size": [313, 313],
        "reason": "上游 046.png 被从不规则五列联系表按 4x4 错误切片，混入了 047 的画面；按源联系表已核验边界重切并等比留白。",
    }
}

AssetRequest = Callable[[str], bytes]


def _crop_contact_sheet(sheet_bytes: bytes, rule: Mapping[str, Any]) -> tuple[bytes, tuple[int, int, int, int]]:
    """Return one numbered tile from a verified contact-sheet crop as PNG bytes."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - depends on the local runtime
        raise RuntimeError(
            "资源修复需要 Pillow。请先运行: python -m pip install -r requirements.txt"
        ) from exc

    with Image.open(io.BytesIO(sheet_bytes)) as image:
        image.load()
        box_values = rule.get("crop_box")
        if not isinstance(box_values, (list, tuple)) or len(box_values) != 4:
            raise ValueError(f"invalid contact-sheet crop rule: {rule}")
        box = tuple(int(value) for value in box_values)
        if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
            raise ValueError(f"crop box is outside source image: {box} / {image.size}")
        tile = image.crop(box).convert("RGB")
        output_size = rule.get("output_size")
        if output_size is not None:
            if not isinstance(output_size, (list, tuple)) or len(output_size) != 2:
                raise ValueError(f"invalid output size in repair rule: {rule}")
            target_size = (int(output_size[0]), int(output_size[1]))
            if min(target_size) < 1:
                raise ValueError(f"invalid output size in repair rule: {rule}")
            fitted = ImageOps.contain(tile, target_size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", target_size, "white")
            canvas.paste(fitted, ((target_size[0] - fitted.width) // 2, (target_size[1] - fitted.height) // 2))
            tile = canvas
        output = io.BytesIO()
        tile.save(output, format="PNG")
    return output.getvalue(), box


def apply_known_repairs(
    *,
    preview_dir: Path,
    source_sheet_dir: Path,
    base_url: str,
    revision: str,
    request: AssetRequest,
    rules: Mapping[str, Mapping[str, Any]] = KNOWN_ASSET_REPAIRS,
) -> list[dict[str, Any]]:
    """Apply the checked-in repair map and return auditable repair records."""
    preview_dir.mkdir(parents=True, exist_ok=True)
    source_sheet_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    for style_id, rule in rules.items():
        source_path = str(rule["source_path"])
        source_url = f"{base_url.rstrip('/')}/{source_path}"
        source_name = Path(source_path).name
        cached_sheet = source_sheet_dir / f"{revision[:12]}-{source_name}"
        if cached_sheet.exists():
            sheet_bytes = cached_sheet.read_bytes()
        else:
            sheet_bytes = request(source_url)
            cached_sheet.write_bytes(sheet_bytes)

        expected_hash = rule.get("expected_source_sha256")
        actual_hash = hashlib.sha256(sheet_bytes).hexdigest()
        if expected_hash and actual_hash != str(expected_hash):
            raise RuntimeError(
                f"资源修复规则 {style_id} 只适用于指定源文件；"
                f"当前 {source_path} SHA-256 为 {actual_hash}，请先复核裁切边界。"
            )
        tile_bytes, crop_box = _crop_contact_sheet(sheet_bytes, rule)
        destination = preview_dir / f"{str(style_id).zfill(3)}.png"
        destination.write_bytes(tile_bytes)
        records.append(
            {
                "style_id": str(style_id).zfill(3),
                "method": "contact_sheet_crop",
                "source_path": source_path,
                "source_url": source_url,
                "source_sha256": actual_hash,
                "crop_box": list(crop_box),
                "output_size": list(rule["output_size"]) if rule.get("output_size") else None,
                "reason": str(rule["reason"]),
            }
        )
    return records


if __name__ == "__main__":  # pragma: no cover - repairs are normally called by the updater
    raise SystemExit("请通过 update_style_library.py --repair-assets 调用资源修复。")
