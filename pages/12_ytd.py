"""
Acumulado YTD — Real vs Presupuesto año a la fecha.
Enero al mes seleccionado: tabla P&L, tendencia mensual y detalle por cuenta.
"""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date

from utils.auth import login
from utils.db import query
from utils.components import (
    header, sidebar_kreems, inject_font,
    ANO_FISCAL, MESES, MES_NUM_ACTUAL, boton_excel,
)

_ANO = ANO_FISCAL

st.set_page_config(
    page_title="Acumulado YTD · Kreems",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not login():
    st.stop()

inject_font()
sidebar_kreems(mostrar_sociedad=False)
header(f"Acumulado YTD — {_ANO}")

# ══════════════════════════════════════════════════════════════════
# FILTROS
# ══════════════════════════════════════════════════════════════════
c1, c2 = st.columns([2, 2])

with c1:
    meses_disp = [(n, nm) for n, nm in MESES.items() if n <= MES_NUM_ACTUAL]
    mes_nombres = [nm for _, nm in meses_disp]
    mes_nums    = {nm: n for n, nm in meses_disp}
    mes_sel     = st.selectbox("Acumulado hasta", mes_nombres, index=len(mes_nombres) - 1)
    mes_num     = mes_nums[mes_sel]
    p_desde     = f"{_ANO}-01"
    p_hasta     = f"{_ANO}-{mes_num:02d}"

with c2:
    df_soc = query("SELECT DISTINCT sociedad FROM marts.vw_real_vs_ppto ORDER BY sociedad")
    opciones_soc = ["Todas"] + (df_soc["sociedad"].tolist() if not df_soc.empty else [])
    sociedad = st.selectbox("Sociedad", opciones_soc)

filtro_soc = f"AND sociedad = '{sociedad}'" if sociedad != "Todas" else ""
titulo_ytd = f"Enero – {mes_sel} {_ANO}  ·  {sociedad}"
n_meses    = mes_num   # cuántos meses acumula


# ══════════════════════════════════════════════════════════════════
# QUERIES
# ══════════════════════════════════════════════════════════════════
def _load_pl(desde, hasta, fs):
    return query(f"""
        SELECT clasificacion,
               SUM(valor_real)  AS monto_r,
               SUM(valor_ppto)  AS monto_p
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :desde AND :hasta {fs}
        GROUP BY clasificacion
    """, {"desde": desde, "hasta": hasta})


def _load_tendencia(desde, hasta, fs):
    """Datos mes a mes por clasificación para gráfico de tendencia."""
    return query(f"""
        SELECT periodo,
               clasificacion,
               SUM(valor_real)  AS monto_r,
               SUM(valor_ppto)  AS monto_p
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :desde AND :hasta {fs}
        GROUP BY periodo, clasificacion
        ORDER BY periodo
    """, {"desde": desde, "hasta": hasta})


def _load_detalle(desde, hasta, fs):
    return query(f"""
        SELECT clasificacion,
               nombre_cuenta,
               SUM(valor_real)  AS monto_r,
               SUM(valor_ppto)  AS monto_p,
               SUM(valor_real) - SUM(valor_ppto) AS varianza
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :desde AND :hasta {fs}
        GROUP BY clasificacion, nombre_cuenta
        ORDER BY clasificacion,
                 ABS(SUM(valor_real) - SUM(valor_ppto)) DESC
    """, {"desde": desde, "hasta": hasta})


# ══════════════════════════════════════════════════════════════════
# CARGA
# ══════════════════════════════════════════════════════════════════
with st.spinner("Cargando datos YTD..."):
    df_pl   = _load_pl(p_desde, p_hasta, filtro_soc)
    df_tend = _load_tendencia(p_desde, p_hasta, filtro_soc)
    df_det  = _load_detalle(p_desde, p_hasta, filtro_soc)

if df_pl.empty:
    st.info(f"Sin datos para {titulo_ytd}.")
    st.stop()


# ══════════════════════════════════════════════════════════════════
# CÁLCULO P&L ACUMULADO
# ══════════════════════════════════════════════════════════════════
def gv(cls, col):
    row = df_pl[df_pl["clasificacion"] == cls]
    return float(row[col].sum()) if not row.empty else 0.0


v_r  = gv("INGRESO",        "monto_r");  v_p  = gv("INGRESO",        "monto_p")
cv_r = gv("COSTO_VAR",      "monto_r");  cv_p = gv("COSTO_VAR",      "monto_p")
cf_r = gv("COSTO_FIJO",     "monto_r");  cf_p = gv("COSTO_FIJO",     "monto_p")
ox_r = gv("OPEX",           "monto_r");  ox_p = gv("OPEX",           "monto_p")
fn_r = gv("FINANCIERO",     "monto_r");  fn_p = gv("FINANCIERO",     "monto_p")
no_r = gv("NO_OPERACIONAL",  "monto_r"); no_p = gv("NO_OPERACIONAL",  "monto_p")

ub_r  = v_r  - cv_r;                    ub_p  = v_p  - cv_p
ei_r  = ub_r - cf_r - ox_r;             ei_p  = ub_p - cf_p - ox_p
un_r  = ei_r - fn_r - no_r;             un_p  = ei_p - fn_p - no_p
gt_r  = cv_r + cf_r + ox_r + fn_r + no_r
gt_p  = cv_p + cf_p + ox_p + fn_p + no_p


def _pct(r, p):   return r / p * 100 if p else 0.0
def _fmt(v):      return f"${v/1e6:,.2f}M"
def _fmt_k(v):    return f"${v/1e3:,.0f}K"


# ── Semáforo con corrección para ppto negativo ──────────────────
def _sc(pct_: float, inv: bool = False, pval: float = 1.0) -> str:
    if not inv and pval < 0:
        inv = True
    if not inv:
        return "#0F6E56" if pct_ >= 100 else ("#b45309" if pct_ >= 90 else "#cc0000")
    return "#0F6E56" if pct_ <= 90 else ("#b45309" if pct_ <= 100 else "#cc0000")


def _sl(r: float, p: float, inv: bool = False) -> str:
    if p == 0:
        return "Sin ppto"
    if not inv and p < 0:
        if r >= 0:
            return "▲ Superó ppto"
        return "▲ Pérdida reducida" if abs(r) < abs(p) else "▼ Pérdida mayor"
    return f"{r/p*100:.1f}% ppto"


pct_v  = _pct(v_r,  v_p)
pct_ub = _pct(ub_r, ub_p)
pct_e  = _pct(ei_r, ei_p)
pct_u  = _pct(un_r, un_p)
pct_g  = _pct(gt_r, gt_p)


# ══════════════════════════════════════════════════════════════════
# KPI CARDS
# ══════════════════════════════════════════════════════════════════
st.markdown(
    f"<div style='font-size:13px;color:#94A3B8;margin-bottom:12px;'>"
    f"📅 Período acumulado: <b style='color:#2d0050;'>{titulo_ytd}</b>"
    f"&nbsp;·&nbsp; {n_meses} mes{'es' if n_meses > 1 else ''} acumulado{'s' if n_meses > 1 else ''}"
    f"</div>", unsafe_allow_html=True
)

kc = st.columns(4)
kpi_data = [
    ("Ventas YTD",    v_r,  v_p,  pct_v,  False),
    ("EBIT YTD",      ei_r, ei_p, pct_e,  False),
    ("Ut. Neta YTD",  un_r, un_p, pct_u,  False),
    ("Gastos YTD",    gt_r, gt_p, pct_g,  True),
]

for col, (lbl, r, p, pct_, inv) in zip(kc, kpi_data):
    col_k   = _sc(pct_, inv, pval=p)
    lbl_pct = _sl(r, p, inv)
    var_abs = r - p
    signo   = "+" if var_abs >= 0 else ""
    with col:
        st.markdown(f"""
        <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;
                    padding:16px 14px;text-align:center;border-top:3px solid {col_k};">
            <div style="font-size:9px;color:#94A3B8;font-weight:700;text-transform:uppercase;
                        letter-spacing:.8px;margin-bottom:5px;">{lbl}</div>
            <div style="font-size:21px;font-weight:800;color:#2d0050;margin-bottom:3px;">{_fmt(r)}</div>
            <div style="font-size:12px;font-weight:700;color:{col_k};margin-bottom:2px;">{lbl_pct}</div>
            <div style="font-size:10px;color:#94A3B8;">
                Obj: {_fmt(p)} &nbsp;·&nbsp; Var: <span style="color:{col_k};">{signo}{_fmt(var_abs)}</span>
            </div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
st.markdown("---")


# ══════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════
tab_pl, tab_tend, tab_det = st.tabs([
    "📊 P&L Acumulado",
    "📈 Tendencia Mensual",
    "📑 Detalle por Cuenta",
])


# ─────────────────────────────────────────────────────────────────
# TAB 1 — P&L ACUMULADO
# ─────────────────────────────────────────────────────────────────
with tab_pl:

    col_tbl, col_bar = st.columns([3, 2], gap="large")

    with col_tbl:
        st.markdown("#### Tabla P&L YTD")

        # Construir tabla resumen
        filas = [
            ("Ventas",                 v_r,  v_p,  False, True),
            ("Costo de Venta",         cv_r, cv_p, True,  False),
            ("Utilidad Bruta",         ub_r, ub_p, False, True),
            ("Costo Fijo",             cf_r, cf_p, True,  False),
            ("OPEX",                   ox_r, ox_p, True,  False),
            ("EBIT",                   ei_r, ei_p, False, True),
            ("Gastos Financieros",     fn_r, fn_p, True,  False),
            ("Gastos No Operacionales",no_r, no_p, True,  False),
            ("Utilidad Neta",          un_r, un_p, False, True),
        ]

        rows = []
        for nombre, r, p, inv, subtotal in filas:
            var = r - p
            pct_ = _pct(r, p)
            col_var = _sc(pct_, inv, pval=p)
            rows.append({
                "Línea":        nombre,
                "Real YTD":     _fmt(r),
                "Ppto YTD":     _fmt(p),
                "Varianza":     ("+" if var >= 0 else "") + _fmt(var),
                "% Ejec.":      _sl(r, p, inv),
                "_subtotal":    subtotal,
                "_col_var":     col_var,
                "_inv":         inv,
                "_pct":         pct_,
            })

        # Renderizar tabla HTML
        tbl_html = """
        <table style="width:100%;border-collapse:collapse;font-size:12.5px;">
        <thead>
            <tr style="background:#2d0050;color:#fff;">
                <th style="padding:7px 10px;text-align:left;">Línea</th>
                <th style="padding:7px 10px;text-align:right;">Real YTD</th>
                <th style="padding:7px 10px;text-align:right;">Ppto YTD</th>
                <th style="padding:7px 10px;text-align:right;">Varianza</th>
                <th style="padding:7px 10px;text-align:right;">% Ejec.</th>
            </tr>
        </thead><tbody>"""

        for i, row in enumerate(rows):
            bg   = "#F0EBF8" if row["_subtotal"] else ("#F8F9FB" if i % 2 == 0 else "#FFFFFF")
            fw   = "700" if row["_subtotal"] else "400"
            cvar = row["_col_var"]
            tbl_html += f"""
            <tr style="background:{bg};">
                <td style="padding:6px 10px;font-weight:{fw};color:#2d0050;">{row['Línea']}</td>
                <td style="padding:6px 10px;text-align:right;font-weight:{fw};color:#0F172A;">{row['Real YTD']}</td>
                <td style="padding:6px 10px;text-align:right;color:#64748b;">{row['Ppto YTD']}</td>
                <td style="padding:6px 10px;text-align:right;font-weight:600;color:{cvar};">{row['Varianza']}</td>
                <td style="padding:6px 10px;text-align:right;font-weight:600;color:{cvar};">{row['% Ejec.']}</td>
            </tr>"""

        tbl_html += "</tbody></table>"
        st.markdown(tbl_html, unsafe_allow_html=True)

        # Export Excel
        df_export = pd.DataFrame([
            {"Línea": r["Línea"], "Real YTD": r["Real YTD"],
             "Ppto YTD": r["Ppto YTD"], "Varianza": r["Varianza"], "% Ejec.": r["% Ejec."]}
            for r in rows
        ])
        boton_excel(df_export, f"ytd_{p_hasta}_{sociedad.lower().replace(' ','_')}.xlsx",
                    "⬇️ Exportar Excel")

    with col_bar:
        st.markdown("#### Ejecución por Línea")
        fig_bar = go.Figure()

        lineas_bar = [
            ("Ventas",    pct_v,  False, v_p),
            ("Ut. Bruta", pct_ub, False, ub_p),
            ("EBIT",      pct_e,  False, ei_p),
            ("Ut. Neta",  pct_u,  False, un_p),
            ("Gastos",    pct_g,  True,  gt_p),
        ]

        colores = [_sc(p_, inv, pv) for _, p_, inv, pv in lineas_bar]
        labels  = [l for l, *_ in lineas_bar]
        pcts    = [p_ for _, p_, *_ in lineas_bar]

        fig_bar.add_trace(go.Bar(
            x=pcts,
            y=labels,
            orientation="h",
            marker_color=colores,
            text=[f"{p_:.1f}%" for p_ in pcts],
            textposition="outside",
            cliponaxis=False,
        ))
        fig_bar.add_vline(x=100, line_dash="dash", line_color="#94A3B8",
                          annotation_text="100%", annotation_position="top right",
                          annotation_font_size=10)
        fig_bar.update_layout(
            margin=dict(l=10, r=50, t=20, b=10),
            height=280,
            plot_bgcolor="white",
            paper_bgcolor="white",
            showlegend=False,
            xaxis=dict(range=[0, max(pcts + [110]) + 20],
                       showgrid=True, gridcolor="#F1F5F9",
                       ticksuffix="%"),
            yaxis=dict(autorange="reversed", showgrid=False),
            font=dict(family="Inter, sans-serif", size=12),
        )
        st.plotly_chart(fig_bar, use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 2 — TENDENCIA MENSUAL
# ─────────────────────────────────────────────────────────────────
with tab_tend:

    if df_tend.empty:
        st.info("Sin datos de tendencia para el período seleccionado.")
    else:
        # Construir series mensuales
        periodos_ord = sorted(df_tend["periodo"].unique())
        mes_labels   = [MESES[int(p.split("-")[1])][:3] for p in periodos_ord]

        # Calcular P&L por cada mes
        series = {k: [] for k in [
            "vr", "vp", "ubr", "ubp", "er", "ep", "ur", "up"
        ]}
        acum = {k: 0.0 for k in series}
        acum_series = {k: [] for k in series}

        for per in periodos_ord:
            dm = df_tend[df_tend["periodo"] == per]
            def gvm(cls, col):
                r = dm[dm["clasificacion"] == cls]
                return float(r[col].sum()) if not r.empty else 0.0

            vr_m  = gvm("INGRESO",        "monto_r"); vp_m  = gvm("INGRESO",        "monto_p")
            cvr_m = gvm("COSTO_VAR",      "monto_r"); cvp_m = gvm("COSTO_VAR",      "monto_p")
            cfr_m = gvm("COSTO_FIJO",     "monto_r"); cfp_m = gvm("COSTO_FIJO",     "monto_p")
            oxr_m = gvm("OPEX",           "monto_r"); oxp_m = gvm("OPEX",           "monto_p")
            fnr_m = gvm("FINANCIERO",     "monto_r"); fnp_m = gvm("FINANCIERO",     "monto_p")
            nor_m = gvm("NO_OPERACIONAL",  "monto_r"); nop_m = gvm("NO_OPERACIONAL", "monto_p")

            ubr_m = vr_m - cvr_m;              ubp_m = vp_m - cvp_m
            er_m  = ubr_m - cfr_m - oxr_m;    ep_m  = ubp_m - cfp_m - oxp_m
            ur_m  = er_m  - fnr_m - nor_m;    up_m  = ep_m  - fnp_m - nop_m

            vals = {"vr": vr_m, "vp": vp_m, "ubr": ubr_m, "ubp": ubp_m,
                    "er": er_m, "ep": ep_m, "ur": ur_m, "up": up_m}

            for k, v in vals.items():
                series[k].append(v / 1e6)
                acum[k] += v
                acum_series[k].append(acum[k] / 1e6)

        # ── Selector de métrica y vista ───────────────────────────
        col_ctrl1, col_ctrl2 = st.columns([2, 2])
        with col_ctrl1:
            metrica = st.selectbox(
                "Métrica",
                ["Ventas", "Ut. Bruta", "EBIT", "Ut. Neta"],
                key="ytd_metrica"
            )
        with col_ctrl2:
            vista = st.radio(
                "Vista",
                ["Mensual", "Acumulado YTD"],
                horizontal=True,
                key="ytd_vista"
            )

        MAP = {
            "Ventas":    ("vr", "vp"),
            "Ut. Bruta": ("ubr", "ubp"),
            "EBIT":      ("er", "ep"),
            "Ut. Neta":  ("ur", "up"),
        }
        kr, kp = MAP[metrica]
        src = acum_series if vista == "Acumulado YTD" else series

        y_real = src[kr]
        y_ppto = src[kp]

        COL_REAL  = "#2d0050"
        COL_PPTO  = "#c4007a"
        COL_AREA  = "rgba(45,0,80,0.08)"

        fig_line = go.Figure()

        # Área entre real y ppto
        fig_line.add_trace(go.Scatter(
            x=mes_labels + mes_labels[::-1],
            y=y_real + y_ppto[::-1],
            fill="toself",
            fillcolor=COL_AREA,
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        ))

        fig_line.add_trace(go.Scatter(
            x=mes_labels, y=y_ppto,
            name="Presupuesto",
            mode="lines+markers",
            line=dict(color=COL_PPTO, width=2, dash="dot"),
            marker=dict(size=6, color=COL_PPTO, symbol="diamond"),
            hovertemplate="<b>%{x}</b><br>Ppto: $%{y:.2f}M<extra></extra>",
        ))

        fig_line.add_trace(go.Scatter(
            x=mes_labels, y=y_real,
            name="Real",
            mode="lines+markers",
            line=dict(color=COL_REAL, width=3),
            marker=dict(size=7, color=COL_REAL),
            hovertemplate="<b>%{x}</b><br>Real: $%{y:.2f}M<extra></extra>",
        ))

        # Línea de referencia en 0 si hay negativos
        if min(y_real + y_ppto) < 0:
            fig_line.add_hline(y=0, line_color="#E2E8F0", line_width=1)

        titulo_graf = f"{metrica} — {'Acumulado YTD' if vista == 'Acumulado YTD' else 'Por Mes'}"
        fig_line.update_layout(
            title=dict(text=titulo_graf, font=dict(size=13, color="#2d0050"), x=0),
            margin=dict(l=10, r=10, t=40, b=20),
            height=380,
            plot_bgcolor="white",
            paper_bgcolor="white",
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center",
                        font=dict(size=11)),
            xaxis=dict(showgrid=False, tickfont=dict(size=11)),
            yaxis=dict(showgrid=True, gridcolor="#F1F5F9",
                       tickprefix="$", ticksuffix="M",
                       tickfont=dict(size=11)),
            font=dict(family="Inter, sans-serif"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_line, use_container_width=True)

        # ── Mini-tabla resumen mensual ────────────────────────────
        st.markdown("##### Detalle mensual")
        rows_mes = []
        for i, mes in enumerate(mes_labels):
            yr  = series[kr][i]
            yp  = series[kp][i]
            pct_ = (yr / yp * 100) if yp else 0.0
            var  = yr - yp
            rows_mes.append({
                "Mes":       mes,
                "Real ($M)": round(yr, 2),
                "Ppto ($M)": round(yp, 2),
                "Var ($M)":  round(var, 2),
                "% Ejec.":   f"{pct_:.1f}%",
            })
        df_mes_tbl = pd.DataFrame(rows_mes)
        st.dataframe(df_mes_tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────
# TAB 3 — DETALLE POR CUENTA
# ─────────────────────────────────────────────────────────────────
with tab_det:

    if df_det.empty:
        st.info("Sin detalle disponible.")
    else:
        # Filtros de la tabla
        col_fc1, col_fc2 = st.columns([2, 3])
        with col_fc1:
            clases = ["Todas"] + sorted(df_det["clasificacion"].dropna().unique().tolist())
            clase_sel = st.selectbox("Clasificación", clases, key="ytd_clase")
        with col_fc2:
            busq = st.text_input("Buscar cuenta", placeholder="Ej: honorarios, arriendo...",
                                 key="ytd_busq")

        df_v = df_det.copy()
        if clase_sel != "Todas":
            df_v = df_v[df_v["clasificacion"] == clase_sel]
        if busq:
            df_v = df_v[df_v["nombre_cuenta"].str.contains(busq, case=False, na=False)]

        st.markdown(
            f"<div style='font-size:11px;color:#94A3B8;margin-bottom:8px;'>"
            f"{len(df_v)} cuenta(s)</div>",
            unsafe_allow_html=True
        )

        # Tabla con colores
        tbl2 = """
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead>
            <tr style="background:#2d0050;color:#fff;">
                <th style="padding:7px 8px;text-align:left;">Clasificación</th>
                <th style="padding:7px 8px;text-align:left;">Cuenta</th>
                <th style="padding:7px 8px;text-align:right;">Real YTD</th>
                <th style="padding:7px 8px;text-align:right;">Ppto YTD</th>
                <th style="padding:7px 8px;text-align:right;">Varianza</th>
                <th style="padding:7px 8px;text-align:right;">% Ejec.</th>
            </tr>
        </thead><tbody>"""

        # Determinar si la clasificación es de costo (inv=True)
        CLASES_COSTO = {"COSTO_VAR", "COSTO_FIJO", "OPEX", "FINANCIERO", "NO_OPERACIONAL"}

        for idx, row in enumerate(df_v.itertuples()):
            r     = float(row.monto_r)
            p     = float(row.monto_p)
            var_v = float(row.varianza)
            inv   = row.clasificacion in CLASES_COSTO
            pct_  = _pct(r, p)
            cvar  = _sc(pct_, inv, pval=p)
            bg    = "#F8F9FB" if idx % 2 == 0 else "#FFFFFF"
            signo = "+" if var_v >= 0 else ""
            lbl_p = _sl(r, p, inv)

            tbl2 += f"""
            <tr style="background:{bg};">
                <td style="padding:5px 8px;color:#64748b;font-size:11px;">{row.clasificacion}</td>
                <td style="padding:5px 8px;color:#0F172A;">{row.nombre_cuenta}</td>
                <td style="padding:5px 8px;text-align:right;color:#0F172A;">{_fmt(r)}</td>
                <td style="padding:5px 8px;text-align:right;color:#64748b;">{_fmt(p)}</td>
                <td style="padding:5px 8px;text-align:right;font-weight:600;color:{cvar};">{signo}{_fmt(var_v)}</td>
                <td style="padding:5px 8px;text-align:right;font-weight:600;color:{cvar};">{lbl_p}</td>
            </tr>"""

        tbl2 += "</tbody></table>"
        st.markdown(tbl2, unsafe_allow_html=True)

        # Export
        df_export2 = df_v[["clasificacion", "nombre_cuenta", "monto_r", "monto_p", "varianza"]].copy()
        df_export2.columns = ["Clasificación", "Cuenta", "Real YTD", "Ppto YTD", "Varianza"]
        boton_excel(df_export2,
                    f"ytd_detalle_{p_hasta}_{sociedad.lower().replace(' ','_')}.xlsx",
                    "⬇️ Exportar detalle Excel")
