"""
Pobiera dane o wskaźnikach CPI z API GUS DBW i zapisuje do data/gus_data.parquet.

Lokalnie:
    uv run --env-file .env python scripts/fetch_gus.py

GitHub Actions:
    Klucz API pochodzi ze zmiennej środowiskowej GUS_API_KEY (GitHub Secret).
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from requests.exceptions import ConnectionError, HTTPError, Timeout

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

PARQUET_PATH = Path("data/gus_data.parquet")
YEARS = list(range(2015, datetime.now().year + 1))
VARIABLE_FILTER = "Wskaźniki cen towarów i usług konsumpcyjnych"
KEY_COLUMNS = [
    "opis-pozycja-3", "opis-pozycja-2", "opis-okres",
    "sposob-prezentacji", "nazwa-przekroj", "id-rok",
]

QUOTA_WAIT_SECONDS = 15 * 60 + 10
SERVER_ERROR_WAIT_SECONDS = 30

# ---------------------------------------------------------------------------
# Logging — stdout, żeby GitHub Actions przechwycił logi
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("gus")

# ---------------------------------------------------------------------------
# Globalne — inicjalizowane w main()
# ---------------------------------------------------------------------------

SESSION: requests.Session
RATE_LIMITER: "RateLimiter"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait(reason: str, seconds: int) -> None:
    resume_at = datetime.now() + timedelta(seconds=seconds)
    logger.warning(f"{reason} — czekam {seconds}s, wznawianie o {resume_at:%H:%M:%S}")
    for _ in range(seconds):
        time.sleep(1)


class RateLimiter:
    def __init__(self, per_second: int = 10, per_15min: int = 500):
        self._per_second = per_second
        self._per_15min = per_15min
        self._timestamps: list[float] = []

    def _cleanup(self, now: float) -> None:
        self._timestamps = [t for t in self._timestamps if now - t < 900]

    def wait_if_needed(self) -> None:
        now = time.monotonic()
        self._cleanup(now)

        if len(self._timestamps) >= self._per_15min - 5:
            sleep_for = int(900 - (now - self._timestamps[0])) + 1
            _wait("Zbliżam się do limitu 500/15min", sleep_for)
            now = time.monotonic()

        recent_1s = [t for t in self._timestamps if now - t < 1.0]
        if len(recent_1s) >= self._per_second:
            sleep_for = 1.0 - (now - recent_1s[0])
            if sleep_for > 0:
                time.sleep(sleep_for)

        self._timestamps.append(time.monotonic())

    def seconds_until_retry(self) -> int:
        now = time.monotonic()
        self._cleanup(now)
        recent_1s = [t for t in self._timestamps if now - t < 1.0]
        if len(recent_1s) >= self._per_second:
            return 2
        return QUOTA_WAIT_SECONDS


def _get_session() -> requests.Session:
    api_key = os.environ["GUS_API_KEY"]
    session = requests.Session()
    session.headers.update({
        "accept": "application/json",
        "X-ClientId": api_key,
    })

    def _log_response(response, *args, **kwargs):
        elapsed = response.elapsed.total_seconds()
        endpoint = response.url.split("/api/")[-1].split("?")[0]
        logger.info(f"{endpoint} → {response.status_code} ({elapsed:.2f}s)")

    session.hooks["response"].append(_log_response)
    return session


def _get(url: str, params: dict, timeout: tuple = (5, 60)) -> requests.Response:
    while True:
        RATE_LIMITER.wait_if_needed()
        try:
            response = SESSION.get(url, params=params, timeout=timeout)
        except (Timeout, ConnectionError) as e:
            _wait(f"Timeout/ConnectionError ({e.__class__.__name__})", QUOTA_WAIT_SECONDS)
            continue

        if response.status_code == 429 or "quota exceeded" in response.text.lower():
            wait_seconds = RATE_LIMITER.seconds_until_retry()
            _wait(f"Rate limit 429 (czekam {wait_seconds}s)", wait_seconds)
            continue

        if response.status_code in (500, 503):
            _wait(f"Błąd serwera ({response.status_code})", SERVER_ERROR_WAIT_SECONDS)
            continue

        return response

# ---------------------------------------------------------------------------
# API — słowniki (cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_periods() -> dict:
    url = "https://api-dbw.stat.gov.pl/api/dictionaries/periods-dictionary"
    params = {"page-size": 5000, "page": 0, "lang": "pl"}

    first = _get(url, params)
    first.raise_for_status()
    first_json = first.json()
    data = first_json["data"]

    for page in range(1, first_json["page-count"] + 1):
        params["page"] = page
        r = _get(url, params)
        r.raise_for_status()
        data.extend(r.json()["data"])

    return {d["id-okres"]: d["opis"] for d in data}


@lru_cache(maxsize=1)
def _get_ways_of_presentation() -> dict:
    url = "https://api-dbw.stat.gov.pl/api/dictionaries/way-of-presentation"
    params = {"page": 0, "page-size": 5000, "lang": "pl"}

    first = _get(url, params)
    first.raise_for_status()
    first_json = first.json()
    data = first_json["data"]

    for page in range(1, first_json["page-count"] + 1):
        params["page"] = page
        r = _get(url, params)
        r.raise_for_status()
        data.extend(r.json()["data"])

    return {d["id-sposob-prezentacji-miara"]: d["nazwa"] for d in data}


@lru_cache(maxsize=128)
def _get_positions_lookup(section_id: int) -> dict:
    url = "https://api-dbw.stat.gov.pl/api/variable/variable-section-position"
    r = _get(url, {"id-przekroj": section_id, "lang": "pl"})
    r.raise_for_status()
    return {d["id-pozycja"]: d["nazwa-pozycja"] for d in r.json()}

# ---------------------------------------------------------------------------
# API — dane
# ---------------------------------------------------------------------------

def get_variables_periods_sections() -> pd.DataFrame:
    url = "https://api-dbw.stat.gov.pl/api/variable/variable-section-periods"
    params = {"ile-na-stronie": 5000, "numer-strony": 0, "lang": "pl"}

    first = _get(url, params)
    first.raise_for_status()
    first_json = first.json()
    pages = first_json["page-count"]
    data = first_json["data"]

    for page in range(1, pages + 1):
        params["numer-strony"] = page
        r = _get(url, params)
        r.raise_for_status()
        data.extend(r.json()["data"])
        logger.info(f"variable-section-periods: strona {page}/{pages}")

    df = pd.DataFrame(data)
    df["opis-okres"] = df["id-okres"].map(_get_periods())
    return df


def get_years_to_fetch(all_years: list[int]) -> list[int]:
    if not PARQUET_PATH.exists():
        return all_years

    df_existing = pd.read_parquet(PARQUET_PATH, columns=["id-rok"])
    fetched_years = set(df_existing["id-rok"].unique())
    last_fetched = max(fetched_years) if fetched_years else None

    # Zawsze ponownie pobieraj ostatni rok — GUS może korygować dane wstecznie
    return [y for y in all_years if y not in fetched_years or y == last_fetched]


def get_data(
    variable_id: int,
    section_periods: dict[int, list[int]],
    year_ids: list[int],
    section_names: dict,
) -> pd.DataFrame:
    url = "https://api-dbw.stat.gov.pl/api/variable/variable-data-section"
    results = []

    for section_id, period_ids in section_periods.items():
        for year_id in year_ids:
            logger.info(f"Pobieranie: section={section_id}, rok={year_id}, periods={len(period_ids)}")
            for period_id in period_ids:
                params = {
                    "id-zmienna": variable_id,
                    "id-przekroj": section_id,
                    "id-rok": year_id,
                    "id-okres": period_id,
                    "ile-na-stronie": 5000,
                    "numer-strony": 0,
                    "lang": "pl",
                }

                try:
                    first = _get(url, params, timeout=(5, 30))
                    first.raise_for_status()
                except HTTPError as e:
                    if e.response.status_code == 404:
                        continue
                    raise

                first_json = first.json()
                data = first_json["data"]

                for page in range(1, first_json["page-count"] + 1):
                    params["numer-strony"] = page
                    r = _get(url, params, timeout=(5, 30))
                    r.raise_for_status()
                    data.extend(r.json()["data"])

                section_df = pd.DataFrame(data)
                section_df["id-rok"] = year_id
                results.append(section_df)

    if not results:
        return pd.DataFrame()

    df = pd.concat(results, ignore_index=True)
    logger.info("Pobieranie zakończone")

    df["opis-okres"] = df["id-okres"].map(_get_periods())
    df["sposob-prezentacji"] = df["id-sposob-prezentacji-miara"].map(_get_ways_of_presentation())
    df["opis-pozycja-2"] = df.apply(
        lambda row: _get_positions_lookup(row["id-przekroj"]).get(row["id-pozycja-2"]), axis=1
    )
    df["opis-pozycja-3"] = df.apply(
        lambda row: _get_positions_lookup(row["id-przekroj"]).get(row["id-pozycja-3"]), axis=1
    )
    df["nazwa-przekroj"] = df["id-przekroj"].map(section_names)

    return df[["nazwa-przekroj", "opis-pozycja-3", "opis-pozycja-2", "opis-okres",
               "sposob-prezentacji", "id-rok", "wartosc"]]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global SESSION, RATE_LIMITER
    SESSION = _get_session()
    RATE_LIMITER = RateLimiter()

    PARQUET_PATH.parent.mkdir(exist_ok=True)

    logger.info("Pobieranie metadanych (zmienne, przekroje, okresy)...")
    df_meta = get_variables_periods_sections()

    variable_id = int(
        df_meta[df_meta["nazwa-zmienna"] == VARIABLE_FILTER]["id-zmienna"].unique()[0]
    )
    logger.info(f"Zmienna: '{VARIABLE_FILTER}' (id={variable_id})")

    df_var = df_meta[df_meta["id-zmienna"] == variable_id]
    section_names = {
        int(k): v for k, v in zip(df_var["id-przekroj"], df_var["nazwa-przekroj"])
    }
    section_periods = {
        int(k): [int(v) for v in vs]
        for k, vs in df_var.groupby("id-przekroj")["id-okres"].apply(list).to_dict().items()
    }

    years_to_fetch = get_years_to_fetch(YEARS)
    if not years_to_fetch:
        logger.info("Brak nowych lat do pobrania. Koniec.")
        return
    logger.info(f"Lata do pobrania: {years_to_fetch}")

    df_new = get_data(
        variable_id=variable_id,
        section_periods=section_periods,
        year_ids=years_to_fetch,
        section_names=section_names,
    )

    if df_new.empty:
        logger.warning("Nie pobrano żadnych danych.")
        return

    if PARQUET_PATH.exists():
        df_existing = pd.read_parquet(PARQUET_PATH)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=KEY_COLUMNS, keep="last")
    else:
        df_combined = df_new

    df_combined.to_parquet(PARQUET_PATH, index=False)
    size_mb = PARQUET_PATH.stat().st_size / 1024**2
    logger.info(f"Zapisano {len(df_combined)} wierszy → {PARQUET_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
