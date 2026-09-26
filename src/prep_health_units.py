"""Prepare health-unit data (INS TEMPO, matrix SAN101B, year 2024).

Reads the raw CSV exports, one per county, and produces one row per locality
with one column per category of health unit.

The script stays faithful to its source: it contains **only** the localities that
have at least one unit. Expanding to all 3,180 localities happens in the join
step, where absence becomes an explicit, verifiable zero.

Usage:
    python src/prep_health_units.py
"""

from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = ROOT / "data" / "raw" / "health_units" / "san_*.csv"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "health_units_by_locality.csv"

# Source column names, exactly as INS TEMPO exports them.
SRC_CATEGORY = "Categorii de unitati sanitare"
SRC_COUNTY = "Judete"
SRC_LOCALITY = "Localitati"
SRC_VALUE = "Valoare"
SRC_YEAR = "Ani"

EXPECTED_YEAR = "Anul 2024"

# Reference values, computed independently with awk on the raw CSVs, after the
# aggregate rows are removed.
EXPECTED_ROWS = 17_138
EXPECTED_POSITIVE_ROWS = 11_347
EXPECTED_TOTAL_UNITS = 57_027
EXPECTED_LOCALITIES = 3_040
EXPECTED_CATEGORIES = 33

log = logging.getLogger("prep_health_units")


class DataError(RuntimeError):
    """The data broke an assumption the pipeline relies on."""


def require(condition: bool, message: str) -> None:
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
    df = pd.concat(
        [pd.read_csv(p, skipinitialspace=True) for p in paths], ignore_index=True
    )
    df.columns = df.columns.str.strip()
    log.info("%d raw rows", len(df))

    years = sorted(df[SRC_YEAR].unique())
    require(
        years == [EXPECTED_YEAR],
        f"expected only {EXPECTED_YEAR!r}, found {years}. "
        "An export covering several years would double-count units at the pivot.",
    )
    return df


def drop_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove rows where `Localitati` is `TOTAL` — per-county aggregates.

    If `TOTAL` stays selected under LOCALITATI in the TEMPO interface, the export
    carries a county-total row alongside the per-locality rows. Verified: the
    TOTAL row equals the sum over localities exactly, so it would double-count.

    In the September 2026 download only Constanta carried such rows: 41 rows and
    2,694 units, a 4.7% inflation of the national total.

    The filter is defensive rather than a one-off correction — the same mistake
    can recur on any re-export. That is also why the amount removed is logged.
    """
    aggregates = df[SRC_LOCALITY].str.strip().eq("TOTAL")

    if aggregates.any():
        counties = sorted(df.loc[aggregates, SRC_COUNTY].str.strip().unique())
        log.warning(
            "dropping %d aggregate rows (Localitati = TOTAL), %d units, counties: %s",
            aggregates.sum(),
            int(df.loc[aggregates, SRC_VALUE].sum()),
            ", ".join(counties),
        )

    df = df.loc[~aggregates].copy()
    require(
        len(df) == EXPECTED_ROWS,
        f"expected {EXPECTED_ROWS:,} rows after dropping aggregates, got {len(df):,}",
    )
    return df


def split_siruta(df: pd.DataFrame) -> pd.DataFrame:
    """Split the SIRUTA code from the name — identical to the population pipeline."""
    df = df.copy()
    df[["siruta_code", "locality"]] = df[SRC_LOCALITY].str.split(" ", n=1, expand=True)

    malformed = df["siruta_code"].isna() | ~df["siruta_code"].str.fullmatch(r"\d+")
    require(
        not malformed.any(),
        f"{malformed.sum()} rows do not match the '<code> <name>' pattern:\n"
        f"{df.loc[malformed, SRC_LOCALITY].head(10).to_string()}",
    )
    return df


def keep_positive_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows whose value is 0.

    TEMPO exports zeros inconsistently from county to county: Alba has 2% zero
    rows, Prahova 49%, Bacau 91%. Bacau ends up with four times as many rows as
    Prahova and fewer health units.

    So a row count means nothing. A missing row and a row holding 0 say the same
    thing: the locality does not have that category of unit.
    """
    require(
        (df[SRC_VALUE] >= 0).all(),
        f"{(df[SRC_VALUE] < 0).sum()} rows hold negative values",
    )

    positive = df[df[SRC_VALUE] > 0].copy()
    log.info(
        "keeping %d rows with a positive value out of %d (%d zeros dropped)",
        len(positive),
        len(df),
        len(df) - len(positive),
    )
    require(
        len(positive) == EXPECTED_POSITIVE_ROWS,
        f"expected {EXPECTED_POSITIVE_ROWS:,} positive rows, got {len(positive):,}",
    )
    return positive


def pivot(df: pd.DataFrame) -> pd.DataFrame:
    """One row per locality, one column per category of health unit.

    This uses `pivot_table` with `aggfunc="sum"`, unlike the population pipeline
    which uses `pivot`. The reason is the mirror image: there, two rows for the
    same combination would have meant corrupted data, so failing was the point.
    Here every locality has up to three rows per category — public, mixed,
    private — and they are meant to be added up. The aggregation is intentional
    and documented rather than accidental.

    Category labels are kept verbatim from INS, so any figure can be traced back
    to the TEMPO export it came from.
    """
    total_before = df[SRC_VALUE].sum()

    wide = df.pivot_table(
        index=[SRC_COUNTY, "siruta_code", "locality"],
        columns=SRC_CATEGORY,
        values=SRC_VALUE,
        aggfunc="sum",
        fill_value=0,          # a category absent for a locality means zero units
    ).reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={SRC_COUNTY: "county"})

    # Safety net for pivot_table: no unit was lost and none was invented.
    category_columns = [c for c in wide.columns if c not in ("county", "siruta_code", "locality")]
    total_after = wide[category_columns].to_numpy().sum()
    require(
        total_after == total_before,
        f"the pivot changed the total: {total_before:,} before, {total_after:,} after",
    )

    wide["total_units"] = wide[category_columns].sum(axis=1)
    return wide


def validate(df: pd.DataFrame) -> None:
    """Check the result against the figures computed independently with awk."""
    require(
        len(df) == EXPECTED_LOCALITIES,
        f"expected {EXPECTED_LOCALITIES:,} localities with at least one unit, got {len(df):,}",
    )

    duplicated = df["siruta_code"].duplicated()
    require(
        not duplicated.any(),
        f"{duplicated.sum()} duplicate SIRUTA codes: "
        f"{df.loc[df['siruta_code'].duplicated(keep=False), 'siruta_code'].unique()[:10].tolist()}",
    )

    categories = [
        c for c in df.columns
        if c not in ("county", "siruta_code", "locality", "total_units")
    ]
    require(
        len(categories) == EXPECTED_CATEGORIES,
        f"expected {EXPECTED_CATEGORIES} categories, got {len(categories)}: {sorted(categories)}",
    )

    require(
        df["total_units"].sum() == EXPECTED_TOTAL_UNITS,
        f"total units: expected {EXPECTED_TOTAL_UNITS:,}, got {df['total_units'].sum():,}",
    )

    # After dropping the zeros, every remaining locality must hold something.
    empty = df["total_units"] == 0
    require(
        not empty.any(),
        f"{empty.sum()} localities reached the result with zero units:\n"
        f"{df.loc[empty, ['locality', 'total_units']].head(10).to_string()}",
    )

    log.info("%d localities validated, 5 checks passed", len(df))


def write(df: pd.DataFrame, output: Path) -> None:
    """Write the CSV and round-trip it to confirm it reads back identically."""
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)

    reread = pd.read_csv(output, dtype={"siruta_code": "str"})
    require(len(reread) == len(df), f"wrote {len(df)} rows, read back {len(reread)}")
    require(
        reread["total_units"].sum() == df["total_units"].sum(),
        "the unit total differs after export",
    )
    log.info("wrote %s (%d rows, %.0f KB)", output, len(reread), output.stat().st_size / 1024)


def prepare(pattern: str, output: Path | None = None) -> pd.DataFrame:
    """The full chain: read -> aggregates -> SIRUTA -> zeros -> pivot -> validate."""
    df = read(pattern)
    df = drop_aggregates(df)
    df = split_siruta(df)
    df = keep_positive_only(df)
    wide = pivot(df)
    validate(wide)

    if output is not None:
        write(wide, output)
    return wide


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), type=Path)
    parser.add_argument("--verbose", "-v", action="store_true")
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
