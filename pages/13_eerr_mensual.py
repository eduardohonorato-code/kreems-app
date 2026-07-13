"""
EERR Mensual & Análisis — Estado de Resultados mes a mes (Real, sin presupuesto)
con análisis vertical (% sobre ventas), análisis horizontal (variación mes a mes)
y análisis IA estructural con persona CFO.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from utils.auth import login, get_cc_sql_filter, requiere_acceso_total
from utils.db import query, guardar_reporte
from utils.components import (
    header, sidebar_kreems, fmt_mill, boton_excel, boton_excel_pct,
    get_soc_sql_filter, ETIQUETA_SOCIEDAD, MESES, MES_NUM_ACTUAL,
)
from utils.ai import generar_analisis_estructural

_ANO = date.today().year

st.set_page_config(page_title="EERR Mensual · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_acceso_total()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header(f"Estado de Resultados Mensual & Análisis — {_ANO}")

_ABREV = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

col_sel, _ = st.columns([1.4, 4])
with col_sel:
    meses_disp = [MESES[n] for n in range(1, MES_NUM_ACTUAL + 1)]
    mes_hasta_nom = st.selectbox("Mostrar hasta", meses_disp, index=len(meses_disp) - 1)

mes_hasta_num = [n for n, nom in MESES.items() if nom == mes_hasta_nom][0]
periodo_desde = f"{_ANO}-01"
periodo_hasta = f"{_ANO}-{mes_hasta_num:02d}"

filtro_soc = get_soc_sql_filter(sociedad_sel)
filtro_cc  = get_cc_sql_filter()

# ── DATOS: serie mensual REAL por clasificación ───────────────
df_raw = query(f"""
    SELECT
        periodo,
        clasificacion,
        SUM(valor_real) AS real
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta {filtro_soc} {filtro_cc}
    GROUP BY periodo, clasificacion
    ORDER BY periodo
""", {"desde": periodo_desde, "hasta": periodo_hasta})

if df_raw.empty:
    st.info("Sin datos para el periodo y filtros seleccionados.")
    st.stop()

_MESES_NUM  = list(range(1, mes_hasta_num + 1))
_PERIODOS   = [f"{_ANO}-{m:02d}" for m in _MESES_NUM]
_COL_LABELS = [_ABREV[m] for m in _MESES_NUM]
_CLASIFS    = ["INGRESO", "COSTO_VAR", "COSTO_FIJO", "OPEX", "FINANCIERO", "NO_OPERACIONAL"]


def _serie_mensual(clasif: str) -> list:
    """Valores REAL del mes (no acumulados) para cada periodo."""
    sub = df_raw[df_raw["clasificacion"] == clasif].set_index("periodo")["real"]
    return [float(sub.get(p, 0.0) or 0.0) for p in _PERIODOS]


# Matriz mensual por clasificación + subtotales derivados
M = {c: _serie_mensual(c) for c in _CLASIFS}
_n = len(_MESES_NUM)
M["UB"]   = [M["INGRESO"][i] - M["COSTO_VAR"][i] for i in range(_n)]
M["EBIT"] = [M["UB"][i] - M["COSTO_FIJO"][i] - M["OPEX"][i] for i in range(_n)]
M["UN"]   = [M["EBIT"][i] - M["FINANCIERO"][i] - M["NO_OPERACIONAL"][i] for i in range(_n)]

# Filas del P&L: (nombre, clave en M, es_subtotal)
_FILAS = [
    ("Ventas",                  "INGRESO",        False),
    ("Costo de Venta",          "COSTO_VAR",      False),
    ("Utilidad Bruta",          "UB",             True),
    ("Costo Fijo",              "COSTO_FIJO",     False),
    ("OPEX",                    "OPEX",           False),
    ("EBIT",                    "EBIT",           True),
    ("Gastos Financieros",      "FINANCIERO",     False),
    ("Gastos No Operacionales", "NO_OPERACIONAL", False),
    ("Utilidad Neta",           "UN",             True),
]
_SUB_IDX = [i for i, (_, _, s) in enumerate(_FILAS) if s]


def _estilo_sub(row):
    if row.name in _SUB_IDX:
        return ["font-weight:bold; background:#fdf5fb; color:#2d0050"] * len(row)
    return [""] * len(row)


st.caption(
    f"Valores **reales del mes** (no acumulados), sin presupuesto · {sociedad_sel} · Enero–{mes_hasta_nom}"
)

tab_mes, tab_cuenta, tab_vert, tab_horiz, tab_ia = st.tabs([
    "📅  Mes a Mes (Real)",
    "📒  Mes a Mes por Cuenta",
    "📊  Análisis Vertical",
    "↔️  Análisis Horizontal",
    "🤖  Análisis IA (CFO)",
])

# ╔══════════════════════════════════════════╗
# ║  TAB 1 — MES A MES (REAL)                ║
# ╚══════════════════════════════════════════╝
with tab_mes:
    rows = []
    for nombre, key, _sub in _FILAS:
        fila = {"Concepto": nombre}
        for lbl, val in zip(_COL_LABELS, M[key]):
            fila[lbl] = val
        fila["Total YTD"] = sum(M[key])
        rows.append(fila)
    df_mes = pd.DataFrame(rows)

    col_t, col_e = st.columns([4, 1])
    with col_t:
        st.markdown("##### Estado de Resultados mes a mes (Real)")
    with col_e:
        boton_excel({"EERR Mensual": df_mes}, f"EERR_Mensual_{periodo_hasta}")

    _cols_num = _COL_LABELS + ["Total YTD"]
    st.dataframe(
        df_mes.style
            .format({c: (lambda v: fmt_mill(v)) for c in _cols_num})
            .apply(_estilo_sub, axis=1),
        use_container_width=True, hide_index=True, height=360,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### Evolución mensual — Ventas vs Utilidad Neta")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=_COL_LABELS, y=[v / 1_000_000 for v in M["INGRESO"]],
        name="Ventas", marker_color="#c4007a", opacity=0.85,
        text=[f"${v/1_000_000:,.1f}M" for v in M["INGRESO"]],
        textposition="outside", textfont={"size": 10},
    ))
    fig.add_trace(go.Scatter(
        x=_COL_LABELS, y=[v / 1_000_000 for v in M["UN"]],
        name="Utilidad Neta", mode="lines+markers",
        line=dict(color="#0F6E56", width=2.5), marker=dict(size=7),
    ))
    fig.add_trace(go.Scatter(
        x=_COL_LABELS, y=[v / 1_000_000 for v in M["EBIT"]],
        name="EBIT", mode="lines+markers",
        line=dict(color="#2d0050", width=2, dash="dot"), marker=dict(size=6),
    ))
    fig.update_layout(
        height=340, margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", ticksuffix="M", gridcolor="#f5eef8", zeroline=True, zerolinecolor="#e8d8f0"),
        xaxis=dict(gridcolor="#f5eef8"),
        legend=dict(orientation="h", y=1.14, x=0, font=dict(size=11)),
        font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ╔══════════════════════════════════════════╗
# ║  TAB 2 — MES A MES POR CUENTA CONTABLE   ║
# ╚══════════════════════════════════════════╝
with tab_cuenta:
    st.markdown("##### Estado de Resultados mes a mes por Cuenta Contable (Real)")
    st.caption(
        f"Mismo detalle mensual, abierto por **cuenta contable** y agrupado por línea "
        f"del EERR · {ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)} · "
        f"Enero–{mes_hasta_nom}. Elige **Consolidado** en la barra lateral para ver "
        "ambas sociedades."
    )

    df_ctas = query(f"""
        SELECT periodo, codigo_cuenta, nombre_cuenta, clasificacion,
               SUM(valor_real) AS real
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :desde AND :hasta {filtro_soc} {filtro_cc}
        GROUP BY periodo, codigo_cuenta, nombre_cuenta, clasificacion
    """, {"desde": periodo_desde, "hasta": periodo_hasta})

    if df_ctas.empty:
        st.info("Sin datos para el periodo y filtros seleccionados.")
    else:
        df_ctas["Cuenta"] = (df_ctas["codigo_cuenta"] + " "
                             + df_ctas["nombre_cuenta"].fillna(""))
        piv_c = df_ctas.pivot_table(
            index=["clasificacion", "codigo_cuenta", "Cuenta"],
            columns="periodo", values="real", aggfunc="sum", fill_value=0.0)

        def _serie_idx(idx) -> list:
            return [float(piv_c.loc[idx, p]) if p in piv_c.columns else 0.0
                    for p in _PERIODOS]

        # Orden P&L: clasificación → (etiqueta del subtotal). Las claves "__"
        # son subtotales derivados (diferencias, no suma de cuentas).
        _GRUPOS = [
            ("INGRESO",        "Ventas"),
            ("COSTO_VAR",      "Costo de Venta"),
            ("__UB__",         "Utilidad Bruta"),
            ("COSTO_FIJO",     "Costo Fijo"),
            ("OPEX",           "OPEX"),
            ("__EBIT__",       "EBIT"),
            ("FINANCIERO",     "Gastos Financieros"),
            ("NO_OPERACIONAL", "Gastos No Operacionales"),
            ("__UN__",         "Utilidad Neta"),
        ]

        _z = [0.0] * _n
        cat, filas, sub_idx = {}, [], []

        def _add_fila(etiqueta, serie, es_sub):
            fila = {"Cuenta": etiqueta}
            for lbl, val in zip(_COL_LABELS, serie):
                fila[lbl] = val
            fila["Total YTD"] = sum(serie)
            if es_sub:
                sub_idx.append(len(filas))
            filas.append(fila)

        for clasif, label in _GRUPOS:
            if clasif == "__UB__":
                serie = [cat.get("INGRESO", _z)[i] - cat.get("COSTO_VAR", _z)[i]
                         for i in range(_n)]
                _add_fila(label, serie, True)
            elif clasif == "__EBIT__":
                ub = [cat.get("INGRESO", _z)[i] - cat.get("COSTO_VAR", _z)[i]
                      for i in range(_n)]
                serie = [ub[i] - cat.get("COSTO_FIJO", _z)[i] - cat.get("OPEX", _z)[i]
                         for i in range(_n)]
                _add_fila(label, serie, True)
            elif clasif == "__UN__":
                ub = [cat.get("INGRESO", _z)[i] - cat.get("COSTO_VAR", _z)[i]
                      for i in range(_n)]
                ebit = [ub[i] - cat.get("COSTO_FIJO", _z)[i] - cat.get("OPEX", _z)[i]
                        for i in range(_n)]
                serie = [ebit[i] - cat.get("FINANCIERO", _z)[i]
                         - cat.get("NO_OPERACIONAL", _z)[i] for i in range(_n)]
                _add_fila(label, serie, True)
            else:
                # Cuentas de la clasificación (orden por código), omitiendo las
                # que quedan en cero todo el periodo
                sub = piv_c[piv_c.index.get_level_values("clasificacion") == clasif]
                acc_sum = list(_z)
                for idx in sub.sort_index().index:
                    serie = _serie_idx(idx)
                    acc_sum = [acc_sum[i] + serie[i] for i in range(_n)]
                    if sum(serie) != 0:
                        _add_fila(idx[2], serie, False)  # idx[2] = etiqueta Cuenta
                cat[clasif] = acc_sum
                _add_fila(label, acc_sum, True)  # subtotal de la línea

        df_cuenta = pd.DataFrame(filas)
        _cols_num_c = _COL_LABELS + ["Total YTD"]

        col_tc, col_ec = st.columns([4, 1])
        with col_tc:
            st.markdown("##### Detalle por cuenta contable")
        with col_ec:
            boton_excel({"EERR Mensual x Cuenta": df_cuenta},
                        f"EERR_Mensual_Cuenta_{periodo_hasta}")

        def _estilo_sub_c(row):
            if row.name in sub_idx:
                return ["font-weight:bold; background:#fdf5fb; color:#2d0050"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_cuenta.style
                .format({c: (lambda v: fmt_mill(v)) for c in _cols_num_c})
                .apply(_estilo_sub_c, axis=1),
            use_container_width=True, hide_index=True, height=560,
        )

# ╔══════════════════════════════════════════╗
# ║  TAB 3 — ANÁLISIS VERTICAL               ║
# ╚══════════════════════════════════════════╝
with tab_vert:
    st.markdown("##### Análisis Vertical — cada línea como % de las Ventas")
    st.caption("Ventas = 100%. Muestra la estructura de costos y márgenes de cada mes.")

    rows_v = []
    for nombre, key, _sub in _FILAS:
        fila = {"Concepto": nombre}
        for i, lbl in enumerate(_COL_LABELS):
            ventas_i = M["INGRESO"][i]
            fila[lbl] = (M[key][i] / ventas_i * 100) if ventas_i else 0.0
        # YTD
        v_ytd = sum(M["INGRESO"])
        fila["YTD"] = (sum(M[key]) / v_ytd * 100) if v_ytd else 0.0
        rows_v.append(fila)
    df_v = pd.DataFrame(rows_v)

    col_tv, col_ev = st.columns([4, 1])
    with col_ev:
        boton_excel_pct({"Analisis Vertical": df_v}, f"EERR_Vertical_{periodo_hasta}")

    _cols_v = _COL_LABELS + ["YTD"]

    def _color_vert(row):
        # Subtotales (márgenes) en morado bold; resto normal
        if row.name in _SUB_IDX:
            return ["font-weight:bold; background:#fdf5fb; color:#2d0050"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_v.style
            .format({c: (lambda v: f"{v:.1f}%") for c in _cols_v})
            .apply(_color_vert, axis=1),
        use_container_width=True, hide_index=True, height=360,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### Evolución de la estructura de márgenes (% de ventas)")
    fig_v = go.Figure()
    for nombre, key, color in [
        ("Margen Bruto", "UB", "#9b59b6"),
        ("Margen EBIT",  "EBIT", "#2d0050"),
        ("Margen Neto",  "UN", "#0F6E56"),
    ]:
        serie = [(M[key][i] / M["INGRESO"][i] * 100) if M["INGRESO"][i] else 0.0
                 for i in range(_n)]
        fig_v.add_trace(go.Scatter(
            x=_COL_LABELS, y=serie, mode="lines+markers", name=nombre,
            line=dict(color=color, width=2.5), marker=dict(size=6),
        ))
    fig_v.update_layout(
        height=320, margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(ticksuffix="%", gridcolor="#f5eef8", zeroline=True, zerolinecolor="#e8d8f0"),
        xaxis=dict(gridcolor="#f5eef8"),
        legend=dict(orientation="h", y=1.14, x=0, font=dict(size=11)),
        font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"),
    )
    st.plotly_chart(fig_v, use_container_width=True)

# ╔══════════════════════════════════════════╗
# ║  TAB 3 — ANÁLISIS HORIZONTAL             ║
# ╚══════════════════════════════════════════╝
with tab_horiz:
    st.markdown("##### Análisis Horizontal — variación entre periodos")
    if _n < 2:
        st.info("Se necesitan al menos 2 meses con datos para el análisis horizontal.")
    else:
        modo_h = st.radio(
            "Comparar contra",
            ["Mes anterior", "Base (Enero)"],
            horizontal=True, key="modo_horiz",
        )
        st.caption(
            "Variación % de cada línea. " +
            ("Cada mes vs el mes inmediatamente anterior." if modo_h == "Mes anterior"
             else "Cada mes vs Enero (mes base).")
        )

        # Columnas de comparación: desde el 2º mes en adelante
        rows_h = []
        for nombre, key, _sub in _FILAS:
            fila = {"Concepto": nombre}
            serie = M[key]
            for i in range(1, _n):
                base = serie[i - 1] if modo_h == "Mes anterior" else serie[0]
                if modo_h == "Mes anterior":
                    col_lbl = f"{_COL_LABELS[i]} vs {_COL_LABELS[i-1]}"
                else:
                    col_lbl = f"{_COL_LABELS[i]} vs Ene"
                fila[col_lbl] = ((serie[i] - base) / abs(base) * 100) if base else 0.0
            rows_h.append(fila)
        df_h = pd.DataFrame(rows_h)
        _cols_h = [c for c in df_h.columns if c != "Concepto"]

        col_th, col_eh = st.columns([4, 1])
        with col_eh:
            boton_excel_pct({"Analisis Horizontal": df_h}, f"EERR_Horizontal_{periodo_hasta}")

        def _color_h(val):
            if not isinstance(val, (int, float)):
                return ""
            if val > 0:
                return "color:#0F6E56; font-weight:500"
            if val < 0:
                return "color:#cc0000; font-weight:500"
            return "color:#999"

        def _sub_h(row):
            if row.name in _SUB_IDX:
                return ["font-weight:bold; background:#fdf5fb"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_h.style
                .format({c: (lambda v: f"{v:+.1f}%") for c in _cols_h})
                .apply(_sub_h, axis=1)
                .map(_color_h, subset=_cols_h),
            use_container_width=True, hide_index=True, height=360,
        )
        st.caption("🟢 Verde = aumento vs base · 🔴 Rojo = disminución. "
                   "Recuerda: en costos un aumento no siempre es bueno.")

# ╔══════════════════════════════════════════╗
# ║  TAB 4 — ANÁLISIS IA (CFO)               ║
# ╚══════════════════════════════════════════╝
with tab_ia:
    st.markdown("##### Análisis IA — Estructura y Tendencia (visión CFO)")

    if "estruct_analisis_texto" not in st.session_state:
        st.session_state["estruct_analisis_texto"] = ""

    _datos_ia = {
        "sociedad":      sociedad_sel,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "mes_hasta":     mes_hasta_nom,
        "n_meses":       _n,
        "meses":         _COL_LABELS,
        "mensual": {
            "ventas": M["INGRESO"], "cv": M["COSTO_VAR"], "cf": M["COSTO_FIJO"],
            "opex": M["OPEX"], "fin": M["FINANCIERO"], "nooper": M["NO_OPERACIONAL"],
            "ub": M["UB"], "ebit": M["EBIT"], "un": M["UN"],
        },
        "ytd": {
            "ventas": sum(M["INGRESO"]), "cv": sum(M["COSTO_VAR"]), "cf": sum(M["COSTO_FIJO"]),
            "opex": sum(M["OPEX"]), "fin": sum(M["FINANCIERO"]), "nooper": sum(M["NO_OPERACIONAL"]),
            "ub": sum(M["UB"]), "ebit": sum(M["EBIT"]), "un": sum(M["UN"]),
        },
    }
    # Campos de compatibilidad para las KPI cards de Reportes Guardados
    _datos_ia["ventas_r"] = _datos_ia["ytd"]["ventas"]
    _datos_ia["ebit_r"]   = _datos_ia["ytd"]["ebit"]
    _datos_ia["un_r"]     = _datos_ia["ytd"]["un"]

    col_ia, col_cerrar, _ = st.columns([2, 1, 2])
    with col_ia:
        if st.button("Generar Análisis con IA", type="primary", use_container_width=True, key="btn_ia_estruct"):
            with st.spinner("Analizando estructura y tendencia con IA..."):
                st.session_state["estruct_analisis_texto"] = generar_analisis_estructural(_datos_ia)
                st.session_state["estruct_analisis_datos"] = _datos_ia

    if st.session_state["estruct_analisis_texto"]:
        with col_cerrar:
            if st.button("✕ Cerrar", use_container_width=True, key="estruct_cerrar"):
                st.session_state["estruct_analisis_texto"] = ""
                st.rerun()

    if st.session_state["estruct_analisis_texto"]:
        st.markdown(f"""
        <div style="background:#fafafa; border:1px solid #e2e8f0; border-left:4px solid #2d0050;
                    border-radius:8px; padding:20px 24px; margin-top:12px;
                    font-size:13px; line-height:1.8; color:#333; white-space:pre-wrap;">
{st.session_state["estruct_analisis_texto"]}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("**Guardar este análisis**")
            col_input, col_save = st.columns([4, 1])
            with col_input:
                titulo_rpt = st.text_input(
                    "Título",
                    value=f"EERR Estructural Ene–{mes_hasta_nom} · {sociedad_sel}",
                    label_visibility="collapsed", key="estruct_titulo_rpt",
                )
            with col_save:
                if st.button("Guardar", type="primary", use_container_width=True, key="estruct_guardar_btn"):
                    try:
                        guardar_reporte(
                            titulo=titulo_rpt, tipo="EERR_ESTRUCT",
                            periodo_desde=periodo_desde, periodo_hasta=periodo_hasta,
                            sociedad=sociedad_sel,
                            datos=st.session_state.get("estruct_analisis_datos", {}),
                            analisis=st.session_state["estruct_analisis_texto"],
                            creado_por=st.session_state.get("nombre", ""),
                        )
                        st.success("✓ Reporte guardado. Ve a **Reportes Guardados** para revisarlo.")
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
