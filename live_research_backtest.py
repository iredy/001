#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
live_research_backtest.py
可落地的月频投研回测框架（SQLite + Pandas）
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class Config:
    db_path: str = "quant_live.sqlite3"
    start_date: str = "2019-01-01"
    end_date: str = "2026-03-31"

    max_single_weight: float = 0.06
    max_industry_weight: float = 0.30
    min_cash_weight: float = 0.03
    turnover_limit: float = 0.20

    fee_bps: float = 2.0
    slippage_bps: float = 4.0
    impact_coef_bps: float = 10.0

    n_defensive: int = 30
    n_growth: int = 30
    n_tactical: int = 20

    # 映射模块（可选）：将策略风格映射为 sleeve 偏好，再与 regime 权重融合
    mapping_enabled: bool = True
    mapping_strength: float = 0.35  # 0~1，越大越偏向映射模块输出
    active_styles: Tuple[str, ...] = (
        "估值修复",
        "确定增长",
        "技术兼容",
        "波段增强",
        "业绩成长",
    )
    style_to_sleeve: Dict[str, str] = None

    regime_weights: Dict[str, Dict[str, float]] = None

    def __post_init__(self):
        if self.regime_weights is None:
            self.regime_weights = {
                "A_DELEVERAGING": {"defensive": 0.65, "growth": 0.25, "tactical": 0.07, "cash": 0.03},
                "B_WEAK_RECOVERY": {"defensive": 0.50, "growth": 0.40, "tactical": 0.07, "cash": 0.03},
                "C_CREDIT_EXPANSION": {"defensive": 0.35, "growth": 0.55, "tactical": 0.07, "cash": 0.03},
            }
        if self.style_to_sleeve is None:
            self.style_to_sleeve = {
                "估值修复": "defensive",
                "确定增长": "growth",
                "技术兼容": "tactical",
                "波段增强": "tactical",
                "业绩成长": "tactical",
            }


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_bar (
    trade_date TEXT,
    ticker TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    amount REAL,
    adj_factor REAL,
    is_tradable INTEGER,
    PRIMARY KEY (trade_date, ticker)
);

CREATE TABLE IF NOT EXISTS fundamental (
    ann_date TEXT,
    period_end TEXT,
    ticker TEXT,
    revenue_ttm REAL,
    netprofit_ttm REAL,
    fcf_ttm REAL,
    total_equity REAL,
    total_liab REAL,
    div_cash_ttm REAL,
    rd_expense_ttm REAL,
    PRIMARY KEY (ann_date, ticker, period_end)
);

CREATE TABLE IF NOT EXISTS macro_monthly (
    month TEXT PRIMARY KEY,
    hh_credit_yoy REAL,
    savings_rate REAL,
    retail_sales_yoy REAL,
    credit_impulse REAL,
    m2_yoy REAL,
    cpi_yoy REAL,
    ppi_yoy REAL,
    pmi REAL,
    gdp_yoy REAL,
    usdcny_yoy REAL,
    lpr_1y REAL
);

CREATE TABLE IF NOT EXISTS security_master (
    ticker TEXT PRIMARY KEY,
    industry_l1 TEXT,
    industry_l2 TEXT,
    list_date TEXT,
    delist_date TEXT
);

CREATE TABLE IF NOT EXISTS feature_snapshot (
    trade_date TEXT,
    ticker TEXT,
    industry_l1 TEXT,
    is_tradable INTEGER,
    div_yield REAL,
    fcf_yield REAL,
    low_vol REAL,
    quality REAL,
    valuation REAL,
    revenue_growth REAL,
    earnings_revision REAL,
    rd_intensity REAL,
    momentum_6m REAL,
    momentum_3m REAL,
    volume_trend REAL,
    PRIMARY KEY (trade_date, ticker)
);

CREATE TABLE IF NOT EXISTS bt_result (
    signal_day TEXT,
    exec_day TEXT,
    hold_to TEXT,
    regime TEXT,
    gross_ret REAL,
    cost REAL,
    net_ret REAL,
    nav REAL,
    turnover REAL
);
"""


def get_conn(cfg: Config) -> sqlite3.Connection:
    return sqlite3.connect(cfg.db_path)


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)
    ensure_macro_columns(con)
    con.commit()


def ensure_macro_columns(con: sqlite3.Connection) -> None:
    """兼容旧版 SQLite 文件，补齐新增宏观指标列。"""
    existing = {row[1] for row in con.execute("PRAGMA table_info(macro_monthly)").fetchall()}
    columns = {
        "pmi": "REAL",
        "gdp_yoy": "REAL",
        "usdcny_yoy": "REAL",
        "lpr_1y": "REAL",
    }
    for name, col_type in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE macro_monthly ADD COLUMN {name} {col_type}")


def gen_trade_calendar(start: str = "2018-01-01", end: str = "2026-03-31") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, end=end, freq="B")


def _write_df(con: sqlite3.Connection, df: pd.DataFrame, table: str) -> None:
    df.to_sql(table, con, if_exists="append", index=False)


def seed_mock_data(con: sqlite3.Connection, seed: int = 42) -> None:
    cnt = pd.read_sql_query("SELECT COUNT(*) AS n FROM daily_bar", con)["n"].iloc[0]
    if cnt > 0:
        print("[INFO] daily_bar already exists, skip mock seed.")
        return

    np.random.seed(seed)
    print("[INFO] seeding mock data ...")

    tickers = [f"S{i:04d}" for i in range(1, 251)]
    industries = np.random.choice(
        ["Tech", "Utility", "Bank", "Industrial", "Consumer", "Healthcare"],
        size=len(tickers),
        p=[0.23, 0.12, 0.14, 0.21, 0.20, 0.10],
    )

    sm = pd.DataFrame(
        {
            "ticker": tickers,
            "industry_l1": industries,
            "industry_l2": industries,
            "list_date": "2010-01-01",
            "delist_date": None,
        }
    )
    _write_df(con, sm, "security_master")

    dates = gen_trade_calendar()
    bars = []
    for ticker, ind in zip(tickers, industries):
        n = len(dates)
        drift = np.random.uniform(0.0000, 0.0006)
        vol = np.random.uniform(0.008, 0.03)
        ret = np.random.normal(drift, vol, n)

        if ind == "Tech":
            ret += np.random.normal(0.0001, 0.002, n)
        if ind == "Utility":
            ret += np.random.normal(-0.00005, 0.0015, n)

        close = 20 * np.cumprod(1 + ret)
        open_ = close * (1 + np.random.normal(0, 0.002, n))
        high = np.maximum(open_, close) * (1 + np.abs(np.random.normal(0.003, 0.002, n)))
        low = np.minimum(open_, close) * (1 - np.abs(np.random.normal(0.003, 0.002, n)))
        volume = np.random.lognormal(mean=12, sigma=0.5, size=n)
        amount = volume * close

        bars.append(
            pd.DataFrame(
                {
                    "trade_date": dates.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                    "adj_factor": 1.0,
                    "is_tradable": (np.random.rand(n) > 0.03).astype(int),
                }
            )
        )

    _write_df(con, pd.concat(bars, ignore_index=True), "daily_bar")

    months = pd.date_range("2018-01-31", "2026-03-31", freq="ME")
    t = np.arange(len(months))
    macro = pd.DataFrame(
        {
            "month": months.strftime("%Y-%m-%d"),
            "hh_credit_yoy": 1.5 + 2.0 * np.sin(t / 9) + np.random.normal(0, 0.8, len(months)),
            "savings_rate": 0.30 + 0.03 * np.cos(t / 11) + np.random.normal(0, 0.006, len(months)),
            "retail_sales_yoy": 3.0 + 2.5 * np.sin(t / 10 + 0.7) + np.random.normal(0, 0.7, len(months)),
            "credit_impulse": 0.2 * np.sin(t / 7) + np.random.normal(0, 0.2, len(months)),
            "m2_yoy": 8 + 1.0 * np.sin(t / 12) + np.random.normal(0, 0.4, len(months)),
            "cpi_yoy": 1.5 + 1.0 * np.sin(t / 8) + np.random.normal(0, 0.3, len(months)),
            "ppi_yoy": 0.5 + 2.0 * np.sin(t / 6) + np.random.normal(0, 0.5, len(months)),
            "pmi": 50 + 1.6 * np.sin(t / 8 + 0.3) + np.random.normal(0, 0.4, len(months)),
            "gdp_yoy": 5.0 + 0.8 * np.sin(t / 14 + 0.5) + np.random.normal(0, 0.2, len(months)),
            "usdcny_yoy": 1.0 * np.sin(t / 10) + np.random.normal(0, 1.2, len(months)),
            "lpr_1y": 3.45 - 0.15 * np.sin(t / 18) + np.random.normal(0, 0.03, len(months)),
        }
    )
    _write_df(con, macro, "macro_monthly")

    anns = []
    for y in range(2018, 2027):
        for q_end, ann_day in [("03-31", "04-30"), ("06-30", "08-30"), ("09-30", "10-30"), ("12-31", "04-30")]:
            ann_date = f"{y}-{ann_day}"
            period_end = f"{y}-{q_end}"
            for tkr in tickers:
                base = np.random.lognormal(7.5, 0.5)
                rev = base * np.random.uniform(2.0, 6.0)
                npf = rev * np.random.uniform(0.05, 0.18)
                fcf = npf * np.random.uniform(0.6, 1.4)
                eq = base * np.random.uniform(5, 12)
                liab = eq * np.random.uniform(0.3, 1.5)
                div = max(0.0, npf * np.random.uniform(0.05, 0.5))
                rd = rev * np.random.uniform(0.01, 0.18)
                anns.append([ann_date, period_end, tkr, rev, npf, fcf, eq, liab, div, rd])

    fundamentals = pd.DataFrame(
        anns,
        columns=[
            "ann_date",
            "period_end",
            "ticker",
            "revenue_ttm",
            "netprofit_ttm",
            "fcf_ttm",
            "total_equity",
            "total_liab",
            "div_cash_ttm",
            "rd_expense_ttm",
        ],
    )
    _write_df(con, fundamentals, "fundamental")
    con.commit()
    print("[INFO] mock data done.")


def _month_end_signals(daily: pd.DataFrame, cfg: Config) -> pd.Series:
    dd = daily.copy()
    dd["trade_date"] = pd.to_datetime(dd["trade_date"])
    dd = dd[(dd["trade_date"] >= cfg.start_date) & (dd["trade_date"] <= cfg.end_date)]
    return dd.groupby(dd["trade_date"].dt.to_period("M"))["trade_date"].max().sort_values()


def build_feature_snapshot(con: sqlite3.Connection, cfg: Config) -> None:
    con.execute("DELETE FROM feature_snapshot WHERE trade_date BETWEEN ? AND ?", (cfg.start_date, cfg.end_date))

    daily = pd.read_sql_query("SELECT * FROM daily_bar", con)
    security = pd.read_sql_query("SELECT ticker, industry_l1 FROM security_master", con)
    funda = pd.read_sql_query("SELECT * FROM fundamental", con)

    daily["trade_date"] = pd.to_datetime(daily["trade_date"])
    funda["ann_date"] = pd.to_datetime(funda["ann_date"])

    daily = daily.sort_values(["ticker", "trade_date"]) 
    daily["adj_close"] = daily["close"] * daily["adj_factor"]

    month_ends = _month_end_signals(daily, cfg)
    rows = []

    for signal_day in month_ends:
        px = daily[daily["trade_date"] == signal_day][["ticker", "close", "amount", "is_tradable"]].copy()
        if px.empty:
            continue

        hist = daily[daily["trade_date"] <= signal_day].copy()
        hist["ret"] = hist.groupby("ticker")["adj_close"].pct_change()

        by_ticker = hist.groupby("ticker", sort=False)
        mom3 = by_ticker["adj_close"].apply(lambda s: s.iloc[-1] / s.iloc[-64] - 1 if len(s) > 63 else np.nan)
        mom6 = by_ticker["adj_close"].apply(lambda s: s.iloc[-1] / s.iloc[-127] - 1 if len(s) > 126 else np.nan)
        vol = by_ticker["ret"].apply(lambda s: s.tail(60).std(ddof=0))
        avg_amount = by_ticker["amount"].apply(lambda s: s.tail(60).mean())

        mkt = pd.DataFrame(
            {
                "ticker": mom3.index,
                "momentum_3m": mom3.values,
                "momentum_6m": mom6.values,
                "hist_vol": vol.values,
                "avg_amount_60": avg_amount.values,
            }
        )

        visible = funda[funda["ann_date"] <= signal_day].sort_values(["ticker", "ann_date"]).groupby("ticker", as_index=False).tail(1)
        feat = px.merge(security, on="ticker", how="left").merge(mkt, on="ticker", how="left").merge(visible, on="ticker", how="left")

        feat["div_yield"] = feat["div_cash_ttm"] / feat["close"].replace(0, np.nan)
        feat["fcf_yield"] = feat["fcf_ttm"] / feat["close"].replace(0, np.nan)
        feat["low_vol"] = -feat["hist_vol"]
        feat["quality"] = feat["netprofit_ttm"] / feat["total_equity"].replace(0, np.nan)
        feat["valuation"] = feat["close"] / feat["total_equity"].replace(0, np.nan)
        feat["revenue_growth"] = feat["revenue_ttm"] / feat["total_equity"].replace(0, np.nan)
        feat["earnings_revision"] = feat["netprofit_ttm"] / feat["total_equity"].replace(0, np.nan)
        feat["rd_intensity"] = feat["rd_expense_ttm"] / feat["revenue_ttm"].replace(0, np.nan)
        feat["volume_trend"] = feat["avg_amount_60"] / feat["amount"].replace(0, np.nan)

        out = feat[
            [
                "ticker",
                "industry_l1",
                "is_tradable",
                "div_yield",
                "fcf_yield",
                "low_vol",
                "quality",
                "valuation",
                "revenue_growth",
                "earnings_revision",
                "rd_intensity",
                "momentum_6m",
                "momentum_3m",
                "volume_trend",
            ]
        ].copy()
        out.insert(0, "trade_date", signal_day.strftime("%Y-%m-%d"))

        for col in out.columns:
            if col not in ["trade_date", "ticker", "industry_l1"]:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        out = out.replace([np.inf, -np.inf], np.nan)
        rows.append(out)

    if rows:
        all_feat = pd.concat(rows, ignore_index=True)
        _write_df(con, all_feat, "feature_snapshot")
    con.commit()
    print("[INFO] feature_snapshot refreshed.")


def zscore(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    std = s.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def classify_regime(m: pd.Series) -> str:
    pmi = float(m.get("pmi", 50.0)) if pd.notna(m.get("pmi", 50.0)) else 50.0
    gdp_yoy = float(m.get("gdp_yoy", 5.0)) if pd.notna(m.get("gdp_yoy", 5.0)) else 5.0
    usdcny_yoy = float(m.get("usdcny_yoy", 0.0)) if pd.notna(m.get("usdcny_yoy", 0.0)) else 0.0
    lpr_1y = float(m.get("lpr_1y", 3.45)) if pd.notna(m.get("lpr_1y", 3.45)) else 3.45
    credit_impulse = float(m["credit_impulse"])
    hh_credit_yoy = float(m["hh_credit_yoy"])
    retail_sales_yoy = float(m["retail_sales_yoy"])
    ppi_yoy = float(m["ppi_yoy"])
    savings_rate = float(m["savings_rate"])

    weak_demand = ppi_yoy < 0 and savings_rate > 0.30 and pmi < 50.5
    policy_support = credit_impulse > 0 and lpr_1y <= 3.55
    fx_stress = usdcny_yoy > 4.0

    if (hh_credit_yoy < 0.0) and (savings_rate > 0.30) and (credit_impulse <= 0):
        return "A_DELEVERAGING"
    if policy_support and weak_demand:
        return "B_WEAK_RECOVERY"
    if (hh_credit_yoy > 3.0) and (retail_sales_yoy > 4.0) and (credit_impulse > 0) and (pmi >= 50.0) and (gdp_yoy >= 4.8) and not fx_stress:
        return "C_CREDIT_EXPANSION"
    return "B_WEAK_RECOVERY"


def factor_score(univ: pd.DataFrame, sleeve: str) -> pd.Series:
    if sleeve == "defensive":
        score = 0.30 * zscore(univ["div_yield"]) + 0.25 * zscore(univ["fcf_yield"]) + 0.20 * zscore(univ["low_vol"]) + 0.15 * zscore(univ["quality"]) - 0.10 * zscore(univ["valuation"])
    elif sleeve == "growth":
        score = 0.30 * zscore(univ["revenue_growth"]) + 0.25 * zscore(univ["earnings_revision"]) + 0.20 * zscore(univ["rd_intensity"]) + 0.15 * zscore(univ["momentum_6m"]) - 0.10 * zscore(univ["valuation"])
    elif sleeve == "tactical":
        score = 0.6 * zscore(univ["momentum_3m"]) + 0.4 * zscore(univ["volume_trend"])
    else:
        raise ValueError(f"Unknown sleeve: {sleeve}")
    return score.replace([np.inf, -np.inf], np.nan).fillna(score.median())


def resolve_regime_weights(cfg: Config, regime: str) -> Dict[str, float]:
    """融合基础 regime 权重与映射模块权重。"""
    base = cfg.regime_weights[regime].copy()
    if not cfg.mapping_enabled or not cfg.active_styles:
        return base

    sleeve_pref = {"defensive": 0.0, "growth": 0.0, "tactical": 0.0}
    per_style = 1.0 / len(cfg.active_styles)
    for style in cfg.active_styles:
        sleeve = cfg.style_to_sleeve.get(style)
        if sleeve in sleeve_pref:
            sleeve_pref[sleeve] += per_style

    # 基于基础现金权重，映射模块只重分配权益部分
    cash = base["cash"]
    equity_base = 1.0 - cash
    mapped = {k: sleeve_pref[k] * equity_base for k in sleeve_pref}

    s = min(max(cfg.mapping_strength, 0.0), 1.0)
    fused = {
        "defensive": (1 - s) * base["defensive"] + s * mapped["defensive"],
        "growth": (1 - s) * base["growth"] + s * mapped["growth"],
        "tactical": (1 - s) * base["tactical"] + s * mapped["tactical"],
        "cash": cash,
    }

    # 归一到 (1-cash)
    eq_sum = fused["defensive"] + fused["growth"] + fused["tactical"]
    if eq_sum > 0:
        scale = (1 - cash) / eq_sum
        fused["defensive"] *= scale
        fused["growth"] *= scale
        fused["tactical"] *= scale
    return fused


def softmax_weights(scores: pd.Series, temp: float = 0.8) -> pd.Series:
    x = scores.values / max(temp, 1e-6)
    ex = np.exp(x - np.max(x))
    return pd.Series(ex / ex.sum(), index=scores.index)


def cap_single(w: pd.Series, cap: float) -> pd.Series:
    w = w.copy()
    for _ in range(10):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        room = (cap - w).clip(lower=0)
        if room.sum() <= 1e-12:
            break
        w += excess * room / room.sum()
    return w / w.sum()


def cap_industry(w: pd.Series, ind: pd.Series, cap: float) -> pd.Series:
    w = w.copy()
    for _ in range(10):
        agg = w.groupby(ind.reindex(w.index)).sum()
        over = agg[agg > cap]
        if over.empty:
            break
        for industry in over.index:
            idx = ind[ind == industry].index.intersection(w.index)
            total = w.loc[idx].sum()
            if total > 0:
                w.loc[idx] *= cap / total
        w /= w.sum()
    return w


def build_sleeve(univ: pd.DataFrame, sleeve: str, target_weight: float, cfg: Config) -> pd.Series:
    if target_weight <= 0 or univ.empty:
        return pd.Series(dtype=float)

    n_map = {"defensive": cfg.n_defensive, "growth": cfg.n_growth, "tactical": cfg.n_tactical}
    score = factor_score(univ, sleeve).sort_values(ascending=False)
    selected = score.head(min(n_map[sleeve], len(score))).index
    w = softmax_weights(score.loc[selected])
    w = cap_single(w, cfg.max_single_weight)
    w = cap_industry(w, univ["industry_l1"], cfg.max_industry_weight)
    return w * target_weight


def combine_weights(univ: pd.DataFrame, regime: str, cfg: Config) -> pd.Series:
    rw = resolve_regime_weights(cfg, regime)
    total = pd.concat(
        [
            build_sleeve(univ, "defensive", rw["defensive"], cfg),
            build_sleeve(univ, "growth", rw["growth"], cfg),
            build_sleeve(univ, "tactical", rw["tactical"], cfg),
        ],
        axis=1,
    ).fillna(0.0).sum(axis=1)

    cash = max(cfg.min_cash_weight, rw["cash"])
    if total.sum() > 0:
        total = total / total.sum() * (1 - cash)
    total["CASH"] = cash
    return total.sort_values(ascending=False)


def apply_turnover_limit(target: pd.Series, prev: pd.Series, limit: float) -> Tuple[pd.Series, float]:
    idx = target.index.union(prev.index)
    t = target.reindex(idx).fillna(0.0)
    p = prev.reindex(idx).fillna(0.0)
    turnover = np.abs(t - p).sum() / 2
    if turnover <= limit:
        return t[t > 0], float(turnover)

    alpha = limit / max(turnover, 1e-12)
    n = p + alpha * (t - p)
    n[n < 1e-8] = 0
    n = n / n.sum()
    return n[n > 0], float(np.abs(n - p).sum() / 2)


def est_cost(trade_w: pd.Series, adv: pd.Series, cfg: Config) -> float:
    tw = trade_w.reindex(adv.index).fillna(0.0)
    adv = adv.replace(0, np.nan).fillna(adv.median()).clip(lower=1e-6)
    fee = tw.sum() * (cfg.fee_bps + cfg.slippage_bps) / 10000.0
    participation = (tw / adv).clip(0, 1)
    impact = (tw * (cfg.impact_coef_bps / 10000.0) * np.sqrt(participation)).sum()
    return float(fee + impact)


def load_month_ends(con: sqlite3.Connection, cfg: Config) -> pd.DataFrame:
    q = """
    SELECT substr(trade_date,1,7) AS month, MAX(trade_date) AS signal_day
    FROM daily_bar
    WHERE trade_date BETWEEN ? AND ?
    GROUP BY substr(trade_date,1,7)
    ORDER BY month
    """
    return pd.read_sql_query(q, con, params=(cfg.start_date, cfg.end_date))


def next_trade_day(con: sqlite3.Connection, date_str: str) -> Optional[str]:
    q = "SELECT MIN(trade_date) AS d FROM daily_bar WHERE trade_date > ?"
    d = pd.read_sql_query(q, con, params=(date_str,))["d"].iloc[0]
    return None if pd.isna(d) else str(d)


def load_macro_visible(con: sqlite3.Connection, signal_day: str) -> Optional[pd.Series]:
    month_end = (pd.Timestamp(signal_day).to_period("M").to_timestamp("M")).strftime("%Y-%m-%d")
    q = "SELECT * FROM macro_monthly WHERE month <= ? ORDER BY month DESC LIMIT 1"
    df = pd.read_sql_query(q, con, params=(month_end,))
    if df.empty:
        return None
    return df.iloc[0]


def load_universe(con: sqlite3.Connection, signal_day: str) -> pd.DataFrame:
    q = "SELECT * FROM feature_snapshot WHERE trade_date = ? AND is_tradable = 1"
    df = pd.read_sql_query(q, con, params=(signal_day,))
    if df.empty:
        return df
    df = df.set_index("ticker")
    cols = [
        "div_yield", "fcf_yield", "low_vol", "quality", "valuation", "revenue_growth",
        "earnings_revision", "rd_intensity", "momentum_6m", "momentum_3m", "volume_trend",
    ]
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        df[c] = df[c].fillna(df[c].median())
    return df


def load_return_and_adv(con: sqlite3.Connection, exec_day: str, hold_to: str) -> pd.DataFrame:
    q = """
    SELECT a.ticker,
           ((b.close*b.adj_factor)/(a.open*a.adj_factor)-1.0) AS ret,
           a.amount AS adv
    FROM daily_bar a
    JOIN daily_bar b ON a.ticker = b.ticker
    WHERE a.trade_date = ? AND b.trade_date = ? AND a.is_tradable = 1
    """
    df = pd.read_sql_query(q, con, params=(exec_day, hold_to))
    if df.empty:
        return df
    return df.set_index("ticker")


def run_backtest(con: sqlite3.Connection, cfg: Config) -> pd.DataFrame:
    con.execute("DELETE FROM bt_result")

    month_ends = load_month_ends(con, cfg)
    prev_w = pd.Series({"CASH": 1.0})
    nav = 1.0
    rows = []

    for i in range(len(month_ends) - 1):
        signal_day = month_ends.iloc[i]["signal_day"]
        hold_to = month_ends.iloc[i + 1]["signal_day"]
        exec_day = next_trade_day(con, signal_day)
        if exec_day is None:
            continue

        macro = load_macro_visible(con, signal_day)
        if macro is None:
            continue
        regime = classify_regime(macro)

        univ = load_universe(con, signal_day)
        if len(univ) < 50:
            continue

        target = combine_weights(univ, regime, cfg)
        target, turnover = apply_turnover_limit(target, prev_w, cfg.turnover_limit)

        ret_adv = load_return_and_adv(con, exec_day, hold_to)
        if ret_adv.empty:
            continue

        w_eq = target.drop(labels=["CASH"], errors="ignore").reindex(ret_adv.index).fillna(0.0)
        gross_ret = float((w_eq * ret_adv["ret"]).sum())

        old_eq = prev_w.drop(labels=["CASH"], errors="ignore").reindex(w_eq.index).fillna(0.0)
        trade_w = (w_eq - old_eq).abs()
        cost = est_cost(trade_w, ret_adv["adv"], cfg)

        net_ret = gross_ret - cost
        nav *= 1 + net_ret

        rows.append(
            {
                "signal_day": signal_day,
                "exec_day": exec_day,
                "hold_to": hold_to,
                "regime": regime,
                "gross_ret": gross_ret,
                "cost": cost,
                "net_ret": net_ret,
                "nav": nav,
                "turnover": turnover,
            }
        )
        prev_w = target.copy()

    res = pd.DataFrame(rows)
    if res.empty:
        return res

    res["cummax"] = res["nav"].cummax()
    res["drawdown"] = res["nav"] / res["cummax"] - 1
    res[["signal_day", "exec_day", "hold_to", "regime", "gross_ret", "cost", "net_ret", "nav", "turnover"]].to_sql(
        "bt_result", con, if_exists="append", index=False
    )
    con.commit()
    return res


def perf_report(res: pd.DataFrame) -> Dict:
    if res.empty:
        return {}

    months = len(res)
    ann_vol = float(res["net_ret"].std(ddof=0) * np.sqrt(12))
    report = {
        "months": months,
        "nav_end": float(res["nav"].iloc[-1]),
        "annual_return": float(res["nav"].iloc[-1] ** (12 / months) - 1),
        "annual_vol": ann_vol,
        "sharpe": float((res["net_ret"].mean() * 12) / (ann_vol + 1e-12)),
        "max_drawdown": float(res["drawdown"].min()),
        "win_rate": float((res["net_ret"] > 0).mean()),
        "avg_turnover": float(res["turnover"].mean()),
        "total_cost_drag": float(res["cost"].sum()),
        "regime_contribution": res.groupby("regime")["net_ret"].agg(["count", "mean", "sum"]).reset_index().to_dict(orient="records"),
    }

    tmp = res.copy()
    tmp["year"] = pd.to_datetime(tmp["hold_to"]).dt.year
    report["yearly_return"] = tmp.groupby("year")["net_ret"].apply(lambda x: float(np.prod(1 + x) - 1)).to_dict()
    return report


def save_outputs(res: pd.DataFrame, report: Dict, out_dir: str = "outputs") -> None:
    os.makedirs(out_dir, exist_ok=True)
    res.to_csv(os.path.join(out_dir, "bt_result.csv"), index=False)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main() -> None:
    cfg = Config()
    con = get_conn(cfg)
    init_db(con)
    seed_mock_data(con)
    build_feature_snapshot(con, cfg)
    res = run_backtest(con, cfg)

    if res.empty:
        print("[WARN] backtest result is empty.")
        return

    report = perf_report(res)
    save_outputs(res, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
