import base64
import io

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
    df = pd.read_parquet("data/gus_data.parquet")
    for col in df.select_dtypes("object").columns:
        df[col] = df[col].astype("category")
    return df


def idx(options: list, keyword: str) -> int:
    kw = keyword.lower()
    for i, o in enumerate(options):
        if kw in str(o).lower():
            return i
    return 0


def get_period_month_num(opis: str) -> int:
    opis_lower = opis.lower()
    result = 0
    for name, num in MONTH_ORDER.items():
        if name in opis_lower:
            result = max(result, num)
    return result


df = load_data()

with open("inflacja_dashboard.svg", "rb") as _f:
    _svg_b64 = base64.b64encode(_f.read()).decode()

img_col, title_col = st.columns([1, 4])
with img_col:
    st.markdown(
        f'<img src="data:image/svg+xml;base64,{_svg_b64}" style="width:100%;max-height:130px;object-fit:contain;">',
        unsafe_allow_html=True,
    )
with title_col:
    st.title("Wskaźniki cen towarów i usług konsumpcyjnych")

st.markdown("<div style='margin-bottom: 1.5rem'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filtry globalne
# ---------------------------------------------------------------------------

with st.expander("Filtry", expanded=False):
    tcol, mcol = st.columns([1, 2])
    with tcol:
        tryb = st.radio("Tryb okresu", ["Narastający", "Miesięczny"])
    with mcol:
        selected_months = st.multiselect("Miesiące", MONTH_NAMES, default=MONTH_NAMES)

    if tryb == "Narastający":
        df_t = df[df["opis-okres"].str.contains("miesiąc - dane narastające", na=False, case=False)]
    else:
        df_t = df[df["opis-okres"].str.contains("dane miesięczne", na=False, case=False)]

    if selected_months:
        nums = {MONTH_NAMES.index(m) + 1 for m in selected_months}
        df_t = df_t[df_t["opis-okres"].apply(get_period_month_num).isin(nums)]

    pcol, rcol = st.columns([1, 1])
    prezentacje = sorted(df_t["sposob-prezentacji"].dropna().unique())
    with pcol:
        prezentacja = st.selectbox(
            "Sposób prezentacji", prezentacje, index=idx(prezentacje, "analogiczny")
        )

    df_prez = df_t[df_t["sposob-prezentacji"] == prezentacja]

    min_rok = int(df_prez["id-rok"].min())
    max_rok = int(df_prez["id-rok"].max())
    with rcol:
        if min_rok < max_rok:
            rok_od, rok_do = st.slider(
                "Zakres lat",
                min_value=min_rok,
                max_value=max_rok,
                value=(min_rok, max_rok),
                key=f"slider_lat_{min_rok}_{max_rok}",
            )
        else:
            st.text_input("Zakres lat", value=str(min_rok), disabled=True)
            rok_od, rok_do = min_rok, max_rok

df_base = df_prez[df_prez["id-rok"].between(rok_od, rok_do)].copy()
available_przekroje = sorted(df_base["nazwa-przekroj"].dropna().unique())

# ---------------------------------------------------------------------------
# Sloty wyboru pozycji — przekrój + pozycja, 2×2
# ---------------------------------------------------------------------------

BRAK = "- brak -"


def get_pozycje(przekroj: str) -> list[str]:
    return sorted(
        df_base[df_base["nazwa-przekroj"] == przekroj]["opis-pozycja-2"].dropna().unique()
    )


def render_slot_required(col, slot_key: str, default_przekroj_kw: str, default_poz_kw: str):
    with col:
        pr = st.selectbox(
            "Przekrój",
            available_przekroje,
            index=idx(available_przekroje, default_przekroj_kw),
            key=f"{slot_key}_przekroj",
        )
        pozycje = get_pozycje(pr)
        if not pozycje:
            st.warning("Brak pozycji dla tego przekroju.")
            return None, None
        p_col, _ = st.columns([11, 1])
        with p_col:
            poz = st.selectbox(
                "Pozycja 1",
                pozycje,
                index=idx(pozycje, default_poz_kw),
                key=f"{slot_key}_poz",
            )
        return pr, poz


def render_slot_optional(col, slot_key: str, label: str):
    with col:
        poz_key = f"{slot_key}_poz"
        pr = st.selectbox(
            "Przekrój",
            available_przekroje,
            index=idx(available_przekroje, "COICOP 1999"),
            key=f"{slot_key}_przekroj",
        )
        pozycje_opt = [BRAK] + get_pozycje(pr)
        p_col, btn_col = st.columns([11, 1])
        with p_col:
            poz = st.selectbox(label, pozycje_opt, key=poz_key)
        with btn_col:
            st.markdown('<div style="margin-top: 1.75rem"></div>', unsafe_allow_html=True)
            st.button(
                "✕", key=f"clear_{slot_key}",
                help="Wyczyść",
                disabled=(poz == BRAK),
                on_click=lambda k=poz_key: st.session_state.update({k: BRAK}),
            )
        if poz == BRAK:
            return None, None
        return pr, poz


r1c1, r1c2 = st.columns(2)
r2c1, r2c2 = st.columns(2)

pr1, poz1 = render_slot_required(r1c1, "slot1", "COICOP 1999", "Usługi lekarskie")
pr2, poz2 = render_slot_optional(r1c2, "slot2", "Pozycja 2")
pr3, poz3 = render_slot_optional(r2c1, "slot3", "Pozycja 3")
pr4, poz4 = render_slot_optional(r2c2, "slot4", "Pozycja 4")

slots = [(pr, poz) for pr, poz in [(pr1, poz1), (pr2, poz2), (pr3, poz3), (pr4, poz4)] if pr and poz]

if not slots:
    st.warning("Wybierz co najmniej jedną pozycję.")
    st.stop()

# ---------------------------------------------------------------------------
# Zbieranie danych z aktywnych slotów
# ---------------------------------------------------------------------------

multi_przekroj = len({pr for pr, _ in slots}) > 1

frames = []
for pr, poz in slots:
    df_slot = df_base[
        (df_base["nazwa-przekroj"] == pr) &
        (df_base["opis-pozycja-2"] == poz)
    ].copy()
    df_slot["_label"] = f"{poz} ({pr})" if multi_przekroj else poz
    frames.append(df_slot)

df_chart = pd.concat(frames, ignore_index=True)

df_chart["month_num"] = df_chart["opis-okres"].apply(get_period_month_num)
df_chart["date"] = pd.to_datetime(
    df_chart["id-rok"].astype(str) + "-" + df_chart["month_num"].astype(str).str.zfill(2),
    format="%Y-%m",
)

group_cols = ["_label", "date"]
if df_chart.groupby(group_cols).size().max() > 1:
    df_chart = df_chart.groupby(group_cols, as_index=False)["wartosc"].mean()

df_chart = df_chart.sort_values(group_cols)

# ---------------------------------------------------------------------------
# Wykres
# ---------------------------------------------------------------------------

if df_chart.empty:
    st.warning("Brak danych dla wybranych pozycji.")
    st.stop()

show_labels = st.toggle("Etykiety na wykresie", value=True)

if show_labels:
    n_points = df_chart.groupby("_label").size().max()
    step = max(1, n_points // 12)
    df_chart["_rank"] = df_chart.groupby("_label").cumcount()
    df_chart["_text"] = df_chart.apply(
        lambda r: str(round(r["wartosc"], 1)) if r["_rank"] % step == 0 else "", axis=1
    )
    text_col = "_text"
else:
    text_col = None

df_chart["_date_label"] = df_chart["date"].apply(
    lambda d: f"{MONTH_NAMES[d.month - 1]} {d.year}"
)

fig = px.line(
    df_chart,
    x="date",
    y="wartosc",
    color="_label",
    markers=True,
    text=text_col,
    custom_data=["_date_label", "wartosc", "_label"],
    labels={
        "date": "Data",
        "wartosc": "Wartość",
        "_label": "Pozycja",
    },
)
if show_labels:
    fig.update_traces(textposition="top center")
fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[2]}</b><br>"
        "%{customdata[0]}<br>"
        "Wartość: <b>%{customdata[1]:.1f}</b>"
        "<extra></extra>"
    )
)

title_parts = " | ".join(f"{poz} ({pr})" if multi_przekroj else poz for pr, poz in slots)
subtitle = f"{tryb}  |  {prezentacja}"

fig.update_layout(
    title=dict(
        text=title_parts,
        font=dict(size=22),
        subtitle=dict(
            text=subtitle,
            font=dict(size=13),
        ),
    ),
    legend=dict(orientation="h", yanchor="bottom", y=-0.3),
)

st.plotly_chart(fig)

# ---------------------------------------------------------------------------
# Dane źródłowe + eksport Excel
# ---------------------------------------------------------------------------

with st.expander("Dane źródłowe"):
    df_export = df_chart[["_label", "date", "wartosc"]].copy()
    df_export["date"] = df_export["date"].dt.date
    df_export["sposob_prezentacji"] = prezentacja
    df_export["tryb_okresu"] = tryb
    df_export = df_export.rename(columns={
        "_label": "pozycja",
        "date": "data",
        "wartosc": "wartosc",
    })
    df_export = df_export[["tryb_okresu", "sposob_prezentacji", "pozycja", "data", "wartosc"]]

    buf = io.BytesIO()
    df_export.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        label="Pobierz Excel",
        data=buf.getvalue(),
        file_name="dane_gus.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.dataframe(df_export.sort_values(["pozycja", "data"]), hide_index=True)
