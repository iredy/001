"""Command line interface for market rotation monitoring."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .models import SecuritySnapshot
from .monitor import MarketRotationMonitor


FIELDNAMES = (
    "symbol",
    "name",
    "sector",
    "board",
    "close",
    "pct_change",
    "relative_strength",
    "position_60d",
    "position_120d",
    "ma20_slope",
    "ma60_slope",
    "drawdown_60d",
    "turnover_ratio",
    "volume_ratio",
)


def load_snapshots(path: Path) -> list[SecuritySnapshot]:
    """Load normalized security snapshots from CSV."""

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = set(FIELDNAMES) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")
        return [
            SecuritySnapshot(
                symbol=row["symbol"],
                name=row["name"],
                sector=row["sector"],
                board=row["board"],
                close=float(row["close"]),
                pct_change=float(row["pct_change"]),
                relative_strength=float(row["relative_strength"]),
                position_60d=float(row["position_60d"]),
                position_120d=float(row["position_120d"]),
                ma20_slope=float(row["ma20_slope"]),
                ma60_slope=float(row["ma60_slope"]),
                drawdown_60d=float(row["drawdown_60d"]),
                turnover_ratio=float(row.get("turnover_ratio") or 0.0),
                volume_ratio=float(row.get("volume_ratio") or 1.0),
            )
            for row in reader
        ]


def render_report(snapshots: list[SecuritySnapshot]) -> str:
    """Render a compact Markdown report for pools and rotation signals."""

    monitor = MarketRotationMonitor()
    pools = monitor.build_pools(snapshots)
    signals = monitor.detect_rotation(snapshots)
    lines = ["# 中周期高低位监控报告", ""]

    for pool_name, title in (("high", "高位监控池"), ("low", "低位监控池"), ("neutral", "中性观察池")):
        lines.extend([f"## {title}", "", "| 标的 | 板块 | 得分 | 退潮风险 | 修复信号 | 原因 |", "| --- | --- | ---: | ---: | ---: | --- |"])
        for member in pools[pool_name]:
            reasons = "；".join(member.reasons)
            lines.append(
                f"| {member.snapshot.name}({member.snapshot.symbol}) | {member.snapshot.sector} | "
                f"{member.score:.2f} | {member.risk_score:.2f} | {member.repair_score:.2f} | {reasons} |"
            )
        lines.append("")

    lines.extend(["## 切换信号", ""])
    for signal in signals:
        lines.append(f"- **{signal.direction}**：{signal.source} → {signal.target}，强度 {signal.strength:.2f}。{signal.summary}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build medium-cycle high/low watch pools and rotation signals.")
    parser.add_argument("csv", type=Path, help="CSV file with normalized security snapshots")
    args = parser.parse_args()
    print(render_report(load_snapshots(args.csv)))


if __name__ == "__main__":
    main()
