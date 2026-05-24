"""
Flash Report Mensual — Resumen ejecutivo de 1 página.
Genera vista previa HTML y PDF descargable.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import date

from utils.auth import login
from utils.components import header, sidebar_kreems, inject_font
from utils.db import query
from utils.ai import generar_analisis_flash
from utils.pdf_report import generar_flash_report

st.set_page_config(
    page_title="Flash Report · Kreems",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not login():
    st.stop()

inject_font()
sidebar_kreems(mostrar_sociedad=False)
header("Flash Report Mensual")

# ── Constantes ─────────────────────────────────────────────────
_ANO = date.today().year

MESES_LABEL = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MESES_VAL = {lbl: f"{_ANO}-{(i+1):02d}" for i, lbl in enumerate(MESES_LABEL)}
_mes_actual_key = date.today().strftime(f"{_ANO}-%m")
_idx_default    = list(MESES_VAL.values()).index(_mes_actual_key) if _mes_actual_key in MESES_VAL.values() else 0

# ── Filtros ─────────────────────────────────────────────────────
c1, c2, c3 = st.columns([2, 2, 4])

with c1:
    mes_label = st.selectbox("Período", MESES_LABEL, index=_idx_default)
    periodo   = MESES_VAL[mes_label]

with c2:
    df_soc = query("SELECT DISTINCT sociedad FROM marts.vw_real_vs_ppto ORDER BY sociedad")
    opciones_soc = ["Todas"] + (df_soc["sociedad"].tolist() if not df_soc.empty else [])
    sociedad = st.selectbox("Sociedad", opciones_soc)

with c3:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_ia  = st.button("🤖 Generar análisis IA", use_container_width=True)
    with col_btn2:
        btn_pdf = st.button("📄 Descargar PDF",        use_container_width=True, type="primary")


# ── Queries ─────────────────────────────────────────────────────
def _load_pl(p: str, soc: str) -> pd.DataFrame:
    """Mismo patrón que EERR: valor_real/valor_ppto, filtro_soc como f-string."""
    filtro_soc = f"AND sociedad = '{soc}'" if soc != "Todas" else ""
    return query(f"""
        SELECT clasificacion,
               SUM(valor_real) AS monto_r,
               SUM(valor_ppto) AS monto_p
        FROM marts.vw_real_vs_ppto
        WHERE periodo = :p {filtro_soc}
        GROUP BY clasificacion
    """, {"p": p})


def _load_top_desv(p: str, soc: str, n: int = 7) -> pd.DataFrame:
    """Top N cuentas por desviación absoluta. nombre_cuenta ya está en la vista."""
    filtro_soc = f"AND sociedad = '{soc}'" if soc != "Todas" else ""
    return query(f"""
        SELECT nombre_cuenta AS cuenta,
               SUM(valor_real)  AS monto_r,
               SUM(valor_ppto)  AS monto_p,
               SUM(valor_real) - SUM(valor_ppto) AS varianza
        FROM marts.vw_real_vs_ppto
        WHERE periodo = :p
          AND clasificacion NOT IN ('INGRESO')
          {filtro_soc}
        GROUP BY nombre_cuenta
        HAVING SUM(valor_ppto) > 0
        ORDER BY ABS(SUM(valor_real) - SUM(valor_ppto)) DESC
        LIMIT :n
    """, {"p": p, "n": n})


# ── Helpers ─────────────────────────────────────────────────────
def _gv(df: pd.DataFrame, cls: str, col: str) -> float:
    row = df[df["clasificacion"] == cls]
    return float(row[col].sum()) if not row.empty else 0.0


def _build_datos(df: pd.DataFrame) -> dict:
    v_r = _gv(df, "INGRESO",        "monto_r");  v_p = _gv(df, "INGRESO",        "monto_p")
    c_r = _gv(df, "COSTO_VAR",      "monto_r");  c_p = _gv(df, "COSTO_VAR",      "monto_p")
    f_r = _gv(df, "COSTO_FIJO",     "monto_r");  f_p = _gv(df, "COSTO_FIJO",     "monto_p")
    o_r = _gv(df, "OPEX",           "monto_r");  o_p = _gv(df, "OPEX",           "monto_p")
    n_r = _gv(df, "FINANCIERO",     "monto_r");  n_p = _gv(df, "FINANCIERO",     "monto_p")
    x_r = _gv(df, "NO_OPERACIONAL", "monto_r");  x_p = _gv(df, "NO_OPERACIONAL", "monto_p")

    ub_r = v_r - c_r;                    ub_p = v_p - c_p
    ei_r = ub_r - f_r - o_r;            ei_p = ub_p - f_p - o_p
    un_r = ei_r - n_r - x_r;            un_p = ei_p - n_p - x_p
    gt_r = c_r + f_r + o_r + n_r + x_r; gt_p = c_p + f_p + o_p + n_p + x_p

    return dict(
        ventas_r=v_r, ventas_p=v_p, cv_r=c_r, cv_p=c_p,
        cf_r=f_r,     cf_p=f_p,     opex_r=o_r, opex_p=o_p,
        fin_r=n_r,    fin_p=n_p,    nooper_r=x_r, nooper_p=x_p,
        ub_r=ub_r,    ub_p=ub_p,    ebit_r=ei_r,   ebit_p=ei_p,
        un_r=un_r,    un_p=un_p,    gastos_r=gt_r,  gastos_p=gt_p,
        periodo=periodo, sociedad=sociedad,
    )


def _fmt(v: float) -> str:
    return f"${v/1_000_000:,.2f}M"


def _sem_color(pct: float, inv: bool = False) -> str:
    if not inv:
        if pct >= 100: return "#0F6E56"
        if pct >= 90:  return "#b45309"
        return "#cc0000"
    else:
        if pct <= 90:  return "#0F6E56"
        if pct <= 100: return "#b45309"
        return "#cc0000"


def _sem_label(pct: float) -> str:
    if pct >= 100: return "🟢 OK"
    if pct >= 90:  return "🟡 Atención"
    return "🔴 Alerta"


# ── Carga de datos ───────────────────────────────────────────────
with st.spinner("Cargando datos..."):
    df_pl  = _load_pl(periodo, sociedad)
    df_top = _load_top_desv(periodo, sociedad)

if df_pl.empty:
    st.info("Sin datos para el período y sociedad seleccionados.")
    st.stop()

datos = _build_datos(df_pl)

v_r, v_p = datos["ventas_r"], datos["ventas_p"]
e_r, e_p = datos["ebit_r"],   datos["ebit_p"]
u_r, u_p = datos["un_r"],     datos["un_p"]
g_r, g_p = datos["gastos_r"], datos["gastos_p"]
ub_r, ub_p = datos["ub_r"],   datos["ub_p"]

pct_v  = v_r / v_p * 100 if v_p else 0
pct_e  = e_r / e_p * 100 if e_p else 0
pct_u  = u_r / u_p * 100 if u_p else 0
pct_g  = g_r / g_p * 100 if g_p else 0
pct_ub = ub_r / ub_p * 100 if ub_p else 0

titulo_mes = f"{mes_label} {_ANO}"

# ── IA: ejecutar si se presionó el botón ────────────────────────
if btn_ia:
    with st.spinner("Generando análisis IA..."):
        analisis = generar_analisis_flash(datos, df_top)
    st.session_state[f"flash_analisis_{periodo}_{sociedad}"] = analisis

analisis_txt = st.session_state.get(f"flash_analisis_{periodo}_{sociedad}", "")

# ── PDF: generar y ofrecer descarga si se solicitó ───────────────
if btn_pdf:
    with st.spinner("Generando PDF..."):
        pdf_bytes = generar_flash_report(
            datos, df_top,
            analisis_texto=analisis_txt,
            titulo_mes=titulo_mes,
        )
    st.session_state["flash_pdf_bytes"] = pdf_bytes
    st.session_state["flash_pdf_name"]  = (
        f"flash_report_{periodo}_{sociedad.lower().replace(' ','_')}.pdf"
    )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# LAYOUT PRINCIPAL: Preview izquierda | Acciones derecha
# ═══════════════════════════════════════════════════════════════
col_prev, col_side = st.columns([5, 2], gap="large")

with col_prev:
    st.markdown("#### Vista Previa")

    # ── Construir filas de top desviaciones ─────────────────────
    top_rows_html = ""
    for _, row in df_top.iterrows():
        r_val  = float(row["monto_r"])
        p_val  = float(row["monto_p"])
        var_v  = float(row["varianza"])
        prow   = r_val / p_val * 100 if p_val else 0
        color  = "#cc0000" if var_v > 0 else "#0F6E56"
        signo  = "+" if var_v >= 0 else ""
        cuenta_display = str(row["cuenta"])[:38]
        top_rows_html += f"""
        <tr style="border-bottom:1px solid #F1F5F9;">
            <td style="padding:5px 8px;font-size:11px;color:#0F172A;">{cuenta_display}</td>
            <td style="padding:5px 8px;font-size:11px;text-align:right;color:#0F172A;">{_fmt(r_val)}</td>
            <td style="padding:5px 8px;font-size:11px;text-align:right;color:#64748b;">{_fmt(p_val)}</td>
            <td style="padding:5px 8px;font-size:11px;text-align:right;color:{color};font-weight:600;">
                {signo}{_fmt(var_v)}</td>
            <td style="padding:5px 8px;font-size:11px;text-align:right;color:{color};">{prow:.1f}%</td>
        </tr>"""

    # ── Barras P&L ───────────────────────────────────────────────
    lineas_barra = [
        ("Ventas",       pct_v,  False),
        ("Ut. Bruta",    pct_ub, False),
        ("EBIT",         pct_e,  False),
        ("Ut. Neta",     pct_u,  False),
        ("Gastos Total", pct_g,  True),
    ]
    barras_html = ""
    for lbl, pct, inv in lineas_barra:
        col_bar = _sem_color(pct, inv)
        bar_w   = min(pct, 130)
        barras_html += f"""
        <div style="margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
                <span style="color:#475569;font-weight:500;">{lbl}</span>
                <span style="color:{col_bar};font-weight:700;">{pct:.1f}%</span>
            </div>
            <div style="background:#E2E8F0;border-radius:4px;height:7px;overflow:hidden;">
                <div style="background:{col_bar};width:{min(bar_w,100):.1f}%;height:7px;
                            border-radius:4px;transition:width .4s;"></div>
            </div>
        </div>"""

    # ── KPI cards HTML ───────────────────────────────────────────
    kpis_html = ""
    for lbl, r, p, pct, inv in [
        ("Ventas",    v_r, v_p, pct_v, False),
        ("EBIT",      e_r, e_p, pct_e, False),
        ("Ut. Neta",  u_r, u_p, pct_u, False),
        ("Gastos",    g_r, g_p, pct_g, True),
    ]:
        col_k = _sem_color(pct, inv)
        kpis_html += f"""
        <div style="flex:1;background:#fff;border:1px solid #E2E8F0;border-radius:10px;
                    padding:14px 10px;text-align:center;border-top:3px solid {col_k};">
            <div style="font-size:9px;color:#94A3B8;font-weight:700;text-transform:uppercase;
                        letter-spacing:.8px;margin-bottom:4px;">{lbl}</div>
            <div style="font-size:17px;font-weight:800;color:#2d0050;margin-bottom:2px;">{_fmt(r)}</div>
            <div style="font-size:11px;font-weight:700;color:{col_k};">{pct:.1f}% ppto</div>
            <div style="font-size:9px;color:#94A3B8;margin-top:2px;">Obj: {_fmt(p)}</div>
        </div>"""

    # ── Semáforo global ──────────────────────────────────────────
    sem_g_label = _sem_label(pct_v)

    # ── HTML PREVIEW COMPLETO ─────────────────────────────────────
    html_preview = f"""
    <div style="font-family:'Inter',sans-serif;border:1px solid #E2E8F0;
                border-radius:14px;overflow:hidden;
                box-shadow:0 4px 24px rgba(0,0,0,0.07);max-width:720px;">

        <!-- Header morado -->
        <div style="background:linear-gradient(135deg,#2d0050,#4a007e);
                    padding:18px 24px;display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div style="color:#fff;font-size:17px;font-weight:800;letter-spacing:.3px;">KREEMS FP&A</div>
                <div style="color:rgba(255,255,255,0.6);font-size:11px;margin-top:2px;">Flash Report Mensual</div>
            </div>
            <div style="text-align:right;">
                <div style="color:#fff;font-size:14px;font-weight:700;">{titulo_mes}</div>
                <div style="color:rgba(255,255,255,0.6);font-size:10px;">{sociedad} &nbsp;·&nbsp; {date.today().strftime('%d/%m/%Y')}</div>
            </div>
        </div>

        <!-- KPI Row -->
        <div style="display:flex;gap:10px;padding:16px 20px;background:#F8F9FB;
                    border-bottom:1px solid #E2E8F0;">
            {kpis_html}
        </div>

        <!-- Semáforo global -->
        <div style="padding:8px 20px;background:#fff;border-bottom:1px solid #E2E8F0;
                    display:flex;align-items:center;gap:12px;">
            <span style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
                         letter-spacing:.5px;">Estado General:</span>
            <span style="font-size:13px;font-weight:700;">{sem_g_label}</span>
            <span style="font-size:10px;color:#94A3B8;">
                Ventas {pct_v:.1f}% &nbsp;·&nbsp; EBIT {pct_e:.1f}% &nbsp;·&nbsp; Ut.Neta {pct_u:.1f}%
            </span>
        </div>

        <!-- Body: 2 columnas -->
        <div style="display:grid;grid-template-columns:1fr 1fr;background:#fff;">

            <!-- Top desviaciones -->
            <div style="padding:16px 20px;border-right:1px solid #E2E8F0;">
                <div style="font-size:10px;font-weight:700;color:#2d0050;text-transform:uppercase;
                            letter-spacing:.8px;margin-bottom:8px;">Top Desviaciones (Costos)</div>
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#F8F9FB;">
                            <th style="padding:5px 8px;font-size:9px;color:#94A3B8;font-weight:600;text-align:left;">Cuenta</th>
                            <th style="padding:5px 8px;font-size:9px;color:#94A3B8;font-weight:600;text-align:right;">Real</th>
                            <th style="padding:5px 8px;font-size:9px;color:#94A3B8;font-weight:600;text-align:right;">Ppto</th>
                            <th style="padding:5px 8px;font-size:9px;color:#94A3B8;font-weight:600;text-align:right;">Var $</th>
                            <th style="padding:5px 8px;font-size:9px;color:#94A3B8;font-weight:600;text-align:right;">%</th>
                        </tr>
                    </thead>
                    <tbody>{top_rows_html}</tbody>
                </table>
            </div>

            <!-- Barras P&L -->
            <div style="padding:16px 20px;">
                <div style="font-size:10px;font-weight:700;color:#2d0050;text-transform:uppercase;
                            letter-spacing:.8px;margin-bottom:12px;">Ejecución P&L</div>
                {barras_html}
            </div>
        </div>

        <!-- Footer -->
        <div style="background:#F8F9FB;padding:7px 20px;border-top:1px solid #E2E8F0;">
            <span style="font-size:9px;color:#94A3B8;">
                Generado automáticamente · Kreems FP&A · {date.today().strftime('%d/%m/%Y %H:%M')}
            </span>
        </div>
    </div>
    """
    st.markdown(html_preview, unsafe_allow_html=True)

    # ── Comentario IA (debajo del preview) ──────────────────────
    if analisis_txt:
        st.markdown("#### Comentario Ejecutivo IA")
        st.markdown(f"""
        <div style="background:#F8F9FB;border-left:3px solid #2d0050;
                    padding:14px 18px;border-radius:6px;font-size:13px;
                    color:#1e1e1e;line-height:1.7;margin-top:8px;">
            {analisis_txt.replace(chr(10), '<br>')}
        </div>
        """, unsafe_allow_html=True)


# ── PANEL LATERAL ────────────────────────────────────────────────
with col_side:
    st.markdown("#### KPI Semáforo")

    for lbl, pct, inv in [
        ("Ventas",       pct_v,  False),
        ("Ut. Bruta",    pct_ub, False),
        ("EBIT",         pct_e,  False),
        ("Ut. Neta",     pct_u,  False),
        ("Gastos Total", pct_g,  True),
    ]:
        icono = "🟢" if _sem_color(pct, inv) == "#0F6E56" else (
                "🟡" if _sem_color(pct, inv) == "#b45309" else "🔴")
        col_txt = _sem_color(pct, inv)
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:6px 0;border-bottom:1px solid #F1F5F9;font-size:13px;'>"
            f"<span>{icono} {lbl}</span>"
            f"<span style='color:{col_txt};font-weight:700;'>{pct:.1f}%</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("#### Acciones")

    if analisis_txt:
        st.success("✅ Análisis IA listo")
    else:
        st.info("Presiona **🤖 Generar análisis IA** para agregar comentario ejecutivo al reporte.")

    # Descarga PDF si ya fue generado
    if "flash_pdf_bytes" in st.session_state:
        st.download_button(
            label="⬇️ Descargar Flash Report PDF",
            data=st.session_state["flash_pdf_bytes"],
            file_name=st.session_state.get("flash_pdf_name", "flash_report.pdf"),
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown("#### ¿Qué incluye?")
    st.markdown("""
    <div style="font-size:12px;color:#64748b;line-height:1.8;">
    📊 4 KPIs ejecutivos con semáforo<br>
    🎯 Estado general de ejecución<br>
    📋 Top 7 desviaciones de costos<br>
    📈 Barras de ejecución P&L<br>
    🤖 Comentario IA opcional<br>
    📄 PDF descargable 1 página
    </div>
    """, unsafe_allow_html=True)
