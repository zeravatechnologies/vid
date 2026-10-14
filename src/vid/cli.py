"""`vid` command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import urllib.request

from vid import __version__, paths
from vid.config import Config


def _status(config: Config) -> int:
    token_path = paths.token_file()
    if not token_path.is_file():
        print("Vid has not run yet on this account (no control token).", file=sys.stderr)
        return 1
    req = urllib.request.Request(f"http://127.0.0.1:{config.control_port}/status",
                                 headers={"Authorization": f"Bearer {token_path.read_text('utf-8').strip()}"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            print(json.dumps(json.load(r), indent=2))
        return 0
    except OSError as e:
        print(f"Vid is not answering on 127.0.0.1:{config.control_port}: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vid", description="Vid: a local guard between an AI agent and its model.")
    p.add_argument("--config", help="configuration file (default: see `vid paths`)")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the guard (the background service runs this)")
    sub.add_parser("status", help="ask the running guard what it protects and how it is doing")
    sub.add_parser("paths", help="where configuration and data live")
    sub.add_parser("version")
    args = p.parse_args(argv)

    from pathlib import Path
    config = Config.load(Path(args.config) if args.config else None)

    if args.cmd == "version":
        print(f"vid {__version__}")
        return 0
    if args.cmd == "paths":
        print(f"config file: {paths.config_file()}{'' if paths.config_file().is_file() else '  (not created; defaults in use)'}")
        print(f"data:        {paths.data_dir()}")
        return 0
    if args.cmd == "status":
        return _status(config)
    if args.cmd == "serve":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        from vid.server import serve
        try:
            asyncio.run(serve(config))
        except KeyboardInterrupt:
            pass
        return 0
    p.print_help()
    return 0
