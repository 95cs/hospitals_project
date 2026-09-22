# Acces la servicii medicale în România

Analiză la nivel de localitate (UAT) a relației dintre îmbătrânirea populației și accesul la
servicii medicale, pentru fundamentarea unei decizii de amplasare de centre medicale noi.

---

## Întrebarea de business

> **Ministerul Sănătății trebuie să decidă unde să deschidă 10 centre medicale noi. În care
> localități se suprapun cel mai puternic o populație vârstnică numeroasă, distanța mare până
> la cea mai apropiată unitate spitalicească, și o densitate de personal medical sub media
> națională?**

**Destinatarul** ia o decizie de alocare bugetară cu 10 poziții. **Acțiunea** e concretă:
lista scurtă de comune. Răspunsul cere **trei surse** care nu se potrivesc natural și nu poate
fi ghicit dinainte.

### Ce rămâne de decis în formularea de mai sus

| Întrebare deschisă | De ce contează |
|---|---|
| Ce distanță înseamnă „mare"? | Pragul (25 km? 30?) schimbă complet lista finală și trebuie apărat |
| Cum se combină cele trei criterii? | Un filtru cu „ȘI" poate returna 3 comune sau 400. Pentru „primele 10" e nevoie de o **regulă de prioritizare** (scor compus sau ordonare lexicografică), iar ponderile alese vor fi prima întrebare pe care o primești |
| Distanță în linie dreaptă sau pe drum? | În Hunedoara, Caraș-Severin și Apuseni — exact zonele cu cele mai îmbătrânite comune — diferența e uriașă |

---

## Aria analizei

Validarea se face pe **toate cele 3.181 de localități**. Din analizele la nivel de localitate
se exclude, deocamdată, doar **Municipiul București**.

| | UAT-uri | Populație | Persoane 65+ | Pondere 65+ |
|---|---|---|---|---|
| Set complet (validat) | 3.181 | 21.646.220 | 4.076.589 | 18,8% |
| București (exclus) | 1 | 2.108.049 | 426.601 | 20,2% |
| **Set de lucru** | **3.180** | **19.538.171** | **3.649.988** | **18,7%** |

**Motivul excluderii Bucureștiului este tehnic, nu tematic:** vine agregat, ca un singur rând
de 2,1 milioane de locuitori, fără defalcare pe sectoare. Restul țării e la nivel de UAT, cu o
mediană de 3.003 locuitori. Un punct de date care reprezintă 10% din populația țării nu e
comparabil cu celelalte 3.180 și ar domina orice vizualizare la nivel de localitate.

Validarea rămâne pe setul complet, înaintea excluderii — un set validat integral e o bază mai
solidă decât unul validat după filtrare, și permite recalcularea totalurilor naționale.

### Decizie amânată: restrângerea la mediul rural

Întrebarea vizează zonele fără acces, iar orașele și municipiile concentrează unitățile
spitalicești. O variantă este restrângerea la cele 2.862 de comune:

| | UAT-uri | Populație | Persoane 65+ |
|---|---|---|---|
| Comune | 2.862 | 9.697.493 | 1.701.854 |
| Orașe + municipii | 319 | 11.948.727 | 2.374.735 |

Ar însemna excluderea a 55,2% din populația țării, iar ponderea 65+ ar coborî la 17,5% —
mediul urban are, în cifre absolute, mai mulți vârstnici.

**Nu se aplică deocamdată**, pentru că filtrul administrativ taie greșit în ambele direcții.
Clasificarea comună / oraș / municipiu este juridică, nu funcțională: nu urmărește nici
mărimea, nici izolarea, nici accesul real.

- `FLORESTI` (Cluj) are 58.010 locuitori și e comună — ar rămâne, deși e suburbia Clujului,
  la câțiva kilometri de trei spitale mari.
- `ORAS VASCAU` (Bihor) are 2.041 de locuitori și 27,7% vârstnici, în Munții Apuseni — ar
  ieși, deși e exact profilul căutat.
- 120 de orașe și municipii au sub 10.000 de locuitori; `ORAS BAILE TUSNAD` (1.550) e mai mic
  decât mediana setului de lucru.

Decizia se ia după ce sursa de unități sanitare arată cum se distribuie efectiv accesul.
Un criteriu de mărime sau de acces real poate fi mai potrivit decât cel administrativ.

---

## Surse de date

| # | Sursă | Ce conține | Granularitate | Stare |
|---|---|---|---|---|
| 1 | INS TEMPO, matricea POP107D | Populație pe grupe de vârstă, 2026, ambele sexe | localitate (cod SIRUTA) | ✅ 42/42 fișiere, procesată și validată |
| 2 | _(de stabilit)_ | Unități sanitare / paturi de spital | localitate sau județ | ⬜ |
| 3 | _(de stabilit)_ | Personal medical (medici la 1.000 locuitori) | județ, probabil | ⬜ |
| 4 | _(de stabilit)_ | Coordonate geografice pentru SIRUTA | localitate | ⬜ necesară pentru calculul distanțelor |

**Sursa 1 — detalii.** 42 de exporturi CSV (41 de județe + București), descărcate manual din
TEMPO. Grupele selectate: `Total`, `65-69`, `70-74`, `75-79`, `80-84`, `85+`.
19.086 rânduri brute → 3.181 localități după pivotare → 3.180 după excluderea Bucureștiului.

**Sursa 4 nu era prevăzută inițial.** Criteriul de distanță din întrebarea de business cere
coordonate atât pentru comune, cât și pentru spitale — codul SIRUTA nu le conține. Este o
componentă geospațială care extinde semnificativ scopul proiectului.

---

## Ce nu spun datele

**1. Populație după domiciliu, nu populație rezidentă.**
Totalul brut este **21.646.220**, față de ~19 milioane de rezidenți reali. Diferența o
reprezintă persoanele cu domiciliul înregistrat în România care locuiesc în străinătate.
Cifrele **supraestimează** populația exact în comunele rurale cu emigrație ridicată — adică
zonele cel mai probabil să apară în răspunsul final. Orice indicator „per locuitor" are un
numitor umflat în mediul rural, iar efectul e cu atât mai mare cu cât comuna e mai mică.
Aceasta este cea mai importantă limitare a întregii analize.

**2. Numele de localități nu sunt unice.**
239 de nume se repetă între județe (`ADANCATA`, `ALBESTI`, `POPESTI`…).
**Cheia de join este `cod_siruta`, niciodată numele.**

**3. Comunele mici au procente exacte, dar greu comparabile.**
Datele sunt exhaustive, nu un eșantion: `BATRANA` (Hunedoara) chiar are 51 de persoane peste
65 de ani dintr-un total de 109 locuitori, iar 46,8% este cifra corectă. Nu există eroare de
măsurare. Problemele sunt altele: indicatorul e **instabil în timp** (cinci decese îl mișcă
patru puncte) și **greu de comparat** cu o localitate de 20.000 de locuitori.

**Nu se aplică prag de populație.** Un prag de 2.000 de locuitori ar elimina 848 de localități
cu 270.201 persoane de 65+ — exact populația cu accesul cel mai slab la servicii medicale,
adică subiectul analizei. Problema de comparabilitate se rezolvă altfel: prin afișarea
simultană a ponderii, a numărului absolut de vârstnici și a populației totale, și prin
codificarea vizuală a mărimii localității (dimensiunea punctului), nu prin ascunderea datelor.

---

## Interpretare: media rapoartelor ≠ raportul sumelor

| Cifră | Valoare (set de lucru) | Ce înseamnă |
|---|---|---|
| Media coloanei `pondere_65plus` | **19,4%** | media aritmetică a 3.180 de procente — `BATRANA` (109 locuitori) cântărește cât `MUNICIPIUL IASI` (370.437) |
| Total 65+ ÷ total populație | **18,7%** | fiecare persoană cântărește la fel |

Ambele sunt corecte și răspund la întrebări diferite:
*„Ce procent dintre locuitori au peste 65 de ani?"* → 18,7%.
*„Cât de îmbătrânită e o localitate tipică?"* → 19,4%.

Diferența nu e zgomot — e informația în sine: România are multe comune mici și îmbătrânite,
iar ele trag media nepondera în sus. În dashboard, fiecare indicator trebuie etichetat astfel
încât să fie clar care dintre cele două este.

---

## Decizii de curățare

| # | Decizie | Ce s-a ales | De ce |
|---|---|---|---|
| 1 | Nume de coloane | `.str.strip()`, denumirile INS păstrate ca atare | trasabilitate către sursă — cine compară cu exportul TEMPO regăsește aceleași denumiri, fără traducere mentală |
| 2 | Tipul lui `cod_siruta` | text (`str`) | e un **identificator**, nu o cantitate: nu se fac operații aritmetice pe el, iar păstrarea ca text elimină riscul pierderii unor eventuale zerouri la început și forțează potrivirea explicită a tipurilor la join. **Atenție la consum:** CSV-ul nu păstrează tipurile — orice recitire trebuie să forțeze `dtype={"cod_siruta": "str"}`, altfel devine `int64` și join-ul cu sursa de spitale nu potrivește nimic, fără să dea eroare |
| 3 | Coloana `Localitati` originală | nu ajunge în tabelul lat | pivotarea păstrează doar coloanele din index; informația e integral acoperită de `cod_siruta` + `localitate`. Rămâne disponibilă în tabelul lung, pentru verificări |
| 4 | Separarea cod / nume | `str.split(" ", n=1)` | o singură tăietură, la primul spațiu — păstrează intacte numele compuse (`MUNICIPIUL ALBA IULIA`, `VIZANTEA-LIVEZI`). Verificat: toate cele 19.086 de rânduri respectă tiparul `cod` + spațiu + `nume` |
| 5 | `pivot` vs `pivot_table` | `pivot` | `pivot_table` agregează în tăcere duplicatele (implicit: media). `pivot` crapă — validează gratuit că fiecare localitate are exact 6 grupe de vârstă |
| 6 | Scara lui `pondere_65plus` | raport 0–1 | formatarea ca procent aparține stratului de prezentare; Power BI înmulțește cu 100 la afișare, iar stocarea pe scara 0–100 produce `1880%` |
| 7 | Aria analizei | validare pe 3.181; București exclus din analizele la nivel de localitate | motiv tehnic: vine agregat, 2,1M într-un singur rând, fără sectoare — incomparabil cu restul. Restrângerea la mediul rural rămâne o decizie amânată |

---

## Validare

Cifrele de referință au fost calculate **independent**, cu `awk` direct pe cele 42 de CSV-uri
brute, fără pandas. Pipeline-ul reproduce aceleași valori — verificare încrucișată pe două
implementări fără cod comun.

Validarea se aplică pe setul complet de 3.181 de localități, **înainte** de orice excludere.

| Verificare | Valoare așteptată |
|---|---|
| Localități | 3.181 (= 2.862 comune + 216 orașe + 103 municipii, numărul oficial de UAT-uri) |
| `cod_siruta` unic | 0 duplicate |
| Valori lipsă | 0 |
| `populatie_65plus ≤ Total` | pe fiecare rând |
| `pondere_65plus ∈ [0, 1]` | pe fiecare rând |
| Total populație 65+ | 4.076.589 |
| Total populație | 21.646.220 |
| Pondere 65+ la nivel național | 18,8% |
| Extreme | max 46,8% `BATRANA` (HD) · min 2,8% `BARBULESTI` (IL) |

După excluderea Bucureștiului: 3.180 de localități, între 109 și 370.437 locuitori, mediana 3.003.

---

## Structura proiectului

```
data/raw/         date brute, niciodată modificate manual
data/processed/   rezultatul curățării (ignorat de git)
notebooks/        explorare interactivă
src/              cod care rulează repetat
```

## Setup

```bash
python3 -m venv venv && source venv/bin/activate && pip install pandas jupyter
```

## Rulare

Reface întregul lanț, de la CSV-urile brute la fișierul din `data/processed/`:

```bash
python src/prep_populatie.py
```

Scriptul se oprește cu `EroareDeDate` și cod de ieșire 1 dacă vreuna dintre
presupunerile despre date nu se confirmă. Notebook-ul rămâne ca urmă a explorării.

---

## Stadiu

**Sursa 1 — populație**
- [x] Ingerare din 42 de CSV-uri, curățare, separare SIRUTA, pivotare
- [x] 8 verificări automate pe setul complet de 3.181 de localități
- [x] Excluderea Bucureștiului (după validare) → 3.180 de localități
- [x] Export în `data/processed/populatie_localitati.csv`
- [x] Mutarea logicii din notebook în `src/prep_populatie.py`

**Decizii de scop, de luat înainte de sursa 2**
- [ ] Se restrânge analiza la mediul rural? (vezi *Aria analizei*)
- [ ] Se păstrează criteriul de distanță? Implică sursa 4 și geocodare
- [ ] Ce prag de distanță înseamnă „acces slab"?

**Mai departe**
- [ ] Sursa 2 — unități sanitare
- [ ] Sursa 3 — personal medical
- [ ] Join pe `cod_siruta` (atenție la `dtype` — vezi decizia 2)
- [ ] Regula de prioritizare pentru „primele 10"
- [ ] Dashboard Power BI
