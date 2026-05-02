"""Live data provider and macro threshold monitor."""

from __future__ import annotations

import importlib
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class MacroDataProvider:
    """Thread-safe macro provider with background refresh."""

    def __init__(self, threshold_bps: float = 10.0, update_interval_sec: int = 300) -> None:
        self.threshold_bps = threshold_bps
        self.update_interval_sec = update_interval_sec
        self._lock = threading.Lock()
        self._market_data: dict[str, Any] = {
            "cn10y_yield_current": 2.50,
            "cn10y_yield_baseline": 2.50,
            "cn10y_yield_chg_bps": 0.0,
            "pmi_manufacturing": 50.0,
            "macro_phase": "neutral",
        }
        self._is_running = False
        self._monitor_thread: threading.Thread | None = None
        self._init_baseline()

    def _load_akshare(self):
        return importlib.import_module("akshare")

    def _fetch_bond_df(self):
        ak = self._load_akshare()
        return ak.bond_zh_us_rate()

    def _init_baseline(self) -> None:
        try:
            df = self._fetch_bond_df()
            if not df.empty:
                baseline_idx = -5 if len(df) >= 5 else -1
                baseline_row = df.iloc[baseline_idx]
                baseline = float(baseline_row["中国国债收益率10年"])
                with self._lock:
                    self._market_data["cn10y_yield_baseline"] = baseline
                logger.info("Initialized 10Y baseline: %s", baseline)
        except Exception as exc:
            logger.warning("Baseline initialization failed, fallback defaults in use: %s", exc)

    def _fetch_live_data(self) -> None:
        try:
            df = self._fetch_bond_df()
            if df.empty:
                return
            latest_yield = float(df.iloc[-1]["中国国债收益率10年"])
            with self._lock:
                baseline = float(self._market_data["cn10y_yield_baseline"])
            chg_bps = round((latest_yield - baseline) * 100.0, 2)

            with self._lock:
                self._market_data["cn10y_yield_current"] = latest_yield
                self._market_data["cn10y_yield_chg_bps"] = chg_bps
                if chg_bps <= -10:
                    self._market_data["macro_phase"] = "risk_on"
                elif chg_bps >= 10:
                    self._market_data["macro_phase"] = "risk_off"
                else:
                    self._market_data["macro_phase"] = "neutral"

            if abs(chg_bps) >= self.threshold_bps:
                logger.warning("Macro rate shock detected: %.2f bps (threshold=%.2f)", chg_bps, self.threshold_bps)
        except Exception as exc:
            logger.error("Error fetching live macro data: %s", exc)

    def _run_monitor_loop(self) -> None:
        while self._is_running:
            self._fetch_live_data()
            time.sleep(self.update_interval_sec)

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._monitor_thread = threading.Thread(target=self._run_monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Macro data monitor started")

    def stop(self) -> None:
        self._is_running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3)

    def get_market_data(self, time_tag: str = "current") -> Mapping[str, Any]:
        with self._lock:
            snapshot = dict(self._market_data)
        snapshot["time_tag"] = time_tag
        snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
        return snapshot

    def check_macro_event_flags(self) -> bool:
        with self._lock:
            chg_bps = float(self._market_data.get("cn10y_yield_chg_bps", 0.0))
        return abs(chg_bps) >= self.threshold_bps
