"""
Dashboard — Resumen ejecutivo de ventas vs presupuesto
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date
from utils.auth import login, get_cc_sql_filter
from utils.db import query
from utils.components import (
    header, selector_meses, kpi_card, sidebar_kreems,
    fmt_mill, badge_html, boton_excel, semaforo_texto, semaforo_style_cell
)

_ANO = date.today().year

st.set_page_config(
    page_title="Resumen Ejecutivo · Kreems",
    page_icon="💜",
    layout="wide",
    initial_sidebar_state="expanded"
)

if not login():
    st.stop()

# ── SIDEBAR ────────────────────────────────────────────────────
sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True, mostrar_cc=False)

# ── HEADER ────────────────────────────────────────────────────
header("Resumen Ejecutivo — Ventas Real vs Presupuesto")

# ── SELECTOR MESES ────────────────────────────────────────────
periodo_desde, periodo_hasta = selector_meses(key="dash", default="Mayo")
st.markdown("<br>", unsafe_allow_html=True)

# ── FILTROS SQL ───────────────────────────────────────────────
filtro_soc = f"AND sociedad = '{sociedad_sel}'" if sociedad_sel != "Todas" else ""
filtro_cc  = get_cc_sql_filter()

# ── DATOS: Ventas totales periodo seleccionado ────────────────
df_ventas = query(f"""
    SELECT
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta
      AND clasificacion = 'INGRESO'
      {filtro_soc}
""", {"desde": periodo_desde, "hasta": periodo_hasta})

# ── DATOS: Serie mensual ventas (siempre todos los meses) ─────
df_mensual = query(f"""
    SELECT
        periodo,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE clasificacion = 'INGRESO'
      {filtro_soc}
    GROUP BY periodo
    ORDER BY periodo
""", {})

# ── DATOS: % Ejecución por CC (gastos operativos) ────────────
df_cc = query(f"""
    SELECT
        nombre_cc,
        codigo_cc,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta
      AND codigo_cc NOT IN ('CC-00')
      AND clasificacion <> 'INGRESO'
      {filtro_soc}
      {filtro_cc}
    GROUP BY nombre_cc, codigo_cc
    ORDER BY codigo_cc
""", {"desde": periodo_desde, "hasta": periodo_hasta})

# ── MÉTRICAS ──────────────────────────────────────────────────
ventas_real = float(df_ventas["real"].fillna(0).iloc[0]) if not df_ventas.empty else 0
ventas_ppto = float(df_ventas["ppto"].fillna(0).iloc[0]) if not df_ventas.empty else 0
pct_cumpl   = (ventas_real / ventas_ppto * 100) if ventas_ppto else 0
variacion   = ventas_real - ventas_ppto

# ── FILA KPIs + GAUGE ────────────────────────────────────────
col_gauge, col_k1, col_k2, col_k3, col_k4 = st.columns([1.8, 1, 1, 1, 1])

with col_gauge:
    max_val = max(ventas_ppto, ventas_real) / 1_000_000 * 1.25 or 100
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=ventas_real / 1_000_000,
        number={
            "suffix": " M",
            "valueformat": ",.2f",
            "font": {"size": 28, "color": "#2d0050"}
        },
        delta={
            "reference": ventas_ppto / 1_000_000,
            "valueformat": ",.2f",
            "suffix": " M",
            "increasing": {"color": "#0F6E56"},
            "decreasing": {"color": "#c4007a"}
        },
        title={
            "text": f"Ventas Real vs Presupuesto<br>"
                    f"<span style='font-size:13px;color:#999'>"
                    f"{pct_cumpl:.1f}% de cumplimiento</span>",
            "font": {"size": 14, "color": "#2d0050"}
        },
        gauge={
            "axis": {
                "range": [0, max_val],
                "tickformat": ",.0f",
                "ticksuffix": "M",
                "tickcolor": "#ccc",
                "tickfont": {"size": 10}
            },
            "bar": {"color": "#c4007a", "thickness": 0.28},
            "bgcolor": "white",
            "borderwidth": 0,
            "steps": [
                {"range": [0, ventas_ppto / 1_000_000 * 0.75], "color": "#fce4f3"},
                {"range": [ventas_ppto / 1_000_000 * 0.75, ventas_ppto / 1_000_000], "color": "#f4b8e0"},
                {"range": [ventas_ppto / 1_000_000, max_val], "color": "#e8f5ee"},
            ],
            "threshold": {
                "line": {"color": "#2d0050", "width": 3},
                "thickness": 0.85,
                "value": ventas_ppto / 1_000_000
            }
        }
    ))
    fig_gauge.update_layout(
        height=260,
        margin=dict(t=70, b=10, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, Arial, sans-serif"}
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_k1:
    kpi_card("Ventas Reales YTD", ventas_real, None)
with col_k2:
    kpi_card("Presupuesto YTD", ventas_ppto, None)
with col_k3:
    clase = "#0F6E56" if variacion >= 0 else "#cc0000"
    icono = "↑" if variacion >= 0 else "↓"
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #f0dff0;border-radius:12px;
                padding:16px 18px;text-align:center;margin-top:4px;">
        <div style="font-size:11px;color:#999;margin-bottom:6px;">Variación ($)</div>
        <div style="font-size:22px;font-weight:700;color:{clase};">
            {icono} ${abs(variacion)/1_000_000:,.2f}M
        </div>
        <div style="font-size:11px;color:#aaa;margin-top:4px;">vs presupuesto</div>
    </div>
    """, unsafe_allow_html=True)
with col_k4:
    clase = "#0F6E56" if pct_cumpl >= 100 else "#cc0000"
    icono = "↑" if pct_cumpl >= 100 else "↓"
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #f0dff0;border-radius:12px;
                padding:16px 18px;text-align:center;margin-top:4px;">
        <div style="font-size:11px;color:#999;margin-bottom:6px;">% Cumplimiento</div>
        <div style="font-size:22px;font-weight:700;color:{clase};">
            {pct_cumpl:.1f}%
        </div>
        <div style="font-size:11px;color:#aaa;margin-top:4px;">Real / Presupuesto</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── GRÁFICOS ─────────────────────────────────────────────────
col_bar, col_cc = st.columns(2)

with col_bar:
    st.markdown("##### Ventas mensuales — Real vs Presupuesto")
    if not df_mensual.empty:
        # Nombres de meses para el eje X
        nombres_meses = {
            f"{_ANO}-01": "Ene", f"{_ANO}-02": "Feb", f"{_ANO}-03": "Mar",
            f"{_ANO}-04": "Abr", f"{_ANO}-05": "May", f"{_ANO}-06": "Jun",
            f"{_ANO}-07": "Jul", f"{_ANO}-08": "Ago", f"{_ANO}-09": "Sep",
            f"{_ANO}-10": "Oct", f"{_ANO}-11": "Nov", f"{_ANO}-12": "Dic"
        }
        df_mensual["mes_nombre"] = df_mensual["periodo"].astype(str).map(nombres_meses)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_mensual["mes_nombre"],
            y=df_mensual["real"] / 1_000_000,
            name="Real",
            marker_color="#c4007a",
            opacity=0.9,
            text=(df_mensual["real"] / 1_000_000).apply(lambda v: f"${v:.1f}M"),
            textposition="outside",
            textfont={"size": 10}
        ))
        fig.add_trace(go.Scatter(
            x=df_mensual["mes_nombre"],
            y=df_mensual["ppto"] / 1_000_000,
            name="Presupuesto",
            mode="lines+markers",
            line=dict(color="#2d0050", width=2, dash="dot"),
            marker=dict(size=7, color="#2d0050")
        ))
        fig.update_layout(
            height=300,
            margin=dict(t=30, b=10, l=10, r=10),
            legend=dict(orientation="h", y=1.12, x=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(
                tickprefix="$", ticksuffix="M",
                gridcolor="#f5eef8", zeroline=False
            ),
            xaxis=dict(gridcolor="#f5eef8"),
            font=dict(family="Inter, Arial, sans-serif", size=11, color="#555")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos para el periodo seleccionado.")

with col_cc:
    st.markdown("##### % Ejecución por Centro de Costo")
    if not df_cc.empty:
        df_cc["pct"] = (df_cc["real"] / df_cc["ppto"] * 100).round(1).fillna(0)
        colores = ["#c4007a" if v > 100 else "#9b59b6" for v in df_cc["pct"]]

        fig_cc = go.Figure()
        fig_cc.add_trace(go.Bar(
            y=df_cc["nombre_cc"],
            x=df_cc["pct"],
            orientation="h",
            marker_color=colores,
            text=df_cc["pct"].apply(lambda v: f"{v:.1f}%"),
            textposition="outside",
            textfont={"size": 11}
        ))
        fig_cc.add_vline(
            x=100, line_dash="dash",
            line_color="#2d0050", line_width=1.5,
            annotation_text="100%",
            annotation_position="top right",
            annotation_font_color="#2d0050"
        )
        max_x = max(df_cc["pct"].max() * 1.2, 130) if not df_cc.empty else 130
        fig_cc.update_layout(
            height=300,
            margin=dict(t=20, b=10, l=10, r=60),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                ticksuffix="%",
                gridcolor="#f5eef8",
                range=[0, max_x],
                zeroline=False
            ),
            yaxis=dict(gridcolor="#f5eef8"),
            showlegend=False,
            font=dict(family="Inter, Arial, sans-serif", size=11, color="#555")
        )
        st.plotly_chart(fig_cc, use_container_width=True)
    else:
        st.info("Sin datos operativos para el periodo seleccionado.")

st.markdown("---")

# ── TABLA RESUMEN POR CC ──────────────────────────────────────
col_tit_cc, col_exp_cc = st.columns([4, 1])
with col_tit_cc:
    st.markdown("##### Resumen por Centro de Costo")
with col_exp_cc:
    if not df_cc.empty:
        _export_df = df_cc[["nombre_cc", "real", "ppto"]].copy()
        _export_df["variacion"] = _export_df["real"] - _export_df["ppto"]
        _export_df["pct"] = (_export_df["real"] / _export_df["ppto"] * 100).round(1)
        _export_df.columns = ["Centro de Costo", "Real", "Presupuesto", "Variación", "% Ejec."]
        boton_excel(
            {"Resumen CC": _export_df, "Ventas Mensual": df_mensual},
            f"Dashboard_{periodo_desde}_{periodo_hasta}",
        )

if not df_cc.empty:
    df_tabla = df_cc[["nombre_cc", "real", "ppto"]].copy()
    df_tabla["variacion"] = df_tabla["real"] - df_tabla["ppto"]
    df_tabla["pct"]       = (df_tabla["real"] / df_tabla["ppto"] * 100).round(1)
    df_tabla["estado"]    = df_tabla["pct"].apply(semaforo_texto)

    total_real = df_tabla["real"].sum()
    total_ppto = df_tabla["ppto"].sum()
    total_pct  = round(total_real / total_ppto * 100, 1) if total_ppto else 0
    total = pd.DataFrame([{
        "nombre_cc": "TOTAL",
        "real":      total_real,
        "ppto":      total_ppto,
        "variacion": total_real - total_ppto,
        "pct":       total_pct,
        "estado":    semaforo_texto(total_pct),
    }])

    df_tabla = pd.concat([df_tabla, total], ignore_index=True)

    df_show = df_tabla.rename(columns={
        "nombre_cc": "Centro de Costo",
        "real":      "Real",
        "ppto":      "Presupuesto",
        "variacion": "Variación",
        "pct":       "% Ejec.",
        "estado":    "Estado",
    })

    def _color_var(val):
        if isinstance(val, str): return ""
        return "color:#0F6E56; font-weight:500" if val <= 0 else "color:#cc0000; font-weight:500"

    def _color_pct(val):
        if isinstance(val, str): return ""
        return semaforo_style_cell(val)

    def _resaltar_total(row):
        if row["Centro de Costo"] == "TOTAL":
            return ["font-weight:bold; background:#fdf5fb"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_show.style
            .format({
                "Real":        lambda v: fmt_mill(v),
                "Presupuesto": lambda v: fmt_mill(v),
                "Variación":   lambda v: fmt_mill(v),
                "% Ejec.":     lambda v: f"{v:.1f}%" if isinstance(v, float) else v,
            })
            .apply(_resaltar_total, axis=1)
            .map(_color_var, subset=["Variación"])
            .map(_color_pct, subset=["% Ejec."]),
        use_container_width=True,
        hide_index=True,
        height=220,
        column_config={"Estado": st.column_config.TextColumn("Estado", width="small")},
    )
else:
    st.info("Sin datos para el periodo seleccionado.")
