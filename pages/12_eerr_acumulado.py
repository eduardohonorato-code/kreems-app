"""
EERR Acumulado — Estado de Resultados con progresión mes a mes (YTD).
Muestra cada línea del P&L acumulada desde Enero hasta cada mes, con
gráfico de evolución y análisis IA guardable (tipo 'EERR_ACUM').
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from utils.auth import login, get_cc_sql_filter, requiere_acceso_total
from utils.db import query, guardar_reporte
from utils.components import (
    header, sidebar_kreems, fmt_mill, boton_excel,
    get_soc_sql_filter, MESES, MES_NUM_ACTUAL,
)
from utils.ai import generar_analisis_eerr_acumulado

_ANO = date.today().year

st.set_page_config(page_title="EERR Acumulado · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_acceso_total()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header(f"Estado de Resultados Acumulado — {_ANO}")

# ── SELECTOR: acumular hasta qué mes ──────────────────────────
_ABREV = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}
col_sel, col_modo, _ = st.columns([1.4, 1.4, 3])
with col_sel:
    meses_disp = [MESES[n] for n in range(1, MES_NUM_ACTUAL + 1)]
    mes_hasta_nom = st.selectbox("Acumulado hasta", meses_disp, index=len(meses_disp) - 1)
with col_modo:
    modo = st.radio("Ver progresión en", ["Real", "Presupuesto"], horizontal=True)

mes_hasta_num = [n for n, nom in MESES.items() if nom == mes_hasta_nom][0]
periodo_desde = f"{_ANO}-01"
periodo_hasta = f"{_ANO}-{mes_hasta_num:02d}"

st.caption(
    f"Cada columna muestra el valor **acumulado** desde Enero hasta ese mes "
    f"({sociedad_sel}). La última columna es el total YTD."
)
st.markdown("<br>", unsafe_allow_html=True)

filtro_soc = get_soc_sql_filter(sociedad_sel)
filtro_cc  = get_cc_sql_filter()

# ── DATOS: serie mensual por clasificación ────────────────────
df_raw = query(f"""
    SELECT
        periodo,
        clasificacion,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta {filtro_soc} {filtro_cc}
    GROUP BY periodo, clasificacion
    ORDER BY periodo
""", {"desde": periodo_desde, "hasta": periodo_hasta})

if df_raw.empty:
    st.info("Sin datos para el periodo y filtros seleccionados.")
    st.stop()

# ── CONSTRUIR MATRICES ACUMULADAS ─────────────────────────────
_MESES_NUM = list(range(1, mes_hasta_num + 1))
_PERIODOS  = [f"{_ANO}-{m:02d}" for m in _MESES_NUM]
_COL_LABELS = [_ABREV[m] for m in _MESES_NUM]

_CLASIFS = ["INGRESO", "COSTO_VAR", "COSTO_FIJO", "OPEX", "FINANCIERO", "NO_OPERACIONAL"]


def _serie_acumulada(col: str) -> dict:
    """Retorna {clasif: [valores acumulados por mes]} para la columna real/ppto."""
    out = {}
    for clasif in _CLASIFS:
        sub = df_raw[df_raw["clasificacion"] == clasif].set_index("periodo")[col]
        mensual = [float(sub.get(p, 0.0) or 0.0) for p in _PERIODOS]
        acum, run = [], 0.0
        for v in mensual:
            run += v
            acum.append(run)
        out[clasif] = acum
    return out


cum_real = _serie_acumulada("real")
cum_ppto = _serie_acumulada("ppto")


def _derivados(cum: dict) -> dict:
    """Calcula subtotales del P&L por mes a partir de las clasificaciones acumuladas."""
    n = len(_MESES_NUM)
    ub   = [cum["INGRESO"][i]   - cum["COSTO_VAR"][i] for i in range(n)]
    ebit = [ub[i] - cum["COSTO_FIJO"][i] - cum["OPEX"][i] for i in range(n)]
    un   = [ebit[i] - cum["FINANCIERO"][i] - cum["NO_OPERACIONAL"][i] for i in range(n)]
    return {"UB": ub, "EBIT": ebit, "UN": un}


der_real = _derivados(cum_real)
der_ppto = _derivados(cum_ppto)

# ── KPI CARDS (YTD = última columna) ──────────────────────────
_i = len(_MESES_NUM) - 1   # índice del último mes acumulado
ventas_r, ventas_p = cum_real["INGRESO"][_i], cum_ppto["INGRESO"][_i]
ub_r, ub_p         = der_real["UB"][_i],      der_ppto["UB"][_i]
ebit_r, ebit_p     = der_real["EBIT"][_i],    der_ppto["EBIT"][_i]
un_r, un_p         = der_real["UN"][_i],      der_ppto["UN"][_i]

st.markdown(f"##### Resultado Acumulado YTD · Enero – {mes_hasta_nom}")
cols_kpi = st.columns(4)
_kpis = [
    ("Ventas",         ventas_r, ventas_p),
    ("Utilidad Bruta", ub_r,     ub_p),
    ("EBIT",           ebit_r,   ebit_p),
    ("Utilidad Neta",  un_r,     un_p),
]
for col, (label, r, p) in zip(cols_kpi, _kpis):
    var = r - p
    pct = (r / p * 100) if p else 0
    color = "#0F6E56" if var >= 0 else "#cc0000"
    icono = "↑" if var >= 0 else "↓"
    with col:
        st.markdown(f"""
        <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                    padding:16px 18px; text-align:center;">
            <div style="font-size:11px; color:#999; margin-bottom:6px;">{label} YTD Real vs Ppto</div>
            <div style="font-size:22px; font-weight:700; color:#2d0050;">${r/1_000_000:,.2f}M</div>
            <div style="font-size:12px; color:{color}; margin-top:4px;">
                {icono} {abs(var)/1_000_000:,.2f}M ({pct:.1f}%)</div>
            <div style="font-size:11px; color:#aaa;">Obj: ${p/1_000_000:,.2f}M</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── EXPORTAR P&L PRESUPUESTO vs REAL ──────────────────────────
with st.container(border=True):
    st.markdown("##### 📤 Exportar Estado de Resultados — Presupuesto vs Real")
    st.caption(
        "Excel con 3 hojas: P&L del **Presupuesto** mes a mes (12 meses), P&L **Real** "
        "mes a mes, y la **comparación acumulada YTD**. Ideal para ajustar el presupuesto "
        "viendo la desviación vs el real."
    )

    _MESES_EXP = [_ABREV[m] for m in range(1, 13)]
    _PL_DEF = [
        ("Ventas",                  "INGRESO",        "linea"),
        ("Costo de Venta",          "COSTO_VAR",      "linea"),
        ("Utilidad Bruta",          None,             "UB"),
        ("Costo Fijo",              "COSTO_FIJO",     "linea"),
        ("OPEX",                    "OPEX",           "linea"),
        ("EBIT",                    None,             "EBIT"),
        ("Gastos Financieros",      "FINANCIERO",     "linea"),
        ("Gastos No Operacionales", "NO_OPERACIONAL", "linea"),
        ("Utilidad Neta",           None,             "UN"),
    ]

    # P&L mensual de todo el año (presupuesto = 12 meses; real = meses con datos)
    df_full = query(f"""
        SELECT periodo, clasificacion,
               SUM(valor_real) AS real, SUM(valor_ppto) AS ppto
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :d AND :h {filtro_soc} {filtro_cc}
        GROUP BY periodo, clasificacion
    """, {"d": f"{_ANO}-01", "h": f"{_ANO}-12"})

    def _serie_full(col, clasif):
        if df_full.empty:
            return [0.0] * 12
        sub = df_full[df_full["clasificacion"] == clasif].set_index("periodo")[col]
        return [float(sub.get(f"{_ANO}-{m:02d}", 0) or 0) for m in range(1, 13)]

    def _pl_mensual(col):
        base = {c: _serie_full(col, c) for c in
                ["INGRESO", "COSTO_VAR", "COSTO_FIJO", "OPEX", "FINANCIERO", "NO_OPERACIONAL"]}
        ub   = [base["INGRESO"][i] - base["COSTO_VAR"][i] for i in range(12)]
        ebit = [ub[i] - base["COSTO_FIJO"][i] - base["OPEX"][i] for i in range(12)]
        un   = [ebit[i] - base["FINANCIERO"][i] - base["NO_OPERACIONAL"][i] for i in range(12)]
        deriv = {"UB": ub, "EBIT": ebit, "UN": un}
        rows = []
        for nombre, clasif, kind in _PL_DEF:
            serie = base[clasif] if kind == "linea" else deriv[kind]
            d = {"Concepto": nombre}
            for m in range(12):
                d[_MESES_EXP[m]] = serie[m]
            d["Total"] = sum(serie)
            rows.append(d)
        return pd.DataFrame(rows)

    df_ppto_m = _pl_mensual("ppto")
    df_real_m = _pl_mensual("real")

    # Acumulado YTD (hasta el mes seleccionado) Real vs Ppto
    ytd_rows = []
    for nombre, clasif, kind in _PL_DEF:
        if kind == "linea":
            rv, pv = cum_real[clasif][_i], cum_ppto[clasif][_i]
        else:
            rv, pv = der_real[kind][_i], der_ppto[kind][_i]
        ytd_rows.append({
            "Concepto": nombre, "Real YTD": rv, "Ppto YTD": pv,
            "Varianza": rv - pv, "% Ejec.": round(rv / pv * 100, 1) if pv else 0,
        })
    df_ytd = pd.DataFrame(ytd_rows)

    boton_excel(
        {"Ppto mensual": df_ppto_m,
         "Real mensual": df_real_m,
         f"Acum YTD a {mes_hasta_nom}": df_ytd},
        f"EERR_Presupuesto_vs_Real_{periodo_hasta}",
        label="⬇ Exportar P&L Ppto vs Real (Excel)",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── TABLA PROGRESIÓN MES A MES ────────────────────────────────
cum_sel = cum_real if modo == "Real" else cum_ppto
der_sel = der_real if modo == "Real" else der_ppto

# filas: (nombre, serie, es_subtotal)
_FILAS = [
    ("Ventas",                  cum_sel["INGRESO"],        False),
    ("Costo de Venta",          cum_sel["COSTO_VAR"],      False),
    ("Utilidad Bruta",          der_sel["UB"],             True),
    ("Costo Fijo",              cum_sel["COSTO_FIJO"],     False),
    ("OPEX",                    cum_sel["OPEX"],           False),
    ("EBIT",                    der_sel["EBIT"],           True),
    ("Gastos Financieros",      cum_sel["FINANCIERO"],     False),
    ("Gastos No Operacionales", cum_sel["NO_OPERACIONAL"], False),
    ("Utilidad Neta",           der_sel["UN"],             True),
]

rows = []
for nombre, serie, _sub in _FILAS:
    fila = {"Concepto": nombre}
    for lbl, val in zip(_COL_LABELS, serie):
        fila[lbl] = val
    rows.append(fila)

df_prog = pd.DataFrame(rows)
_sub_idx = [i for i, (_, _, s) in enumerate(_FILAS) if s]

col_tit, col_exp = st.columns([4, 1])
with col_tit:
    st.markdown(f"##### Progresión acumulada mes a mes — {modo}")
with col_exp:
    boton_excel({"EERR Acumulado": df_prog}, f"EERR_Acumulado_{periodo_hasta}_{modo}")


def _estilo_sub(row):
    if row.name in _sub_idx:
        return ["font-weight:bold; background:#fdf5fb; color:#2d0050"] * len(row)
    return [""] * len(row)


st.dataframe(
    df_prog.style
        .format({lbl: (lambda v: fmt_mill(v)) for lbl in _COL_LABELS})
        .apply(_estilo_sub, axis=1),
    use_container_width=True,
    hide_index=True,
    height=360,
)

st.markdown("<br>", unsafe_allow_html=True)

# ── GRÁFICO EVOLUCIÓN ACUMULADA ───────────────────────────────
st.markdown("##### Evolución acumulada del resultado (Real)")
_LINEAS = [
    ("Ventas",        cum_real["INGRESO"], "#c4007a"),
    ("Utilidad Bruta", der_real["UB"],     "#9b59b6"),
    ("EBIT",          der_real["EBIT"],    "#2d0050"),
    ("Utilidad Neta", der_real["UN"],      "#0F6E56"),
]
fig = go.Figure()
for nombre, serie, color in _LINEAS:
    fig.add_trace(go.Scatter(
        x=_COL_LABELS,
        y=[v / 1_000_000 for v in serie],
        mode="lines+markers",
        name=nombre,
        line=dict(color=color, width=2.5),
        marker=dict(size=6, color=color),
    ))
fig.update_layout(
    height=340,
    margin=dict(t=20, b=10, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    yaxis=dict(tickprefix="$", ticksuffix="M", gridcolor="#f5eef8", zeroline=True,
               zerolinecolor="#e8d8f0"),
    xaxis=dict(gridcolor="#f5eef8"),
    legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
    font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"),
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── ANÁLISIS IA ───────────────────────────────────────────────
st.markdown("---")
st.markdown("##### Análisis IA")

if "acum_analisis_texto" not in st.session_state:
    st.session_state["acum_analisis_texto"] = ""

# Datos para la IA: acumulados YTD (Real vs Ppto) + trayectoria mes a mes
_datos_ia = {
    "ventas_r": ventas_r, "ventas_p": ventas_p,
    "cv_r": cum_real["COSTO_VAR"][_i],   "cv_p": cum_ppto["COSTO_VAR"][_i],
    "cf_r": cum_real["COSTO_FIJO"][_i],  "cf_p": cum_ppto["COSTO_FIJO"][_i],
    "opex_r": cum_real["OPEX"][_i],      "opex_p": cum_ppto["OPEX"][_i],
    "fin_r": cum_real["FINANCIERO"][_i], "fin_p": cum_ppto["FINANCIERO"][_i],
    "nooper_r": cum_real["NO_OPERACIONAL"][_i], "nooper_p": cum_ppto["NO_OPERACIONAL"][_i],
    "ub_r": ub_r, "ub_p": ub_p,
    "ebit_r": ebit_r, "ebit_p": ebit_p,
    "un_r": un_r, "un_p": un_p,
    "periodo_desde": periodo_desde,
    "periodo_hasta": periodo_hasta,
    "sociedad": sociedad_sel,
    # Contexto acumulado específico de esta página
    "n_meses":   len(_MESES_NUM),
    "mes_hasta": mes_hasta_nom,
    "meses":     _COL_LABELS,
    "serie": {
        "ventas": cum_real["INGRESO"],
        "ub":     der_real["UB"],
        "ebit":   der_real["EBIT"],
        "un":     der_real["UN"],
    },
    "serie_ppto": {
        "ventas": cum_ppto["INGRESO"],
        "ub":     der_ppto["UB"],
        "ebit":   der_ppto["EBIT"],
        "un":     der_ppto["UN"],
    },
}

col_ia, col_cerrar, _ = st.columns([2, 1, 2])
with col_ia:
    if st.button("Generar Análisis con IA", type="primary", use_container_width=True, key="btn_ia_acum"):
        with st.spinner("Analizando datos acumulados con IA..."):
            st.session_state["acum_analisis_texto"] = generar_analisis_eerr_acumulado(_datos_ia)
            st.session_state["acum_analisis_datos"] = _datos_ia

if st.session_state["acum_analisis_texto"]:
    with col_cerrar:
        if st.button("✕ Cerrar", use_container_width=True, key="acum_cerrar"):
            st.session_state["acum_analisis_texto"] = ""
            st.rerun()

if st.session_state["acum_analisis_texto"]:
    st.markdown(f"""
    <div style="background:#fafafa; border:1px solid #e2e8f0; border-left:4px solid #2d0050;
                border-radius:8px; padding:20px 24px; margin-top:12px;
                font-size:13px; line-height:1.8; color:#333; white-space:pre-wrap;">
{st.session_state["acum_analisis_texto"]}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**Guardar este análisis**")
        col_input, col_save = st.columns([4, 1])
        with col_input:
            titulo_rpt = st.text_input(
                "Título",
                value=f"EERR Acumulado Ene–{mes_hasta_nom} · {sociedad_sel}",
                label_visibility="collapsed",
                key="acum_titulo_rpt",
            )
        with col_save:
            if st.button("Guardar", type="primary", use_container_width=True, key="acum_guardar_btn"):
                try:
                    guardar_reporte(
                        titulo=titulo_rpt, tipo="EERR_ACUM",
                        periodo_desde=periodo_desde, periodo_hasta=periodo_hasta,
                        sociedad=sociedad_sel,
                        datos=st.session_state.get("acum_analisis_datos", {}),
                        analisis=st.session_state["acum_analisis_texto"],
                        creado_por=st.session_state.get("nombre", ""),
                    )
                    st.success("✓ Reporte guardado. Ve a **Reportes Guardados** para revisarlo.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
