import time

from app.system import Collector


def test_sampling_requires_baseline_and_bounds_real_values():
    collector = Collector()
    first = collector.collect()
    assert first["cpu_percent"] is None
    assert first["network"]["received_bps"] is None
    assert all(p["cpu_percent"] is None for p in first["processes"])
    time.sleep(0.12)
    second = collector.collect()
    assert 0 <= second["cpu_percent"] <= 100
    assert second["network"]["received_bps"] >= 0
    assert second["memory"]["total"] >= second["memory"]["used"] >= 0
    assert second["disks"]
    assert second["collected_at"] > first["collected_at"]
