import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Dashboard CPI — GUS", layout="wide")

MONTH_ORDER = {
    "styczeń": 1, "luty": 2, "marzec": 3, "kwiecień": 4,
    "maj": 5, "czerwiec": 6, "lipiec": 7, "sierpień": 8,
    "wrzesień": 9, "październik": 10, "listopad": 11, "grudzień": 12,
}
MONTH_NAMES = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]


@st.cache_data
def load_data() -> pd.DataFrame:
    return pd.read_parquet("data/gus_data.parquet")


def idx(options: list, keyword: str) -> int:
    kw = keyword.lower()
    for i, o in enumerate(options):
        if kw in str(o).lower():
            return i
    return 0


def get_period_month_num(opis: str) -> int:
    """
    Zwraca miesiąc okresu:
    - dla miesięcznych: sam miesiąc
    - dla narastających: miesiąc końcowy (np. 'styczeń–czerwiec' → 6)
    """
    opis_lower = opis.lower()
    result = 0
    for name, num in MONTH_ORDER.items():
        if name in opis_lower:
            result = max(result, num)
    return result


df = load_data()

st.title("Wskaźniki cen towarów i usług konsumpcyjnych")

# ---------------------------------------------------------------------------
# Wiersz 1: Przekrój (50%)
# ---------------------------------------------------------------------------

pcol, _ = st.columns([1, 1])
przekroje = sorted(df["nazwa-przekroj"].dropna().unique())
with pcol:
    przekroj = st.selectbox("Przekrój", przekroje, index=idx(przekroje, "COICOP 1999"))

df_p = df[df["nazwa-przekroj"] == przekroj]

# ---------------------------------------------------------------------------
# Wiersz 2: Tryb (20%) + Miesiące (30%)
# ---------------------------------------------------------------------------

tcol, mcol, _ = st.columns([2, 3, 5])

with tcol:
    tryb = st.radio("Tryb okresu", ["Narastający", "Miesięczny"])

if tryb == "Narastający":
    df_p = df_p[df_p["opis-okres"].str.contains("miesiąc - dane narastające", na=False, case=False)]
else:
    df_p = df_p[df_p["opis-okres"].str.contains("dane miesięczne", na=False, case=False)]

with mcol:
    selected_months = st.multiselect("Miesiące", MONTH_NAMES, default=MONTH_NAMES)

if selected_months:
    nums = {MONTH_NAMES.index(m) + 1 for m in selected_months}
    df_p = df_p[df_p["opis-okres"].apply(get_period_month_num).isin(nums)]

# ---------------------------------------------------------------------------
# Wiersz 3: Sposób prezentacji (50%)
# ---------------------------------------------------------------------------

scol, _ = st.columns([1, 1])
prezentacje = sorted(df_p["sposob-prezentacji"].dropna().unique())
with scol:
    prezentacja = st.selectbox(
        "Sposób prezentacji", prezentacje, index=idx(prezentacje, "analogiczny")
    )

df_p = df_p[df_p["sposob-prezentacji"] == prezentacja]

# ---------------------------------------------------------------------------
# Suwak lat
# ---------------------------------------------------------------------------

min_rok = int(df_p["id-rok"].min())
max_rok = int(df_p["id-rok"].max())
rok_od, rok_do = st.slider(
    "Zakres lat",
    min_value=min_rok,
    max_value=max_rok,
    value=(min_rok, max_rok),
)

df_filtered = df_p[df_p["id-rok"].between(rok_od, rok_do)].copy()
df_filtered["month_num"] = df_filtered["opis-okres"].apply(get_period_month_num)
df_filtered["date"] = pd.to_datetime(
    df_filtered["id-rok"].astype(str) + "-"
    + df_filtered["month_num"].astype(str).str.zfill(2),
    format="%Y-%m",
)

# ---------------------------------------------------------------------------
# Wybór pozycji
# ---------------------------------------------------------------------------

pozycje = sorted(df_filtered["opis-pozycja-2"].dropna().unique())

if len(pozycje) < 2:
    st.warning("Za mało danych dla wybranych filtrów.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    poz1 = st.selectbox("Pozycja 1", pozycje, index=idx(pozycje, "Usługi lekarskie"))
with col2:
    poz2 = st.selectbox("Pozycja 2", pozycje, index=idx(pozycje, "Zdrowie"))

# ---------------------------------------------------------------------------
# Wykres
# ---------------------------------------------------------------------------

df_chart = df_filtered[df_filtered["opis-pozycja-2"].isin([poz1, poz2])].copy()

if df_chart.empty:
    st.warning("Brak danych dla wybranych pozycji.")
    st.stop()

group_cols = ["opis-pozycja-2", "date"]
if df_chart.groupby(group_cols).size().max() > 1:
    df_chart = df_chart.groupby(group_cols, as_index=False)["wartosc"].mean()

df_chart = df_chart.sort_values(group_cols)

fig = px.line(
    df_chart,
    x="date",
    y="wartosc",
    color="opis-pozycja-2",
    markers=True,
    labels={
        "date": "Data",
        "wartosc": "Wartość",
        "opis-pozycja-2": "Pozycja",
    },
    title=f"{poz1}  vs  {poz2}",
)
fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.3))

st.plotly_chart(fig)

# ---------------------------------------------------------------------------
# Tabela danych
# ---------------------------------------------------------------------------

with st.expander("Dane źródłowe"):
    st.dataframe(
        df_chart.sort_values(group_cols),
        hide_index=True,
    )
