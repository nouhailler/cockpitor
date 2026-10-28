"""Collect read-only VM prerequisites. Never runs a sensitive qualification trial."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.i18n import language
from app.qualification_preflight import collect, save_report


def main():
    parser = argparse.ArgumentParser(
        description="Read-only VM qualification prerequisites (no execution enabled)"
    )
    parser.add_argument("--profile", choices=("all", "systemd", "docker", "podman"), default="all")
    parser.add_argument("--language", choices=("fr", "en"), default="fr")
    parser.add_argument("--docker-socket")
    parser.add_argument("--podman-socket")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    language.set(args.language)
    report = asyncio.run(
        collect(args.profile, docker_socket=args.docker_socket, podman_socket=args.podman_socket)
    )
    if args.output is not None:
        try:
            save_report(args.output, report)
        except (OSError, ValueError):
            parser.exit(3, "Report could not be saved in a new private file.\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "prerequisites_met" else 2


if __name__ == "__main__":
    raise SystemExit(main())
