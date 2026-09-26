"""Prepare population-by-age-group data (INS TEMPO, matrix POP107D).

Reads the raw CSV exports, one per county, and produces one row per locality:
total population, population by age group, the 65+ population and its share.

Usage:
    python src/prep_population.py
    python src/prep_population.py --input "data/*.csv" --output /tmp/out.csv
"""

from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

# Project root, derived from this file's location rather than the working
# directory, so the script behaves the same wherever it is launched from.
ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = ROOT / "data" / "raw" / "population" / "*.csv"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "population_by_locality.csv"

# Source column names, exactly as INS TEMPO exports them.
SRC_AGE_GROUP = "Varste si grupe de varsta"
SRC_COUNTY = "Judete"
SRC_LOCALITY = "Localitati"
SRC_VALUE = "Valoare"
SRC_YEAR = "Ani"

# Age-group labels are INS values that become columns after the pivot; they are
# renamed to stable English identifiers because the pipeline owns them downstream.
AGE_GROUP_COLUMNS = {
    "65-69 ani": "age_65_69",
    "70-74 ani": "age_70_74",
    "75-79 ani": "age_75_79",
    "80-84 ani": "age_80_84",
    "85 ani si peste": "age_85_plus",
    "Total": "population_total",
}
AGE_GROUPS_65_PLUS = [
    "age_65_69",
    "age_70_74",
    "age_75_79",
    "age_80_84",
    "age_85_plus",
]

BUCHAREST_SIRUTA = "179132"

# Reference values, computed independently with awk straight from the raw CSVs.
# Declared once, so an error message cannot contradict its own condition.
EXPECTED_LOCALITIES = 3181
EXPECTED_TOTAL_65_PLUS = 4_076_589
EXPECTED_TOTAL_POPULATION = 21_646_220

log = logging.getLogger("prep_population")


class DataError(RuntimeError):
    """The data broke an assumption the pipeline relies on.

    Distinct from ordinary exceptions: it does not signal a bug in the code, but
    that the source changed or holds something other than what we expected.
    """


def require(condition: bool, message: str) -> None:
    """Raise `DataError` when an assumption does not hold.

    `raise` rather than `assert`: `python -O` strips assert statements entirely,
    which would remove every check exactly where it matters most — in production.
    """
    if not condition:
        raise DataError(message)


def read(pattern: str) -> pd.DataFrame:
    """Read every CSV matching the pattern and concatenate them."""
    paths = sorted(glob.glob(pattern))
    require(
        bool(paths),
        f"no files matched the pattern {pattern!r} (working directory: {Path.cwd()})",
    )

    log.info("reading %d files", len(paths))
    # skipinitialspace: the TEMPO export puts a space after every comma.
    frames = [pd.read_csv(path, skipinitialspace=True) for path in paths]
    df = pd.concat(frames, ignore_index=True)

    df.columns = df.columns.str.strip()  # 'Localitati ' -> 'Localitati'
    return df


def split_siruta(df: pd.DataFrame) -> pd.DataFrame:
    """Split `'1017 MUNICIPIUL ALBA IULIA'` into a SIRUTA code and a name.

    A single cut, at the first space, so compound names stay intact. The code is
    kept as text: it is an identifier, not a quantity.
    """
    df = df.copy()
    df[["siruta_code", "locality"]] = df[SRC_LOCALITY].str.split(" ", n=1, expand=True)

    malformed = df["siruta_code"].isna() | ~df["siruta_code"].str.fullmatch(r"\d+")
    require(
        not malformed.any(),
        f"{malformed.sum()} rows do not match the '<code> <name>' pattern:\n"
        f"{df.loc[malformed, SRC_LOCALITY].head(10).to_string()}",
    )
    return df


def pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape from long (one row per locality x age group) to wide.

    `pivot` rather than `pivot_table`: the latter silently aggregates duplicates
    (mean, by default). `pivot` raises `ValueError` instead, which validates for
    free that every locality appears exactly once per age group.
    """
    wide = df.pivot(
        index=[SRC_COUNTY, "siruta_code", "locality"],
        columns=SRC_AGE_GROUP,
        values=SRC_VALUE,
    ).reset_index()
    wide.columns.name = None  # drop the stray label left on the column axis

    missing = [c for c in AGE_GROUP_COLUMNS if c not in wide.columns]
    require(not missing, f"missing age-group columns: {missing}")

    return wide.rename(columns={SRC_COUNTY: "county", **AGE_GROUP_COLUMNS})


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add `population_65plus` (sum of the five groups) and `share_65plus` (0-1)."""
    df = df.copy()

    # axis=1: sum across the row, one value per locality. 'population_total' is
    # deliberately excluded — it is the denominator, not one of the parts.
    df["population_65plus"] = df[AGE_GROUPS_65_PLUS].sum(axis=1)

    # Division by zero would silently produce inf rather than an error.
    zero = df["population_total"] == 0
    require(
        not zero.any(),
        f"{zero.sum()} localities have population_total = 0; the division would yield inf:\n"
        f"{df.loc[zero, ['locality', 'population_total']].head(10).to_string()}",
    )
    # Kept as a 0-1 ratio: percent formatting belongs to the presentation layer.
    df["share_65plus"] = df["population_65plus"] / df["population_total"]
    return df


def validate(df: pd.DataFrame) -> None:
    """Check the complete set, before any exclusion."""
    require(
        len(df) == EXPECTED_LOCALITIES,
        f"expected {EXPECTED_LOCALITIES} localities, got {len(df)}",
    )

    # The join key for every downstream source. If it breaks, joins multiply rows
    # silently instead of failing.
    duplicated = df["siruta_code"].duplicated()
    require(
        not duplicated.any(),
        f"{duplicated.sum()} duplicate SIRUTA codes: "
        f"{df.loc[df['siruta_code'].duplicated(keep=False), 'siruta_code'].unique()[:10].tolist()}",
    )

    # sum(axis=1) treats NaN as zero, so missing values would have gone unnoticed.
    missing = df.isna().sum()
    require(missing.sum() == 0, f"missing values by column:\n{missing[missing > 0].to_string()}")

    over = ~df["population_65plus"].between(0, df["population_total"])
    require(
        not over.any(),
        f"{over.sum()} localities where population_65plus falls outside [0, population_total]:\n"
        f"{df.loc[over, ['locality', 'population_65plus', 'population_total']].head(10).to_string()}",
    )

    outside = ~df["share_65plus"].between(0, 1)
    require(
        not outside.any(),
        f"{outside.sum()} localities where share_65plus falls outside [0, 1]:\n"
        f"{df.loc[outside, ['locality', 'population_total', 'share_65plus']].head(10).to_string()}",
    )

    # Cross-check against the independent awk implementation: the only checks that
    # validate content rather than shape.
    require(
        df["population_65plus"].sum() == EXPECTED_TOTAL_65_PLUS,
        f"total 65+: expected {EXPECTED_TOTAL_65_PLUS:,}, got {df['population_65plus'].sum():,}",
    )
    require(
        df["population_total"].sum() == EXPECTED_TOTAL_POPULATION,
        f"total population: expected {EXPECTED_TOTAL_POPULATION:,}, "
        f"got {df['population_total'].sum():,}",
    )

    log.info("%d localities validated, 8 checks passed", len(df))


def exclude_bucharest(df: pd.DataFrame) -> pd.DataFrame:
    """Drop Bucharest from locality-level analysis.

    The reason is technical, not thematic: it arrives aggregated, 2.1 million
    people in a single row with no breakdown by sector, which makes it
    incomparable with the remaining 3,180 territorial units.
    """
    result = df[df["siruta_code"] != BUCHAREST_SIRUTA].copy()

    # A filter that fails to filter raises nothing — if the column's type changed
    # from text to number, for instance, the comparison would always be true.
    removed = len(df) - len(result)
    require(
        removed == 1,
        f"the filter should have removed exactly 1 row (Bucharest), it removed {removed}; "
        f"the siruta_code column has type {df['siruta_code'].dtype}",
    )
    return result.reset_index(drop=True)


def write(df: pd.DataFrame, output: Path) -> None:
    """Write the CSV and round-trip it to confirm it reads back identically."""
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)

    # CSV does not preserve dtypes: siruta_code would come back as int64 and break
    # downstream joins without raising. Hence the explicit dtype on read.
    reread = pd.read_csv(output, dtype={"siruta_code": "str"})
    require(len(reread) == len(df), f"wrote {len(df)} rows, read back {len(reread)}")
    require(
        reread["population_total"].sum() == df["population_total"].sum(),
        "total population differs after export — likely a formatting problem",
    )
    log.info("wrote %s (%d rows, %.0f KB)", output, len(reread), output.stat().st_size / 1024)


def prepare(pattern: str, output: Path | None = None) -> pd.DataFrame:
    """The full chain: read -> split -> pivot -> indicators -> validate -> exclude."""
    df = read(pattern)
    df = split_siruta(df)
    wide = pivot(df)
    wide = add_indicators(wide)

    validate(wide)                      # on the complete set, before any exclusion
    working = exclude_bucharest(wide)

    if output is not None:
        write(working, output)
    return working


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="glob pattern for the raw CSVs")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), type=Path, help="resulting CSV file")
    parser.add_argument("--verbose", "-v", action="store_true", help="also show debug messages")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    try:
        prepare(args.input, args.output)
    except DataError as e:
        log.error("the data broke a pipeline assumption:\n%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
