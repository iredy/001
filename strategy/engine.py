from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from io import StringIO
from enum import Enum
from math import isfinite
from statistics import mean, pstdev
from typing import Sequence


class Action(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MacroSnapshot:
    pmi: float | None = None
    gdp_growth: float | None = None
    cpi: float | None = None
    ppi: float | None = None
    m2_growth: float | None = None
    credit_impulse: float | None = None
    lpr: float | None = None
    fx_change: float | None = None
    savings_rate: float | None = None
    fcf_yield: float | None = None
    earnings_growth: float | None = None


@dataclass(frozen=True)
class SentimentSnapshot:
    score: float = 0.0
    news_count: int = 0
    social_volume_z: float = 0.0


@dataclass(frozen=True)
class StrategySignal:
    module: str
    action: Action
    confidence: float
    reason: str
    metadata: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyDecision:
    action: Action
    confidence: float
    reason: str
    signals: tuple[StrategySignal, ...]
    risk_score: float
    position_size: float


def _clamp(value: float, lower: float = 0.0, upper: float = 0.95) -> float:
    if not isfinite(value):
        return lower
    return max(lower, min(upper, value))


def _sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window or window <= 0:
        return None
    return mean(values[-window:])


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out


def _rsi(closes: Sequence[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, cur in zip(closes[-period - 1 : -1], closes[-period:]):
        change = cur - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _macd(closes: Sequence[float]) -> tuple[float, float, float] | None:
    if len(closes) < 35:
        return None
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal_line = _ema_series(macd_line, 9)
    return macd_line[-1], signal_line[-1], macd_line[-1] - signal_line[-1]


def _pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old


class StrategyEngine:
    """High-confidence ensemble for Wyckoff/Gann, band, volume-price, technical and macro signals."""

    def __init__(self, min_confidence: float = 0.70) -> None:
        self.min_confidence = min_confidence

    def evaluate(
        self,
        bars: Sequence[Bar],
        *,
        macro: MacroSnapshot | None = None,
        sentiment: SentimentSnapshot | None = None,
    ) -> StrategyDecision:
        clean_bars = self._validate_bars(bars)
        signals = (
            self.wyckoff_gann(clean_bars),
            self.band(clean_bars),
            self.volume_price(clean_bars),
            self.technical(clean_bars),
            self.macro(macro or MacroSnapshot()),
            self.sentiment(sentiment or SentimentSnapshot()),
            self.dense_proxy(clean_bars),
            self.truth_proxy(clean_bars),
        )
        return self.combine(tuple(signals))

    def _validate_bars(self, bars: Sequence[Bar]) -> tuple[Bar, ...]:
        if len(bars) < 35:
            raise ValueError("at least 35 bars are required")
        ordered = tuple(sorted(bars, key=lambda x: x.date))
        for bar in ordered:
            if min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.volume < 0:
                raise ValueError(f"invalid OHLCV data at {bar.date}")
            if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
                raise ValueError(f"inconsistent high/low data at {bar.date}")
        return ordered

    def wyckoff_gann(self, bars: Sequence[Bar]) -> StrategySignal:
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        last = bars[-1]
        lookback = bars[-21:]
        prior_low = min(b.low for b in bars[-22:-1])
        avg_vol = mean(volumes[-21:-1]) if len(volumes) >= 22 else mean(volumes)
        body = abs(last.close - last.open)
        lower_shadow = min(last.open, last.close) - last.low
        spring = last.low < prior_low and lower_shadow > max(body * 1.5, last.close * 0.01) and last.volume < avg_vol
        ma20 = _sma(closes[:-1], 20) or closes[-2]
        days_from_low = len(bars) - 1 - min(range(len(bars)), key=lambda i: bars[i].low)
        gann_window = any(abs(days_from_low - w) <= 1 for w in (7, 14, 21, 30, 45, 60, 90))
        breakout = last.close > ma20 and closes[-2] <= ma20
        recent_high = max(b.high for b in bars[-21:-1])
        distribution = last.high > recent_high and last.close < last.open and last.volume > avg_vol * 1.3
        acd = sum((_pct_change(b.close, b.open) * b.volume) for b in lookback) / max(sum(b.volume for b in lookback), 1)
        if spring and (gann_window or breakout):
            conf = 0.60 + (0.10 if gann_window else 0) + (0.10 if breakout else 0)
            return StrategySignal("wyckoff_gann", Action.BUY, _clamp(conf), "Spring with Gann/time-price confirmation", {"acd": acd})
        if distribution:
            return StrategySignal("wyckoff_gann", Action.SELL, 0.72, "Distribution breakout failure", {"acd": acd})
        return StrategySignal("wyckoff_gann", Action.HOLD, 0.40, "No confirmed Wyckoff/Gann setup", {"acd": acd})

    def band(self, bars: Sequence[Bar]) -> StrategySignal:
        closes = [b.close for b in bars]
        last = closes[-1]
        peak = max(closes)
        drawdown = 1 - last / peak
        age = len(bars)
        stages = [30, 50, 80, 120, 150, 200]
        stage = sum(age >= x for x in stages) + 1
        p75_map = {1: 0.06, 2: 0.09, 3: 0.12, 4: 0.16, 5: 0.20, 6: 0.24, 7: 0.28}
        threshold = p75_map[stage]
        volatility = pstdev(closes[-20:]) / mean(closes[-20:]) if len(closes) >= 20 else 0.0
        stability_bonus = 0.05 if volatility < 0.035 else 0.0
        if drawdown >= threshold * 1.25:
            return StrategySignal("band", Action.BUY, _clamp(0.60 + stability_bonus), "Band low-buy zone", {"stage": stage, "drawdown": drawdown})
        if drawdown <= threshold * 0.2 and last >= mean(closes[-20:]) * 1.08:
            return StrategySignal("band", Action.SELL, _clamp(0.80), "Band trim/clear zone", {"stage": stage, "drawdown": drawdown})
        return StrategySignal("band", Action.HOLD, 0.45, "Band neutral", {"stage": stage, "drawdown": drawdown})

    def volume_price(self, bars: Sequence[Bar]) -> StrategySignal:
        last = bars[-1]
        avg_vol = mean(b.volume for b in bars[-21:-1])
        volratio = last.volume / avg_vol if avg_vol else 1.0
        pricechange = _pct_change(last.close, bars[-2].close)
        strength = min(abs(pricechange) / 0.05, 1.0) * 0.2
        if volratio > 1.5 and pricechange > 0.02:
            return StrategySignal("volume_price", Action.BUY, _clamp(0.50 + 0.25 + strength), "Volume-price expansion", {"volratio": volratio, "pricechange": pricechange})
        if volratio > 1.5 and pricechange < -0.02:
            return StrategySignal("volume_price", Action.SELL, _clamp(0.50 + 0.25 + strength), "Bearish volume-price divergence", {"volratio": volratio, "pricechange": pricechange})
        if volratio < 0.8 and pricechange > 0.02:
            return StrategySignal("volume_price", Action.HOLD, 0.55, "Low-volume rise warning", {"volratio": volratio, "pricechange": pricechange})
        return StrategySignal("volume_price", Action.HOLD, 0.40, "Volume-price neutral", {"volratio": volratio, "pricechange": pricechange})

    def technical(self, bars: Sequence[Bar]) -> StrategySignal:
        closes = [b.close for b in bars]
        rsi = _rsi(closes) or 50.0
        macd_tuple = _macd(closes)
        macd_line, signal_line, hist = macd_tuple or (0.0, 0.0, 0.0)
        prev_macd_tuple = _macd(closes[:-1])
        prev_macd, prev_signal, _ = prev_macd_tuple or (macd_line, signal_line, 0.0)
        ma20 = _sma(closes, 20) or closes[-1]
        sigma = pstdev(closes[-20:]) if len(closes) >= 20 else 0.0
        lower = ma20 - 2 * sigma
        upper = ma20 + 2 * sigma
        golden = prev_macd <= prev_signal and macd_line > signal_line
        death = prev_macd >= prev_signal and macd_line < signal_line
        if (golden and rsi < 35) or (closes[-1] <= lower * 1.02 and macd_line > 0):
            return StrategySignal("technical", Action.BUY, _clamp(0.50 + 0.25 + min(abs(hist), 0.2)), "Technical buy confluence", {"rsi": rsi, "macd": macd_line})
        if (death and rsi > 65) or (closes[-1] >= upper * 0.98 and macd_line < 0):
            return StrategySignal("technical", Action.SELL, _clamp(0.50 + 0.25 + min(abs(hist), 0.2)), "Technical sell confluence", {"rsi": rsi, "macd": macd_line})
        return StrategySignal("technical", Action.HOLD, 0.40, "Technical neutral", {"rsi": rsi, "macd": macd_line})

    def macro(self, snap: MacroSnapshot) -> StrategySignal:
        positives = 0
        negatives = 0
        if snap.pmi is not None:
            positives += snap.pmi >= 50
            negatives += snap.pmi < 49
        if snap.credit_impulse is not None:
            positives += snap.credit_impulse > 0
            negatives += snap.credit_impulse < -0.5
        if snap.ppi is not None:
            positives += snap.ppi > -1
            negatives += snap.ppi < -3
        if snap.earnings_growth is not None:
            positives += snap.earnings_growth > 0
            negatives += snap.earnings_growth < -0.05
        atypical_recovery = (snap.credit_impulse or 0) > 0 and (snap.ppi or 0) < 0 and (snap.savings_rate or 0) > 0.35
        if positives >= negatives + 2 or atypical_recovery:
            return StrategySignal("macro", Action.BUY, 0.70, "Macro recovery support", {"positives": positives, "negatives": negatives})
        if negatives >= positives + 2:
            return StrategySignal("macro", Action.SELL, 0.70, "Macro deterioration", {"positives": positives, "negatives": negatives})
        return StrategySignal("macro", Action.HOLD, 0.50, "Macro neutral", {"positives": positives, "negatives": negatives})

    def sentiment(self, snap: SentimentSnapshot) -> StrategySignal:
        confidence = _clamp(0.45 + min(abs(snap.score), 1.0) * 0.25 + min(snap.news_count / 100, 0.15))
        if snap.score > 0.35 and snap.social_volume_z > -1:
            return StrategySignal("sentiment", Action.BUY, confidence, "Positive sentiment", {"score": snap.score})
        if snap.score < -0.35:
            return StrategySignal("sentiment", Action.SELL, confidence, "Negative sentiment", {"score": snap.score})
        return StrategySignal("sentiment", Action.HOLD, 0.40, "Sentiment neutral", {"score": snap.score})

    def dense_proxy(self, bars: Sequence[Bar]) -> StrategySignal:
        closes = [b.close for b in bars]
        momentum = _pct_change(closes[-1], closes[-21])
        volatility = pstdev(closes[-20:]) / mean(closes[-20:])
        score = momentum / max(volatility, 0.01)
        if score > 1.2:
            return StrategySignal("dense", Action.BUY, _clamp(0.55 + min(score / 10, 0.30)), "Dense proxy positive risk-adjusted momentum", {"score": score})
        if score < -1.2:
            return StrategySignal("dense", Action.SELL, _clamp(0.55 + min(abs(score) / 10, 0.30)), "Dense proxy negative risk-adjusted momentum", {"score": score})
        return StrategySignal("dense", Action.HOLD, 0.40, "Dense proxy neutral", {"score": score})

    def truth_proxy(self, bars: Sequence[Bar]) -> StrategySignal:
        closes = [b.close for b in bars]
        short = _sma(closes, 5) or closes[-1]
        medium = _sma(closes, 20) or closes[-1]
        slope = _pct_change(short, medium)
        if slope > 0.03:
            return StrategySignal("truth", Action.BUY, 0.62, "Truth proxy confirms uptrend", {"slope": slope})
        if slope < -0.03:
            return StrategySignal("truth", Action.SELL, 0.62, "Truth proxy confirms downtrend", {"slope": slope})
        return StrategySignal("truth", Action.HOLD, 0.40, "Truth proxy neutral", {"slope": slope})

    def combine(self, signals: Sequence[StrategySignal]) -> StrategyDecision:
        buy_score = sum(s.confidence for s in signals if s.action == Action.BUY)
        sell_score = sum(s.confidence for s in signals if s.action == Action.SELL)
        active_count = sum(1 for s in signals if s.action != Action.HOLD)
        total = buy_score + sell_score
        if total == 0 or active_count < 2:
            return StrategyDecision(Action.HOLD, 0.40, "Insufficient active confirmations", tuple(signals), 0.50, 0.0)
        edge = abs(buy_score - sell_score) / total
        direction = Action.BUY if buy_score > sell_score else Action.SELL
        agreement = max(buy_score, sell_score) / max(active_count, 1)
        conflict_penalty = min(buy_score, sell_score) / total * 0.30
        confidence = _clamp(0.45 + agreement * 0.35 + edge * 0.25 - conflict_penalty)
        if confidence < self.min_confidence:
            return StrategyDecision(Action.HOLD, confidence, "Confidence below execution threshold", tuple(signals), 1 - confidence, 0.0)
        risk_score = _clamp(1 - confidence, 0.05, 0.80)
        position_size = _clamp((confidence - self.min_confidence) / (0.95 - self.min_confidence), 0.0, 1.0)
        reasons = "; ".join(s.reason for s in signals if s.action == direction)
        return StrategyDecision(direction, confidence, reasons, tuple(signals), risk_score, position_size)


def _parse_csv_text(text: str) -> list[Bar]:
    import csv

    reader = csv.DictReader(StringIO(text))
    bars = []
    for row in reader:
        raw_date = row["date"]
        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        bars.append(
            Bar(
                date=parsed_date,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    return bars


def load_csv(path: str) -> list[Bar]:
    with open(path, newline="", encoding="utf-8") as handle:
        return _parse_csv_text(handle.read())


def load_csv_url(url: str, *, config=None) -> list[Bar]:
    from .data_source import fetch_text

    return _parse_csv_text(fetch_text(url, config=config))


def evaluate_csv(path: str) -> StrategyDecision:
    return StrategyEngine().evaluate(load_csv(path))


def evaluate_csv_url(url: str, *, config=None) -> StrategyDecision:
    return StrategyEngine().evaluate(load_csv_url(url, config=config))
