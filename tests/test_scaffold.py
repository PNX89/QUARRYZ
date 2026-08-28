"""The scaffold, asserted so the first commit is a green build rather than an empty one.

A repository whose first CI run is red teaches its own author to ignore the badge. These are
small on purpose: they check the shape of the thing rather than any behaviour, because there is
no behaviour yet.

Two of them exist because of specific failures in sibling repositories, and each says which.
"""

from __future__ import annotations

import pathlib
import subprocess
import tomllib
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]


def pyproject() -> dict[str, Any]:
    with (REPO / "pyproject.toml").open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


def tracked_files() -> list[pathlib.Path]:
    """What is IN the repository, asked of git rather than of the filesystem.

    A sibling repository walked the working tree past a hand-maintained skip list and therefore
    saw files that are not in the repository at all: a `.DS_Store` that Finder leaves behind is
    ignored by git, absent in CI and present on any Mac that has opened the folder, so the check
    failed locally and stayed green in CI. A check that passes on the machine running it and
    fails on the machine reading it is worse than no check.
    """
    listed = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True, cwd=REPO)
    return [REPO / name for name in listed.stdout.decode().split("\0") if name]


def test_the_package_imports_and_declares_a_version() -> None:
    import quarryz

    assert quarryz.__version__ == "0.1.0"


def test_every_declared_marker_is_carried_by_a_test() -> None:
    """A marker naming a suite that does not exist reads as coverage and is not.

    This is written before there are any markers, which is the point: a sibling repository
    declared three, deselected all three by default, and two of them were carried by NO TEST AT
    ALL. Worse, the test policing the list asserted the exact three names, so the assertion
    cemented the fiction it existed to prevent. What is checked here is usage, not names.
    """
    config = pyproject()["tool"]["pytest"]["ini_options"]
    declared = {str(entry).split(":")[0] for entry in config.get("markers", [])}

    used: set[str] = set()
    for path in sorted((REPO / "tests").glob("test_*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("@pytest.mark."):
                used.add(stripped.removeprefix("@pytest.mark.").split("(")[0].strip())

    unused = declared - {"parametrize", "skipif", "xfail"} - used
    assert unused == set(), f"declared and carried by nothing: {sorted(unused)}"

    deselected = {
        word for word in str(config["addopts"]).replace("'", " ").split() if word in declared
    }
    assert declared == deselected, (
        f"declared {sorted(declared)} and deselected {sorted(deselected)} disagree, so a suite "
        f"is either running where it cannot or hidden where it could"
    )


def test_mypy_covers_every_directory_holding_python() -> None:
    """A directory of Python that nothing type checks is the one that breaks in CI.

    In a sibling repository `scripts` was outside mypy's file list, so the two scripts CI and
    the README depended on were the only Python in the tree that was never checked. The list
    grows with the first file in a directory rather than in advance, because naming a directory
    mypy cannot find is an error and not a no-op.
    """
    checked = {str(entry) for entry in pyproject()["tool"]["mypy"]["files"]}
    holding = {
        path.relative_to(REPO).parts[0]
        for path in tracked_files()
        if path.suffix == ".py" and len(path.relative_to(REPO).parts) > 1
    }
    missing = holding - checked
    assert missing == set(), f"these directories hold Python and mypy does not read them: {missing}"


def test_no_third_party_binary_is_tracked() -> None:
    """This repository downloads a 167 MB ClickHouse binary and must never commit one.

    Checked against the TREE rather than against .gitignore, because an ignore rule added after
    a file is already tracked does nothing at all, which is how 121.7 MiB of provider binaries
    reached a sibling repository's history.
    """
    heavy = [
        path.relative_to(REPO)
        for path in tracked_files()
        if path.is_file() and path.stat().st_size > 1_000_000
    ]
    assert heavy == [], f"these tracked files are over a megabyte: {heavy}"
