"""Pregătește datele despre unități sanitare (INS TEMPO, matricea SAN101B, anul 2024).

Citește exporturile CSV brute, câte unul per județ, și produce un tabel cu o linie
per localitate și câte o coloană per categorie de unitate sanitară.

Scriptul rămâne fidel sursei: conține **doar** localitățile care au cel puțin o
unitate. Extinderea la toate cele 3.180 de localități se face la pasul de join,
unde absența devine zero în mod explicit și verificabil.

Rulare:
    python src/prep_unitati.py
"""

from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

RADACINA = Path(__file__).resolve().parent.parent

INTRARE_IMPLICITA = RADACINA / "data" / "raw" / "unitati_sanitare" / "san_*.csv"
IESIRE_IMPLICITA = RADACINA / "data" / "processed" / "unitati_localitati.csv"

ANUL_ASTEPTAT = "Anul 2024"

# Valori de referință, calculate independent cu awk pe CSV-urile brute,
# după eliminarea rândurilor agregate.
RANDURI_ASTEPTATE = 17_138
RANDURI_POZITIVE_ASTEPTATE = 11_347
TOTAL_UNITATI_ASTEPTAT = 57_027
LOCALITATI_ASTEPTATE = 3_040
CATEGORII_ASTEPTATE = 33

log = logging.getLogger("prep_unitati")


class EroareDeDate(RuntimeError):
    """Datele au încălcat o presupunere pe care se bazează pipeline-ul."""


def _cere(conditie: bool, mesaj: str) -> None:
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
    df = pd.concat(
        [pd.read_csv(c, skipinitialspace=True) for c in cai], ignore_index=True
    )
    df.columns = df.columns.str.strip()
    log.info("%d randuri brute", len(df))

    ani = sorted(df["Ani"].unique())
    _cere(
        ani == [ANUL_ASTEPTAT],
        f"asteptam doar {ANUL_ASTEPTAT!r}, am gasit {ani}. "
        "Un export cu mai multi ani ar dubla unitatile la pivotare.",
    )
    return df


def elimina_agregate(df: pd.DataFrame) -> pd.DataFrame:
    """Scoate rândurile în care `Localitati` este `TOTAL` — agregate pe județ.

    Daca in interfata TEMPO ramane bifat `TOTAL` la LOCALITATI, exportul contine
    si un rand cu totalul judetean, pe langa randurile per localitate. Verificat:
    randul TOTAL este exact suma localitatilor, deci ar dubla unitatile.

    La descarcarea din 2026-09, doar judetul Constanta avea asemenea randuri:
    41 de randuri cu 2.694 de unitati, adica 4,7% inflatie pe totalul national.

    Filtrul e defensiv, nu o corectie punctuala: acelasi lucru se poate intampla
    la orice reexport. De aceea se si loghează cat s-a eliminat.
    """
    agregate = df["Localitati"].str.strip().eq("TOTAL")

    if agregate.any():
        judete = sorted(df.loc[agregate, "Judete"].str.strip().unique())
        log.warning(
            "elimin %d randuri agregate (Localitati = TOTAL), %d unitati, judete: %s",
            agregate.sum(),
            int(df.loc[agregate, "Valoare"].sum()),
            ", ".join(judete),
        )

    df = df.loc[~agregate].copy()
    _cere(
        len(df) == RANDURI_ASTEPTATE,
        f"asteptam {RANDURI_ASTEPTATE:,} randuri dupa eliminarea agregatelor, am {len(df):,}",
    )
    return df


def separa_siruta(df: pd.DataFrame) -> pd.DataFrame:
    """Desparte codul SIRUTA de denumire — identic cu pipeline-ul de populație."""
    df = df.copy()
    df[["cod_siruta", "localitate"]] = df["Localitati"].str.split(" ", n=1, expand=True)

    fara_cod = df["cod_siruta"].isna() | ~df["cod_siruta"].str.fullmatch(r"\d+")
    _cere(
        not fara_cod.any(),
        f"{fara_cod.sum()} randuri nu respecta tiparul '<cod> <nume>':\n"
        f"{df.loc[fara_cod, 'Localitati'].head(10).to_string()}",
    )
    return df


def pastreaza_doar_pozitive(df: pd.DataFrame) -> pd.DataFrame:
    """Elimină rândurile cu valoarea 0.

    TEMPO exporta zerourile inconsecvent de la judet la judet: Alba are 2% randuri
    cu 0, Prahova 49%, Bacau 91%. Bacau are de patru ori mai multe randuri decat
    Prahova si mai putine unitati sanitare.

    Deci numarul de randuri nu inseamna nimic. Un rand absent si un rand cu 0
    inseamna acelasi lucru: localitatea nu are acea categorie de unitate.
    """
    _cere(
        (df["Valoare"] >= 0).all(),
        f"{(df['Valoare'] < 0).sum()} randuri au valori negative",
    )

    pozitive = df[df["Valoare"] > 0].copy()
    log.info(
        "pastrez %d randuri cu valoare pozitiva din %d (%d zerouri eliminate)",
        len(pozitive),
        len(df),
        len(df) - len(pozitive),
    )
    _cere(
        len(pozitive) == RANDURI_POZITIVE_ASTEPTATE,
        f"asteptam {RANDURI_POZITIVE_ASTEPTATE:,} randuri pozitive, am {len(pozitive):,}",
    )
    return pozitive


def pivoteaza(df: pd.DataFrame) -> pd.DataFrame:
    """O linie per localitate, o coloană per categorie de unitate sanitară.

    Aici se foloseste `pivot_table` cu `aggfunc="sum"`, nu `pivot` ca la populatie.
    Motivul e opus: acolo, doua randuri pentru aceeasi combinatie ar fi insemnat
    date corupte, deci voiam sa crape. Aici, fiecare localitate are pana la trei
    randuri per categorie — publica, mixta, privata — si vrem sa le adunam.
    Agregarea e intentionata si documentata, nu accidentala.
    """
    total_inainte = df["Valoare"].sum()

    lat = df.pivot_table(
        index=["Judete", "cod_siruta", "localitate"],
        columns="Categorii de unitati sanitare",
        values="Valoare",
        aggfunc="sum",
        fill_value=0,          # categorie absenta pentru o localitate = 0 unitati
    ).reset_index()
    lat.columns.name = None

    # Plasa de siguranta pentru pivot_table: nicio unitate nu s-a pierdut si
    # niciuna nu s-a inventat prin agregare.
    coloane_categorii = [c for c in lat.columns if c not in ("Judete", "cod_siruta", "localitate")]
    total_dupa = lat[coloane_categorii].to_numpy().sum()
    _cere(
        total_dupa == total_inainte,
        f"pivotarea a schimbat totalul: {total_inainte:,} inainte, {total_dupa:,} dupa",
    )

    lat["total_unitati"] = lat[coloane_categorii].sum(axis=1)
    return lat


def valideaza(df: pd.DataFrame) -> None:
    """Verifică rezultatul față de cifrele calculate independent cu awk."""
    _cere(
        len(df) == LOCALITATI_ASTEPTATE,
        f"asteptam {LOCALITATI_ASTEPTATE:,} localitati cu cel putin o unitate, am {len(df):,}",
    )

    dubluri = df["cod_siruta"].duplicated()
    _cere(
        not dubluri.any(),
        f"{dubluri.sum()} coduri SIRUTA duplicate: "
        f"{df.loc[df['cod_siruta'].duplicated(keep=False), 'cod_siruta'].unique()[:10].tolist()}",
    )

    categorii = [c for c in df.columns if c not in ("Judete", "cod_siruta", "localitate", "total_unitati")]
    _cere(
        len(categorii) == CATEGORII_ASTEPTATE,
        f"asteptam {CATEGORII_ASTEPTATE} categorii, am {len(categorii)}: {sorted(categorii)}",
    )

    _cere(
        df["total_unitati"].sum() == TOTAL_UNITATI_ASTEPTAT,
        f"total unitati: asteptam {TOTAL_UNITATI_ASTEPTAT:,}, am {df['total_unitati'].sum():,}",
    )

    # Dupa filtrarea zerourilor, fiecare localitate ramasa trebuie sa aiba ceva.
    goale = df["total_unitati"] == 0
    _cere(
        not goale.any(),
        f"{goale.sum()} localitati au ajuns in rezultat cu zero unitati:\n"
        f"{df.loc[goale, ['localitate', 'total_unitati']].head(10).to_string()}",
    )

    log.info("%d localitati validate, 5 verificari trecute", len(df))


def scrie(df: pd.DataFrame, iesire: Path) -> None:
    """Scrie CSV-ul și verifică dus-întors că se recitește identic."""
    iesire.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(iesire, index=False)

    recitit = pd.read_csv(iesire, dtype={"cod_siruta": "str"})
    _cere(len(recitit) == len(df), f"am scris {len(df)} randuri, am recitit {len(recitit)}")
    _cere(
        recitit["total_unitati"].sum() == df["total_unitati"].sum(),
        "totalul unitatilor difera dupa export",
    )
    log.info("scris %s (%d randuri, %.0f KB)", iesire, len(recitit), iesire.stat().st_size / 1024)


def prepara(tipar: str, iesire: Path | None = None) -> pd.DataFrame:
    """Lanțul complet: citire → agregate → SIRUTA → zerouri → pivotare → validare."""
    df = citeste(tipar)
    df = elimina_agregate(df)
    df = separa_siruta(df)
    df = pastreaza_doar_pozitive(df)
    lat = pivoteaza(df)
    valideaza(lat)

    if iesire is not None:
        scrie(lat, iesire)
    return lat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--intrare", default=str(INTRARE_IMPLICITA))
    parser.add_argument("--iesire", default=str(IESIRE_IMPLICITA), type=Path)
    parser.add_argument("--verbose", "-v", action="store_true")
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
