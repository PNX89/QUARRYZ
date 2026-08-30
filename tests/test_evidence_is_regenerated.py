"""Every committed measurement is produced by a script, and CI runs that script.

A repository arguing that a number without a date is worthless cannot itself carry numbers
nobody re-derives. These tests are the join between three things that are easy to let drift
apart: a directory under `docs/evidence`, the script that writes it, and a CI job that runs the
script and diffs the result.

TWO OF THE THREE ARE THE EASY HALF. Checking that a script exists and that a directory exists
proves nothing about whether they are connected, so what is asserted here is that the workflow
NAMES the script AND diffs the directory the script writes. A job that runs a harness and does
not compare its output is a job that proves the harness does not crash.
"""

from __future__ import annotations

import ast
import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def workflow() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return loaded


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def run_commands() -> str:
    """Every line the workflow actually EXECUTES, with comments and step names left out.

    THE WHOLE FILE WAS SEARCHED BEFORE THIS EXISTED, and a mutation proved what that was worth:
    replacing `python scripts/measure_snapshots.py` with a script that does not exist left this
    suite entirely green, because line 34 of the workflow mentions the same filename in a
    comment explaining why mypy needs the engine group. The enforcement was satisfied by prose
    ABOUT the harness while the step that ran it was gone.

    That is the same defect twice in this repository, which is why it is now fixed at the
    source rather than in one assertion: the workflow is parsed, and only `run:` bodies are
    searched, minus their own comment lines.
    """
    jobs = workflow()["jobs"]
    assert isinstance(jobs, dict)
    executed: list[str] = []
    for job in jobs.values():
        assert isinstance(job, dict)
        for step in job.get("steps", []):
            command = step.get("run")
            if not isinstance(command, str):
                continue
            executed += [line for line in command.splitlines() if not line.strip().startswith("#")]
    assert executed, "the workflow runs no commands at all"
    return "\n".join(executed)


def executed_diffs() -> str:
    """Only the lines that compare something, which is where an exemption is decided."""
    return "\n".join(
        line for line in run_commands().splitlines() if "diff" in line or "status" in line
    )


def evidence_directories() -> list[pathlib.Path]:
    if not EVIDENCE.exists():
        return []
    return sorted(path for path in EVIDENCE.iterdir() if path.is_dir())


def test_every_evidence_directory_has_a_summary_that_is_json() -> None:
    """The transcripts are for a reader and the summary is what CI diffs.

    A harness in a sibling repository wrote a summary that was not JSON at all, twice, and still
    exited zero: once because an unterminated container put the bare word `none` where a number
    belonged, and once because `grep -c .` prints 0 AND exits 1 on empty input, so a fallback
    appended a second zero and the value spanned two lines.
    """
    import json

    directories = evidence_directories()
    assert directories, "there is no committed evidence at all, so this checks nothing"
    for directory in directories:
        summary = directory / "summary.json"
        assert summary.exists(), f"{directory.name} has no summary.json for CI to diff"
        json.loads(summary.read_text(encoding="utf-8"))


def joined_path(node: ast.expr) -> str | None:
    """A chain of `/` over string literals, flattened. Anything else is not a path we can read."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = joined_path(node.right)
        if right is None:
            return None
        left = joined_path(node.left)
        return f"{left}/{right}" if left else right
    return None


def paths_the_harnesses_write() -> dict[str, list[str]]:
    """Where each script ASSIGNS its output, read as an assignment rather than as prose.

    THE WORD WAS SEARCHED FOR AND NOT THE PATH, and a mutation walked through the difference.
    The check was `directory.name in text` over every script concatenated, so the bare words
    "snapshots", "agreement", "collapse" and "gate" satisfied it from the harnesses' own
    docstrings and comments. Pointing `OUT` in scripts/measure_snapshots.py at a scratch
    directory left it green, and so did the CI step behind it: `git diff --exit-code --
    docs/evidence/snapshots` compares a directory nothing rewrote and exits 0.

    So the assignments are parsed. A sentence about where a harness writes cannot satisfy this;
    only an assignment naming the path can.
    """
    written: dict[str, list[str]] = {}
    for path in sorted((REPO / "scripts").glob("*.py")):
        found = []
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign):
                continue
            target = joined_path(node.value)
            if target and target.startswith("docs/evidence/"):
                found.append(target)
        written[path.name] = found
    # `$ROOT/` and not a bare path, because a shell harness `cd`s into dbt/ and a relative one
    # would then name a directory that does not exist.
    for path in sorted((REPO / "scripts").glob("*.sh")):
        text = path.read_text(encoding="utf-8")
        written[path.name] = re.findall(
            r'^[A-Z_]+="\$ROOT/(docs/evidence/[^"]+)"$', text, re.MULTILINE
        )
    return written


def test_a_script_writes_every_evidence_directory() -> None:
    """A committed artefact nobody can regenerate is a claim about the past."""
    written = paths_the_harnesses_write()
    assert any(written.values()), (
        "no script under scripts/ assigns a path under docs/evidence at all, so either every "
        "harness has stopped writing evidence or this test has stopped being able to read them"
    )
    for directory in evidence_directories():
        target = f"docs/evidence/{directory.name}"
        assert any(target in found for found in written.values()), (
            f"no script under scripts/ writes to {target}, so that evidence cannot be "
            f"regenerated and the CI step diffing it is comparing a directory nothing rewrote. "
            f"What the scripts do write: {written}"
        )


def test_ci_runs_every_harness_and_diffs_what_it_wrote() -> None:
    """The join that matters, and the half a weaker test would miss.

    Running a harness proves it does not crash. Diffing what it wrote is what turns a changed
    outcome into a red build, and the two are separate lines in the workflow, so both are
    asserted for each evidence directory rather than either being taken as the other.
    """
    text = run_commands()
    for directory in evidence_directories():
        relative = f"docs/evidence/{directory.name}"
        # THE DIRECTORY AND NOT THE SUMMARY. This asserted summary.json alone, which left the
        # transcripts, the files a human being actually reads, compared by nothing at all.
        assert f"git diff --exit-code -- {relative}\n" in text, (
            f"CI does not diff {relative}, so a changed outcome is not a red build"
        )
        # And a diff is silent about a file that is new, so the status check is asserted too.
        assert f'test -z "$(git status --porcelain {relative})"' in text, (
            f"CI diffs {relative} but never checks for a file the harness newly created, which "
            f"a diff against the index does not see"
        )

    # BOTH SUFFIXES, and globbing only `.sh` meant two of the four harnesses were unenforced.
    # measure_agreement.py and measure_snapshots.py are Python, so this loop never saw them: the
    # workflow could drop the step that runs either one and every test here would still pass,
    # while the diff step it left behind would exit 0 having compared a file nothing rewrote.
    # That is the exact failure this file's docstring says it exists to catch.
    harnesses = sorted(
        list((REPO / "scripts").glob("measure_*.sh"))
        + list((REPO / "scripts").glob("measure_*.py"))
    )
    assert len(harnesses) >= 4, f"only {len(harnesses)} harnesses found, which cannot be right"
    for script in harnesses:
        assert f"scripts/{script.name}" in text, f"CI never runs scripts/{script.name}"


def test_every_job_in_the_workflow_is_named() -> None:
    """An unnamed job shows as its key, and the key is not what a reader is told to look for."""
    jobs = workflow()["jobs"]
    assert isinstance(jobs, dict)
    for key, job in jobs.items():
        assert isinstance(job, dict)
        assert job.get("name") or job.get("uses"), f"job {key} has no name"


def test_every_third_party_action_is_pinned_by_commit() -> None:
    """A tag is a pointer its owner can move, and this repository downloads binaries.

    Written with the first workflow rather than after the fact: a sibling shipped twelve floating
    major tags under a generated file claiming every workflow pinned an exact version.
    """
    # EVERY WORKFLOW FILE, AND IT USED TO BE ci.yml ALONE. pages.yml arrived pinned by commit
    # and this test would not have noticed either way, which makes it a check on one file
    # rather than on the repository. A second workflow is exactly where a floating tag gets in:
    # it is written once, at publication, and never looked at again.
    workflows = sorted((REPO / ".github" / "workflows").glob("*.yml"))
    assert len(workflows) >= 1
    text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)

    first_party = "PNX89/"
    uses = re.findall(r"^\s*(?:- )?uses:\s*(\S+)\s*(#.*)?$", text, re.MULTILINE)
    assert uses, "the workflows have no `uses:` lines at all"
    for ref, trailing in uses:
        if ref.startswith(first_party):
            continue
        assert re.search(r"@[0-9a-f]{40}$", ref), f"{ref} is pinned by a movable tag"
        assert trailing.strip().startswith("#"), f"{ref} is pinned with no version named beside it"


def test_the_offline_suite_imports_nothing_from_the_engine_group() -> None:
    """The claim that a stranger can clone this and run pytest with nothing installed.

    The CI job that runs the offline suite ALSO installs the engine group, because mypy cannot
    check a file whose imports it cannot resolve. That is a type-checking need and not a testing
    one, and the distinction only holds if the tests genuinely do not touch those packages. So
    it is asserted rather than trusted: every test here reads committed JSON and CSV.
    """
    engines = ("pyiceberg", "moto", "boto3", "duckdb", "pyarrow")
    offenders: list[str] = []
    for path in sorted((REPO / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for package in engines:
                if stripped.startswith((f"import {package}", f"from {package}")):
                    offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], (
        "the offline suite imports an engine package, so cloning this and running pytest with "
        f"--dev alone no longer works: {offenders}"
    )


def test_no_committed_transcript_carries_a_clock() -> None:
    """The reason the transcripts went undiffed for so long, now a check rather than a habit.

    dbt stamps `22:46:17` on every line it prints and reports each test as `[FAIL 7 in 0.00s]`.
    Both change when nothing has changed, so a transcript carrying them cannot be compared
    between runs, and the response to a file that cannot be compared is to stop comparing it.
    `scripts/measure_gate.sh` strips both. This is what stops the next harness reintroducing one
    and quietly forcing the same retreat.

    A DATE IS NOT A CLOCK. These transcripts are full of dates, because a publication date is the
    subject of this repository. What is banned is a wall time, an elapsed duration and a full
    ISO instant: the three things that record when the measurement ran rather than what it found.
    """
    clocks = re.compile(r"\b\d{2}:\d{2}:\d{2}\b|\bin \d+\.\d+s\b|\d{4}-\d{2}-\d{2}T")
    offenders: list[str] = []
    for directory in evidence_directories():
        for path in sorted(directory.glob("*.txt")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if clocks.search(line):
                    offenders.append(f"{directory.name}/{path.name}:{number}: {line.strip()[:70]}")
    assert offenders == [], (
        "a committed transcript records when it was produced, so re-running the harness rewrites "
        f"it and the CI diff becomes a coin toss: {offenders}"
    )


def test_the_demo_output_is_captured_by_a_script_and_rerun_by_ci() -> None:
    """The one file under docs/evidence that is not in a directory of its own.

    `demo.txt` is what the portfolio card prints, which makes it the most widely read output
    this repository produces and the easiest to leave behind: it is a paste until something
    regenerates it. The directory loop above cannot see it, so it is asserted separately rather
    than left to look covered.
    """
    captured = EVIDENCE / "demo.txt"
    assert captured.exists(), "there is no captured demo output for the card to show"
    assert captured.read_text(encoding="utf-8").strip(), "the captured demo output is empty"

    script = REPO / "scripts" / "capture_evidence.py"
    assert script.exists()
    assert "demo.txt" in script.read_text(encoding="utf-8")

    # THE ONE CAPTURED FILE CI DOES NOT DIFF, named here so the exemption is visible rather than
    # inferred from its absence. facts.json carries a capture date, so a byte comparison would
    # fail on the second morning and the job would be ignored within a week. Its numbers are
    # held by tests/test_card.py instead, and that file is asserted to exist for that reason.
    assert (REPO / "tests" / "test_card.py").exists(), (
        "facts.json is exempt from the CI diff because it carries a date, and the tests that "
        "check its contents another way are gone, so nothing checks it at all"
    )
    assert "facts.json" not in executed_diffs(), (
        "facts.json is now diffed by CI, which will fail on the day after it was captured"
    )

    executed = run_commands()
    assert "uv run python scripts/capture_evidence.py" in executed, "CI never re-runs the demo"
    assert "git diff --exit-code -- docs/evidence/demo.txt" in executed, (
        "CI runs the demo and does not compare what it printed, which proves only that it does "
        "not crash"
    )


def test_the_demo_needs_nothing_the_offline_suite_does_not() -> None:
    """The claim the demo is FOR, and the one that would rot first.

    Its whole purpose is being runnable by somebody who has just cloned this and installed
    nothing. An import of duckdb or pyiceberg would break that silently, because the machine
    writing the demo always has them.
    """
    text = (REPO / "examples" / "what_the_publisher_changed.py").read_text(encoding="utf-8")
    for package in ("pyiceberg", "moto", "boto3", "duckdb", "pyarrow", "psycopg", "yaml"):
        assert f"import {package}" not in text, (
            f"the demo imports {package}, so it no longer runs on a clone with nothing installed"
        )
    assert "requests" not in text and "urllib" not in text, "the demo reaches the network"
