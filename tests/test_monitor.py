from market_monitor.monitor import MarketRotationMonitor
from market_monitor.models import SecuritySnapshot


def sample_snapshots():
    return [
        SecuritySnapshot("688008", "澜起科技", "科创半导体", "科创板", 88.3, -0.0781, -3.8, 0.86, 0.82, -0.012, 0.004, -0.09, 4.2, 1.8),
        SecuritySnapshot("688521", "芯原股份", "科创半导体", "科创板", 53.4, -0.0736, -3.35, 0.79, 0.76, -0.018, -0.002, -0.13, 5.1, 1.7),
        SecuritySnapshot("688772", "珠海冠宇", "超跌修复", "科创板", 16.19, 0.0125, 0.85, 0.21, 0.25, 0.006, -0.003, -0.31, 2.0, 1.2),
        SecuritySnapshot("000568", "泸州老窖", "消费", "主板", 132.4, 0.009, 0.91, 0.29, 0.34, 0.004, 0.001, -0.24, 1.1, 1.2),
    ]


def test_builds_high_and_low_pools():
    pools = MarketRotationMonitor().build_pools(sample_snapshots())

    high_names = [member.snapshot.name for member in pools["high"]]
    low_names = [member.snapshot.name for member in pools["low"]]

    assert "澜起科技" in high_names
    assert "芯原股份" in high_names
    assert "珠海冠宇" in low_names
    assert "泸州老窖" in low_names


def test_detects_high_to_low_rotation_window():
    signals = MarketRotationMonitor().detect_rotation(sample_snapshots())

    assert any(signal.direction == "high_to_low" for signal in signals)
    assert any(signal.direction == "sector_rotation" for signal in signals)
