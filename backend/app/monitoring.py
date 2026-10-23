"""Cached, bounded read-only inspection. No package installation or active network probes."""

import asyncio
import ipaddress
import json
import math
import re
from pathlib import Path

import psutil

from .system import timestamp


async def command(*args):
    process = None
    readers = []
    try:
        async with asyncio.timeout(4):
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": "/nonexistent"},
            )

            async def read(stream, maximum):
                body = bytearray()
                while chunk := await stream.read(16384):
                    body.extend(chunk)
                    if len(body) > maximum:
                        raise ValueError("output limit")
                return body.decode("utf-8", errors="replace")

            readers = [
                asyncio.create_task(read(process.stdout, 512 * 1024)),
                asyncio.create_task(read(process.stderr, 8192)),
            ]
            out, _ = await asyncio.gather(*readers)
            await process.wait()
            if process.returncode and not (
                args[0] == "/usr/sbin/smartctl" and process.returncode & 7 == 0
            ):
                return {"status": "unavailable", "code": "PERMISSION_OR_TOOL_ERROR"}
            return {"status": "available", "output": out}
    except (OSError, TimeoutError, ValueError):
        return {"status": "unavailable", "code": "TOOL_UNAVAILABLE"}
    finally:
        for reader in readers:
            reader.cancel()
        if readers:
            await asyncio.gather(*readers, return_exceptions=True)
        if process and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()


def exposure(address):
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_loopback:
            return "loopback"
        if ip.is_multicast:
            return "multicast"
        if ip.is_link_local:
            return "link_local"
        if ip.is_unspecified:
            return "all_interfaces"
        return "private" if ip.is_private else "public_address"
    except ValueError:
        return "unknown"


def network():
    result = {
        "status": "available",
        "interfaces": [],
        "listeners": [],
        "listeners_status": "available",
    }
    try:
        stats = psutil.net_if_stats()
        for name, addresses in list(psutil.net_if_addrs().items())[:64]:
            result["interfaces"].append(
                {
                    "name": name,
                    "up": stats[name].isup if name in stats else None,
                    "addresses": [a.address for a in addresses if a.family in {2, 10}][:16],
                }
            )
        rows = psutil.net_connections(kind="inet")
        for row in rows:
            if row.status == "LISTEN" or (row.type == 2 and row.laddr and not row.raddr):
                result["listeners"].append(
                    {
                        "address": row.laddr.ip,
                        "port": row.laddr.port,
                        "protocol": "udp" if row.type == 2 else "tcp",
                        "scope": exposure(row.laddr.ip),
                    }
                )
                if len(result["listeners"]) >= 512:
                    break
    except (OSError, psutil.Error):
        result["listeners_status"] = "unavailable"
    result["dns"] = []
    result["routes"] = []
    try:
        with Path("/etc/resolv.conf").open() as source:
            content = source.read(16384)
        result["dns"] = [
            str(ipaddress.ip_address(fields[1]))
            for line in content.splitlines()
            if len(fields := line.split()) >= 2 and fields[0] == "nameserver"
        ][:8]
    except (OSError, ValueError):
        pass
    try:
        with Path("/proc/net/route").open() as source:
            for line in source.read(32768).splitlines()[1:65]:
                fields = line.split()
                result["routes"].append(
                    {
                        "interface": fields[0],
                        "destination": str(
                            ipaddress.IPv4Address(int(fields[1], 16).to_bytes(4, "little"))
                        ),
                        "gateway": str(
                            ipaddress.IPv4Address(int(fields[2], 16).to_bytes(4, "little"))
                        ),
                    }
                )
    except (OSError, ValueError, IndexError):
        pass
    return result


def power():
    rows = []
    try:
        for entry in list(Path("/sys/class/power_supply").glob("*"))[:16]:
            values = {}
            for key in ("type", "status", "capacity", "online"):
                try:
                    values[key] = (entry / key).read_text()[:128].strip()
                except OSError:
                    pass
            rows.append({"name": entry.name, **values})
    except OSError:
        pass
    return {
        "status": "available" if rows else "unavailable",
        "items": rows,
        "scope": "kernel_power_supply",
    }


async def inspect():
    async def section(args, parser):
        data = await command(*args)
        if data["status"] != "available":
            return data
        try:
            return {"status": "available", "data": parser(data["output"])}
        except (ValueError, TypeError, KeyError):
            return {"status": "unavailable", "code": "INVALID_RESPONSE"}

    def units(out):
        return [
            {"unit": fields[0], "state": fields[1]}
            for line in out.splitlines()
            if len(fields := line.split()) >= 2 and fields[0].endswith(".service")
        ][:2000]

    def updates(out):
        return [
            {"package": line.split()[0].split("/")[0], "version": line.split()[1]}
            for line in out.splitlines()
            if "/" in line and len(line.split()) >= 2
        ][:2000]

    def gpu(out):
        result = []
        for line in out.splitlines()[:16]:
            fields = [value.strip() for value in line.split(",")]
            if len(fields) == 4:
                if not all(
                    math.isfinite(float(value)) and float(value) >= 0 for value in fields[1:]
                ):
                    raise ValueError("invalid GPU counters")
                result.append(
                    {
                        "name": fields[0],
                        "utilization": float(fields[1]),
                        "memory_used_mib": float(fields[2]),
                        "memory_total_mib": float(fields[3]),
                    }
                )
        return result

    disks, services, updates_data, time_data, gpu_data = await asyncio.gather(
        section(
            ("/usr/bin/lsblk", "--json", "--bytes", "--output", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT"),
            json.loads,
        ),
        section(
            (
                "/usr/bin/systemctl",
                "list-unit-files",
                "--type=service",
                "--no-legend",
                "--no-pager",
                "--no-ask-password",
            ),
            units,
        ),
        section(("/usr/bin/apt", "list", "--upgradable"), updates),
        section(
            (
                "/usr/bin/timedatectl",
                "show",
                "--no-pager",
                "--property=Timezone",
                "--property=NTPSynchronized",
                "--property=NTP",
            ),
            lambda out: dict(line.split("=", 1) for line in out.splitlines() if "=" in line),
        ),
        section(
            (
                "/usr/bin/nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ),
            gpu,
        ),
    )
    smart = []
    if disks["status"] == "available":
        for disk in disks["data"].get("blockdevices", [])[:4]:
            name = disk.get("name", "")
            if disk.get("type") == "disk" and re.fullmatch(
                r"(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+)", name
            ):
                value = await command("/usr/sbin/smartctl", "--json", "--health", "/dev/" + name)
                if value["status"] == "available":
                    try:
                        health = (
                            json.loads(value.pop("output")).get("smart_status", {}).get("passed")
                        )
                        value = {
                            "status": "available" if isinstance(health, bool) else "unavailable",
                            "passed": health,
                        }
                    except ValueError:
                        value = {"status": "unavailable"}
                smart.append({"device": name, **value})
    ups = []
    discovered = await command("/usr/bin/upsc", "-l", "127.0.0.1")
    if discovered["status"] == "available":
        for name in discovered["output"].splitlines()[:4]:
            if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
                reading = await command("/usr/bin/upsc", name + "@127.0.0.1")
                values = {}
                if reading["status"] == "available":
                    for line in reading["output"].splitlines():
                        if ": " in line:
                            key, value = line.split(": ", 1)
                            if key in {
                                "ups.status",
                                "battery.charge",
                                "battery.runtime",
                                "ups.load",
                            }:
                                values[key] = value[:64]
                ups.append({"name": name, "status": reading["status"], "values": values})
    return {
        "ups": {
            "status": "available" if ups else "unavailable",
            "items": ups,
            "scope": "local_nut_only",
        },
        "collected_at": timestamp(),
        "network": await asyncio.to_thread(network),
        "power": await asyncio.to_thread(power),
        "disks": disks,
        "smart": smart,
        "installed_services": services,
        "updates": {**updates_data, "scope": "existing_apt_cache"},
        "time": time_data,
        "gpu": {**gpu_data, "scope": "nvidia_only"},
    }
