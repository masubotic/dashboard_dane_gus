# Architektura: Dashboard Danych GUS

## Cel
Aplikacja Streamlit do wizualizacji wskaźników CPI (cen towarów i usług konsumpcyjnych) z API BDL GUS. Hostowana na Streamlit Community Cloud. Dane są dostępne natychmiast po wejściu użytkownika — bez pobierania na żywo z API w runtime.

---

## Struktura repozytorium

```
├── .github/workflows/
│   └── refresh_data.yml       # GitHub Actions — cron tygodniowy
├── data/
│   └── gus_data.parquet       # dane pobrane z API, commitowane do repo
├── scripts/
│   └── fetch_gus.py           # skrypt pobierający dane z API BDL GUS
├── app.py                     # dashboard Streamlit
└── pyproject.toml
```

---

## Przepływ danych

```
GitHub Actions (cron, każdy poniedziałek 6:00 UTC)
    → scripts/fetch_gus.py
        → data/gus_data.parquet  (commit do repo)
            → Streamlit Community Cloud (automatyczny redeploy)
                → app.py czyta parquet lokalnie
                    → użytkownik widzi dane natychmiast
```

---

## Warstwy

### 1. Pobieranie danych — `scripts/fetch_gus.py`
- Odpytuje API BDL GUS przez `requests` z obsługą retry i limitów kwotowych
- Filtruje zmienne po frazie `"Wskaźniki cen towarów i usług konsumpcyjnych"`
- Pobiera dane dla lat 2015 – bieżący rok
- Zawsze ponownie pobiera ostatni znany rok (GUS może korygować dane wstecznie)
- Deduplikuje po kluczu biznesowym: `(opis-pozycja-3, opis-pozycja-2, opis-okres, sposob-prezentacji, nazwa-przekroj, id-rok)` — przy duplikatach zostaje nowszy wiersz
- Zapisuje wynik do `data/gus_data.parquet` (PyArrow); kolumny tekstowe jako `category`
- Wymaga zmiennej środowiskowej `GUS_API_KEY`

### 2. Automatyzacja — `.github/workflows/refresh_data.yml`
- Cron: w każdy poniedziałek o 6:00 UTC (`0 6 * * 1`)
- Instaluje zależności przez `uv sync --no-dev`
- Po pobraniu commituje zaktualizowany parquet do repozytorium (`[skip ci]`)
- Możliwe ręczne odpalenie przez `workflow_dispatch`
- Klucz API przechowywany jako GitHub Secret (`GUS_API_KEY`)

### 3. Dashboard — `app.py`
- Czyta dane lokalnie z `data/gus_data.parquet` przez `pd.read_parquet` owiniętą w `@st.cache_data`
- Kolumny tekstowe konwertowane do `category` przy ładowaniu (mniejsze zużycie pamięci)
- Brak TTL w cache — dane zmieniają się tylko przez commit, Streamlit robi redeploy automatycznie
- Hostowany na Streamlit Community Cloud (darmowy dla publicznych repo)

#### Struktura UI
- **Filtry** (expander): tryb okresu, miesiące, sposób prezentacji, zakres lat
- **Przekroje i wskaźniki** (expander): 1–4 sloty, każdy z selectboxem przekroju i wskaźnika
  - Slot 1 wymagany, sloty 2–4 opcjonalne (dodawane przyciskiem `＋`)
  - Wskaźniki deduplikowane: sole-child sub-kody z tą samą nazwą są ukrywane
  - Wskaźniki wyświetlane z wcięciem oddającym hierarchię kodu (COICOP)
- **Wykres** (Plotly): linia czasowa, etykiety wartości, legenda pod wykresem
- **Dane źródłowe** (expander): podgląd tabeli + eksport do Excel

---

## Kluczowe założenia
- Repozytorium publiczne na GitHub
- Plik `data/gus_data.parquet` nie przekroczy 100 MB (limit GitHub); Parquet jest znacznie bardziej kompaktowy niż CSV
- Dane GUS aktualizowane miesięcznie/kwartalnie, ale nieregularnie — stąd cron tygodniowy
- Streamlit Community Cloud trzyma lokalną kopię repo — zero requestów do GitHub w runtime
