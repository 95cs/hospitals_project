"""Build the serving layer for the Power BI report.

`analysis_dataset.csv` holds everything the analysis needs: 47 columns, 33 of which
are raw INS category labels in Romanian. A report should not carry that. This script
produces a narrower table, in English, holding exactly what the two report pages show.

The shortlist rule is the one designed in `notebooks/02_indicators.ipynb`:
a 1,000-inhabitant threshold, ranked by 65+ share, at most 2 localities per county,
top 10.

Output:
    data/processed/dashboard_dataset.csv   3,180 rows, one per locality

Usage:
    python src/build_dashboard_dataset.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

SOURCE = PROCESSED / "analysis_dataset.csv"
DEFAULT_OUTPUT = PROCESSED / "dashboard_dataset.csv"

# Prioritisation rule, as decided and documented in the README.
MIN_POPULATION = 1_000
MAX_PER_COUNTY = 2
SHORTLIST_SIZE = 10

# The only raw INS categories the report needs: the two that define the indicators,
# plus two that give context on a locality's care provision.
KEPT_CATEGORIES = {
    "Cabinete medicale de familie": "family_doctor_practices",
    "Farmacii": "pharmacies",
    "Puncte farmaceutice": "pharmacy_points",
    "Dispensare medicale": "medical_dispensaries",
}

ACCESS_GROUP_LABELS = {
    (False, False): "No doctor, no pharmacy",
    (False, True): "No doctor, has pharmacy",
    (True, False): "Has doctor, no pharmacy",
    (True, True): "Has doctor and pharmacy",
}

EXPECTED_LOCALITIES = 3_180
EXPECTED_SHORTLIST = 10
EXPECTED_WITHOUT_ACCESS = 169

log = logging.getLogger("build_dashboard_dataset")


class DataError(RuntimeError):
    """The data broke an assumption the pipeline relies on."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DataError(message)


def read(path: Path) -> pd.DataFrame:
    require(path.exists(), f"{path} is missing. Run build_dataset.py first.")
    df = pd.read_csv(path, dtype={"siruta_code": "str"})
    log.info("%s: %d rows, %d columns", path.name, len(df), len(df.columns))
    return df


def select_shortlist(df: pd.DataFrame) -> pd.Index:
    """Apply the prioritisation rule and return the index of the selected localities.

    Order of operations matters. `sort_values` rather than `nlargest`, because taking
    the top 10 first would discard the candidates needed to replace the ones the
    per-county cap removes. `groupby(...).head(n)` keeps the first n rows of each group
    *in the current order*, so the sort has to come first and the cut to ten has to
    come last.
    """
    candidates = df[
        (~df["has_family_doctor"])
        & (~df["has_pharmacy"])
        & (df["population_total"] >= MIN_POPULATION)
    ]
    ranked = candidates.sort_values("share_65plus", ascending=False)
    capped = ranked.groupby("county").head(MAX_PER_COUNTY)
    shortlist = capped.head(SHORTLIST_SIZE)

    require(
        len(shortlist) == EXPECTED_SHORTLIST,
        f"expected a shortlist of {EXPECTED_SHORTLIST}, got {len(shortlist)}",
    )
    per_county = shortlist["county"].value_counts()
    require(
        (per_county <= MAX_PER_COUNTY).all(),
        f"the per-county cap was not applied: {per_county[per_county > MAX_PER_COUNTY].to_dict()}",
    )
    return shortlist.index


def build_serving_table(df: pd.DataFrame) -> pd.DataFrame:
    """Narrow the analysis dataset down to what the report displays."""
    out = pd.DataFrame(
        {
            "county": df["county"],
            "locality": df["locality"],
            "siruta_code": df["siruta_code"],
            # Geocoding helpers. Bing cannot disambiguate a bare locality name — 239
            # of them repeat across counties — so the full string carries the county.
            "county_geo": df["county"] + ", Romania",
            "locality_geo": df["locality"] + ", " + df["county"] + ", Romania",
            "population_total": df["population_total"],
            "population_65plus": df["population_65plus"],
            "share_65plus": df["share_65plus"],
            "has_family_doctor": df["has_family_doctor"],
            "has_pharmacy": df["has_pharmacy"],
            "total_health_units": df["total_units"],
        }
    )

    for age_column in [c for c in df.columns if c.startswith("age_")]:
        out[age_column] = df[age_column]

    for source_name, target_name in KEPT_CATEGORIES.items():
        require(source_name in df.columns, f"missing expected category column: {source_name!r}")
        out[target_name] = df[source_name]

    # A single label per locality, so charts can colour or group by access situation
    # without rebuilding the 2x2 logic inside the report.
    out["access_group"] = [
        ACCESS_GROUP_LABELS[(doctor, pharmacy)]
        for doctor, pharmacy in zip(df["has_family_doctor"], df["has_pharmacy"])
    ]

    shortlist_index = select_shortlist(df)
    out["is_shortlisted"] = out.index.isin(shortlist_index)
    out["shortlist_rank"] = pd.Series(
        range(1, len(shortlist_index) + 1), index=shortlist_index
    ).reindex(out.index)

    return out


def validate(df: pd.DataFrame) -> None:
    require(
        len(df) == EXPECTED_LOCALITIES,
        f"expected {EXPECTED_LOCALITIES:,} localities, got {len(df):,}",
    )
    require(
        int(df["is_shortlisted"].sum()) == EXPECTED_SHORTLIST,
        f"expected {EXPECTED_SHORTLIST} shortlisted localities, got {int(df['is_shortlisted'].sum())}",
    )

    without_access = int((df["access_group"] == "No doctor, no pharmacy").sum())
    require(
        without_access == EXPECTED_WITHOUT_ACCESS,
        f"expected {EXPECTED_WITHOUT_ACCESS} localities without access, got {without_access}",
    )

    # Every shortlisted locality must come from the group with no access at all.
    wrong_group = df[df["is_shortlisted"] & (df["access_group"] != "No doctor, no pharmacy")]
    require(
        wrong_group.empty,
        f"{len(wrong_group)} shortlisted localities are not in the no-access group:\n"
        f"{wrong_group[['county', 'locality', 'access_group']].to_string()}",
    )

    # Ranks must be 1..10 with no gaps or repeats.
    ranks = sorted(df.loc[df["is_shortlisted"], "shortlist_rank"].astype(int))
    require(
        ranks == list(range(1, EXPECTED_SHORTLIST + 1)),
        f"shortlist ranks are not 1..{EXPECTED_SHORTLIST}: {ranks}",
    )

    log.info(
        "%d localities | %d shortlisted | %d without any access",
        len(df), int(df["is_shortlisted"].sum()), without_access,
    )


def write(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)

    reread = pd.read_csv(output, dtype={"siruta_code": "str"})
    require(len(reread) == len(df), f"wrote {len(df)} rows, read back {len(reread)}")
    log.info(
        "wrote %s (%d rows, %d columns, %.0f KB)",
        output, len(reread), len(reread.columns), output.stat().st_size / 1024,
    )


def build(output: Path | None = None) -> pd.DataFrame:
    df = read(SOURCE)
    serving = build_serving_table(df)
    validate(serving)
    if output is not None:
        write(serving, output)
    return serving


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), type=Path)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )
    try:
        build(args.output)
    except DataError as e:
        log.error("the data broke a pipeline assumption:\n%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
