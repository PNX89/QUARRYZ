"""Capture the demo's stdout, byte for byte, into the evidence directory.

    uv run python scripts/capture_demo.py

WHY A CAPTURE RATHER THAN A PASTE. The portfolio card for this repository shows the demo's
output, and a card is built from this file rather than from anything typed. A pasted block is a
claim about a program that ran once on somebody's laptop; this one is regenerated in CI and the
build fails if a single byte differs.

The demo needs no engine, no network and no credential, which is the reason it can be the thing
CI re-runs on every push while the four measurements need jobs of their own.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "what_the_publisher_changed.py"
OUT = ROOT / "docs" / "evidence" / "demo.txt"


def main() -> int:
    result = subprocess.run(
        [sys.executable, str(DEMO)], capture_output=True, text=True, cwd=ROOT, check=False
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    if not result.stdout.strip():
        print("the demo printed nothing, so there is no card to build", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(result.stdout, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(result.stdout.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
