#!/usr/bin/env python3
"""基于沪深300趋势波段，统计个股上涨空间与回撤幅度映射。"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from glob import glob
from statistics import mean, median
from typing import Dict, List, Sequence, Tuple

THRESHOLDS = [0.30, 0.50, 0.80, 1.00, 1.20, 1.50, 2.00, 2.50, 3.00, 5.00]


@dataclass
class Segment:
    start: date
    peak: date
    end: date
    trough_price: float
    peak_price: float

    @property
    def rise(self) -> float:
        return self.peak_price / self.trough_price - 1.0


@dataclass
class StockWaveStat:
    symbol: str
    segment_start: date
    segment_end: date
    max_gain: float
    max_drawdown_after_peak: float


@dataclass
class ArchitectureSignal:
    symbol: str
    segment_start: date
    as_of: date
    runup_pct: float
    current_dd_pct: float
    vol_ratio_3d_launch: float | None
    vol_ratio_1d_60d: float | None
    stage_name: str
    stability_score: int
    action: str
    days_in_stage: int
    risk_drawdown_pct: float | None
    theil_sen_support: float | None
    close: float
    blacklist: bool
    reverse_panic: bool
    reasons: List[str]


def parse_date(text: str) -> date:
    return datetime.strptime(text.strip(), "%Y-%m-%d").date()


def read_price_csv(path: str, date_col: str = "date", close_col: str = "close") -> Dict[date, float]:
    out: Dict[date, float] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if date_col not in reader.fieldnames or close_col not in reader.fieldnames:
            raise ValueError(f"{path} 缺少必须字段: {date_col}, {close_col}")
        for row in reader:
            try:
                d = parse_date(row[date_col])
                c = float(row[close_col])
            except Exception:
                continue
            if c > 0:
                out[d] = c
    return out


def read_volume_csv(path: str, date_col: str = "date", volume_col: str = "volume") -> Dict[date, float]:
    out: Dict[date, float] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if date_col not in reader.fieldnames or volume_col not in reader.fieldnames:
            return out
        for row in reader:
            try:
                d = parse_date(row[date_col])
                v = float(row[volume_col])
            except Exception:
                continue
            if v > 0:
                out[d] = v
    return out


def clip_last_years(series: Dict[date, float], years: int = 10) -> Dict[date, float]:
    if not series:
        return {}
    end = max(series)
    start = end - timedelta(days=365 * years)
    return {d: p for d, p in series.items() if d >= start}


def detect_up_segments(index_series: Dict[date, float], reversal_pct: float = 0.12) -> List[Segment]:
    items = sorted(index_series.items())
    if len(items) < 3:
        return []

    segments: List[Segment] = []
    trough_date, trough_price = items[0]
    peak_date, peak_price = items[0]
    in_uptrend = False

    for d, p in items[1:]:
        if p < trough_price and not in_uptrend:
            trough_date, trough_price = d, p
            peak_date, peak_price = d, p
            continue

        if p > peak_price:
            peak_date, peak_price = d, p
            if peak_price / trough_price - 1.0 >= reversal_pct:
                in_uptrend = True

        if in_uptrend:
            drawdown = 1.0 - p / peak_price
            if drawdown >= reversal_pct:
                # 一个完整波段定义为：上一谷底 -> 峰值 -> 回撤触发时点（该时点近似下一谷底区间入口）
                segments.append(
                    Segment(
                        start=trough_date,
                        peak=peak_date,
                        end=d,
                        trough_price=trough_price,
                        peak_price=peak_price,
                    )
                )
                trough_date, trough_price = d, p
                peak_date, peak_price = d, p
                in_uptrend = False

    if in_uptrend and peak_date > trough_date:
        # 尾段尚未发生足够回撤，使用最后一个交易日作为段终点
        segments.append(
            Segment(
                start=trough_date,
                peak=peak_date,
                end=items[-1][0],
                trough_price=trough_price,
                peak_price=peak_price,
            )
        )
    return [s for s in segments if s.rise > 0]


def _series_between(series: Dict[date, float], start: date, end: date) -> List[Tuple[date, float]]:
    return sorted((d, p) for d, p in series.items() if start <= d <= end)


def calc_stock_wave_stat(symbol: str, series: Dict[date, float], segment: Segment) -> StockWaveStat | None:
    part = _series_between(series, segment.start, segment.end)
    if len(part) < 5:
        return None

    base = part[0][1]
    gains = [(d, px / base - 1.0) for d, px in part]
    peak_date, max_gain = max(gains, key=lambda x: x[1])

    post_peak = [(d, px) for d, px in part if d >= peak_date]
    if not post_peak:
        return None

    peak_px = post_peak[0][1]
    trough_after_peak = min(px for _, px in post_peak)
    max_dd = 1.0 - trough_after_peak / peak_px

    return StockWaveStat(
        symbol=symbol,
        segment_start=segment.start,
        segment_end=segment.end,
        max_gain=max_gain,
        max_drawdown_after_peak=max_dd,
    )


def load_stock_universe(stock_dir: str) -> Dict[str, Dict[date, float]]:
    data: Dict[str, Dict[date, float]] = {}
    for path in sorted(glob(os.path.join(stock_dir, "*.csv"))):
        symbol = os.path.splitext(os.path.basename(path))[0]
        try:
            data[symbol] = read_price_csv(path)
        except Exception:
            continue
    return data


def load_volume_universe(stock_dir: str) -> Dict[str, Dict[date, float]]:
    data: Dict[str, Dict[date, float]] = {}
    for path in sorted(glob(os.path.join(stock_dir, "*.csv"))):
        symbol = os.path.splitext(os.path.basename(path))[0]
        data[symbol] = read_volume_csv(path)
    return data


def winsorize(values: Sequence[float], lower_q: float = 0.02, upper_q: float = 0.98) -> List[float]:
    if not values:
        return []
    arr = sorted(values)
    lo_i = max(0, int(len(arr) * lower_q) - 1)
    hi_i = min(len(arr) - 1, int(len(arr) * upper_q))
    lo, hi = arr[lo_i], arr[hi_i]
    return [min(max(v, lo), hi) for v in values]


def summarize(records: Sequence[StockWaveStat]) -> Dict[str, List[Dict[str, float | int | str | None]]]:
    def _safe(v: float | None) -> float | None:
        return round(v, 4) if v is not None else None

    def _quantile(arr: Sequence[float], q: float) -> float | None:
        if not arr:
            return None
        s = sorted(arr)
        if len(s) == 1:
            return s[0]
        pos = (len(s) - 1) * q
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return s[lo]
        weight = pos - lo
        return s[lo] * (1 - weight) + s[hi] * weight

    summary_map: List[Dict[str, float | int | None]] = []
    rise_dd_pairs: List[Dict[str, float | int | None]] = []
    for th in THRESHOLDS:
        dds = [r.max_drawdown_after_peak for r in records if r.max_gain >= th]
        dds_w = winsorize(dds)
        dd_mean = mean(dds_w) if dds_w else None
        dd_median = median(dds_w) if dds_w else None
        dd_p75 = _quantile(dds_w, 0.75)
        summary_map.append(
            {
                "rise_threshold": th,
                "samples": len(dds),
                "dd_mean": _safe(dd_mean),
                "dd_median": _safe(dd_median),
                "dd_p75": _safe(dd_p75),
            }
        )
        rise_dd_pairs.append(
            {
                "rise_pct": int(th * 100),
                "X_median_drawdown_pct": _safe(dd_median * 100) if dd_median is not None else None,
                "samples": len(dds),
            }
        )

    bucket_stats: List[Dict[str, float | int | str | None]] = []
    bounds = THRESHOLDS + [float("inf")]
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        dds = [r.max_drawdown_after_peak for r in records if lo <= r.max_gain < hi]
        dds_w = winsorize(dds)
        bucket_stats.append(
            {
                "rise_bucket": f"[{int(lo*100)}%, {'∞' if math.isinf(hi) else str(int(hi*100))+'%'} )",
                "samples": len(dds),
                "dd_mean": _safe(mean(dds_w)) if dds_w else None,
                "dd_median": _safe(median(dds_w)) if dds_w else None,
            }
        )

    return {"threshold_map": summary_map, "rise_dd_pairs": rise_dd_pairs, "bucket_stats": bucket_stats}


def _threshold_p75_map(threshold_map: Sequence[Dict[str, float | int | None]]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for row in threshold_map:
        threshold = row.get("rise_threshold")
        dd_p75 = row.get("dd_p75")
        if isinstance(threshold, (int, float)) and isinstance(dd_p75, (int, float)):
            out[int(round(float(threshold) * 100))] = float(dd_p75) * 100
    return out


def _architecture_stage(runup_pct: float) -> Tuple[str, int, float, float]:
    if 0 <= runup_pct < 30:
        return "底部地基结构（脱离成本区）", 4, 0, 30
    if 30 <= runup_pct < 50:
        return "中继洗盘结构（承重梁加固）", 5, 30, 50
    if 50 <= runup_pct < 80:
        return "主升启动结构（趋势正式立柱）", 6, 50, 80
    if 80 <= runup_pct < 120:
        return "主升核心主体结构（黄金房体）", 7, 80, 120
    if 120 <= runup_pct < 150:
        return "加速脆弱结构（顶楼松动）", 3, 120, 150
    if 150 <= runup_pct < 200:
        return "鱼尾衰退结构（危楼出货）", 2, 150, 200
    if runup_pct >= 200:
        return "泡沫异化结构（空中楼阁）", 1, 200, float("inf")
    return "未知结构", 0, float("-inf"), 0


def analyze_market_architecture(
    runup_pct: float,
    current_dd_pct: float,
    vol_ratio: float | None,
    days_in_stage: int = 0,
    vol_ratio_1d_60d: float | None = None,
    risk_drawdown_pct: float | None = None,
    close: float | None = None,
    theil_sen_support: float | None = None,
) -> Dict[str, object]:
    """基于空间层级结构的实盘决策状态机。"""
    stage_name, stability_score, _, _ = _architecture_stage(runup_pct)
    action = "观望"
    reasons: List[str] = []

    if 0 <= runup_pct < 30:
        if current_dd_pct >= -10:
            action = "试探性建仓（博弈突破有效）"
        else:
            action = "放弃（地基不稳，疑似假突破）"
    elif 30 <= runup_pct < 50:
        if -22 <= current_dd_pct <= -15 and vol_ratio is not None and vol_ratio <= 0.4:
            action = "伏击点（筹码分层健康，缩量洗盘）"
        elif current_dd_pct < -25 or (vol_ratio is not None and vol_ratio > 0.8):
            action = "警惕（洗盘变出货，结构夭折）"
        else:
            action = "观察承重梁是否放量突破"
    elif 50 <= runup_pct < 80:
        if -18 <= current_dd_pct <= -12 and vol_ratio is not None and vol_ratio <= 0.5:
            action = "右侧加仓点（主升浪前夜）"
        else:
            action = "持股观望"
    elif 80 <= runup_pct < 120:
        if -15 <= current_dd_pct <= -8 and vol_ratio is not None and vol_ratio <= 0.45:
            action = "黄金买点（健康缩量回踩）"
        else:
            action = "锁仓持有，等待加速"
    elif 120 <= runup_pct < 150:
        action = "只出不进（加速脆弱段，随时准备撤退）"
    elif 150 <= runup_pct < 200:
        action = "分批减仓（危楼段，严禁新增仓位）"
    elif runup_pct >= 200:
        action = "清仓/围观（泡沫异化，绝不追高）"

    if days_in_stage > 20 and 30 <= runup_pct < 80:
        stability_score = max(1, stability_score - 1)
        reasons.append("洗盘/立柱区停留超过20个交易日未突破，结构评级下调一级")

    breach_p75 = risk_drawdown_pct is not None and abs(current_dd_pct) >= risk_drawdown_pct
    volume_break = vol_ratio_1d_60d is not None and vol_ratio_1d_60d >= 1.5
    trend_break = close is not None and theil_sen_support is not None and close < theil_sen_support
    danger_zone = runup_pct >= 150
    golden_body = 80 <= runup_pct < 120
    reverse_panic = danger_zone and breach_p75 and volume_break and trend_break
    golden_breakdown = golden_body and breach_p75 and volume_break
    blacklist = reverse_panic or golden_breakdown

    if breach_p75:
        reasons.append("回撤跌破历史P75风险位")
    if volume_break:
        reasons.append("当日放量超过60日均量1.5倍")
    if trend_break:
        reasons.append("收盘跌破Theil-Sen趋势支撑")
    if reverse_panic:
        action = "绝对拉黑/可进入做空观察池（危楼断裂，切入反向杀恐慌段）"
        stability_score = 0
        reasons.append("危楼/泡沫段同时满足P75破位、放量、Theil-Sen破位")
    elif golden_breakdown:
        action = "无条件清仓（黄金房体结构性塌方）"
        stability_score = 0
        reasons.append("黄金房体跌破P75风险位且放量破位")

    return {
        "当前层级": stage_name,
        "稳定性得分": stability_score,
        "实盘决策指令": action,
        "回撤深度": round(current_dd_pct, 4),
        "量能萎缩度": round(vol_ratio * 100, 4) if vol_ratio is not None else None,
        "days_in_stage": days_in_stage,
        "blacklist": blacklist,
        "reverse_panic": reverse_panic,
        "reasons": reasons,
    }


def _avg(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _volume_ratio(volumes: Dict[date, float], dates: Sequence[date], numerator_days: int, denominator_dates: Sequence[date]) -> float | None:
    numerator = [volumes[d] for d in dates[-numerator_days:] if d in volumes]
    denominator = [volumes[d] for d in denominator_dates if d in volumes]
    num_avg = _avg(numerator)
    den_avg = _avg(denominator)
    if num_avg is None or den_avg in (None, 0):
        return None
    return num_avg / den_avg


def _theil_sen_support(part: Sequence[Tuple[date, float]], target_index: int) -> float | None:
    if len(part) < 3:
        return None
    slopes: List[float] = []
    for i in range(len(part)):
        for j in range(i + 1, len(part)):
            dx = j - i
            if dx:
                slopes.append((part[j][1] - part[i][1]) / dx)
    if not slopes:
        return None
    slope = median(slopes)
    intercepts = [price - slope * i for i, (_, price) in enumerate(part)]
    intercept = median(intercepts)
    return intercept + slope * target_index


def _days_in_current_stage(part: Sequence[Tuple[date, float]], base: float, stage_lo: float, as_of: date) -> int:
    if not part or not math.isfinite(stage_lo):
        return 0
    for i, (d, price) in enumerate(part):
        if d > as_of:
            break
        if (price / base - 1.0) * 100 >= stage_lo:
            return len([day for day, _ in part[i:] if day <= as_of])
    return 0


def _risk_drawdown_for_runup(runup_pct: float, p75_map: Dict[int, float]) -> float | None:
    candidates = [k for k in p75_map if k <= runup_pct]
    if not candidates:
        return None
    return p75_map[max(candidates)]


def build_architecture_signals(
    stocks: Dict[str, Dict[date, float]],
    volumes: Dict[str, Dict[date, float]],
    segments: Sequence[Segment],
    threshold_map: Sequence[Dict[str, float | int | None]],
) -> List[ArchitectureSignal]:
    if not segments:
        return []
    latest_segment = segments[-1]
    p75_map = _threshold_p75_map(threshold_map)
    signals: List[ArchitectureSignal] = []

    for symbol, series in stocks.items():
        part = _series_between(series, latest_segment.start, latest_segment.end)
        if len(part) < 5:
            continue
        dates = [d for d, _ in part]
        as_of, close = part[-1]
        base = part[0][1]
        peak_index, (peak_date, peak_price) = max(enumerate(part), key=lambda item: item[1][1])
        runup_pct = (peak_price / base - 1.0) * 100
        current_dd_pct = (close / peak_price - 1.0) * 100
        stage_name, stability_score, stage_lo, _ = _architecture_stage(runup_pct)
        days_in_stage = _days_in_current_stage(part, base, stage_lo, as_of)
        up_leg = part[: peak_index + 1]
        launch_dates = [d for d, _ in up_leg]
        volume_series = volumes.get(symbol, {})
        vol_ratio_3d_launch = _volume_ratio(volume_series, dates, 3, launch_dates)
        vol_ratio_1d_60d = _volume_ratio(volume_series, dates, 1, dates[-60:])
        risk_drawdown_pct = _risk_drawdown_for_runup(runup_pct, p75_map)
        support = _theil_sen_support(up_leg, len(part) - 1)
        decision = analyze_market_architecture(
            runup_pct=runup_pct,
            current_dd_pct=current_dd_pct,
            vol_ratio=vol_ratio_3d_launch,
            days_in_stage=days_in_stage,
            vol_ratio_1d_60d=vol_ratio_1d_60d,
            risk_drawdown_pct=risk_drawdown_pct,
            close=close,
            theil_sen_support=support,
        )

        signals.append(
            ArchitectureSignal(
                symbol=symbol,
                segment_start=latest_segment.start,
                as_of=as_of,
                runup_pct=runup_pct,
                current_dd_pct=current_dd_pct,
                vol_ratio_3d_launch=vol_ratio_3d_launch,
                vol_ratio_1d_60d=vol_ratio_1d_60d,
                stage_name=stage_name,
                stability_score=int(decision["稳定性得分"]),
                action=str(decision["实盘决策指令"]),
                days_in_stage=days_in_stage,
                risk_drawdown_pct=risk_drawdown_pct,
                theil_sen_support=support,
                close=close,
                blacklist=bool(decision["blacklist"]),
                reverse_panic=bool(decision["reverse_panic"]),
                reasons=[str(x) for x in decision["reasons"]],
            )
        )
    return signals


def _signal_to_dict(signal: ArchitectureSignal) -> Dict[str, object]:
    def _safe(v: float | None) -> float | None:
        return round(v, 4) if v is not None else None

    return {
        "symbol": signal.symbol,
        "segment_start": signal.segment_start.isoformat(),
        "as_of": signal.as_of.isoformat(),
        "runup_pct": _safe(signal.runup_pct),
        "current_dd_pct": _safe(signal.current_dd_pct),
        "vol_ratio_3d_launch": _safe(signal.vol_ratio_3d_launch),
        "vol_ratio_1d_60d": _safe(signal.vol_ratio_1d_60d),
        "stage_name": signal.stage_name,
        "stability_score": signal.stability_score,
        "action": signal.action,
        "days_in_stage": signal.days_in_stage,
        "risk_drawdown_pct": _safe(signal.risk_drawdown_pct),
        "theil_sen_support": _safe(signal.theil_sen_support),
        "close": _safe(signal.close),
        "blacklist": signal.blacklist,
        "reverse_panic": signal.reverse_panic,
        "reasons": signal.reasons,
    }


def run(index_csv: str, stock_dir: str, output_json: str, reversal_pct: float) -> Dict[str, object]:
    index_raw = read_price_csv(index_csv)
    index_series = clip_last_years(index_raw, years=10)
    segments = detect_up_segments(index_series, reversal_pct=reversal_pct)

    stocks = load_stock_universe(stock_dir)
    volumes = load_volume_universe(stock_dir)
    all_records: List[StockWaveStat] = []
    for symbol, raw_series in stocks.items():
        series = clip_last_years(raw_series, years=10)
        for seg in segments:
            rec = calc_stock_wave_stat(symbol, series, seg)
            if rec:
                all_records.append(rec)

    summary = summarize(all_records)
    architecture_signals = build_architecture_signals(
        stocks=stocks,
        volumes=volumes,
        segments=segments,
        threshold_map=summary["threshold_map"],
    )
    result = {
        "meta": {
            "index_csv": index_csv,
            "stock_count": len(stocks),
            "segment_count": len(segments),
            "record_count": len(all_records),
            "architecture_signal_count": len(architecture_signals),
            "blacklist_count": sum(1 for signal in architecture_signals if signal.blacklist),
            "reversal_pct": reversal_pct,
            "window": "last_10_years",
        },
        "segments": [
            {
                "start": s.start.isoformat(),
                "peak": s.peak.isoformat(),
                "end": s.end.isoformat(),
                "index_rise": round(s.rise, 4),
            }
            for s in segments
        ],
        **summary,
        "architecture_signals": [_signal_to_dict(signal) for signal in architecture_signals],
        "blacklist_symbols": [signal.symbol for signal in architecture_signals if signal.blacklist],
    }

    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="沪深300趋势波段-个股涨幅回撤统计")
    parser.add_argument("--index-csv", default="data/index/000300.csv", help="沪深300指数日线 CSV")
    parser.add_argument("--stock-dir", default="data/stocks", help="个股日线 CSV 文件夹")
    parser.add_argument("--output-json", default="output/wave_summary.json", help="输出 JSON")
    parser.add_argument("--reversal-pct", type=float, default=0.12, help="趋势反转阈值(默认12%%)")
    args = parser.parse_args()

    result = run(
        index_csv=args.index_csv,
        stock_dir=args.stock_dir,
        output_json=args.output_json,
        reversal_pct=args.reversal_pct,
    )
    print(json.dumps(result["meta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
