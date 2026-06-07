"""Medium-cycle high/low pool classifier and rotation detector."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .models import MonitorConfig, PoolMember, RotationSignal, SecuritySnapshot


class MarketRotationMonitor:
    """Build high/low watch pools and detect medium-cycle rotation.

    The monitor deliberately avoids short-term price-only rules. It combines
    60/120-day position, moving-average slope, drawdown, and relative strength
    to identify whether high-position stocks are weakening and whether low-
    position stocks are repairing.
    """

    def __init__(self, config: MonitorConfig | None = None) -> None:
        self.config = config or MonitorConfig()

    def classify(self, snapshot: SecuritySnapshot) -> PoolMember:
        """Classify one security into high, low, or neutral pool."""

        cfg = self.config
        position_score = (snapshot.position_60d * 0.65) + (snapshot.position_120d * 0.35)
        trend_score = self._trend_score(snapshot)
        risk_score = self._breakdown_risk(snapshot, position_score)
        repair_score = self._repair_score(snapshot, position_score)
        reasons: list[str] = []

        if position_score >= cfg.high_position_threshold:
            reasons.append(f"中周期位置偏高({position_score:.2f})")
            if snapshot.relative_strength >= cfg.high_rs_threshold:
                reasons.append("相对强度仍占优")
            if trend_score < 0:
                reasons.append("均线斜率转弱")
            if risk_score >= cfg.high_breakdown_score:
                reasons.append("高位退潮风险升高")
            return PoolMember(snapshot, "high", position_score, risk_score, repair_score, tuple(reasons))

        if position_score <= cfg.low_position_threshold:
            reasons.append(f"中周期位置偏低({position_score:.2f})")
            if snapshot.drawdown_60d <= cfg.steep_drawdown_threshold:
                reasons.append("60日回撤充分")
            if repair_score >= cfg.low_repair_score:
                reasons.append("低位修复信号增强")
            return PoolMember(snapshot, "low", 1 - position_score, risk_score, repair_score, tuple(reasons))

        reasons.append(f"中周期位置居中({position_score:.2f})")
        if snapshot.relative_strength <= cfg.weak_rs_threshold:
            reasons.append("相对强度偏弱，暂不追高")
        return PoolMember(snapshot, "neutral", 0.5, risk_score, repair_score, tuple(reasons))

    def build_pools(self, snapshots: list[SecuritySnapshot]) -> dict[str, list[PoolMember]]:
        """Return high/low/neutral pools sorted by actionable score."""

        pools: dict[str, list[PoolMember]] = {"high": [], "low": [], "neutral": []}
        for snapshot in snapshots:
            member = self.classify(snapshot)
            pools[member.pool].append(member)

        pools["high"].sort(key=lambda item: (item.risk_score, item.score), reverse=True)
        pools["low"].sort(key=lambda item: (item.repair_score, item.score), reverse=True)
        pools["neutral"].sort(key=lambda item: item.risk_score, reverse=True)
        return pools

    def detect_rotation(self, snapshots: list[SecuritySnapshot]) -> list[RotationSignal]:
        """Detect high-low and sector-to-sector switching signals."""

        pools = self.build_pools(snapshots)
        signals: list[RotationSignal] = []
        high_risk = self._average([member.risk_score for member in pools["high"]])
        low_repair = self._average([member.repair_score for member in pools["low"]])

        if high_risk >= self.config.high_breakdown_score and low_repair >= self.config.low_repair_score:
            strength = high_risk + low_repair
            signals.append(
                RotationSignal(
                    "high_to_low",
                    "高位池",
                    "低位池",
                    strength,
                    "高位股退潮风险与低位股修复同步出现，进入高低切换观察窗口。",
                )
            )

        sector_scores = self._sector_scores(snapshots)
        if len(sector_scores) >= 2:
            ranked = sorted(sector_scores.items(), key=lambda item: item[1], reverse=True)
            target, target_score = ranked[0]
            source, source_score = ranked[-1]
            gap = target_score - source_score
            if gap >= self.config.rotation_gap_threshold:
                signals.append(
                    RotationSignal(
                        "sector_rotation",
                        source,
                        target,
                        gap,
                        f"{target}修复/强势得分显著高于{source}，关注板块间高低切换。",
                    )
                )

        if not signals:
            signals.append(RotationSignal("no_rotation", "全市场", "全市场", 0.0, "尚未形成可靠中周期切换信号。"))
        return signals

    def _trend_score(self, snapshot: SecuritySnapshot) -> float:
        score = 0.0
        score += 1.0 if snapshot.ma20_slope > 0 else -1.0
        score += 1.0 if snapshot.ma60_slope > 0 else -1.0
        return score

    def _breakdown_risk(self, snapshot: SecuritySnapshot, position_score: float) -> float:
        cfg = self.config
        score = 0.0
        if position_score >= cfg.high_position_threshold:
            score += 1.0
        if snapshot.pct_change < -0.03:
            score += 1.0
        if snapshot.relative_strength <= cfg.weak_rs_threshold:
            score += 1.0
        if snapshot.ma20_slope < 0:
            score += 0.8
        if snapshot.ma60_slope < 0:
            score += 0.7
        if snapshot.volume_ratio >= 1.4 and snapshot.pct_change < 0:
            score += 0.5
        return score

    def _repair_score(self, snapshot: SecuritySnapshot, position_score: float) -> float:
        cfg = self.config
        score = 0.0
        if position_score <= cfg.low_position_threshold:
            score += 1.0
        if snapshot.drawdown_60d <= cfg.steep_drawdown_threshold:
            score += 0.8
        if snapshot.pct_change >= cfg.rebound_pct_threshold:
            score += 0.8
        if snapshot.relative_strength >= cfg.strong_rs_threshold:
            score += 0.9
        if snapshot.ma20_slope > 0:
            score += 0.5
        if snapshot.volume_ratio >= 1.1 and snapshot.pct_change > 0:
            score += 0.4
        return score

    def _sector_scores(self, snapshots: list[SecuritySnapshot]) -> dict[str, float]:
        grouped: dict[str, list[SecuritySnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            grouped[snapshot.sector].append(snapshot)

        scores: dict[str, float] = {}
        for sector, items in grouped.items():
            sector_members = [self.classify(item) for item in items]
            repair = self._average([member.repair_score for member in sector_members])
            risk = self._average([member.risk_score for member in sector_members])
            rs = self._average([item.relative_strength for item in items])
            pct = self._average([item.pct_change for item in items]) * 20
            scores[sector] = repair - risk + (rs * 0.25) + pct
        return scores

    @staticmethod
    def _average(values: list[float]) -> float:
        return mean(values) if values else 0.0
