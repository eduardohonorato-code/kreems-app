"""
EERR — Estado de Resultados Real vs Presupuesto
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date
from utils.auth import login, get_cc_sql_filter, requiere_acceso_total
from utils.db import query, guardar_reporte
from utils.components import (
    header, selector_meses, sidebar_kreems, fmt_clp, fmt_mill,
    badge_html, boton_excel, semaforo_texto, semaforo_style_cell,
    get_soc_sql_filter, NOMBRES_CC,
)
from utils.ai import generar_analisis_eerr
from utils.pdf_report import generar_pdf_eerr

_ANO = date.today().year

st.set_page_config(page_title="Estado de Resultados · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_acceso_total()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header(f"Estado de Resultados — Real vs Presupuesto {_ANO}")
periodo_desde, periodo_hasta = selector_meses(key="eerr")
st.markdown("<br>", unsafe_allow_html=True)

filtro_soc = get_soc_sql_filter(sociedad_sel)
filtro_cc  = get_cc_sql_filter()

# ── DATOS RAW ────────────────────────────────────────────────
df_raw = query(f"""
    SELECT
        clasificacion,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta {filtro_soc} {filtro_cc}
    GROUP BY clasificacion
""", {"desde": periodo_desde, "hasta": periodo_hasta})

# ── HELPER ───────────────────────────────────────────────────
def get_val(df, clasif, col):
    row = df[df["clasificacion"] == clasif]
    return float(row[col].iloc[0]) if not row.empty else 0.0

ventas_r  = get_val(df_raw, "INGRESO",        "real")
ventas_p  = get_val(df_raw, "INGRESO",        "ppto")
cv_r      = get_val(df_raw, "COSTO_VAR",      "real")
cv_p      = get_val(df_raw, "COSTO_VAR",      "ppto")
cf_r      = get_val(df_raw, "COSTO_FIJO",     "real")
cf_p      = get_val(df_raw, "COSTO_FIJO",     "ppto")
opex_r    = get_val(df_raw, "OPEX",           "real")
opex_p    = get_val(df_raw, "OPEX",           "ppto")
fin_r     = get_val(df_raw, "FINANCIERO",     "real")
fin_p     = get_val(df_raw, "FINANCIERO",     "ppto")
nooper_r  = get_val(df_raw, "NO_OPERACIONAL", "real")
nooper_p  = get_val(df_raw, "NO_OPERACIONAL", "ppto")

ub_r   = ventas_r - cv_r
ub_p   = ventas_p - cv_p
ebit_r = ub_r - cf_r - opex_r
ebit_p = ub_p - cf_p - opex_p
un_r   = ebit_r - fin_r - nooper_r
un_p   = ebit_p - fin_p - nooper_p

def pct(r, p):
    return (r / p * 100) if p else 0.0

def var(r, p):
    return r - p

# ── KPI CARDS ────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

cards = [
    ("Ventas",         ventas_r, ventas_p),
    ("Utilidad Bruta", ub_r,     ub_p),
    ("EBIT",           ebit_r,   ebit_p),
    ("% EBIT",         None,     None),
]

for col, (label, real, ppto_v) in zip([col1, col2, col3, col4], cards):
    with col:
        if label == "% EBIT":
            pct_ebit_r = (ebit_r / ventas_r * 100) if ventas_r else 0
            pct_ebit_p = (ebit_p / ventas_p * 100) if ventas_p else 0
            diff = pct_ebit_r - pct_ebit_p
            color = "#0F6E56" if diff >= 0 else "#cc0000"
            icono = "↑" if diff >= 0 else "↓"
            st.markdown(f"""
            <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                        padding:16px 18px; text-align:center;">
                <div style="font-size:11px; color:#999; margin-bottom:6px;">% EBIT Real vs Obj</div>
                <div style="font-size:22px; font-weight:700; color:#2d0050;">{pct_ebit_r:.2f}%</div>
                <div style="font-size:12px; color:{color}; margin-top:4px;">
                    {icono} {abs(diff):.2f}pp vs obj {pct_ebit_p:.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            variacion = var(real, ppto_v)
            pct_v     = pct(real, ppto_v)
            color = "#0F6E56" if variacion >= 0 else "#cc0000"
            icono = "↑" if variacion >= 0 else "↓"
            st.markdown(f"""
            <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                        padding:16px 18px; text-align:center;">
                <div style="font-size:11px; color:#999; margin-bottom:6px;">{label} Real vs Ppto</div>
                <div style="font-size:22px; font-weight:700; color:#2d0050;">
                    ${real/1_000_000:,.2f}M</div>
                <div style="font-size:12px; color:{color}; margin-top:4px;">
                    {icono} {abs(variacion)/1_000_000:,.2f}M ({pct_v:.1f}%)</div>
                <div style="font-size:11px; color:#aaa;">Obj: ${ppto_v/1_000_000:,.2f}M</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── CONSTRUIR df_eerr (necesario antes de los tabs) ──────────
filas = [
    ("Ventas",                  ventas_r, ventas_p, False, False),
    ("Costo de Venta",          cv_r,     cv_p,     True,  False),
    ("Utilidad Bruta",          ub_r,     ub_p,     False, True),
    ("Costo Fijo",              cf_r,     cf_p,     True,  False),
    ("OPEX",                    opex_r,   opex_p,   True,  False),
    ("EBIT",                    ebit_r,   ebit_p,   False, True),
    ("Gastos Financieros",      fin_r,    fin_p,    True,  False),
    ("Gastos No Operacionales", nooper_r, nooper_p, True,  False),
    ("Utilidad Neta",           un_r,     un_p,     False, True),
]

rows = []
for nombre, r, p, inv, es_subtotal in filas:
    variacion = r - p
    pct_v     = (r / p * 100) if p else 0
    rows.append({
        "Concepto":    nombre,
        "Real":        r,
        "Presupuesto": p,
        "Varianza":    variacion,
        "% Ejec.":     pct_v,
        "_subtotal":   es_subtotal,
        "_inv":        inv,
    })

df_eerr = pd.DataFrame(rows)
subtotales_idx = df_eerr.index[df_eerr["_subtotal"]].tolist()
df_show = df_eerr.drop(columns=["_subtotal", "_inv"])

# ── VARIANZAS para el puente ──────────────────────────────────
dv      = ventas_r - ventas_p          # favorable si > 0 (más ingresos)
dcv     = -(cv_r - cv_p)               # favorable si > 0 (menos costo)
dcf     = -(cf_r - cf_p)               # favorable si > 0 (menos costo)
dopex   = -(opex_r - opex_p)           # favorable si > 0 (menos gasto)
dfin    = -(fin_r - fin_p)             # favorable si > 0 (menos gasto)
dnooper = -(nooper_r - nooper_p)       # favorable si > 0 (menos gasto)
var_total = un_r - un_p

# ── GRÁFICO PUENTE (se construye aquí para usarlo también en PDF) ─
_bridge_labels  = [
    "Ppto\nU. Neta", "△ Ventas", "△ Costo\nVar.",
    "△ Costo\nFijo", "△ OPEX", "△ G.\nFin.",
    "△ G. No\nOper.", "Real\nU. Neta",
]
_bridge_measure = ["absolute","relative","relative","relative","relative","relative","relative","total"]
_bridge_values  = [un_p, dv, dcv, dcf, dopex, dfin, dnooper, un_r]

fig_bridge = go.Figure(go.Waterfall(
    orientation="v", measure=_bridge_measure,
    x=_bridge_labels, y=[v/1_000_000 for v in _bridge_values],
    connector={"line":{"color":"#e0c8e8","width":1,"dash":"dot"}},
    increasing={"marker":{"color":"#0F6E56","line":{"color":"#0a5240","width":1}}},
    decreasing={"marker":{"color":"#c4007a","line":{"color":"#8f005a","width":1}}},
    totals={"marker":{"color":"#2d0050","line":{"color":"#1a0030","width":1}}},
    texttemplate="%{y:+.2f}M", textfont={"size":11,"color":"#333"}, textposition="outside",
))
fig_bridge.update_layout(
    height=420, margin=dict(t=30,b=20,l=10,r=10),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    yaxis=dict(tickprefix="$",ticksuffix="M",gridcolor="#f5eef8",zeroline=True,zerolinecolor="#d8c8e8",zerolinewidth=1.5),
    xaxis=dict(tickfont={"size":10}), showlegend=False,
    font=dict(family="Inter, Arial, sans-serif",size=11,color="#555"),
)

# ── TABS PRINCIPALES ─────────────────────────────────────────
tab_pl, tab_bridge, tab_comp = st.tabs([
    "📋  P&L",
    "📊  Puente de Varianzas",
    "📈  Composición del Resultado",
])

# ╔══════════════════════════════════════════╗
# ║  TAB 1 — P&L                             ║
# ╚══════════════════════════════════════════╝
with tab_pl:
    col_tit_pl, col_exp_pl = st.columns([4, 1])
    with col_tit_pl:
        st.markdown("##### Estado de Resultados")
    with col_exp_pl:
        boton_excel(
            {"EERR": df_show},
            f"EERR_{periodo_desde}_{periodo_hasta}",
        )

    def color_fila_idx(row):
        if row.name in subtotales_idx:
            return ["font-weight:bold; background:#fdf5fb; color:#2d0050"] * len(row)
        return [""] * len(row)

    def color_varianza(val):
        if not isinstance(val, (int, float)):
            return ""
        return "color:#0F6E56;font-weight:500" if val >= 0 else "color:#cc0000;font-weight:500"

    def color_pct(val):
        if not isinstance(val, (int, float)):
            return ""
        return "color:#0F6E56" if val <= 100 else "color:#cc0000; font-weight:600"

    st.dataframe(
        df_show.style
            .format({
                "Real":        lambda v: fmt_clp(v),
                "Presupuesto": lambda v: fmt_clp(v),
                "Varianza":    lambda v: fmt_clp(v),
                "% Ejec.":     lambda v: f"{v:.1f}%"
            })
            .apply(color_fila_idx, axis=1)
            .map(color_varianza, subset=["Varianza"])
            .map(color_pct, subset=["% Ejec."]),
        use_container_width=True,
        hide_index=True,
        height=380,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Ratios financieros ────────────────────────────────────
    st.markdown("##### Ratios Financieros")
    ratios = [
        ("Margen Bruto",  (ub_r / ventas_r * 100) if ventas_r else 0,
                          (ub_p / ventas_p * 100) if ventas_p else 0),
        ("Margen EBIT",   (ebit_r / ventas_r * 100) if ventas_r else 0,
                          (ebit_p / ventas_p * 100) if ventas_p else 0),
        ("Margen Neto",   (un_r / ventas_r * 100) if ventas_r else 0,
                          (un_p / ventas_p * 100) if ventas_p else 0),
        ("OPEX / Ventas", (opex_r / ventas_r * 100) if ventas_r else 0,
                          (opex_p / ventas_p * 100) if ventas_p else 0),
        ("CV / Ventas",   (cv_r / ventas_r * 100) if ventas_r else 0,
                          (cv_p / ventas_p * 100) if ventas_p else 0),
    ]
    cols_r = st.columns(len(ratios))
    for col, (nombre, r_val, p_val) in zip(cols_r, ratios):
        diff = r_val - p_val
        inv  = nombre in ("OPEX / Ventas", "CV / Ventas")
        ok   = (diff <= 0) if inv else (diff >= 0)
        color = "#0F6E56" if ok else "#cc0000"
        icono = "↓" if diff < 0 else "↑"
        with col:
            st.markdown(f"""
            <div style="background:#f5f7fa; border-radius:10px; padding:10px 12px;
                        text-align:center; border:1px solid #e2e8f0;">
                <div style="font-size:10px; color:#888; margin-bottom:4px;">{nombre}</div>
                <div style="font-size:16px; font-weight:700; color:#2d0050;">{r_val:.1f}%</div>
                <div style="font-size:10px; color:{color};">{icono} {abs(diff):.1f}pp</div>
                <div style="font-size:10px; color:#aaa;">Obj: {p_val:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)

    # ── DRILL-DOWN POR LÍNEA P&L ──────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("##### 🔍 Drill-down por Línea del P&L")
    st.caption("Selecciona una línea para ver el desglose de cuentas contables que la componen.")

    # Mapping línea P&L → clasificacion en BD
    _LINEAS_DRILL = {
        "— Selecciona una línea —": None,
        "Ventas":                    "INGRESO",
        "Costo de Venta":            "COSTO_VAR",
        "Costo Fijo":                "COSTO_FIJO",
        "OPEX":                      "OPEX",
        "Gastos Financieros":        "FINANCIERO",
        "Gastos No Operacionales":   "NO_OPERACIONAL",
    }
    _NOMBRES_CC = NOMBRES_CC

    linea_sel = st.selectbox(
        "Línea",
        list(_LINEAS_DRILL.keys()),
        label_visibility="collapsed",
        key="eerr_drill_linea",
    )
    clasif_drill = _LINEAS_DRILL[linea_sel]

    if clasif_drill:
        df_drill = query(f"""
            SELECT
                dc.nombre_cuenta,
                vw.codigo_cc,
                SUM(vw.valor_real) AS real,
                SUM(vw.valor_ppto) AS ppto
            FROM marts.vw_real_vs_ppto vw
            JOIN master.dim_cuentas dc ON dc.codigo_cuenta = vw.codigo_cuenta
            WHERE vw.periodo BETWEEN :desde AND :hasta
              AND vw.clasificacion = :clasif
              {filtro_soc}
            GROUP BY dc.nombre_cuenta, vw.codigo_cc
            ORDER BY SUM(vw.valor_real) DESC
        """, {"desde": periodo_desde, "hasta": periodo_hasta, "clasif": clasif_drill})

        if df_drill.empty:
            st.info("Sin detalle de cuentas para esta línea en el período seleccionado.")
        else:
            df_drill["variacion"] = df_drill["real"] - df_drill["ppto"]
            df_drill["pct"]       = (df_drill["real"] / df_drill["ppto"] * 100).round(1).fillna(0)
            df_drill["estado"]    = df_drill["pct"].apply(semaforo_texto)
            df_drill["cc_nombre"] = df_drill["codigo_cc"].map(_NOMBRES_CC).fillna(df_drill["codigo_cc"])

            col_drill_tbl, col_drill_chart = st.columns([3, 2])

            with col_drill_tbl:
                # totales
                tot_r = df_drill["real"].sum()
                tot_p = df_drill["ppto"].sum()
                tot_pct = round(tot_r / tot_p * 100, 1) if tot_p else 0
                total_dr = pd.DataFrame([{
                    "nombre_cuenta": "TOTAL", "cc_nombre": "",
                    "real": tot_r, "ppto": tot_p,
                    "variacion": tot_r - tot_p,
                    "pct": tot_pct, "estado": semaforo_texto(tot_pct),
                }])
                df_drill_show = pd.concat(
                    [df_drill[["nombre_cuenta","cc_nombre","real","ppto","variacion","pct","estado"]], total_dr],
                    ignore_index=True,
                ).rename(columns={
                    "nombre_cuenta": "Cuenta Contable", "cc_nombre": "CC",
                    "real": "Real", "ppto": "Presupuesto",
                    "variacion": "Varianza", "pct": "% Ejec.", "estado": "Estado",
                })

                def _dv(val):
                    if not isinstance(val, (int, float)): return ""
                    return "color:#0F6E56;font-weight:500" if val <= 0 else "color:#cc0000;font-weight:500"
                def _dp(val):
                    if not isinstance(val, (int, float)): return ""
                    return semaforo_style_cell(val)
                def _dtot(row):
                    if row["Cuenta Contable"] == "TOTAL":
                        return ["font-weight:bold;background:#fdf5fb"] * len(row)
                    return [""] * len(row)

                st.dataframe(
                    df_drill_show.style
                        .format({
                            "Real":        lambda v: fmt_mill(v),
                            "Presupuesto": lambda v: fmt_mill(v),
                            "Varianza":    lambda v: fmt_mill(v),
                            "% Ejec.":     lambda v: f"{v:.1f}%" if isinstance(v, float) else v,
                        })
                        .apply(_dtot, axis=1)
                        .map(_dv,  subset=["Varianza"])
                        .map(_dp,  subset=["% Ejec."]),
                    use_container_width=True,
                    hide_index=True,
                    height=min(40 + 35 * len(df_drill_show), 450),
                    column_config={"Estado": st.column_config.TextColumn("Estado", width="small")},
                )

            with col_drill_chart:
                # Top 8 cuentas por monto real
                df_top = df_drill.nlargest(8, "real").copy()
                df_top["label"] = df_top.apply(
                    lambda r: f"{r['nombre_cuenta'][:22]}<br>({r['cc_nombre']})", axis=1
                )
                colores_bar = ["#cc0000" if p > 100 else ("#d97706" if p >= 90 else "#c4007a")
                               for p in df_top["pct"]]
                fig_drill = go.Figure()
                fig_drill.add_trace(go.Bar(
                    y=df_top["label"],
                    x=df_top["real"] / 1_000_000,
                    orientation="h",
                    marker_color=colores_bar,
                    opacity=0.88,
                    text=(df_top["real"] / 1_000_000).apply(lambda v: f"${v:.2f}M"),
                    textposition="outside",
                    textfont={"size": 10},
                ))
                fig_drill.add_trace(go.Scatter(
                    y=df_top["label"],
                    x=df_top["ppto"] / 1_000_000,
                    mode="markers",
                    name="Ppto",
                    marker=dict(symbol="line-ns", size=14, color="#2d0050",
                                line=dict(width=2, color="#2d0050")),
                ))
                fig_drill.update_layout(
                    height=max(250, 40 + 38 * len(df_top)),
                    margin=dict(t=10, b=10, l=10, r=70),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(tickprefix="$", ticksuffix="M",
                               gridcolor="#f5eef8", zeroline=False),
                    yaxis=dict(gridcolor="#f5eef8", autorange="reversed"),
                    showlegend=False,
                    font=dict(family="Inter, Arial, sans-serif", size=10, color="#555"),
                )
                st.plotly_chart(fig_drill, use_container_width=True)

# ╔══════════════════════════════════════════╗
# ║  TAB 2 — PUENTE DE VARIANZAS             ║
# ╚══════════════════════════════════════════╝
with tab_bridge:
    color_tot = "#0F6E56" if var_total >= 0 else "#cc0000"
    signo_tot = "+" if var_total >= 0 else ""

    st.markdown("##### Puente de Varianzas — Presupuesto → Real (Utilidad Neta)")
    st.caption(
        "Muestra cómo cada línea del P&L contribuyó a la diferencia entre la "
        "Utilidad Neta presupuestada y la real. 🟢 Verde = impacto favorable · 🔴 Rosa = impacto desfavorable."
    )
    st.markdown("<br>", unsafe_allow_html=True)

    col_chart, col_detalle = st.columns([3, 2])

    with col_chart:
        st.plotly_chart(fig_bridge, use_container_width=True)

    with col_detalle:
        st.markdown("**Detalle de contribuciones**")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        detalles = [
            ("Ventas",           dv,      "Más ingresos" if dv >= 0 else "Menos ingresos"),
            ("Costo Variable",   dcv,     "Menor costo"  if dcv >= 0 else "Mayor costo"),
            ("Costo Fijo",       dcf,     "Menor costo"  if dcf >= 0 else "Mayor costo"),
            ("OPEX",             dopex,   "Menor gasto"  if dopex >= 0 else "Mayor gasto"),
            ("G. Financieros",   dfin,    "Menor gasto"  if dfin >= 0 else "Mayor gasto"),
            ("G. No Operac.",    dnooper, "Menor gasto"  if dnooper >= 0 else "Mayor gasto"),
        ]

        for nombre, val, desc in detalles:
            color  = "#0F6E56" if val >= 0 else "#c4007a"
            signo  = "+" if val >= 0 else ""
            icono  = "▲" if val >= 0 else "▼"
            bg     = "rgba(15,110,86,0.06)" if val >= 0 else "rgba(196,0,122,0.06)"
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center;
                        padding:9px 12px; margin-bottom:5px;
                        background:{bg}; border-radius:8px;
                        border-left:3px solid {color};">
                <div>
                    <div style="font-size:12px; font-weight:600; color:#333;">{nombre}</div>
                    <div style="font-size:10px; color:{color};">{icono} {desc}</div>
                </div>
                <div style="font-size:14px; font-weight:700; color:{color};">
                    {signo}${val/1_000_000:,.2f}M
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Total varianza
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center;
                    padding:12px 14px; border-radius:10px;
                    background:#f5f0fb; border:1.5px solid #2d0050;">
            <div>
                <div style="font-size:12px; color:#888; font-weight:600;">VARIANZA TOTAL</div>
                <div style="font-size:10px; color:#888;">Utilidad Neta Real vs Presupuesto</div>
            </div>
            <div style="font-size:18px; font-weight:800; color:{color_tot};">
                {signo_tot}${var_total/1_000_000:,.2f}M
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        # Mini tabla contexto
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; padding:6px 14px;
                    background:#fafafa; border-radius:8px; border:1px solid #e2e8f0;">
            <div style="text-align:center;">
                <div style="font-size:10px; color:#aaa;">Ppto U. Neta</div>
                <div style="font-size:13px; font-weight:700; color:#555;">${un_p/1_000_000:,.2f}M</div>
            </div>
            <div style="font-size:18px; color:#ccc; padding-top:6px;">→</div>
            <div style="text-align:center;">
                <div style="font-size:10px; color:#aaa;">Real U. Neta</div>
                <div style="font-size:13px; font-weight:700; color:#2d0050;">${un_r/1_000_000:,.2f}M</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ╔══════════════════════════════════════════╗
# ║  TAB 3 — COMPOSICIÓN DEL RESULTADO      ║
# ╚══════════════════════════════════════════╝
with tab_comp:
    st.markdown("##### Composición del Resultado (Real)")
    st.caption("Cascade del P&L real: cómo se llega de las Ventas a la Utilidad Neta.")
    st.markdown("<br>", unsafe_allow_html=True)

    col_wf, _ = st.columns([2, 1])
    with col_wf:
        wf_labels  = ["Ventas", "- Costo Var.", "Util. Bruta", "- C. Fijo", "- OPEX",
                      "EBIT", "- G. Fin.", "- G. No Op.", "Util. Neta"]
        wf_measure = ["absolute", "relative", "total", "relative", "relative",
                      "total", "relative", "relative", "total"]
        wf_values  = [ventas_r, -cv_r, ub_r, -cf_r, -opex_r, ebit_r, -fin_r, -nooper_r, un_r]

        fig_wf = go.Figure(go.Waterfall(
            orientation  = "v",
            measure      = wf_measure,
            x            = wf_labels,
            y            = [v / 1_000_000 for v in wf_values],
            connector    = {"line": {"color": "#e0c8e8", "width": 1, "dash": "dot"}},
            increasing   = {"marker": {"color": "#0F6E56"}},
            decreasing   = {"marker": {"color": "#c4007a"}},
            totals       = {"marker": {"color": "#2d0050"}},
            texttemplate = "%{y:.1f}M",
            textfont     = {"size": 10},
            textposition = "outside",
        ))
        fig_wf.update_layout(
            height      = 300,
            margin      = dict(t=20, b=10, l=10, r=10),
            paper_bgcolor = "rgba(0,0,0,0)",
            plot_bgcolor  = "rgba(0,0,0,0)",
            yaxis = dict(
                tickprefix  = "$",
                ticksuffix  = "M",
                gridcolor   = "#f5eef8",
                zeroline    = True,
                zerolinecolor = "#e8d8f0",
            ),
            xaxis      = dict(tickfont={"size": 10}),
            showlegend = False,
            font       = dict(family="Inter, Arial, sans-serif", size=11, color="#555"),
        )
        st.plotly_chart(fig_wf, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── ANÁLISIS IA ───────────────────────────────────────────────
st.markdown("---")
st.markdown("##### Análisis IA")

if "analisis_texto" not in st.session_state:
    st.session_state["analisis_texto"] = ""

col_btn_ia, col_btn_pdf, col_btn_cerrar, _ = st.columns([2, 1.2, 1, 1.5])

# ── Datos IA compartidos ──────────────────────────────────────
_datos_ia_base = {
    "ventas_r": ventas_r, "ventas_p": ventas_p,
    "cv_r":     cv_r,     "cv_p":     cv_p,
    "cf_r":     cf_r,     "cf_p":     cf_p,
    "opex_r":   opex_r,   "opex_p":   opex_p,
    "fin_r":    fin_r,    "fin_p":    fin_p,
    "nooper_r": nooper_r, "nooper_p": nooper_p,
    "ub_r":     ub_r,     "ub_p":     ub_p,
    "ebit_r":   ebit_r,   "ebit_p":   ebit_p,
    "un_r":     un_r,     "un_p":     un_p,
    "periodo_desde": periodo_desde,
    "periodo_hasta": periodo_hasta,
    "sociedad": sociedad_sel,
}

with col_btn_ia:
    if st.button("Generar Análisis con IA", type="primary", use_container_width=True):
        with st.spinner("Analizando datos con IA..."):
            st.session_state["analisis_texto"] = generar_analisis_eerr(_datos_ia_base)
            st.session_state["analisis_datos"] = _datos_ia_base

with col_btn_pdf:
    if st.button("📄 Exportar PDF", use_container_width=True):
        with st.spinner("Generando PDF..."):
            pdf_bytes = generar_pdf_eerr(
                _datos_ia_base,
                analisis_texto=st.session_state.get("analisis_texto", ""),
                fig_bridge=fig_bridge,
            )
        nombre_pdf = f"EERR_{periodo_desde}_{periodo_hasta}_{sociedad_sel}.pdf"
        st.download_button(
            label="⬇ Descargar PDF",
            data=pdf_bytes,
            file_name=nombre_pdf,
            mime="application/pdf",
            use_container_width=True,
            key="dl_pdf_eerr",
        )

if st.session_state["analisis_texto"]:
    with col_btn_cerrar:
        if st.button("✕ Cerrar", use_container_width=True):
            st.session_state["analisis_texto"] = ""
            st.rerun()

if st.session_state["analisis_texto"]:
    st.markdown(f"""
    <div style="background:#fafafa; border:1px solid #e2e8f0; border-left:4px solid #2d0050;
                border-radius:8px; padding:20px 24px; margin-top:12px;
                font-size:13px; line-height:1.8; color:#333; white-space:pre-wrap;">
{st.session_state["analisis_texto"]}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Guardar reporte ──
    with st.container(border=True):
        st.markdown("**Guardar este análisis**")
        col_input, col_save = st.columns([4, 1])
        with col_input:
            titulo_rpt = st.text_input(
                "Título",
                value=f"EERR {periodo_desde} – {periodo_hasta} · {sociedad_sel}",
                label_visibility="collapsed",
            )
        with col_save:
            guardar_btn = st.button("Guardar", type="primary", use_container_width=True)

        if guardar_btn and titulo_rpt:
            datos_snap = st.session_state.get("analisis_datos", {})
            try:
                guardar_reporte(
                    titulo=titulo_rpt, tipo="EERR",
                    periodo_desde=periodo_desde, periodo_hasta=periodo_hasta,
                    sociedad=sociedad_sel, datos=datos_snap,
                    analisis=st.session_state["analisis_texto"],
                    creado_por=st.session_state.get("nombre", ""),
                )
                st.success("✓ Reporte guardado. Ve a **Reportes Guardados** para revisarlo.")
            except Exception as e:
                st.error(f"Error al guardar: {e}")
