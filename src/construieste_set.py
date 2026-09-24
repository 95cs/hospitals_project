"""Îmbină populația cu unitățile sanitare într-un singur set, gata de analiză.

Intrări:
    data/processed/populatie_localitati.csv   3.180 localități (sursa 1)
    data/processed/unitati_localitati.csv     3.040 localități (sursa 2)

Ieșire:
    data/processed/set_analiza.csv            3.180 localități

Cele 140 de localități fără nicio unitate sanitară **nu apar deloc** în sursa 2 —
TEMPO listează doar localitățile care au ceva. Ele sunt exact subiectul analizei,
deci join-ul trebuie să le păstreze și să le completeze cu zero.

Rulare:
    python src/construieste_set.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

RADACINA = Path(__file__).resolve().parent.parent
PROCESATE = RADACINA / "data" / "processed"

POPULATIE = PROCESATE / "populatie_localitati.csv"
UNITATI = PROCESATE / "unitati_localitati.csv"
IESIRE_IMPLICITA = PROCESATE / "set_analiza.csv"

CHEIE = "cod_siruta"

LOCALITATI_ASTEPTATE = 3_180
TOTAL_UNITATI_ASTEPTAT = 57_027
FARA_NICIO_UNITATE_ASTEPTAT = 140

log = logging.getLogger("construieste_set")


class EroareDeDate(RuntimeError):
    """Datele au încălcat o presupunere pe care se bazează pipeline-ul."""


def _cere(conditie: bool, mesaj: str) -> None:
    if not conditie:
        raise EroareDeDate(mesaj)


def citeste(cale: Path) -> pd.DataFrame:
    """Citește un CSV procesat, forțând tipul cheii de join.

    CSV-ul nu pastreaza tipurile. Fara `dtype`, `cod_siruta` ar fi citit ca int64
    intr-un fisier si tot asa in celalalt — dar daca vreunul ar avea un cod cu
    zerouri la inceput, tipurile ar diverge si join-ul nu ar potrivi nimic,
    intorcand un tabel plin de NaN fara nicio eroare.
    """
    _cere(cale.exists(), f"lipseste {cale}. Ruleaza intai scripturile de pregatire.")
    df = pd.read_csv(cale, dtype={CHEIE: "str"})
    log.info("%s: %d randuri, %d coloane", cale.name, len(df), len(df.columns))
    return df


def verifica_cheile(pop: pd.DataFrame, uni: pd.DataFrame) -> None:
    """Confirmă că cheia e utilizabilă înainte de join.

    Trei lucruri, fiecare corespunzand unui mod tacut de esec:
      1. tipurile coincid — altfel nu se potriveste niciun rand;
      2. cheia e unica de ambele parti — altfel join-ul multiplica randuri;
      3. unitatile sunt o submultime a populatiei — altfel un join la stanga
         ar arunca in tacere localitati care au unitati sanitare.
    """
    _cere(
        pop[CHEIE].dtype == uni[CHEIE].dtype,
        f"tipuri diferite pentru {CHEIE}: populatie={pop[CHEIE].dtype}, "
        f"unitati={uni[CHEIE].dtype}. Join-ul nu ar potrivi nimic.",
    )

    for nume, df in (("populatie", pop), ("unitati", uni)):
        dubluri = df[CHEIE].duplicated()
        _cere(
            not dubluri.any(),
            f"{dubluri.sum()} coduri duplicate in {nume}: "
            f"{df.loc[df[CHEIE].duplicated(keep=False), CHEIE].unique()[:10].tolist()}",
        )

    orfane = set(uni[CHEIE]) - set(pop[CHEIE])
    _cere(
        not orfane,
        f"{len(orfane)} localitati au unitati sanitare dar lipsesc din populatie: "
        f"{sorted(orfane)[:10]}. Un join la stanga le-ar pierde in tacere.",
    )


def imbina(pop: pd.DataFrame, uni: pd.DataFrame) -> pd.DataFrame:
    """Join la stânga: populația e tabelul conducător, unitățile se atașează.

    Directia conteaza. Un `inner join` ar pastra doar cele 3.040 de localitati
    care au unitati sanitare si ar sterge exact cele 140 fara nimic — adica
    raspunsul la intrebarea de business.
    """
    # 'Judete' si 'localitate' exista in ambele tabele; le pastram pe cele din
    # populatie, care e sursa de adevar pentru nomenclatorul de localitati.
    coloane_unitati = [c for c in uni.columns if c not in ("Judete", "localitate")]

    rezultat = pop.merge(uni[coloane_unitati], on=CHEIE, how="left", validate="one_to_one")

    _cere(
        len(rezultat) == len(pop),
        f"join-ul a schimbat numarul de randuri: {len(pop)} inainte, {len(rezultat)} dupa. "
        "Cheia nu e unica intr-una dintre parti.",
    )

    # Localitatile absente din sursa 2 au NaN pe toate coloanele de unitati.
    # Absenta inseamna zero, si asta trebuie scris explicit — altfel `sum()` le-ar
    # trata tacut ca zero oricum, dar `mean()` si comparatiile le-ar sari.
    coloane_noi = [c for c in coloane_unitati if c != CHEIE]
    fara_nimic = rezultat[coloane_noi].isna().all(axis=1).sum()
    rezultat[coloane_noi] = rezultat[coloane_noi].fillna(0).astype(int)

    log.info("%d localitati completate cu zero (nu apar in sursa 2)", fara_nimic)
    return rezultat


def valideaza(df: pd.DataFrame, total_unitati_sursa: int) -> None:
    """Verifică setul final."""
    _cere(
        len(df) == LOCALITATI_ASTEPTATE,
        f"asteptam {LOCALITATI_ASTEPTATE:,} localitati, am {len(df):,}",
    )

    lipsa = df.isna().sum()
    _cere(lipsa.sum() == 0, f"valori lipsa ramase:\n{lipsa[lipsa > 0].to_string()}")

    # Nicio unitate pierduta si niciuna inventata de join.
    _cere(
        df["total_unitati"].sum() == total_unitati_sursa == TOTAL_UNITATI_ASTEPTAT,
        f"total unitati: asteptam {TOTAL_UNITATI_ASTEPTAT:,}, "
        f"sursa are {total_unitati_sursa:,}, setul final are {df['total_unitati'].sum():,}",
    )

    fara = (df["total_unitati"] == 0).sum()
    _cere(
        fara == FARA_NICIO_UNITATE_ASTEPTAT,
        f"asteptam {FARA_NICIO_UNITATE_ASTEPTAT} localitati fara nicio unitate, am {fara}",
    )

    log.info("%d localitati validate, %d fara nicio unitate sanitara", len(df), fara)


def scrie(df: pd.DataFrame, iesire: Path) -> None:
    iesire.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(iesire, index=False)

    recitit = pd.read_csv(iesire, dtype={CHEIE: "str"})
    _cere(len(recitit) == len(df), f"am scris {len(df)} randuri, am recitit {len(recitit)}")
    _cere(
        recitit["total_unitati"].sum() == df["total_unitati"].sum(),
        "totalul unitatilor difera dupa export",
    )
    log.info("scris %s (%d randuri, %d coloane, %.0f KB)",
             iesire, len(recitit), len(recitit.columns), iesire.stat().st_size / 1024)


def construieste(iesire: Path | None = None) -> pd.DataFrame:
    pop = citeste(POPULATIE)
    uni = citeste(UNITATI)

    verifica_cheile(pop, uni)
    rezultat = imbina(pop, uni)
    valideaza(rezultat, int(uni["total_unitati"].sum()))

    if iesire is not None:
        scrie(rezultat, iesire)
    return rezultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iesire", default=str(IESIRE_IMPLICITA), type=Path)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    try:
        construieste(args.iesire)
    except EroareDeDate as e:
        log.error("datele nu respecta o presupunere a pipeline-ului:\n%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
