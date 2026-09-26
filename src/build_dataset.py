"""Join population with health units into a single analysis-ready dataset.

Inputs:
    data/processed/population_by_locality.csv    3,180 localities (source 1)
    data/processed/health_units_by_locality.csv  3,040 localities (source 2)

Output:
    data/processed/analysis_dataset.csv          3,180 localities

The 140 localities with no health unit at all **do not appear** in source 2 —
TEMPO only lists localities that have something. They are precisely the subject
of the analysis, so the join must keep them and fill them with zeros.

Usage:
    python src/build_dataset.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

POPULATION = PROCESSED / "population_by_locality.csv"
HEALTH_UNITS = PROCESSED / "health_units_by_locality.csv"
DEFAULT_OUTPUT = PROCESSED / "analysis_dataset.csv"

KEY = "siruta_code"

# Category columns keep their original INS labels, so every figure stays
# traceable to the TEMPO export it came from.
FAMILY_DOCTOR = "Cabinete medicale de familie"
PHARMACY = "Farmacii"
PHARMACY_POINT = "Puncte farmaceutice"

EXPECTED_LOCALITIES = 3_180
EXPECTED_TOTAL_UNITS = 57_027
EXPECTED_WITHOUT_ANY_UNIT = 140
EXPECTED_WITH_FAMILY_DOCTOR = 2_821
EXPECTED_WITH_PHARMACY = 2_553
EXPECTED_WITH_NEITHER = 169

log = logging.getLogger("build_dataset")


class DataError(RuntimeError):
    """The data broke an assumption the pipeline relies on."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DataError(message)


def read(path: Path) -> pd.DataFrame:
    """Read a processed CSV, forcing the type of the join key.

    CSV does not preserve dtypes. Without `dtype`, siruta_code would be read as
    int64 in one file and the same in the other — but if either ever carried a
    leading zero the types would diverge and the join would match nothing,
    returning a frame full of NaN without raising.
    """
    require(path.exists(), f"{path} is missing. Run the preparation scripts first.")
    df = pd.read_csv(path, dtype={KEY: "str"})
    log.info("%s: %d rows, %d columns", path.name, len(df), len(df.columns))
    return df


def check_keys(population: pd.DataFrame, units: pd.DataFrame) -> None:
    """Confirm the key is usable before joining.

    Three checks, each matching one silent failure mode:
      1. the types agree — otherwise no row matches at all;
      2. the key is unique on both sides — otherwise the join multiplies rows;
      3. health units are a subset of population — otherwise a left join would
         silently discard localities that do have health units.
    """
    require(
        population[KEY].dtype == units[KEY].dtype,
        f"mismatched types for {KEY}: population={population[KEY].dtype}, "
        f"units={units[KEY].dtype}. The join would match nothing.",
    )

    for name, df in (("population", population), ("units", units)):
        duplicated = df[KEY].duplicated()
        require(
            not duplicated.any(),
            f"{duplicated.sum()} duplicate codes in {name}: "
            f"{df.loc[df[KEY].duplicated(keep=False), KEY].unique()[:10].tolist()}",
        )

    orphans = set(units[KEY]) - set(population[KEY])
    require(
        not orphans,
        f"{len(orphans)} localities have health units but are absent from population: "
        f"{sorted(orphans)[:10]}. A left join would lose them silently.",
    )


def join(population: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    """Left join: population leads, health units attach to it.

    The direction matters. An inner join would keep only the 3,040 localities
    that have health units and drop exactly the 140 that have none — which is
    the answer to the business question.
    """
    # 'county' and 'locality' exist on both sides; keep the population copies,
    # which are the source of truth for the locality nomenclature.
    unit_columns = [c for c in units.columns if c not in ("county", "locality")]

    result = population.merge(
        units[unit_columns], on=KEY, how="left", validate="one_to_one"
    )

    require(
        len(result) == len(population),
        f"the join changed the row count: {len(population)} before, {len(result)} after. "
        "The key is not unique on one of the sides.",
    )

    # Localities absent from source 2 carry NaN across every unit column.
    # Absence means zero, and saying so explicitly matters: sum() would treat it
    # as zero anyway, but mean() and comparisons would skip it.
    new_columns = [c for c in unit_columns if c != KEY]
    filled = result[new_columns].isna().all(axis=1).sum()
    result[new_columns] = result[new_columns].fillna(0).astype(int)

    log.info("%d localities filled with zeros (absent from source 2)", filled)
    return result


def add_access_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add the two access indicators, on two axes: care and medication.

    `has_family_doctor` — at least one family-medicine practice in the locality.

    `has_pharmacy` — at least one pharmacy **or** one pharmacy point. The
    pharmacy point is the reduced form permitted precisely in localities too
    small to sustain a full pharmacy; 516 localities have one without having a
    pharmacy, and excluding them would declare those localities cut off from
    medication when residents do have somewhere to fill a prescription. The
    caveat: a pharmacy point holds less stock and keeps shorter hours, so
    "has access" does not mean equal access.
    """
    df = df.copy()
    df["has_family_doctor"] = df[FAMILY_DOCTOR] > 0
    df["has_pharmacy"] = (df[PHARMACY] > 0) | (df[PHARMACY_POINT] > 0)
    return df


def validate(df: pd.DataFrame, source_total_units: int) -> None:
    """Check the final dataset."""
    require(
        len(df) == EXPECTED_LOCALITIES,
        f"expected {EXPECTED_LOCALITIES:,} localities, got {len(df):,}",
    )

    missing = df.isna().sum()
    require(missing.sum() == 0, f"missing values remaining:\n{missing[missing > 0].to_string()}")

    # No unit lost and none invented by the join.
    require(
        df["total_units"].sum() == source_total_units == EXPECTED_TOTAL_UNITS,
        f"total units: expected {EXPECTED_TOTAL_UNITS:,}, "
        f"source holds {source_total_units:,}, final dataset holds {df['total_units'].sum():,}",
    )

    without_any = (df["total_units"] == 0).sum()
    require(
        without_any == EXPECTED_WITHOUT_ANY_UNIT,
        f"expected {EXPECTED_WITHOUT_ANY_UNIT} localities with no unit at all, got {without_any}",
    )

    with_doctor = int(df["has_family_doctor"].sum())
    require(
        with_doctor == EXPECTED_WITH_FAMILY_DOCTOR,
        f"expected {EXPECTED_WITH_FAMILY_DOCTOR:,} localities with a family doctor, got {with_doctor:,}",
    )

    with_pharmacy = int(df["has_pharmacy"].sum())
    require(
        with_pharmacy == EXPECTED_WITH_PHARMACY,
        f"expected {EXPECTED_WITH_PHARMACY:,} localities with a pharmacy, got {with_pharmacy:,}",
    )

    with_neither = int((~df["has_family_doctor"] & ~df["has_pharmacy"]).sum())
    require(
        with_neither == EXPECTED_WITH_NEITHER,
        f"expected {EXPECTED_WITH_NEITHER} localities with neither a doctor nor a pharmacy, "
        f"got {with_neither}",
    )

    log.info(
        "%d localities validated | %d without any unit | %d without a doctor and without a pharmacy",
        len(df), without_any, with_neither,
    )


def write(df: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)

    reread = pd.read_csv(output, dtype={KEY: "str"})
    require(len(reread) == len(df), f"wrote {len(df)} rows, read back {len(reread)}")
    require(
        reread["total_units"].sum() == df["total_units"].sum(),
        "the unit total differs after export",
    )
    log.info(
        "wrote %s (%d rows, %d columns, %.0f KB)",
        output, len(reread), len(reread.columns), output.stat().st_size / 1024,
    )


def build(output: Path | None = None) -> pd.DataFrame:
    population = read(POPULATION)
    units = read(HEALTH_UNITS)

    check_keys(population, units)
    result = join(population, units)
    result = add_access_indicators(result)
    validate(result, int(units["total_units"].sum()))

    if output is not None:
        write(result, output)
    return result


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
