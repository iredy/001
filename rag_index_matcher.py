"""RAG strategy to index time-series matcher.

This module implements the pipeline:

    RAG strategy -> date/signal extraction -> index data fetch -> time-series
    alignment -> performance validation -> LLM learning samples

It is intentionally adapter-based so it can be plugged into an existing
``TimeSeriesRAG`` retriever and any market-data source that returns daily index
bars for symbols such as ``000001.SH`` (SSE Composite) or ``000688.SH``
(STAR 50 / 科创50).
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import re
from statistics import mean
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


Signal = str

BULLISH: Signal = "bullish"
BEARISH: Signal = "bearish"
NEUTRAL: Signal = "neutral"
UNKNOWN: Signal = "unknown"


@dataclass(frozen=True)
class StrategyRecord:
    """A historical strategy item extracted from RAG content."""

    strategy_date: date
    signal: Signal
    text: str
    confidence: float = 1.0
    source_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexBar:
    """One daily OHLCV index bar."""

    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(frozen=True)
class StrategyIndexMatch:
    """Alignment and validation result for one strategy record."""

    strategy: StrategyRecord
    index_symbol: str
    aligned_date: date
    entry_close: float
    exit_date: date
    exit_close: float
    forward_return: float
    max_drawdown: float
    max_runup: float
    direction_correct: bool | None
    bars_used: tuple[IndexBar, ...]

    @property
    def forward_return_pct(self) -> float:
        return self.forward_return * 100


@dataclass(frozen=True)
class BacktestSummary:
    """Aggregate quality metrics for matched strategies."""

    total: int
    evaluated: int
    accuracy: float | None
    average_return: float | None
    cumulative_return: float | None
    by_signal: Mapping[Signal, Mapping[str, float | int | None]]


class IndexDataProvider(Protocol):
    """Protocol for index data adapters."""

    def get_index_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> Sequence[IndexBar | Mapping[str, Any]]:
        """Return daily index bars sorted or unsorted within the date range."""


RagRetriever = Callable[[str], Iterable[str | Mapping[str, Any] | StrategyRecord]]


class CsvIndexDataProvider:
    """Simple local CSV adapter for offline backtests.

    ``path_map`` maps index symbols to CSV files. Each CSV should include a
    date-like column (``trade_date``/``date``/``datetime``) and ``close``;
    ``open``, ``high``, ``low`` and ``volume`` are optional.
    """

    def __init__(self, path_map: Mapping[str, str | Path]) -> None:
        self.path_map = {symbol: Path(path) for symbol, path in path_map.items()}

    def get_index_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> Sequence[IndexBar | Mapping[str, Any]]:
        if symbol not in self.path_map:
            raise KeyError(f"No CSV path configured for index symbol {symbol!r}")

        rows: list[Mapping[str, Any]] = []
        with self.path_map[symbol].open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_date = coerce_date(row.get("trade_date") or row.get("date") or row.get("datetime"))
                if row_date is not None and start_date <= row_date <= end_date:
                    rows.append(row)
        return rows


class TimeSeriesRAGIndexMatcher:
    """Match historical RAG strategy signals with index time series.

    Parameters
    ----------
    index_provider:
        Adapter that provides index bars. It can be a class wrapping AkShare,
        Tushare, a database, or local CSV data.
    default_index_symbol:
        Default index used when a strategy does not specify a market/sector.
        ``000001.SH`` is commonly used for 上证指数.
    sector_index_map:
        Optional keyword-to-index routing, e.g. ``{"科创": "000688.SH"}``.
    """

    DEFAULT_BULLISH_KEYWORDS: tuple[str, ...] = (
        "企稳",
        "反弹",
        "修复",
        "突破",
        "上行",
        "看多",
        "做多",
        "增配",
        "加仓",
        "机会",
        "强势",
        "回升",
    )
    DEFAULT_BEARISH_KEYWORDS: tuple[str, ...] = (
        "下跌",
        "回落",
        "调整",
        "破位",
        "走弱",
        "看空",
        "减仓",
        "风险",
        "避险",
        "承压",
        "弱势",
        "谨慎",
    )
    DEFAULT_NEUTRAL_KEYWORDS: tuple[str, ...] = (
        "震荡",
        "观望",
        "分化",
        "均衡",
        "横盘",
        "中性",
    )

    def __init__(
        self,
        index_provider: IndexDataProvider,
        default_index_symbol: str = "000001.SH",
        sector_index_map: Mapping[str, str] | None = None,
    ) -> None:
        self.index_provider = index_provider
        self.default_index_symbol = default_index_symbol
        self.sector_index_map = dict(
            sector_index_map or {"科创": "000688.SH", "科创50": "000688.SH"}
        )

    def retrieve_match_and_evaluate(
        self,
        query: str,
        rag_retriever: RagRetriever,
        *,
        horizon_days: int = 5,
        lookback_days: int = 3,
        explicit_index_symbol: str | None = None,
    ) -> tuple[list[StrategyIndexMatch], BacktestSummary]:
        """Run the full RAG-to-index validation pipeline for one query."""

        raw_items = list(rag_retriever(query))
        strategies = self.extract_strategies(raw_items)
        matches = self.match_strategies(
            strategies,
            horizon_days=horizon_days,
            lookback_days=lookback_days,
            explicit_index_symbol=explicit_index_symbol,
        )
        return matches, self.summarize(matches)

    def extract_strategies(self, items: Iterable[str | Mapping[str, Any] | StrategyRecord]) -> list[StrategyRecord]:
        """Convert RAG results into dated strategy records.

        Supported RAG result shapes:
        * ``StrategyRecord`` objects;
        * strings containing a date and market wording;
        * dictionaries with fields like ``date``, ``content``/``text``,
          ``signal``, ``confidence``, ``id`` and optional ``metadata``.
        """

        strategies: list[StrategyRecord] = []
        for item in items:
            if isinstance(item, StrategyRecord):
                strategies.append(item)
                continue

            if isinstance(item, str):
                text = item
                raw_date: Any = None
                raw_signal: Any = None
                source_id = None
                metadata: Mapping[str, Any] = {}
                confidence = 1.0
            else:
                text = str(item.get("content") or item.get("text") or item.get("document") or "")
                raw_date = item.get("date") or item.get("strategy_date") or item.get("trade_date")
                raw_signal = item.get("signal")
                source_id = str(item.get("id") or item.get("source_id") or "") or None
                metadata = item.get("metadata") or {}
                confidence = float(item.get("confidence", 1.0))

            parsed_date = coerce_date(raw_date) if raw_date is not None else extract_first_date(text)
            if parsed_date is None:
                continue
            signal = normalize_signal(raw_signal) if raw_signal is not None else infer_signal(text)
            strategies.append(
                StrategyRecord(
                    strategy_date=parsed_date,
                    signal=signal,
                    text=text,
                    confidence=confidence,
                    source_id=source_id,
                    metadata=metadata,
                )
            )
        return strategies

    def match_strategies(
        self,
        strategies: Sequence[StrategyRecord],
        *,
        horizon_days: int = 5,
        lookback_days: int = 3,
        explicit_index_symbol: str | None = None,
    ) -> list[StrategyIndexMatch]:
        """Align strategies to index bars and compute forward outcomes."""

        if horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if lookback_days < 0:
            raise ValueError("lookback_days cannot be negative")

        grouped: dict[str, list[StrategyRecord]] = {}
        for strategy in strategies:
            symbol = explicit_index_symbol or self.choose_index_symbol(strategy)
            grouped.setdefault(symbol, []).append(strategy)

        matches: list[StrategyIndexMatch] = []
        for symbol, symbol_strategies in grouped.items():
            start = min(s.strategy_date for s in symbol_strategies) - timedelta(days=lookback_days + 7)
            end = max(s.strategy_date for s in symbol_strategies) + timedelta(days=horizon_days * 3 + 10)
            bars = normalize_bars(self.index_provider.get_index_bars(symbol, start, end))
            if not bars:
                continue
            dates = [bar.trade_date for bar in bars]
            for strategy in symbol_strategies:
                aligned_idx = align_to_trading_day(dates, strategy.strategy_date, lookback_days=lookback_days)
                if aligned_idx is None:
                    continue
                exit_idx = min(aligned_idx + horizon_days, len(bars) - 1)
                if exit_idx == aligned_idx:
                    continue
                window = tuple(bars[aligned_idx : exit_idx + 1])
                entry = bars[aligned_idx]
                exit_bar = bars[exit_idx]
                forward_return = exit_bar.close / entry.close - 1
                matches.append(
                    StrategyIndexMatch(
                        strategy=strategy,
                        index_symbol=symbol,
                        aligned_date=entry.trade_date,
                        entry_close=entry.close,
                        exit_date=exit_bar.trade_date,
                        exit_close=exit_bar.close,
                        forward_return=forward_return,
                        max_drawdown=calculate_max_drawdown(window),
                        max_runup=calculate_max_runup(window),
                        direction_correct=judge_direction(strategy.signal, forward_return),
                        bars_used=window,
                    )
                )
        return sorted(matches, key=lambda match: (match.strategy.strategy_date, match.index_symbol))

    def summarize(self, matches: Sequence[StrategyIndexMatch]) -> BacktestSummary:
        """Aggregate match results into accuracy and return metrics."""

        evaluated_matches = [m for m in matches if m.direction_correct is not None]
        accuracy = None
        if evaluated_matches:
            accuracy = sum(1 for m in evaluated_matches if m.direction_correct) / len(evaluated_matches)

        returns = [m.forward_return for m in matches]
        average_return = mean(returns) if returns else None
        cumulative_return = None
        if returns:
            cumulative = 1.0
            for value in returns:
                cumulative *= 1 + value
            cumulative_return = cumulative - 1

        by_signal: dict[Signal, Mapping[str, float | int | None]] = {}
        for signal in (BULLISH, BEARISH, NEUTRAL, UNKNOWN):
            signal_matches = [m for m in matches if m.strategy.signal == signal]
            signal_evaluated = [m for m in signal_matches if m.direction_correct is not None]
            by_signal[signal] = {
                "total": len(signal_matches),
                "evaluated": len(signal_evaluated),
                "accuracy": (
                    sum(1 for m in signal_evaluated if m.direction_correct) / len(signal_evaluated)
                    if signal_evaluated
                    else None
                ),
                "average_return": mean([m.forward_return for m in signal_matches]) if signal_matches else None,
            }

        return BacktestSummary(
            total=len(matches),
            evaluated=len(evaluated_matches),
            accuracy=accuracy,
            average_return=average_return,
            cumulative_return=cumulative_return,
            by_signal=by_signal,
        )

    def build_llm_learning_samples(self, matches: Sequence[StrategyIndexMatch]) -> list[dict[str, Any]]:
        """Create compact supervised samples for LLM market-judgement learning."""

        samples: list[dict[str, Any]] = []
        for match in matches:
            outcome = "unverifiable"
            if match.direction_correct is True:
                outcome = "correct"
            elif match.direction_correct is False:
                outcome = "incorrect"
            samples.append(
                {
                    "instruction": "根据历史策略文本、指数走势和验证结果，总结哪些研判信号有效。",
                    "strategy_date": match.strategy.strategy_date.isoformat(),
                    "aligned_index_date": match.aligned_date.isoformat(),
                    "index_symbol": match.index_symbol,
                    "strategy_signal": match.strategy.signal,
                    "strategy_text": match.strategy.text,
                    "market_path": [
                        {"date": bar.trade_date.isoformat(), "close": bar.close}
                        for bar in match.bars_used
                    ],
                    "forward_return_pct": round(match.forward_return_pct, 4),
                    "max_drawdown_pct": round(match.max_drawdown * 100, 4),
                    "max_runup_pct": round(match.max_runup * 100, 4),
                    "label": outcome,
                }
            )
        return samples

    def choose_index_symbol(self, strategy: StrategyRecord) -> str:
        """Route a strategy to a broad or sector index using text/metadata hints."""

        explicit = strategy.metadata.get("index_symbol") if strategy.metadata else None
        if explicit:
            return str(explicit)
        text = strategy.text
        for keyword, symbol in self.sector_index_map.items():
            if keyword in text:
                return symbol
        return self.default_index_symbol


def extract_first_date(text: str) -> date | None:
    """Extract the first date from common Chinese/ISO strategy text."""

    patterns = (
        r"(?P<y>20\d{2})[-/.年](?P<m>\d{1,2})[-/.月](?P<d>\d{1,2})日?",
        r"(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    return None


def coerce_date(value: Any) -> date | None:
    """Coerce date-like values from RAG metadata or market adapters."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int):
        value = str(value)
    if isinstance(value, str):
        parsed = extract_first_date(value)
        if parsed is not None:
            return parsed
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
    raise ValueError(f"Unsupported date value: {value!r}")


def infer_signal(text: str) -> Signal:
    """Infer strategy direction from Chinese market judgement keywords."""

    bullish = keyword_score(text, TimeSeriesRAGIndexMatcher.DEFAULT_BULLISH_KEYWORDS)
    bearish = keyword_score(text, TimeSeriesRAGIndexMatcher.DEFAULT_BEARISH_KEYWORDS)
    neutral = keyword_score(text, TimeSeriesRAGIndexMatcher.DEFAULT_NEUTRAL_KEYWORDS)
    if bullish > bearish and bullish >= neutral:
        return BULLISH
    if bearish > bullish and bearish >= neutral:
        return BEARISH
    if neutral > 0:
        return NEUTRAL
    return UNKNOWN


def normalize_signal(value: Any) -> Signal:
    """Normalize user/RAG signal labels to canonical directions."""

    text = str(value).strip().lower()
    if text in {BULLISH, "long", "buy", "positive", "看多", "做多", "反弹", "企稳反弹"}:
        return BULLISH
    if text in {BEARISH, "short", "sell", "negative", "看空", "做空", "回落", "下跌"}:
        return BEARISH
    if text in {NEUTRAL, "hold", "flat", "sideways", "震荡", "观望", "中性"}:
        return NEUTRAL
    return infer_signal(text)


def keyword_score(text: str, keywords: Sequence[str]) -> int:
    return sum(text.count(keyword) for keyword in keywords)


def normalize_bars(items: Sequence[IndexBar | Mapping[str, Any]]) -> list[IndexBar]:
    """Convert market adapter outputs into sorted ``IndexBar`` objects."""

    bars: list[IndexBar] = []
    for item in items:
        if isinstance(item, IndexBar):
            bars.append(item)
            continue
        raw_date = item.get("trade_date") or item.get("date") or item.get("datetime")
        trade_date = coerce_date(raw_date)
        if trade_date is None:
            continue
        bars.append(
            IndexBar(
                trade_date=trade_date,
                open=float(item.get("open", item.get("close"))),
                high=float(item.get("high", item.get("close"))),
                low=float(item.get("low", item.get("close"))),
                close=float(item["close"]),
                volume=float(item["volume"]) if item.get("volume") is not None else None,
            )
        )
    return sorted(bars, key=lambda bar: bar.trade_date)


def align_to_trading_day(dates: Sequence[date], target: date, *, lookback_days: int = 3) -> int | None:
    """Find an index bar for target date or nearest trading day.

    Preference order:
    1. exact target date;
    2. previous trading day within ``lookback_days`` calendar days;
    3. next available trading day.
    """

    insertion = bisect_left(dates, target)
    if insertion < len(dates) and dates[insertion] == target:
        return insertion
    previous = insertion - 1
    if previous >= 0 and (target - dates[previous]).days <= lookback_days:
        return previous
    if insertion < len(dates):
        return insertion
    return None


def calculate_max_drawdown(bars: Sequence[IndexBar]) -> float:
    """Calculate maximum close-to-close drawdown in an aligned window."""

    peak = bars[0].close
    max_drawdown = 0.0
    for bar in bars:
        peak = max(peak, bar.close)
        max_drawdown = min(max_drawdown, bar.close / peak - 1)
    return max_drawdown


def calculate_max_runup(bars: Sequence[IndexBar]) -> float:
    """Calculate maximum close-to-close run-up in an aligned window."""

    trough = bars[0].close
    max_runup = 0.0
    for bar in bars:
        trough = min(trough, bar.close)
        max_runup = max(max_runup, bar.close / trough - 1)
    return max_runup


def judge_direction(signal: Signal, forward_return: float, *, neutral_band: float = 0.005) -> bool | None:
    """Judge whether a signal was directionally correct."""

    if signal == BULLISH:
        return forward_return > 0
    if signal == BEARISH:
        return forward_return < 0
    if signal == NEUTRAL:
        return abs(forward_return) <= neutral_band
    return None
