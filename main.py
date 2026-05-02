"""Service bootstrap: start live macro provider + scheduler + event loop."""

from __future__ import annotations

import logging
import os
import time

from data.eastmoney_provider import EastmoneyMacroProvider
from data.macro_monitor import MacroDataProvider
from scheduler.jobs import EventFlags, run_event_trigger, start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_provider() -> MacroDataProvider:
    source = os.getenv("MACRO_DATA_SOURCE", "eastmoney").lower()
    if source == "akshare":
        return MacroDataProvider(threshold_bps=10.0, update_interval_sec=300)
    return EastmoneyMacroProvider(threshold_bps=10.0, update_interval_sec=900)


def main() -> None:
    provider = _build_provider()
    provider.start()

    def market_data_provider(time_tag: str):
        return provider.get_market_data(time_tag)

    start_scheduler(market_data_provider)

    try:
        while True:
            if provider.check_macro_event_flags():
                flags = EventFlags(macro_rate_shock=True)
                snapshot = provider.get_market_data("event_driven")
                fired = run_event_trigger(snapshot, flags)
                if fired:
                    logger.info("Macro shock event trigger fired")
                    time.sleep(3600)
            time.sleep(60)
    except KeyboardInterrupt:
        provider.stop()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
