from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class AssetDefinition:
    slug: str
    name: str
    benchmark_label: str
    proxy_ticker: str
    group: str
    category: str
    macro_tags: tuple[str, ...]
    ips_min_weight: float
    ips_max_weight: float


@dataclass(frozen=True, slots=True)
class BenchmarkDefinition:
    equity_benchmark_label: str
    fixed_income_benchmark_label: str
    equity_weight: float
    fixed_income_weight: float


ASSET_DEFINITIONS: Final[tuple[AssetDefinition, ...]] = (
    AssetDefinition("us_large_cap", "US Large Cap Equity", "SPTR Index", "VTI", "equity", "us_equity", ("growth", "rates", "inflation", "dollar"), 0.0, 0.50),
    AssetDefinition("us_small_cap", "US Small Cap Equity", "SMLTR Index", "IWM", "equity", "us_equity", ("growth", "rates", "credit"), 0.0, 0.15),
    AssetDefinition("us_value", "US Value Equity", "CSUSVALU Index", "IWD", "equity", "us_equity", ("value", "rates", "economy"), 0.0, 0.20),
    AssetDefinition("us_growth", "US Growth Equity", "CSUSGRWU Index", "IWF", "equity", "us_equity", ("growth", "rates", "risk"), 0.0, 0.20),
    AssetDefinition("intl_developed", "Intl Developed Equity", "MXWO Index", "VEA", "equity", "international_equity", ("growth", "dollar", "eafe"), 0.0, 0.30),
    AssetDefinition("emg_markets", "Emg Markets Equity", "MXEF Index", "VWO", "equity", "emerging_equity", ("growth", "dollar", "risk"), 0.0, 0.20),
    AssetDefinition("us_short_treasury", "US Short Treasury", "BPTXY10 Index", "SHY", "fixed_income", "treasury", ("rates", "credit"), 0.0, 0.30),
    AssetDefinition("us_interm_treasury", "US Interm Treasury", "BPTXY30 Index", "IEF", "fixed_income", "treasury", ("rates", "credit"), 0.0, 0.40),
    AssetDefinition("us_long_treasury", "US Long Treasury", "BPTXY10 Index", "TLT", "fixed_income", "treasury", ("rates", "credit"), 0.0, 0.30),
    AssetDefinition("ig_corporate", "IG Corporate", "CPATREIT Index", "LQD", "fixed_income", "credit", ("rates", "credit"), 0.0, 0.20),
    AssetDefinition("hy_corporate", "HY Corporate", "HWCI Index", "HYG", "fixed_income", "credit", ("rates", "credit", "risk"), 0.0, 0.15),
    AssetDefinition("intl_sovereign", "Intl Sovereign", "LEGATRUU Index", "BWX", "fixed_income", "international_fixed_income", ("rates", "dollar"), 0.0, 0.20),
    AssetDefinition("intl_corporate", "Intl Corporate", "LGCPTRUU Index", "PICB", "fixed_income", "international_fixed_income", ("rates", "credit"), 0.0, 0.15),
    AssetDefinition("usd_em_debt", "USD Emg Debt", "EMUSTOTL Index", "EMB", "fixed_income", "emerging_fixed_income", ("dollar", "risk"), 0.0, 0.15),
    AssetDefinition("reits", "REITs", "FTV Index", "VNQ", "real_assets", "real_assets", ("rates", "growth"), 0.0, 0.15),
    AssetDefinition("gold", "Gold", "XAU USD", "GLD", "real_assets", "real_assets", ("inflation", "dollar", "risk"), 0.0, 0.10),
    AssetDefinition("commodities", "Commodities", "GSCI Index", "DBC", "real_assets", "real_assets", ("inflation", "growth"), 0.0, 0.15),
    AssetDefinition("cash", "Cash", "US0001M Index", "BIL", "cash", "cash", ("rates",), 0.0, 0.20),
)

ASSET_ORDER: Final[tuple[str, ...]] = tuple(asset.slug for asset in ASSET_DEFINITIONS)
ASSETS_BY_SLUG: Final[dict[str, AssetDefinition]] = {asset.slug: asset for asset in ASSET_DEFINITIONS}
GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "equity": tuple(asset.slug for asset in ASSET_DEFINITIONS if asset.group == "equity"),
    "fixed_income": tuple(asset.slug for asset in ASSET_DEFINITIONS if asset.group == "fixed_income"),
    "real_assets": tuple(asset.slug for asset in ASSET_DEFINITIONS if asset.group == "real_assets"),
    "cash": tuple(asset.slug for asset in ASSET_DEFINITIONS if asset.group == "cash"),
}
SIXTY_FORTY_BENCHMARK: Final[BenchmarkDefinition] = BenchmarkDefinition(
    equity_benchmark_label="MSCI ACWI",
    fixed_income_benchmark_label="Bloomberg Aggregate",
    equity_weight=0.60,
    fixed_income_weight=0.40,
)


def get_asset(slug: str) -> AssetDefinition:
    return ASSETS_BY_SLUG[slug]


def build_60_40_benchmark() -> dict[str, float]:
    return {
        "msci_acwi": SIXTY_FORTY_BENCHMARK.equity_weight,
        "bloomberg_aggregate": SIXTY_FORTY_BENCHMARK.fixed_income_weight,
    }
