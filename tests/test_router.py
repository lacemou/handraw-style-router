from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from build_style_profiles import build_profiles  # noqa: E402
from route_topic import infer_topic_features, route_topic  # noqa: E402
from update_style_library import _merge_review_status  # noqa: E402


class RouterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture = Path(__file__).with_name("fixtures_profiles.json")
        cls.payload = json.loads(fixture.read_text(encoding="utf-8"))

    def test_topic_fallback_parser_has_six_fields(self) -> None:
        features = infer_topic_features("办公室里，一个团队讨论如何使用人工智能")
        self.assertEqual(set(features), {"subject", "action", "scene", "abstraction", "mood", "narrative_density"})
        self.assertIn("technology", features["subject"])
        self.assertIn("office", features["scene"])

    def test_route_returns_fixed_roles_and_unique_styles(self) -> None:
        result = route_topic(
            "办公室里，一个团队讨论如何使用人工智能",
            self.payload["styles"],
        )
        self.assertEqual([item["role"] for item in result["candidates"]], [
            "最稳妥",
            "最有表现力",
            "最具故事感",
            "最容易读懂主题",
            "差异化候选",
        ])
        self.assertEqual(len({item["style_id"] for item in result["candidates"]}), 5)
        self.assertGreaterEqual(len({item["group"] for item in result["candidates"]}), 5)

    def test_profile_builder_marks_heuristic_status(self) -> None:
        styles = [{
            "number": "022",
            "group": "A 国际社论漫画 / 幽默手绘",
            "reference": "Sally Nixon",
            "generation_name": "Flat Everyday Women Lifestyle",
            "traits": "日常女性人物、低饱和外套与围巾、旁边的小鸟。",
        }]
        result = build_profiles(styles, source={"revision": "fixture"})
        self.assertEqual(result["profile_status"], "heuristic_pending_review")
        self.assertEqual(result["styles"][0]["style_id"], "022")
        self.assertEqual(result["styles"][0]["status"], "heuristic_pending_review")
        self.assertIn("people", result["styles"][0]["route_affordances"]["subject"])

    def test_new_style_is_gallery_only_after_existing_library_update(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            previous = Path(directory) / "style-profiles.json"
            previous.write_text(json.dumps({
                "styles": [{
                    "style_id": "001",
                    "status": "reviewed",
                    "visual_facts": {"traits": "same"},
                }]
            }), encoding="utf-8")
            payload = {
                "styles": [
                    {"style_id": "001", "status": "heuristic_pending_review", "visual_facts": {"traits": "same"}},
                    {"style_id": "262", "status": "heuristic_pending_review", "visual_facts": {"traits": "new"}},
                ]
            }
            merged = _merge_review_status(payload, previous)
            statuses = {item["style_id"]: item["status"] for item in merged["styles"]}
            self.assertEqual(statuses, {"001": "reviewed", "262": "gallery_only"})
            self.assertEqual(merged["profile_status"], "mixed_review_state")


if __name__ == "__main__":
    unittest.main()
