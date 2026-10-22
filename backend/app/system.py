"""Read-only collection. Sampling is shared, never triggered by API reads."""

import os
import platform
import time
from datetime import UTC, datetime
from typing import Any

import psutil


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class Collector:
    def __init__(self) -> None:
        self.previous_net: Any = None
        self.previous_time: float | None = None
        self.primed = False
        self.seen: set[tuple[int, float]] = set()

    def collect(self) -> dict[str, Any]:
        now = time.monotonic()
        cpu = psutil.cpu_percent(percpu=True)
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        net = psutil.net_io_counters()
        elapsed = now - self.previous_time if self.previous_time is not None else None
        network = {"received_bps": None, "sent_bps": None}
        if elapsed and self.previous_net:
            for field, counter in [("received_bps", "bytes_recv"), ("sent_bps", "bytes_sent")]:
                delta = getattr(net, counter) - getattr(self.previous_net, counter)
                network[field] = delta / elapsed if delta >= 0 else None
        self.previous_net, self.previous_time = net, now
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append(
                    {
                        "mount": partition.mountpoint,
                        "device": partition.device,
                        "total": usage.total,
                        "used": usage.used,
                        "percent": usage.percent,
                        "error": None,
                    }
                )
            except (OSError, psutil.Error):
                disks.append({"mount": partition.mountpoint, "error": "Accès indisponible"})
        if not disks:
            usage = psutil.disk_usage("/")
            disks.append(
                {
                    "mount": "/",
                    "device": None,
                    "total": usage.total,
                    "used": usage.used,
                    "percent": usage.percent,
                    "error": None,
                }
            )
        processes = []
        seen = set()
        for process in psutil.process_iter(
            ["pid", "name", "username", "memory_percent", "status", "create_time"]
        ):
            try:
                info = process.info
                key = (process.pid, info["create_time"])
                percent = process.cpu_percent()
                processes.append(
                    {
                        "pid": process.pid,
                        "name": info["name"],
                        "user": info["username"],
                        "memory_percent": info["memory_percent"],
                        "status": info["status"],
                        "cpu_percent": percent if key in self.seen else None,
                    }
                )
                seen.add(key)
            except (psutil.Error, OSError):
                continue
        self.seen = seen
        temperatures = []
        try:
            for name, sensors in psutil.sensors_temperatures().items():
                for sensor in sensors:
                    temperatures.append({"name": sensor.label or name, "celsius": sensor.current})
        except (AttributeError, OSError, psutil.Error):
            pass
        result = {
            "collected_at": timestamp(),
            "hostname": platform.node(),
            "os": platform.platform(),
            "uptime_seconds": time.time() - psutil.boot_time(),
            "cpu_percent": sum(cpu) / len(cpu) if self.primed and cpu else None,
            "cpu_cores": cpu if self.primed else [],
            "load": list(os.getloadavg()),
            "memory": {
                "total": memory.total,
                "used": memory.total - memory.available,
                "available": memory.available,
                "percent": memory.percent,
            },
            "swap": {"total": swap.total, "used": swap.used, "percent": swap.percent},
            "network": network,
            "disks": disks,
            "temperatures": temperatures,
            "processes": processes,
        }
        self.primed = True
        return result
