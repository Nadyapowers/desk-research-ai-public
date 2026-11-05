"""Task 1 of SPEC.md: the finding in one phrase. Needs neither the model nor the database."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.modules.setdefault("db", types.ModuleType("db"))

from worker.main import clean_answer, clean_headline, shorten, strip_caveats  # noqa: E402


class Shorten(unittest.TestCase):
    def test_exactly_100_characters_stay(self):
        text = "а" * 100
        self.assertEqual(shorten(text), text)

    def test_longer_is_cut_at_a_word_boundary(self):
        text = " ".join(["столовая"] * 30)
        result = shorten(text)
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.endswith("столовая…"))


class Caveats(unittest.TestCase):
    def test_caveat_goes_and_the_event_stays(self):
        text = "КАМАЗ сменил оператора питания. Текст материала состоит только из заголовка."
        self.assertEqual(strip_caveats(text), "КАМАЗ сменил оператора питания.")

    def test_known_phrases_are_removed(self):
        for phrase in (
            "Больше подробностей в тексте не указано.",
            "Больше подробностей в материале нет.",
            "В тексте больше нет подробностей.",
            "В тексте нет данных о конкретных компаниях.",
            "Текст недоступен.",
            "Материал является обзором по теме.",
        ):
            self.assertEqual(strip_caveats(phrase), "", phrase)

    def test_only_a_caveat_gives_the_title(self):
        result = clean_headline("Текст материала состоит только из заголовка.", "КАМАЗ сменил оператора")
        self.assertEqual(result, "КАМАЗ сменил оператора")

    def test_ordinary_words_are_kept(self):
        for phrase in (
            "Компания закупит материалы для столовых",
            "Подробности сделки стороны не раскрывают",
        ):
            self.assertEqual(strip_caveats(phrase), phrase)


class Answer(unittest.TestCase):
    def test_answer_gets_a_clean_headline_and_summary(self):
        answer = clean_answer(
            {
                "about_corp_food": True,
                "headline": "РБЕ получила контракт с заводом.",
                "summary": "РБЕ получила контракт. В тексте больше нет подробностей.",
            },
            "Заголовок",
        )
        self.assertEqual(answer["headline"], "РБЕ получила контракт с заводом")
        self.assertEqual(answer["summary"], "РБЕ получила контракт.")

    def test_summary_of_only_a_caveat_falls_back_to_the_headline(self):
        answer = clean_answer(
            {"about_corp_food": True, "headline": "", "summary": "Текст недоступен."},
            "Заголовок новости",
        )
        self.assertEqual(answer["headline"], "Заголовок новости")
        self.assertEqual(answer["summary"], "Заголовок новости")


if __name__ == "__main__":
    unittest.main()
