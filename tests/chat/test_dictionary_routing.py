import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from luxscale import chat_service  # noqa: E402


class DictionaryRoutingTests(unittest.TestCase):
    def _session(self, suffix: str) -> str:
        return f"dict-routing-{suffix}"

    def test_static_local_standard_name_arabic(self) -> None:
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                "ايه اسم الكود الاوروبي اللي شغال بيه",
                session_id=self._session("static-ar"),
                context_messages=[],
            )
        self.assertEqual("static_local", out.get("source"))

    def test_fixed_exact_from_dictionary_question(self) -> None:
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                "What lux and U0 do I use for office workstations?",
                session_id=self._session("fixed-exact"),
                context_messages=[],
            )
        self.assertEqual("fixed_exact", out.get("source"))

    def test_semantic_suggestion_dictionary_case(self) -> None:
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                "What lighting level is used for warehouse gangway?",
                session_id=self._session("fixed-semantic"),
                context_messages=[],
            )
        self.assertIn(out.get("source"), {"fixed_suggested", "fixed_exact"})
        if out.get("source") == "fixed_suggested":
            self.assertTrue(bool(out.get("requires_confirmation")))

    def test_planning_local_english_question(self) -> None:
        question = "if i have a room with dimensions (80 * 70 * 6) inside factory and how many fixtures i need"
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                question,
                session_id=self._session("planning-en"),
                context_messages=[],
            )
        self.assertEqual("planning_local", out.get("source"))
        self.assertEqual("calculate_lighting_fast", out.get("engine"))
        self.assertTrue(str(out.get("answer") or "").strip().startswith("📐 Inferred Inputs"))

    def test_planning_local_arabic_question(self) -> None:
        question = "لو عندي مصنع ورق ابعاده (90*80*4) ايه الستاندارد بتاعه وايه الكشافات اللي هحتاجها"
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                question,
                session_id=self._session("planning-ar"),
                context_messages=[],
            )
        self.assertEqual("planning_local", out.get("source"))
        self.assertEqual("calculate_lighting_fast", out.get("engine"))
        answer = str(out.get("answer") or "")
        self.assertIn("لوكس (lx)", answer)
        self.assertTrue(answer.strip().startswith("📐 مدخلات التحليل"))

    def test_current_message_language_has_priority_over_context(self) -> None:
        context = [
            {"role": "user", "text": "ايه الكود الاوروبي؟"},
            {"role": "assistant", "text": "المعيار EN 12464-1"},
        ]
        question = "if i have a room with dimensions (80 * 70 *3) inside factory and how many fixtures i need"
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                question,
                session_id=self._session("lang-priority"),
                context_messages=context,
            )
        self.assertEqual("planning_local", out.get("source"))
        self.assertTrue(str(out.get("answer") or "").strip().startswith("📐 Inferred Inputs"))

    def test_company_identity_static_no_gate(self) -> None:
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                "Tell me about Short Circuit company and their website",
                session_id=self._session("company-id"),
                context_messages=[],
            )
        self.assertEqual("static_local", out.get("source"))
        self.assertEqual("company_identity", out.get("intent_key"))
        self.assertIn("shortcircuit.company", str(out.get("answer") or "").lower())

    def test_fixture_catalog_local_indoors_phrase(self) -> None:
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                "what fixtures do u use in indoors",
                session_id=self._session("catalog-indoors"),
                context_messages=[],
            )
        self.assertEqual("fixture_catalog_local", out.get("source"))
        self.assertEqual("fixture_catalog_indoor", out.get("canonical_response_id"))
        self.assertEqual("indoor", out.get("fixture_catalog_scope"))
        ans = str(out.get("answer") or "")
        self.assertIn("SC triproof", ans)
        self.assertIn("SC downlight", ans)
        self.assertNotIn("Recommended baseline:", ans)
        self.assertNotIn("SC street:", ans)

    def test_fixture_catalog_local_outdoor_phrase(self) -> None:
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                "what fixtures do u use outdoor",
                session_id=self._session("catalog-outdoor"),
                context_messages=[],
            )
        self.assertEqual("fixture_catalog_local", out.get("source"))
        self.assertEqual("fixture_catalog_outdoor", out.get("canonical_response_id"))
        self.assertEqual("outdoor", out.get("fixture_catalog_scope"))
        ans = str(out.get("answer") or "")
        self.assertIn("SC highbay", ans)
        self.assertIn("SC street", ans)
        self.assertNotIn("Recommended baseline:", ans)

    def test_fixture_catalog_does_not_override_planning_with_dims(self) -> None:
        question = (
            "if i have a room with dimensions (8 * 7 * 2) inside factory "
            "and how many fixtures i need"
        )
        with patch.object(chat_service, "ask_gemini_text", side_effect=AssertionError("Gemini should not be called")):
            out = chat_service.handle_question(
                question,
                session_id=self._session("catalog-vs-plan"),
                context_messages=[],
            )
        self.assertEqual("planning_local", out.get("source"))

    def test_format_local_calc_warns_when_u0_non_compliant(self) -> None:
        opts = [
            {
                "label": "SC Panel",
                "fixtures": 4,
                "power_w": 32,
                "achieved_lux": 225.3,
                "u0": 0.244,
                "total_kw": 0.13,
                "watts_per_m2": 2.29,
                "lumens": 3959,
                "uf": 0.6,
                "mf": 0.8,
                "layout_nx": 2,
                "layout_ny": 2,
                "product_title": "SC Panel 60x60",
                "product_url": "",
                "image_url": "",
                "selection": "closest_non_compliant_candidate",
                "lux_pass": True,
                "u0_pass": False,
                "uniformity_evaluated": True,
            }
        ]
        text = chat_service._format_local_calc_answer(
            8.0,
            7.0,
            2.0,
            56.0,
            "Factory",
            200.0,
            0.4,
            opts,
            "en",
            task_or_activity="Furnaces",
        )
        self.assertIn("below required", text)
        self.assertIn("⚠️", text)
        self.assertIn("Standard check", text)


if __name__ == "__main__":
    unittest.main()
