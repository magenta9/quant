from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.assets import ASSET_DEFINITIONS, ASSET_ORDER
from core.cma_builder import AssetAnalysisResult, run_asset_analysis
from core.database import initialize_database, persist_cma_methods, persist_macro_view
from core.macro_analyzer import MacroStageResult, run_macro_stage
from core.utils import ensure_directory, generate_run_id


class Phase2DataProvider(Protocol):
    def get_macro_indicators(self) -> object: ...

    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> object: ...


@dataclass(frozen=True, slots=True)
class Phase2PipelineResult:
    run_id: str
    run_directory: Path
    ips_assets: tuple[str, ...]
    macro_result: MacroStageResult
    asset_results: tuple[AssetAnalysisResult, ...]
    database_path: Path


def run_phase2_pipeline(
    *,
    ips_path: str | Path = "config/ips.md",
    output_root: str | Path = "output/runs",
    database_path: str | Path = "database/portfolio.db",
    data_provider: Phase2DataProvider | None = None,
    run_id: str | None = None,
) -> Phase2PipelineResult:
    ips_assets = parse_ips_assets(ips_path)
    if ips_assets != ASSET_ORDER:
        raise ValueError(
            f"Phase 2 expects all 18 registered assets in configured order. Found {len(ips_assets)} assets instead."
        )

    resolved_database_path = initialize_database(database_path)
    active_run_id = run_id or generate_run_id()
    run_directory = ensure_directory(Path(output_root) / active_run_id)
    macro_directory = ensure_directory(run_directory / "macro")
    assets_directory = ensure_directory(run_directory / "assets")

    macro_result = run_macro_stage(output_dir=macro_directory, data_provider=data_provider)
    persist_macro_view(resolved_database_path, macro_result.macro_view)

    asset_results: list[AssetAnalysisResult] = []
    for asset_slug in ips_assets:
        result = run_asset_analysis(
            asset_slug=asset_slug,
            macro_view=macro_result.macro_view,
            output_dir=assets_directory / asset_slug,
            data_provider=data_provider,
        )
        persist_cma_methods(
            resolved_database_path,
            asset_slug=asset_slug,
            timestamp=macro_result.macro_view.timestamp,
            methods=result.cma_output.methods,
        )
        asset_results.append(result)

    return Phase2PipelineResult(
        run_id=active_run_id,
        run_directory=run_directory,
        ips_assets=ips_assets,
        macro_result=macro_result,
        asset_results=tuple(asset_results),
        database_path=resolved_database_path,
    )


def parse_ips_assets(ips_path: str | Path) -> tuple[str, ...]:
    asset_name_to_slug = {asset.name: asset.slug for asset in ASSET_DEFINITIONS}
    discovered_assets: list[str] = []
    for raw_line in Path(ips_path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or line.startswith("|-------") or "Asset | Benchmark" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        asset_name = cells[0]
        slug = asset_name_to_slug.get(asset_name)
        if slug is not None:
            discovered_assets.append(slug)
    return tuple(discovered_assets)
