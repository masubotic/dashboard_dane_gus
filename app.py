import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Dashboard CPI — GUS", layout="wide")


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


df = load_data()

st.title("Wskaźniki cen towarów i usług konsumpcyjnych")

# ---------------------------------------------------------------------------
# Filtry
# ---------------------------------------------------------------------------

fcol1, fcol2, fcol3 = st.columns(3)

przekroje = sorted(df["nazwa-przekroj"].dropna().unique())
with fcol1:
    przekroj = st.selectbox("Przekrój", przekroje, index=idx(przekroje, "COICOP 1999"))

df_p = df[df["nazwa-przekroj"] == przekroj]

okresy = sorted(df_p["opis-okres"].dropna().unique())
with fcol2:
    okres = st.selectbox("Okres", okresy, index=idx(okresy, "styczeń - grudzień"))

df_p = df_p[df_p["opis-okres"] == okres]

prezentacje = sorted(df_p["sposob-prezentacji"].dropna().unique())
with fcol3:
    prezentacja = st.selectbox("Sposób prezentacji", prezentacje, index=idx(prezentacje, "analogiczny"))

df_p = df_p[df_p["sposob-prezentacji"] == prezentacja]

min_rok = int(df_p["id-rok"].min())
max_rok = int(df_p["id-rok"].max())
rok_od, rok_do = st.slider(
    "Zakres lat",
    min_value=min_rok,
    max_value=max_rok,
    value=(min_rok, max_rok),
)

df_filtered = df_p[df_p["id-rok"].between(rok_od, rok_do)]

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

# Jeśli jest kolumna opis-pozycja-3 z wieloma wartościami, agreguj średnią
if df_chart.groupby(["opis-pozycja-2", "id-rok"]).size().max() > 1:
    df_chart = (
        df_chart
        .groupby(["opis-pozycja-2", "id-rok"], as_index=False)["wartosc"]
        .mean()
    )

fig = px.line(
    df_chart,
    x="id-rok",
    y="wartosc",
    color="opis-pozycja-2",
    markers=True,
    labels={
        "id-rok": "Rok",
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
        df_chart.sort_values(["opis-pozycja-2", "id-rok"]),
        hide_index=True,
    )
