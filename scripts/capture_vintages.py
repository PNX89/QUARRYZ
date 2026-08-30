"""Capture every published version of four ONS series, as a bitemporal table.

    uv run python scripts/capture_vintages.py            capture all four
    uv run python scripts/capture_vintages.py IKBJ       capture one

WHAT IS COMMITTED AND WHAT IS NOT. Not the versions. Four series across their full publication
history is about 500 documents and 200,000 observations, most of which say the same thing as the
document before them. What is committed is the BITEMPORAL TABLE: one row each time a period's
value changed, carrying the period it is about and the version that changed it. That is not a
compression trick, it is the shape the data actually has, and reconstructing any version from it
is a filter rather than a fetch.

THE URL FORM, BECAUSE THE OBVIOUS ONE IS DEAD. `api.ons.gov.uk/timeseries/<cdid>/dataset/...`
returns 404 with "This API has been decommissioned ... fully retired on 25/11/2024". The live
form carries the topic path, which is load-bearing rather than decorative: the same CDID under
the wrong path is a 404.

    https://www.ons.gov.uk/<topic>/timeseries/<cdid>/<dataset>/data
    https://www.ons.gov.uk/<topic>/timeseries/<cdid>/<dataset>/previous/v<N>/data

FOUR THINGS THAT ARE EASY TO GET WRONG HERE, and each one is a decision this file makes
explicitly rather than by accident. They are the reason this repository exists.

1. THE RELEASE DATE IS NOT A UNIQUE KEY. IKBJ v106 and v107 were both released on 2023-06-13,
   and DZLS v70 and v71 both on 2021-09-20. Transaction time is therefore the PAIR
   (release date, version label), and a table keyed on the date alone merges two different
   states of the world into one.

2. `versions[N].updateDate` IS THE DATE VERSION N WAS SUPERSEDED, not the date it was released.
   It equals version N+1's own `releaseDate`. A loader that takes its transaction time from the
   index array shifts every vintage by one publication, which gives a plausible answer to every
   question and a correct answer to none. The date used here is `description.releaseDate` read
   from inside each version document.

3. AN EMPTY VALUE IS NOT A NULL AND NOT AN ABSENCE. IKBJ's April 1997 read 196, then an empty
   string for four publications, then 257, and reads 402 today. The period key stays in the
   document and only the value is emptied, so `""` is recorded as WITHDRAWN and distinguished
   from a period that has not appeared yet.

4. `len(versions)` OVER-COUNTS. IKBJ's array holds 192 entries with 145 distinct labels. The
   walk goes to a 404 rather than trusting the length, and an empty array does not mean a series
   never changed: `ikbj/diop` has an empty one, a `nextRelease` that never happened, and data
   stopping in March 2021.

ONE REQUEST PER SECOND, and that is measured rather than polite. Four concurrent workers tripped
Cloudflare's 1015 rate limit; one per second sustained about 1,500 requests.

LICENCE. ONS content is published under the Open Government Licence v3.0, whose "You are free
to" list includes "adapt the Information". The attribution the licence requires is in the README
and in SOURCE.json beside the captured data.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import time
import urllib.error
import urllib.request
from collections import defaultdict
from itertools import pairwise
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "quarryz" / "data" / "vintages"

#: The four series, with the topic path each one lives under. None of these is used by the
#: sibling repository that also reads ONS vintages: it takes IHYQ, MGSX, ABMI and D7BT.
#:
#: Chosen for two properties measured before they were picked. Each revises heavily, and none
#: was ever REBASED, which is the trap that makes a rescaling look like a correction: for KAC3
#: and MGRZ the median ratio between consecutive vintages is exactly 1.000000, and IKBJ and DZLS
#: are current-price sterling with no base year at all. A retail sales volume index was rejected
#: for exactly that reason, having been rescaled seven times.
SERIES: dict[str, dict[str, str]] = {
    "IKBJ": {
        "path": "economy/nationalaccounts/balanceofpayments",
        "dataset": "mret",
        "title": "Total trade balance, current prices, seasonally adjusted, GBP million",
        "why": "It carries the largest single revision found anywhere in these four, which is "
        "the figure this repository quotes, and it carries the withdrawal case: a period the "
        "publisher emptied and later refilled.",
    },
    "DZLS": {
        "path": "economy/governmentpublicsectorandtaxes/publicsectorfinance",
        "dataset": "pusf",
        "title": "Public sector net borrowing excluding public sector banks, GBP million",
        "why": "Almost every period this series has ever published has since been restated, so "
        "a warehouse holding only the latest figure is wrong about nearly all of it.",
    },
    "KAC3": {
        "path": "employmentandlabourmarket/peopleinwork/earningsandworkinghours",
        "dataset": "lms",
        "title": "Average weekly earnings, year on year three month average growth, per cent",
        "why": "A rate rather than a level, so a revision here cannot be explained away as a "
        "rescaling of the whole series.",
    },
    "MGRZ": {
        "path": "employmentandlabourmarket/peopleinwork/employmentandemployeetypes",
        "dataset": "lms",
        "title": "People in employment, aged 16 and over, seasonally adjusted, thousands",
        "why": "The control, revised in a minority of its periods: a warehouse that only ever "
        "sees heavy revisers is not being asked a hard question.",
    },
}

WITHDRAWN = "WITHDRAWN"
PACE_SECONDS = 1.0


def fetch(url: str) -> dict[str, Any] | None:
    """One document, or None for a 404, which is how the walk knows it has finished."""
    request = urllib.request.Request(url, headers={"User-Agent": "QUARRYZ vintage capture"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            loaded: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return loaded
    except urllib.error.HTTPError as failure:
        if failure.code == 404:
            return None
        if failure.code == 429:
            raise SystemExit(
                "the ONS returned 429. The pace here is one request per second, which held for "
                "about 1500 requests when this was measured. Wait and run it again."
            ) from failure
        raise


def observations(document: dict[str, Any]) -> dict[str, str]:
    """Every period in one version, keyed by a period string and carrying the raw value.

    The raw value is kept as a STRING deliberately. An empty one is a withdrawal and turning it
    into a float here would erase the distinction this repository is about.
    """
    found: dict[str, str] = {}
    for bucket in ("years", "quarters", "months"):
        for point in document.get(bucket, []):
            period = str(point.get("date", "")).strip()
            if period:
                found[period] = str(point.get("value", "")).strip()
    return found


def walk(cdid: str) -> list[dict[str, str]]:
    """Every version of one series, oldest first, walked to a 404."""
    spec = SERIES[cdid]
    base = f"https://www.ons.gov.uk/{spec['path']}/timeseries/{cdid.lower()}/{spec['dataset']}"
    versions: list[dict[str, str]] = []

    number = 1
    while True:
        document = fetch(f"{base}/previous/v{number}/data")
        time.sleep(PACE_SECONDS)
        if document is None:
            break
        versions.append(
            {
                "label": f"v{number}",
                # From INSIDE the version, never from the index array. See point 2 above.
                "released": str(document["description"]["releaseDate"])[:10],
                "title": str(document["description"].get("title", "")),
                "observations": observations(document),  # type: ignore[dict-item]
            }
        )
        number += 1

    current = fetch(f"{base}/data")
    time.sleep(PACE_SECONDS)
    if current is None:
        raise SystemExit(f"{cdid}: the current document is a 404, which cannot be right")
    versions.append(
        {
            "label": "current",
            "released": str(current["description"]["releaseDate"])[:10],
            "title": str(current["description"].get("title", "")),
            "observations": observations(current),  # type: ignore[dict-item]
        }
    )
    return versions


def changes(versions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """One row each time a period's value changed, which is the bitemporal table.

    A period appearing for the first time is a change from nothing, and an emptied value is a
    change to WITHDRAWN. Both are rows: a warehouse that records only numeric movements cannot
    answer what the publisher said, only what it said when it was saying something.
    """
    rows: list[dict[str, str]] = []
    previous: dict[str, str] = {}
    for version in versions:
        for period, raw in sorted(version["observations"].items()):
            value = WITHDRAWN if raw == "" else raw
            if previous.get(period) == value:
                continue
            rows.append(
                {
                    "period": period,
                    "value": value,
                    "released": version["released"],
                    "version": version["label"],
                }
            )
            previous[period] = value
    return rows


def why_numbers(rows: list[dict[str, str]]) -> dict[str, Any]:
    """The figures `why` used to state in words, computed from the rows just written.

    TWO OF THE THREE TYPED FIGURES WERE WRONG. `why` said DZLS annual 2020 had seventeen
    distinct value states, and that period carries forty-five; it said KAC3's March 2010 had
    read four values, and the corpus holds five. The one that was right, MGRZ revised in 249 of
    941 periods, recomputes exactly, so it was evidently derived once and the other two never
    were. A test excused the whole field as editorial and not recomputable from a CSV of
    numbers, which was true of the prose and false of three quarters of the sentence.

    So the arithmetic lives here, where a recapture rewrites it, and `why` keeps only the part
    a CSV genuinely cannot settle.
    """
    states: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        states[row["period"]].append((row["released"], row["value"]))

    # Ranked with the period label as the tie-break, because several periods share a count and
    # a dict ordering would decide it otherwise: a recapture would then move this field with no
    # measurement behind the move.
    restated = sorted(
        ((len({value for _, value in seq}), period) for period, seq in states.items()),
        key=lambda pair: (-pair[0], pair[1]),
    )

    # A withdrawal is a revision of a different kind, and subtracting it from a number means
    # nothing, so only adjacent numeric states are measured.
    biggest, moved = 0, ("", "", "", "")
    for period, seq in states.items():
        for (_, was), (released, now) in pairwise(seq):
            if WITHDRAWN in (was, now):
                continue
            size = abs(int(float(now)) - int(float(was)))
            if size > biggest:
                biggest, moved = size, (period, was, now, released)

    period, was, now, released = moved
    return {
        "periods": len(states),
        "periods_revised": sum(1 for seq in states.values() if len(seq) > 1),
        "most_restated_period": restated[0][1],
        "most_restated_period_states": restated[0][0],
        "largest_revision": {
            "period": period,
            "was": was,
            "now": now,
            "released": released,
            "size": biggest,
        },
    }


def capture(cdid: str) -> dict[str, Any]:
    print(f"==> {cdid}, walking versions at one request per second")
    versions = walk(cdid)
    rows = changes(versions)

    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / f"{cdid}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["period", "value", "released", "version"])
        writer.writeheader()
        writer.writerows(rows)

    released = [version["released"] for version in versions]
    duplicated = sorted({date for date in released if released.count(date) > 1})
    titles = sorted({version["title"] for version in versions if version["title"]})
    print(
        f"    {len(versions)} versions, {len(rows)} changes, "
        f"{len(set(released))} distinct release dates, {len(titles)} distinct titles"
    )
    return {
        "cdid": cdid,
        "title": SERIES[cdid]["title"],
        "why": SERIES[cdid]["why"],
        "why_numbers": why_numbers(rows),
        "url": f"https://www.ons.gov.uk/{SERIES[cdid]['path']}/timeseries/"
        f"{cdid.lower()}/{SERIES[cdid]['dataset']}/data",
        "versions": len(versions),
        "changes": len(rows),
        "distinct_release_dates": len(set(released)),
        "release_dates_shared_by_two_versions": duplicated,
        "distinct_titles_over_time": titles,
        "withdrawn_rows": sum(1 for row in rows if row["value"] == WITHDRAWN),
        "first_release": min(released),
        "last_release": max(released),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cdid", nargs="*", default=sorted(SERIES), help="which series to capture")
    args = parser.parse_args()

    captured = [capture(cdid.upper()) for cdid in args.cdid]

    source = {
        "publisher": "Office for National Statistics",
        "licence": "Open Government Licence v3.0",
        "attribution": "Contains public sector information licensed under the Open Government "
        "Licence v3.0.",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "permits_adaptation": 'The OGL v3.0 "You are free to" list includes "adapt the '
        'Information", which is what this repository does to it.',
        "api_note": "The api.ons.gov.uk form was retired on 25/11/2024. The live form carries "
        "the topic path and is the one recorded in each url below.",
        "captured": time.strftime("%Y-%m-%d"),
        "series": captured,
    }
    (DATA / "SOURCE.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {DATA / 'SOURCE.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
