"""Eastmoney-backed macro data provider."""

from __future__ import annotations

import logging
from typing import Any, Iterable

import json
from urllib.request import urlopen

from data.macro_monitor import MacroDataProvider

logger = logging.getLogger(__name__)


class EastmoneyMacroProvider(MacroDataProvider):
    """Macro provider using Eastmoney treasury-yield endpoint."""

    def __init__(
        self,
        threshold_bps: float = 10.0,
        update_interval_sec: int = 900,
        endpoint: str | None = None,
        timeout_sec: float = 8.0,
    ) -> None:
        self.endpoint = (
            endpoint
            or "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_TREASURY_YIELD"
            "&columns=ALL&sortColumns=REPORT_DATE&sortTypes=-1&pageNumber=1&pageSize=200"
        )
        self.timeout_sec = timeout_sec
        super().__init__(threshold_bps=threshold_bps, update_interval_sec=update_interval_sec)

    def _request_records(self) -> list[dict[str, Any]]:
        with urlopen(self.endpoint, timeout=self.timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        data = result.get("data", []) if isinstance(result, dict) else []
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _pick_10y_value(record: dict[str, Any]) -> float | None:
        for key in ("EMM00166462", "CN10Y", "VALUE", "YIELD_10Y", "中国国债收益率10年"):
            if key in record and record[key] not in (None, ""):
                return float(record[key])
        return None

    def _iter_10y_values(self, records: Iterable[dict[str, Any]]) -> list[float]:
        values: list[float] = []
        for record in records:
            v = self._pick_10y_value(record)
            if v is not None:
                values.append(v)
        return values

    def _init_baseline(self) -> None:
        try:
            records = self._request_records()
            values = self._iter_10y_values(records)
            if not values:
                return
            baseline = values[min(4, len(values) - 1)]
            with self._lock:
                self._market_data["cn10y_yield_baseline"] = baseline
            logger.info("Initialized Eastmoney 10Y baseline: %s", baseline)
        except Exception as exc:
            logger.warning("Eastmoney baseline init failed, using fallback defaults: %s", exc)

    def _fetch_live_data(self) -> None:
        try:
            records = self._request_records()
            values = self._iter_10y_values(records)
            if not values:
                return
            latest_yield = values[0]
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
                logger.warning("Eastmoney macro shock: %.2f bps", chg_bps)
        except Exception as exc:
            logger.error("Eastmoney live fetch failed: %s", exc)
