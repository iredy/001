"""Scheduled and event-driven jobs for strategy auto-run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from strategy.runner import log_runner_event, run_strategy

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:  # pragma: no cover - optional dependency
    BackgroundScheduler = None


@dataclass(slots=True)
class EventFlags:
    index_breaks_key_level: bool = False
    spring_detected: bool = False
    volume_spike: bool = False
    sector_rotation_shift: bool = False
    manual_review: bool = False
    macro_rate_shock: bool = False

    def should_trigger(self) -> bool:
        return any(
            [
                self.index_breaks_key_level,
                self.spring_detected,
                self.volume_spike,
                self.sector_rotation_shift,
                self.manual_review,
                self.macro_rate_shock,
            ]
        )


def run_morning_scan(market_data: Mapping[str, Any]) -> None:
    result = run_strategy("premarket_scan", market_data)
    log_runner_event(f"08:20 premarket_scan done run_id={result.run_id}")


def run_auction_check(market_data: Mapping[str, Any]) -> None:
    result = run_strategy("auction_check", market_data)
    log_runner_event(f"09:20 auction_check done run_id={result.run_id}")


def run_open_check(market_data: Mapping[str, Any]) -> None:
    result = run_strategy("open_signal_check", market_data)
    log_runner_event(f"09:35 open_signal_check done run_id={result.run_id}")


def run_review(market_data: Mapping[str, Any]) -> None:
    result = run_strategy("postmarket_review", market_data)
    log_runner_event(f"15:30 postmarket_review done run_id={result.run_id}")


def run_event_trigger(market_data: Mapping[str, Any], flags: EventFlags) -> bool:
    if not flags.should_trigger():
        return False
    result = run_strategy("event_trigger", market_data)
    log_runner_event(f"event_trigger done run_id={result.run_id} flags={flags}")
    return True


def build_scheduler(market_data_provider):
    """Build daily cron scheduler for Asia/Shanghai trading cadence."""
    if BackgroundScheduler is None:
        raise RuntimeError("APScheduler is not installed. Please install apscheduler.")

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        lambda: run_morning_scan(market_data_provider("08:20")),
        "cron",
        hour=8,
        minute=20,
        id="premarket_scan",
    )
    scheduler.add_job(
        lambda: run_auction_check(market_data_provider("09:20")),
        "cron",
        hour=9,
        minute=20,
        id="auction_check",
    )
    scheduler.add_job(
        lambda: run_open_check(market_data_provider("09:35")),
        "cron",
        hour=9,
        minute=35,
        id="open_signal_check",
    )
    scheduler.add_job(
        lambda: run_review(market_data_provider("15:30")),
        "cron",
        hour=15,
        minute=30,
        id="postmarket_review",
    )
    return scheduler


def start_scheduler(market_data_provider) -> None:
    scheduler = build_scheduler(market_data_provider)
    scheduler.start()
    log_runner_event(f"scheduler started at {datetime.utcnow().isoformat()}Z")
