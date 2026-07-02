from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .engine import render_markdown_report, run_portfolio_screen, wyckoff_spring_signal
from .models import Company, ScenarioAssumption, Segment, WyckoffObservation


def _load_companies(path: Path) -> list[Company]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    companies: list[Company] = []
    for item in payload["companies"]:
        companies.append(Company(segment=Segment(item.pop("segment")), notes=tuple(item.pop("notes", [])), **item))
    return companies


def _load_scenario(path: Path | None) -> ScenarioAssumption:
    if path is None:
        return ScenarioAssumption()
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioAssumption(**data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AI memory supply-chain research screen.")
    parser.add_argument("--companies", type=Path, default=Path("examples/companies.json"))
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--output", type=Path, default=Path("report.md"))
    parser.add_argument("--wyckoff", type=Path, help="Optional JSON file with a Wyckoff spring observation.")
    args = parser.parse_args()

    scenario = _load_scenario(args.scenario)
    scores = run_portfolio_screen(_load_companies(args.companies), scenario)
    report = render_markdown_report(scores, scenario)

    if args.wyckoff:
        observation = WyckoffObservation(**json.loads(args.wyckoff.read_text(encoding="utf-8")))
        report += f"\n## Wyckoff execution signal\n\n`{wyckoff_spring_signal(observation)}`\n"

    args.output.write_text(report, encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
