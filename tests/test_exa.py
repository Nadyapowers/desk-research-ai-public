"""Task 2 of SPEC.md: the Exa search source. Needs neither the network nor the database."""

import os
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.modules.setdefault("db", types.ModuleType("db"))

from collector import main as collector  # noqa: E402

ANSWER = {
    "results": [
        {
            "url": "https://kamaz.ru/press/news/novyy-operator-pitaniya/",
            "title": "  На КАМАЗе\n сменился оператор питания ",
            "publishedDate": "2026-11-10T08:00:00.000Z",
            "text": "Столовые завода с 1 декабря обслуживает новый оператор. " * 60,
        },
        {
            "url": "https://example.ru/o-kompanii/stolovaya",
            "title": "Наша столовая",
            "publishedDate": None,
            "text": "Страница компании без даты.",
        },
        {
            "url": "https://example.ru/news/bez-zagolovka",
            "title": "",
            "publishedDate": "2026-11-09T00:00:00.000Z",
            "text": "Материал без заголовка.",
        },
    ]
}


class Parse(unittest.TestCase):
    def setUp(self):
        self.items = list(collector.parse_exa(ANSWER))

    def test_fields_are_taken(self):
        item = self.items[0]
        self.assertEqual(item["url"], "https://kamaz.ru/press/news/novyy-operator-pitaniya/")
        self.assertEqual(item["title"], "На КАМАЗе сменился оператор питания")
        self.assertEqual(item["published_at"], "2026-11-10T08:00:00.000Z")
        self.assertTrue(item["text"].startswith("Столовые завода с 1 декабря"))

    def test_without_date_or_title_is_dropped(self):
        self.assertEqual(len(self.items), 1)

    def test_text_is_cut_to_1500(self):
        self.assertEqual(len(self.items[0]["text"]), 1500)

    def test_empty_answer_gives_nothing(self):
        self.assertEqual(list(collector.parse_exa({})), [])


class Request(unittest.TestCase):
    def test_last_7_days_and_text_limit(self):
        now = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)
        body = collector.exa_request("новость о столовой на заводе", now)
        self.assertEqual(body["query"], "новость о столовой на заводе")
        self.assertEqual(body["startPublishedDate"], "2026-11-05T06:00:00+00:00")
        self.assertEqual(body["contents"]["text"]["maxCharacters"], 1500)


class NoKey(unittest.TestCase):
    def test_no_search_without_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            collector, "post_json", side_effect=AssertionError("Exa called without a key")
        ):
            self.assertEqual(list(collector.read_exa("любой запрос")), [])

    def test_key_goes_into_the_header(self):
        with mock.patch.dict(os.environ, {"EXA_API_KEY": "test-key"}), mock.patch.object(
            collector, "post_json", return_value=ANSWER
        ) as post:
            items = list(collector.read_exa("любой запрос"))
        self.assertEqual(len(items), 1)
        self.assertEqual(post.call_args.args[2], {"x-api-key": "test-key"})


if __name__ == "__main__":
    unittest.main()
