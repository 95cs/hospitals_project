"""Pregătește datele de populație pe grupe de vârstă (INS TEMPO, matricea POP107D).

Citește exporturile CSV brute, câte unul per județ, și produce un tabel cu o linie
per localitate: populația totală, pe grupe de vârstă, populația de 65+ și ponderea ei.

Rulare:
    python src/prep_populatie.py
    python src/prep_populatie.py --intrare "date/*.csv" --iesire /tmp/out.csv
"""

from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

# Rădăcina proiectului, dedusă din locul fișierului — nu din directorul curent.
# Astfel scriptul merge la fel indiferent de unde e lansat.
RADACINA = Path(__file__).resolve().parent.parent

INTRARE_IMPLICITA = RADACINA / "data" / "raw" / "populatie" / "*.csv"
IESIRE_IMPLICITA = RADACINA / "data" / "processed" / "populatie_localitati.csv"

GRUPE_65PLUS = [
    "65-69 ani",
    "70-74 ani",
    "75-79 ani",
    "80-84 ani",
    "85 ani si peste",
]

COD_BUCURESTI = "179132"

# Valori de referință, calculate independent (cu awk, direct pe CSV-urile brute).
# Definite o singură dată: mesajele de eroare nu pot contrazice condițiile.
LOCALITATI_ASTEPTATE = 3181
TOTAL_65PLUS_ASTEPTAT = 4_076_589
TOTAL_POPULATIE_ASTEPTAT = 21_646_220

log = logging.getLogger("prep_populatie")


class EroareDeDate(RuntimeError):
    """Datele au încălcat o presupunere pe care se bazează pipeline-ul.

    Distinctă de erorile obișnuite: nu semnalează un bug în cod, ci faptul că
    sursa s-a schimbat sau conține altceva decât ne așteptam.
    """


def _cere(conditie: bool, mesaj: str) -> None:
    """Ridică `EroareDeDate` dacă presupunerea nu se confirmă.

    Se folosește `raise`, nu `assert`: `python -O` elimină complet instrucțiunile
    `assert`, adică exact în producție verificările ar dispărea.
    """
    if not conditie:
        raise EroareDeDate(mesaj)


def citeste(tipar: str) -> pd.DataFrame:
    """Citește toate CSV-urile care se potrivesc cu tiparul și le concatenează."""
    cai = sorted(glob.glob(tipar))
    _cere(
        bool(cai),
        f"niciun fisier gasit pentru tiparul {tipar!r} (director curent: {Path.cwd()})",
    )

    log.info("citesc %d fisiere", len(cai))
    # skipinitialspace: exportul TEMPO pune un spatiu dupa fiecare virgula
    bucati = [pd.read_csv(cale, skipinitialspace=True) for cale in cai]
    df = pd.concat(bucati, ignore_index=True)

    df.columns = df.columns.str.strip()  # 'Localitati ' -> 'Localitati'
    return df


def separa_siruta(df: pd.DataFrame) -> pd.DataFrame:
    """Desparte `'1017 MUNICIPIUL ALBA IULIA'` în cod SIRUTA și denumire.

    O singură tăietură, la primul spațiu, ca numele compuse să rămână intacte.
    Codul rămâne text: e un identificator, nu o cantitate.
    """
    df = df.copy()
    df[["cod_siruta", "localitate"]] = df["Localitati"].str.split(" ", n=1, expand=True)

    fara_cod = df["cod_siruta"].isna() | ~df["cod_siruta"].str.fullmatch(r"\d+")
    _cere(
        not fara_cod.any(),
        f"{fara_cod.sum()} randuri nu respecta tiparul '<cod> <nume>':\n"
        f"{df.loc[fara_cod, 'Localitati'].head(10).to_string()}",
    )
    return df


def pivoteaza(df: pd.DataFrame) -> pd.DataFrame:
    """Din format lung (o linie per localitate × grupă) în lat (o linie per localitate).

    Se folosește `pivot`, nu `pivot_table`: al doilea agregează în tăcere eventualele
    duplicate (implicit: media). `pivot` ridică `ValueError`, ceea ce validează gratuit
    că fiecare localitate apare exact o dată pe grupă de vârstă.
    """
    lat = df.pivot(
        index=["Judete", "cod_siruta", "localitate"],
        columns="Varste si grupe de varsta",
        values="Valoare",
    ).reset_index()
    lat.columns.name = None  # scapa de eticheta stingera de pe axa coloanelor
    return lat


def adauga_indicatori(df: pd.DataFrame) -> pd.DataFrame:
    """Adaugă `populatie_65plus` (suma celor 5 grupe) și `pondere_65plus` (raport 0–1)."""
    df = df.copy()

    lipsa = [c for c in GRUPE_65PLUS if c not in df.columns]
    _cere(not lipsa, f"lipsesc coloanele de grupa de varsta: {lipsa}")

    # axis=1: suma pe orizontala, cate una per localitate. 'Total' NU intra in suma.
    df["populatie_65plus"] = df[GRUPE_65PLUS].sum(axis=1)

    # Impartirea la zero ar produce inf in tacere, nu o eroare.
    zero = df["Total"] == 0
    _cere(
        not zero.any(),
        f"{zero.sum()} localitati au Total = 0, impartirea ar produce inf:\n"
        f"{df.loc[zero, ['localitate', 'Total']].head(10).to_string()}",
    )
    # Ponderea ramane raport 0–1: formatarea ca procent apartine stratului de prezentare.
    df["pondere_65plus"] = df["populatie_65plus"] / df["Total"]
    return df


def valideaza(df: pd.DataFrame) -> None:
    """Verifică setul complet, înainte de orice excludere."""
    _cere(
        len(df) == LOCALITATI_ASTEPTATE,
        f"asteptam {LOCALITATI_ASTEPTATE} localitati, am {len(df)}",
    )

    # Cheia de join cu sursele urmatoare. Daca se strica, join-ul multiplica
    # randuri in tacere in loc sa crape.
    dubluri = df["cod_siruta"].duplicated()
    _cere(
        not dubluri.any(),
        f"{dubluri.sum()} coduri SIRUTA duplicate: "
        f"{df.loc[df['cod_siruta'].duplicated(keep=False), 'cod_siruta'].unique()[:10].tolist()}",
    )

    # sum(axis=1) trateaza NaN ca zero, deci lipsurile ar fi trecut neobservate.
    lipsa = df.isna().sum()
    _cere(lipsa.sum() == 0, f"valori lipsa pe coloane:\n{lipsa[lipsa > 0].to_string()}")

    peste = ~df["populatie_65plus"].between(0, df["Total"])
    _cere(
        not peste.any(),
        f"{peste.sum()} localitati cu populatie_65plus in afara [0, Total]:\n"
        f"{df.loc[peste, ['localitate', 'populatie_65plus', 'Total']].head(10).to_string()}",
    )

    afara = ~df["pondere_65plus"].between(0, 1)
    _cere(
        not afara.any(),
        f"{afara.sum()} localitati cu pondere_65plus in afara [0, 1]:\n"
        f"{df.loc[afara, ['localitate', 'Total', 'pondere_65plus']].head(10).to_string()}",
    )

    # Verificare incrucisata cu implementarea independenta in awk.
    # Singura care valideaza continutul, nu forma.
    _cere(
        df["populatie_65plus"].sum() == TOTAL_65PLUS_ASTEPTAT,
        f"total 65+: asteptam {TOTAL_65PLUS_ASTEPTAT:,}, am {df['populatie_65plus'].sum():,}",
    )
    _cere(
        df["Total"].sum() == TOTAL_POPULATIE_ASTEPTAT,
        f"populatie totala: asteptam {TOTAL_POPULATIE_ASTEPTAT:,}, am {df['Total'].sum():,}",
    )

    log.info("%d localitati validate, 8 verificari trecute", len(df))


def exclude_bucuresti(df: pd.DataFrame) -> pd.DataFrame:
    """Scoate Municipiul București din analizele la nivel de localitate.

    Motivul e tehnic, nu tematic: vine agregat, 2,1 milioane de locuitori într-un
    singur rând, fără defalcare pe sectoare, incomparabil cu restul UAT-urilor.
    """
    rezultat = df[df["cod_siruta"] != COD_BUCURESTI].copy()

    # Un filtru care nu filtreaza nu da eroare — de exemplu daca tipul coloanei
    # s-ar schimba din text in numar, comparatia ar fi mereu adevarata.
    eliminate = len(df) - len(rezultat)
    _cere(
        eliminate == 1,
        f"filtrul trebuia sa elimine exact 1 rand (Bucuresti), a eliminat {eliminate}; "
        f"tipul coloanei cod_siruta este {df['cod_siruta'].dtype}",
    )
    return rezultat.reset_index(drop=True)


def scrie(df: pd.DataFrame, iesire: Path) -> None:
    """Scrie CSV-ul și verifică dus-întors că se recitește identic."""
    iesire.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(iesire, index=False)

    # CSV-ul nu pastreaza tipurile: cod_siruta ar fi recitit ca int64 si ar rupe
    # join-ul cu sursele urmatoare, fara sa dea eroare. De aceea se forteaza la citire.
    recitit = pd.read_csv(iesire, dtype={"cod_siruta": "str"})
    _cere(
        len(recitit) == len(df),
        f"am scris {len(df)} randuri, am recitit {len(recitit)}",
    )
    _cere(
        recitit["Total"].sum() == df["Total"].sum(),
        "totalul populatiei difera dupa export — probabil o problema de format",
    )
    log.info("scris %s (%d randuri, %.0f KB)", iesire, len(recitit), iesire.stat().st_size / 1024)


def prepara(tipar: str, iesire: Path | None = None) -> pd.DataFrame:
    """Lanțul complet: citire → curățare → pivotare → indicatori → validare → excludere."""
    df = citeste(tipar)
    df = separa_siruta(df)
    lat = pivoteaza(df)
    lat = adauga_indicatori(lat)

    valideaza(lat)                      # pe setul complet, inainte de excluderi
    lucru = exclude_bucuresti(lat)

    if iesire is not None:
        scrie(lucru, iesire)
    return lucru


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--intrare", default=str(INTRARE_IMPLICITA), help="tipar glob pentru CSV-urile brute")
    parser.add_argument("--iesire", default=str(IESIRE_IMPLICITA), type=Path, help="fisierul CSV rezultat")
    parser.add_argument("--verbose", "-v", action="store_true", help="afiseaza si mesajele de debug")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    try:
        prepara(args.intrare, args.iesire)
    except EroareDeDate as e:
        log.error("datele nu respecta o presupunere a pipeline-ului:\n%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
