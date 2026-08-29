"""Capture what the portfolio card shows: the demo's stdout, and the facts beside it.

    uv run python scripts/capture_evidence.py

    docs/evidence/demo.txt    the demo's stdout, byte for byte
    docs/evidence/facts.json  the test total, the Python range, the release and the capture date

WHY A CAPTURE RATHER THAN A PASTE. The portfolio card for this repository shows the demo's
output, and a card is built from this file rather than from anything typed. A pasted block is a
claim about a program that ran once on somebody's laptop; this one is regenerated in CI and the
build fails if a single byte differs.

The demo needs no engine, no network and no credential, which is the reason it can be the thing
CI re-runs on every push while the four measurements need jobs of their own.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "what_the_publisher_changed.py"
EVIDENCE = ROOT / "docs" / "evidence"
OUT = EVIDENCE / "demo.txt"
FACTS = EVIDENCE / "facts.json"


def test_total() -> int:
    """Collected by pytest rather than counted by eye or by grep.

    A `def test_` count over the tree is wrong the moment a test is parametrised, and every
    file here parametrises something.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    # SUMMED FROM THE PER-FILE LINES, because this project's pytest configuration prints those
    # instead of a single "N tests collected" line, and a regex looking for the total silently
    # found nothing. Summing is also the version that fails loudly if the format changes again:
    # a missing file contributes no number and the assertion below notices.
    per_file = re.findall(r"^(tests/\S+): (\d+)$", result.stdout, re.MULTILINE)
    if not per_file:
        raise SystemExit(f"pytest reported no collectable files:\n{result.stdout[-500:]}")
    on_disk = len(list((ROOT / "tests").glob("test_*.py")))
    if len(per_file) != on_disk:
        raise SystemExit(
            f"pytest collected {len(per_file)} test files and {on_disk} exist on disk, so one "
            f"of them contributes nothing and the total would understate the suite"
        )
    return sum(int(count) for _, count in per_file)


def python_range() -> str:
    """Read out of the CI matrix, which is the thing that is actually tested.

    Taking it from `requires-python` would state a claim nothing runs: a floor of 3.11 says
    nothing about whether 3.13 was ever executed.
    """
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = re.findall(r'"(\d+\.\d+)"', workflow)
    if not versions:
        raise SystemExit("the CI file names no Python versions, so the range cannot be stated")
    return f"{min(versions, key=float)} to {max(versions, key=float)}"


def release() -> str:
    """The package version, cross-checked against the newest tag.

    Two sources that can disagree, which is the point: a version bumped in pyproject and never
    tagged, or a tag cut from a commit that forgot the bump, are both worth a failure here
    rather than a card stating a release nobody can download.
    """
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    tags = subprocess.run(
        ["git", "tag", "--sort=-v:refname"], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.split()
    if not tags:
        return f"v{version} (untagged)"
    if tags[0] != f"v{version}":
        raise SystemExit(
            f"pyproject says {version} and the newest tag is {tags[0]}. One of them is wrong, "
            f"and the card would state whichever this script happened to read"
        )
    return tags[0]


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

    # FACTS.JSON IS NOT DIFFED BY CI AND demo.txt IS, which is a deliberate difference rather
    # than an oversight. A capture date changes every day by definition, so a byte comparison
    # of this file would fail on the second morning and teach everybody to ignore the job. The
    # numbers in it are held by tests/test_card.py instead, which checks the claim rather than
    # the timestamp: the test total against a live collection, the release against the tag.
    run_id = os.environ.get("GITHUB_RUN_ID")
    slug = os.environ.get("GITHUB_REPOSITORY", "PNX89/QUARRYZ")
    facts = {
        "tests": test_total(),
        "python": python_range(),
        "release": release(),
        "captured": datetime.date.today().isoformat(),
        "runUrl": f"https://github.com/{slug}/actions/runs/{run_id}" if run_id else None,
    }
    FACTS.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)} ({len(result.stdout.splitlines())} lines)")
    print(f"wrote {FACTS.relative_to(ROOT)} {facts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
