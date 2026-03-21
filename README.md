# Dashboard CPI — Dane GUS

Interaktywny dashboard do wizualizacji wskaźników cen towarów i usług konsumpcyjnych (CPI) publikowanych przez Główny Urząd Statystyczny. Zbudowany w Streamlit, hostowany na Streamlit Community Cloud.

**Demo:** https://daneguscpi.streamlit.app

---

## Co robi

- Wyświetla dane CPI z API BDL GUS za lata 2015–teraz
- Pozwala porównać do 4 kategorii cenowych na jednym wykresie
- Filtruje według przekroju, trybu okresu (miesięczny / narastający), sposobu prezentacji i zakresu lat
- Eksportuje przefiltrowane dane do Excela
- Odświeża dane automatycznie co tydzień przez GitHub Actions

---

## Architektura

```
GitHub Actions (cron, co poniedziałek 6:00 UTC)
    → scripts/fetch_gus.py
        → data/gus_data.parquet  (commit do repo)
            → Streamlit Community Cloud (automatyczny redeploy)
                → app.py czyta parquet lokalnie
                    → użytkownik widzi dane natychmiast
```

Dane są przechowywane jako plik Parquet bezpośrednio w repozytorium. Dzięki temu dashboard nie wykonuje żadnych żądań do API w czasie działania — dane są dostępne natychmiast po wejściu.

---

## Struktura repozytorium

```
├── .github/
│   └── workflows/
│       └── refresh_data.yml   # GitHub Actions — cron tygodniowy
├── data/
│   └── gus_data.parquet       # dane CPI, commitowane do repo
├── scripts/
│   └── fetch_gus.py           # skrypt pobierający dane z API GUS
├── app.py                     # dashboard Streamlit
└── pyproject.toml             # zależności (uv)
```

---

## Jak działa pobieranie danych

Skrypt `scripts/fetch_gus.py` odpytuje [API DBW GUS](https://api-dbw.stat.gov.pl) z kluczem API przekazywanym przez nagłówek `X-ClientId`.

### Przyrostowe pobieranie

Skrypt sprawdza które lata są już w pliku Parquet i pobiera tylko brakujące. Ostatni znany rok jest zawsze pobierany ponownie — GUS może korygować dane wstecznie.

### Rate limiting

API GUS ma dwa limity:
- **10 żądań/sekundę** — skrypt odczekuje ułamek sekundy między żądaniami
- **500 żądań/15 minut** — skrypt odczekuje do końca okna przy zbliżeniu się do limitu

Odpowiedzi `429` są obsługiwane z automatycznym retry.

### Format danych

Wynikowy DataFrame zawiera kolumny:

| Kolumna | Opis |
|---|---|
| `nazwa-przekroj` | Klasyfikacja (np. COICOP 1999) |
| `opis-pozycja-2` | Kategoria towarów/usług |
| `opis-pozycja-3` | Podkategoria |
| `opis-okres` | Opis okresu (np. "styczeń — dane miesięczne") |
| `sposob-prezentacji` | Sposób prezentacji wskaźnika |
| `id-rok` | Rok |
| `wartosc` | Wartość wskaźnika |

---

## Uruchomienie lokalne

### Wymagania

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Klucz API GUS ([rejestracja](https://api-dbw.stat.gov.pl))

### Instalacja

```bash
git clone https://github.com/<login>/dashboard_dane_gus.git
cd dashboard_dane_gus
uv sync
```

### Konfiguracja klucza API

```bash
cp .env.example .env
# Wpisz swój klucz w .env:
# GUS_API_KEY=twoj-klucz-tutaj
```

### Pobranie danych

```bash
uv run --env-file .env python scripts/fetch_gus.py
```

Pierwsze uruchomienie pobiera dane za lata 2015–teraz (~kilka minut ze względu na limity API).

### Uruchomienie dashboardu

```bash
uv run streamlit run app.py
```

---

## Deployment na Streamlit Community Cloud

1. Utwórz **publiczne** repozytorium na GitHubie i wypchnij kod
2. Dodaj secret `GUS_API_KEY` w `Settings → Secrets and variables → Actions`
3. Wejdź na [share.streamlit.io](https://share.streamlit.io), zaloguj się GitHubem
4. Utwórz nową aplikację wskazując `app.py` jako plik główny
5. Streamlit automatycznie redeploy'uje aplikację przy każdym nowym commicie

### Automatyczna aktualizacja danych

GitHub Actions uruchamia skrypt co poniedziałek o 6:00 UTC. Po pobraniu nowych danych commituje zaktualizowany plik Parquet, co wyzwala automatyczny redeploy dashboardu.

Workflow można też uruchomić ręcznie: `Actions → Refresh GUS data → Run workflow`.

---

## Technologie

| | |
|---|---|
| **Dashboard** | [Streamlit](https://streamlit.io) |
| **Wykresy** | [Plotly Express](https://plotly.com/python/plotly-express/) |
| **Dane** | [pandas](https://pandas.pydata.org) + [PyArrow](https://arrow.apache.org/docs/python/) |
| **API** | [BDL GUS](https://api-dbw.stat.gov.pl) |
| **CI/CD** | GitHub Actions |
| **Hosting** | Streamlit Community Cloud |
| **Package manager** | [uv](https://docs.astral.sh/uv/) |
