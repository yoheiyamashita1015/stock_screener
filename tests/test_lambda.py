import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from lambda_app.screen import lambda_handler


class FakeStorage:
    def __init__(self):
        self.read_json_called = False

    def last_modified(self, key):
        self.last_modified_key = key
        return datetime(2026, 8, 26, 4, 33, 45, tzinfo=timezone.utc)

    def read_json(self, key):
        self.read_json_called = True
        return {
            "generated_at": "2026-08-26T04:33:44.895314+00:00",
            "stocks": [{"ticker": "AAPL", "market_cap": 3_000_000_000}],
        }


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        self.storage = FakeStorage()
        self.config_patch = patch(
            "lambda_app.screen.BatchConfig.from_env", return_value=object()
        )
        self.storage_patch = patch(
            "lambda_app.screen.create_storage", return_value=self.storage
        )
        self.config_patch.start()
        self.storage_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.addCleanup(self.storage_patch.stop)

    def test_metadata_only_returns_timestamp_without_loading_stock_data(self):
        response = lambda_handler({"metadata_only": True}, None)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["generated_at"], "2026-08-26T04:33:45+00:00")
        self.assertEqual(
            self.storage.last_modified_key, "processed/stocks.json"
        )
        self.assertFalse(self.storage.read_json_called)

    def test_screening_response_includes_dataset_generation_time(self):
        response = lambda_handler(
            {"conditions": {"min_market_cap": 1_000_000_000}}, None
        )
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            body["generated_at"], "2026-08-26T04:33:44.895314+00:00"
        )
        self.assertEqual(body["count"], 1)
        self.assertTrue(self.storage.read_json_called)


if __name__ == "__main__":
    unittest.main()
