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
    tcol, mcol, pcol, rcol = st.columns([1, 3, 2, 2])

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


if "n_slots" not in st.session_state:
    st.session_state.n_slots = 2


def render_slot_required(col, slot_key: str, n: int, default_przekroj_kw: str, default_poz_kw: str):
    with col:
        st.markdown(f"**Przekrój i wskaźnik ({n})**")
        pr_col, _ = st.columns([11, 1])
        with pr_col:
            pr = st.selectbox(
                f"Przekrój {n}",
                available_przekroje,
                index=idx(available_przekroje, default_przekroj_kw),
                key=f"{slot_key}_przekroj",
                label_visibility="collapsed",
            )
        pozycje = get_pozycje(pr)
        if not pozycje:
            st.warning("Brak pozycji dla tego przekroju.")
            return None, None
        poz_key = f"{slot_key}_poz"
        if poz_key not in st.session_state or st.session_state[poz_key] not in pozycje:
            st.session_state[poz_key] = pozycje[idx(pozycje, default_poz_kw)]
        p_col, btn_col = st.columns([11, 1], vertical_alignment="center")
        with p_col:
            poz = st.selectbox(f"Wskaźnik {n}", pozycje, key=poz_key, label_visibility="collapsed")
        with btn_col:
            st.button("↺", key=f"clear_{slot_key}", help="Wyczyść wskaźnik",
                      on_click=lambda k=poz_key, opts=pozycje: st.session_state.update({k: opts[0]}))
        return pr, poz


def render_slot_optional(col, slot_key: str, n: int, removable: bool = False,
                         default_przekroj_kw: str = "COICOP 1999", default_poz_kw: str | None = None):
    with col:
        poz_key = f"{slot_key}_poz"
        st.markdown(f"**Przekrój i wskaźnik ({n})**")
        pr_col, btn_col = st.columns([11, 1], vertical_alignment="center")
        with pr_col:
            pr = st.selectbox(
                f"Przekrój {n}",
                available_przekroje,
                index=idx(available_przekroje, default_przekroj_kw),
                key=f"{slot_key}_przekroj",
                label_visibility="collapsed",
            )
        with btn_col:
            if removable:
                def _remove(k=poz_key, pk=f"{slot_key}_przekroj"):
                    st.session_state.pop(k, None)
                    st.session_state.pop(pk, None)
                    st.session_state.n_slots -= 1
                st.button("✕", key=f"remove_{slot_key}", help="Usuń serię", on_click=_remove)
        pozycje_opt = [BRAK] + get_pozycje(pr)
        if poz_key not in st.session_state or st.session_state[poz_key] not in pozycje_opt:
            st.session_state[poz_key] = pozycje_opt[idx(pozycje_opt, default_poz_kw)] if default_poz_kw else BRAK
        p_col, btn_col = st.columns([11, 1], vertical_alignment="center")
        with p_col:
            poz = st.selectbox(f"Wskaźnik {n}", pozycje_opt, key=poz_key, label_visibility="collapsed")
        with btn_col:
            st.button("↺", key=f"clear_{slot_key}", help="Wyczyść wskaźnik",
                      disabled=(st.session_state.get(poz_key, BRAK) == BRAK),
                      on_click=lambda k=poz_key: st.session_state.update({k: BRAK}))
        if poz == BRAK:
            return None, None
        return pr, poz


r1c1, r1c2 = st.columns(2)
pr1, poz1 = render_slot_required(r1c1, "slot1", 1, "COICOP 2018", "062")
pr2, poz2 = render_slot_optional(r1c2, "slot2", 2, default_przekroj_kw="COICOP 1999", default_poz_kw="06.2.1")

pr3, poz3 = None, None
pr4, poz4 = None, None

if st.session_state.n_slots >= 3:
    r2c1, r2c2 = st.columns(2)
    pr3, poz3 = render_slot_optional(r2c1, "slot3", 3, removable=(st.session_state.n_slots == 3),
                                     default_przekroj_kw="COICOP 2018", default_poz_kw="064")
    if st.session_state.n_slots >= 4:
        pr4, poz4 = render_slot_optional(r2c2, "slot4", 4, removable=True,
                                         default_przekroj_kw="COICOP 2018", default_poz_kw="063")

if st.session_state.n_slots < 4:
    st.button("＋ Dodaj wskaźnik", key="add_slot",
              on_click=lambda: st.session_state.update({"n_slots": st.session_state.n_slots + 1}))

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

subtitle_parts = "  |  ".join(poz for _, poz in slots)

fig.update_layout(
    title=dict(
        text=f"{prezentacja}  |  {tryb}",
        font=dict(size=22),
        subtitle=dict(
            text=subtitle_parts,
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
