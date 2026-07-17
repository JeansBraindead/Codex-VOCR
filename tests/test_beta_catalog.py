from __future__ import annotations

import unittest

from vocr.beta.catalog import CATALOG, CATALOG_BY_CODE
from vocr.beta.scenarios import SCENARIOS


class BetaCatalogTests(unittest.TestCase):
    def test_catalog_codes_are_unique(self) -> None:
        codes = [info.code for info in CATALOG]

        self.assertEqual(len(codes), len(set(codes)))

    def test_catalog_matches_registered_scenarios_exactly(self) -> None:
        catalog_codes = {info.code for info in CATALOG}
        registered_codes = set(SCENARIOS.keys())

        missing_from_catalog = registered_codes - catalog_codes
        orphaned_in_catalog = catalog_codes - registered_codes

        self.assertEqual(missing_from_catalog, set(), "registered scenario missing a CATALOG entry")
        self.assertEqual(orphaned_in_catalog, set(), "CATALOG entry has no matching registered scenario")

    def test_catalog_tier_and_hard_match_registration(self) -> None:
        mismatches = [
            (code, scenario.tier, info.tier, scenario.hard, info.hard)
            for code, scenario in SCENARIOS.items()
            for info in [CATALOG_BY_CODE.get(code)]
            if info is not None and (info.tier != scenario.tier or info.hard != scenario.hard)
        ]

        self.assertEqual(mismatches, [])

    def test_catalog_title_matches_registration(self) -> None:
        mismatches = [
            (code, scenario.title, info.title)
            for code, scenario in SCENARIOS.items()
            for info in [CATALOG_BY_CODE.get(code)]
            if info is not None and info.title != scenario.title
        ]

        self.assertEqual(mismatches, [])

    def test_catalog_cost_labels_match_convention(self) -> None:
        for info in CATALOG:
            if info.tier == "cloud":
                self.assertEqual(info.cost, "kostet Kontingent", info.code)
            elif info.code in {"S21", "S22"}:
                self.assertEqual(info.cost, "GPU-Zeit", info.code)
            else:
                self.assertEqual(info.cost, "gratis", info.code)

    def test_catalog_entries_have_non_empty_german_descriptions(self) -> None:
        for info in CATALOG:
            self.assertTrue(info.what.strip(), info.code)
            self.assertTrue(info.benefit.strip(), info.code)


if __name__ == "__main__":
    unittest.main()
