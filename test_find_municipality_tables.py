import tempfile
import unittest
from pathlib import Path

import find_municipality_tables as finder


class MunicipalityDimensionsTest(unittest.TestCase):
    def test_finds_codes_and_preserves_api_values(self):
        metadata = {
            "variables": [
                {
                    "id": "AREA",
                    "text": "region",
                    "time": False,
                    "map": "denmark_municipality_07",
                    "values": [
                        {"id": "000", "text": "All Denmark"},
                        {"id": "101", "text": "Copenhagen"},
                        {"id": "147", "text": "Frederiksberg"},
                    ],
                },
                {"id": "TIME", "time": True, "values": [{"id": "101", "text": "101"}]},
            ]
        }
        matches = finder.municipality_dimensions(metadata, threshold=2)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["municipality_count"], 2)
        self.assertEqual([value["id"] for value in matches[0]["municipalities"]], ["101", "147"])

    def test_rejects_a_dimension_below_threshold(self):
        metadata = {"variables": [{"id": "X", "values": [{"id": "101"}]}]}
        self.assertEqual(finder.municipality_dimensions(metadata, threshold=2), [])

    def test_rejects_numeric_codes_with_unrelated_labels(self):
        metadata = {
            "variables": [
                {
                    "id": "SUBJECT",
                    "values": [
                        {"id": "101", "text": "Poetry"},
                        {"id": "147", "text": "Book production"},
                    ],
                }
            ]
        }
        self.assertEqual(finder.municipality_dimensions(metadata, threshold=2), [])

    def test_accepts_directional_municipality_labels(self):
        metadata = {
            "variables": [
                {
                    "id": "DESTINATION",
                    "values": [
                        {"id": "101", "text": "Til København"},
                        {"id": "147", "text": "Fra Frederiksberg"},
                    ],
                }
            ]
        }
        matches = finder.municipality_dimensions(metadata, threshold=2)
        self.assertEqual(matches[0]["municipality_count"], 2)

    def test_rejects_pre_2007_municipality_map(self):
        metadata = {
            "variables": [
                {
                    "id": "AREA",
                    "map": "Denmark_municipality",
                    "values": [
                        {"id": "101", "text": "København"},
                        {"id": "147", "text": "Frederiksberg"},
                    ],
                }
            ]
        }
        self.assertEqual(finder.municipality_dimensions(metadata, threshold=2), [])


class TableMetadataTest(unittest.TestCase):
    def test_derives_supported_time_grains(self):
        cases = {
            "2024": "year",
            "2024H1": "half-year",
            "2024K3": "quarter",
            "2024KV3": "quarter",
            "2024M09": "month",
            "2024M09D30": "day",
            "2024U53": "week",
            "2020:2024": "interval",
            "AUG - DEC 2024": "interval",
        }
        for period, expected in cases.items():
            with self.subTest(period=period):
                dimension = {"values": [{"id": period, "text": period}]}
                self.assertEqual(finder.derive_time_grain(dimension), expected)

    def test_table_result_keeps_time_and_non_municipality_variables(self):
        metadata = {
            "variables": [
                {"id": "AREA", "time": False, "values": [{"id": "101"}]},
                {"id": "SEX", "time": False, "values": [{"id": "1", "text": "Men"}]},
                {"id": "TIME", "time": True, "values": [{"id": "2024K1", "text": "2024Q1"}]},
            ]
        }
        dimensions = [{"id": "AREA"}]
        result = finder.table_result({"id": "TEST"}, metadata, dimensions)
        self.assertEqual(result["time_grain"], "quarter")
        self.assertEqual(result["time_dimension"]["id"], "TIME")
        self.assertEqual([variable["id"] for variable in result["variables"]], ["SEX"])


class CacheTest(unittest.TestCase):
    def test_cache_is_invalidated_when_table_was_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "table.json"
            finder.write_json_atomic(path, {"id": "X", "updated": "old"})
            self.assertIsNotNone(finder.load_cached_metadata(path, "old"))
            self.assertIsNone(finder.load_cached_metadata(path, "new"))


if __name__ == "__main__":
    unittest.main()
