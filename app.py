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
    """Zwraca indeks pierwszej opcji zawierającej keyword (case-insensitive)."""
    kw = keyword.lower()
    for i, o in enumerate(options):
        if kw in str(o).lower():
            return i
    return 0


def get_month_num(opis: str) -> int:
    opis_lower = opis.lower()
    for name, num in MONTH_ORDER.items():
        if name in opis_lower:
            return num
    return 0


df = load_data()

st.title("Wskaźniki cen towarów i usług konsumpcyjnych")

# ---------------------------------------------------------------------------
# Filtry — wiersz 1: przekrój | tryb | sposób prezentacji
# ---------------------------------------------------------------------------

fcol1, fcol2, fcol3 = st.columns(3)

przekroje = sorted(df["nazwa-przekroj"].dropna().unique())
with fcol1:
    przekroj = st.selectbox("Przekrój", przekroje, index=idx(przekroje, "COICOP 1999"))

df_p = df[df["nazwa-przekroj"] == przekroj]

prezentacje = sorted(df_p["sposob-prezentacji"].dropna().unique())
with fcol3:
    prezentacja = st.selectbox(
        "Sposób prezentacji", prezentacje, index=idx(prezentacje, "analogiczny")
    )

df_p = df_p[df_p["sposob-prezentacji"] == prezentacja]

with fcol2:
    tryb = st.radio("Tryb okresu", ["Narastający", "Miesięczny"], horizontal=True)

# ---------------------------------------------------------------------------
# Filtry — wiersz 2: zależne od trybu
# ---------------------------------------------------------------------------

if tryb == "Narastający":
    df_p = df_p[df_p["opis-okres"].str.contains("narastające", na=False, case=False)]
    okresy = sorted(df_p["opis-okres"].dropna().unique())
    okres = st.selectbox("Okres", okresy, index=idx(okresy, "styczeń - grudzień"))
    df_p = df_p[df_p["opis-okres"] == okres]
    x_col = "id-rok"
    x_label = "Rok"
else:
    df_p = df_p[df_p["opis-okres"].str.contains("dane miesięczne", na=False, case=False)]
    selected_months = st.multiselect("Miesiące", MONTH_NAMES, default=MONTH_NAMES)
    if selected_months:
        nums = {MONTH_NAMES.index(m) + 1 for m in selected_months}
        df_p = df_p[df_p["opis-okres"].apply(get_month_num).isin(nums)]
    x_col = "date"
    x_label = "Data"

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

if tryb == "Miesięczny":
    df_filtered["month_num"] = df_filtered["opis-okres"].apply(get_month_num)
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

group_cols = ["opis-pozycja-2", x_col]
if df_chart.groupby(group_cols).size().max() > 1:
    df_chart = df_chart.groupby(group_cols, as_index=False)["wartosc"].mean()

df_chart = df_chart.sort_values(group_cols)

fig = px.line(
    df_chart,
    x=x_col,
    y="wartosc",
    color="opis-pozycja-2",
    markers=True,
    labels={
        x_col: x_label,
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
