import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Dashboard CPI — GUS", layout="wide")


@st.cache_data
def load_data() -> pd.DataFrame:
    return pd.read_parquet("data/gus_data.parquet")


df = load_data()

st.title("Wskaźniki cen towarów i usług konsumpcyjnych")

# ---------------------------------------------------------------------------
# Sidebar — filtry
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filtry")

    przekroj = st.selectbox(
        "Przekrój",
        sorted(df["nazwa-przekroj"].dropna().unique()),
    )

    df_p = df[df["nazwa-przekroj"] == przekroj]

    okres = st.selectbox(
        "Okres",
        sorted(df_p["opis-okres"].dropna().unique()),
    )

    df_p = df_p[df_p["opis-okres"] == okres]

    prezentacja = st.selectbox(
        "Sposób prezentacji",
        sorted(df_p["sposob-prezentacji"].dropna().unique()),
    )

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
    poz1 = st.selectbox("Pozycja 1", pozycje, index=0)
with col2:
    poz2 = st.selectbox("Pozycja 2", pozycje, index=min(1, len(pozycje) - 1))

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
