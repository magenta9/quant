import unittest

from core.assets import (
    ASSET_ORDER,
    ASSETS_BY_SLUG,
    GROUPS,
    SIXTY_FORTY_BENCHMARK,
    build_60_40_benchmark,
    get_asset,
)


class AssetRegistryTests(unittest.TestCase):
    def test_registry_covers_all_18_assets_with_required_metadata(self) -> None:
        self.assertEqual(len(ASSET_ORDER), 18)
        self.assertEqual(len(ASSETS_BY_SLUG), 18)
        self.assertEqual(ASSET_ORDER[0], "us_large_cap")
        self.assertEqual(ASSET_ORDER[-1], "cash")

        us_large_cap = get_asset("us_large_cap")
        self.assertEqual(us_large_cap.benchmark_label, "SPTR Index")
        self.assertEqual(us_large_cap.proxy_ticker, "VTI")
        self.assertEqual(us_large_cap.group, "equity")
        self.assertEqual(us_large_cap.category, "us_equity")
        self.assertEqual(us_large_cap.ips_min_weight, 0.0)
        self.assertEqual(us_large_cap.ips_max_weight, 0.50)
        self.assertIn("growth", us_large_cap.macro_tags)

        gold = get_asset("gold")
        self.assertEqual(gold.proxy_ticker, "GLD")
        self.assertEqual(gold.group, "real_assets")
        self.assertEqual(gold.ips_max_weight, 0.10)

    def test_group_collections_match_expected_universe_splits(self) -> None:
        self.assertEqual(
            GROUPS,
            {
                "equity": (
                    "us_large_cap",
                    "us_small_cap",
                    "us_value",
                    "us_growth",
                    "intl_developed",
                    "emg_markets",
                ),
                "fixed_income": (
                    "us_short_treasury",
                    "us_interm_treasury",
                    "us_long_treasury",
                    "ig_corporate",
                    "hy_corporate",
                    "intl_sovereign",
                    "intl_corporate",
                    "usd_em_debt",
                ),
                "real_assets": ("reits", "gold", "commodities"),
                "cash": ("cash",),
            },
        )

    def test_60_40_benchmark_matches_spec_labels(self) -> None:
        benchmark = build_60_40_benchmark()
        self.assertEqual(
            benchmark,
            {
                "msci_acwi": 0.60,
                "bloomberg_aggregate": 0.40,
            },
        )
        self.assertEqual(SIXTY_FORTY_BENCHMARK.equity_benchmark_label, "MSCI ACWI")
        self.assertEqual(SIXTY_FORTY_BENCHMARK.fixed_income_benchmark_label, "Bloomberg Aggregate")


if __name__ == "__main__":
    unittest.main()
