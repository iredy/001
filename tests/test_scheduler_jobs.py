from scheduler.jobs import EventFlags, run_event_trigger


def test_event_flags_trigger_when_macro_shock():
    flags = EventFlags(macro_rate_shock=True)
    assert flags.should_trigger() is True


def test_event_trigger_false_when_no_flags():
    fired = run_event_trigger({"market": "kcb200"}, EventFlags())
    assert fired is False
