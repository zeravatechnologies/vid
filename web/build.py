#!/usr/bin/env python3
"""Bundle Vid's pure-Python input layer into web/pkg.js, so the web app runs
the SAME code as the download, in the browser, with nothing sent anywhere.

Usage: python3 web/build.py   (run from the repo root or anywhere)

It collects the vid package files the input layer needs and writes them as a
JSON map into web/pkg.js (window.VID_FILES). index.html writes them into
Pyodide's virtual filesystem and imports vid.input_layer.
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")

# Only what the input layer imports. No proxy, no server, no network code.
FILES = [
    "vid/__init__.py",
    "vid/defaults.toml",
    "vid/input_layer/__init__.py",
    "vid/input_layer/codes.py",
    "vid/input_layer/textscore.py",
    "vid/input_layer/normalize.py",
    "vid/input_layer/decoders.py",
    "vid/input_layer/structure.py",
    "vid/input_layer/control_tokens.py",
    "vid/input_layer/signals.py",
    "vid/input_layer/types.py",
]


def main() -> None:
    out = {}
    for rel in FILES:
        with open(os.path.join(SRC, rel), encoding="utf-8") as fh:
            out[rel] = fh.read()
    payload = "window.VID_FILES = " + json.dumps(out, ensure_ascii=False) + ";\n"
    dest = os.path.join(HERE, "pkg.js")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(payload)
    print(f"wrote {dest} ({len(out)} files, {len(payload)} bytes)")


if __name__ == "__main__":
    main()
