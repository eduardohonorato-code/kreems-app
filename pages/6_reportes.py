"""
Reportes Guardados — Historial de análisis IA
"""
import streamlit as st
import pandas as pd
import json
from utils.auth import login
from utils.components import header, sidebar_kreems
from utils.db import query_live as query

st.set_page_config(page_title="Reportes Guardados · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

sidebar_kreems(mostrar_sociedad=False)
header("Reportes Guardados")

st.markdown("""
<p style="color:#888; font-size:13px; margin-bottom:20px;">
    Aquí se almacenan los análisis IA generados desde las páginas del modelo.
    Puedes revisar, comparar y eliminar reportes guardados.
</p>
""", unsafe_allow_html=True)


# ── FUNCIONES ────────────────────────────────────────────────
def cargar_reportes():
    try:
        return query("""
            SELECT id, titulo, tipo, periodo_desde, periodo_hasta,
                   sociedad, datos_json, analisis_ia, creado_por, creado_en
            FROM reports.reportes_guardados
            ORDER BY creado_en DESC
        """, {})
    except Exception as e:
        st.error(f"No se pudo cargar la tabla de reportes: {e}")
        st.info("Asegúrate de haber ejecutado: `sql/06_reportes_guardados.sql`")
        return pd.DataFrame()


def eliminar_reporte(reporte_id: int):
    try:
        from sqlalchemy import text as sqlt
        from utils.db import get_engine
        with get_engine().begin() as conn:
            conn.execute(sqlt("DELETE FROM reports.reportes_guardados WHERE id = :id"), {"id": reporte_id})
        return True
    except Exception as e:
        st.error(f"Error al eliminar: {e}")
        return False


# ── CARGAR Y FILTRAR ─────────────────────────────────────────
df_rpt = cargar_reportes()

if df_rpt.empty:
    st.info("Aún no hay reportes guardados. Genera un análisis IA desde cualquier página y guárdalo.")
    st.stop()

col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
with col_f1:
    filtro_soc = st.selectbox("Sociedad", ["Todas"] + sorted(df_rpt["sociedad"].dropna().unique().tolist()))
with col_f2:
    filtro_tipo = st.selectbox("Tipo", ["Todos"] + sorted(df_rpt["tipo"].dropna().unique().tolist()))
with col_f3:
    busqueda = st.text_input("Buscar en título", placeholder="Ej: Mayo, EERR...")

df_vis = df_rpt.copy()
if filtro_soc != "Todas":
    df_vis = df_vis[df_vis["sociedad"] == filtro_soc]
if filtro_tipo != "Todos":
    df_vis = df_vis[df_vis["tipo"] == filtro_tipo]
if busqueda:
    df_vis = df_vis[df_vis["titulo"].str.contains(busqueda, case=False, na=False)]

st.markdown(
    f"<div style='color:#aaa;font-size:12px;margin:4px 0 16px;'>{len(df_vis)} reporte(s) encontrado(s)</div>",
    unsafe_allow_html=True
)

# ── TARJETAS DE REPORTE ──────────────────────────────────────
for _, row in df_vis.iterrows():
    reporte_id    = int(row["id"])
    titulo        = row["titulo"]
    sociedad      = row["sociedad"]
    periodo_desde = row["periodo_desde"]
    periodo_hasta = row["periodo_hasta"]
    creado_por    = row.get("creado_por", "") or ""
    creado_en     = pd.to_datetime(row["creado_en"]).strftime("%d %b %Y %H:%M")
    analisis_txt  = row.get("analisis_ia", "") or ""
    datos_json    = row.get("datos_json") or {}

    if isinstance(datos_json, str):
        try:
            datos_json = json.loads(datos_json)
        except Exception:
            datos_json = {}

    ventas_r = datos_json.get("ventas_r", 0)
    ventas_p = datos_json.get("ventas_p", 0)
    ebit_r   = datos_json.get("ebit_r", 0)
    un_r     = datos_json.get("un_r", 0)
    pct_v    = (ventas_r / ventas_p * 100) if ventas_p else 0
    pct_e    = (ebit_r / ventas_r * 100) if ventas_r else 0
    pct_un   = (un_r / ventas_r * 100) if ventas_r else 0
    color_v  = "#0F6E56" if pct_v >= 100 else "#cc0000"

    # Toggle de visibilidad del análisis
    toggle_key = f"show_analisis_{reporte_id}"
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = False

    with st.container(border=True):
        # ── Encabezado ──
        col_titulo, col_acciones = st.columns([5, 1])
        with col_titulo:
            st.markdown(f"**{titulo}**")
            meta = f"📅 {periodo_desde} → {periodo_hasta} &nbsp;·&nbsp; 🏭 {sociedad} &nbsp;·&nbsp; 🕒 {creado_en}"
            if creado_por:
                meta += f" &nbsp;·&nbsp; 👤 {creado_por}"
            st.markdown(f"<span style='font-size:12px;color:#999;'>{meta}</span>", unsafe_allow_html=True)

        with col_acciones:
            if st.button("🗑 Eliminar", key=f"del_{reporte_id}", type="secondary", use_container_width=True):
                if eliminar_reporte(reporte_id):
                    st.success("Reporte eliminado.")
                    st.rerun()

        # ── KPI Cards ──
        if ventas_r or ebit_r:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            kc1, kc2, kc3 = st.columns(3)
            kpis = [
                ("Ventas Real",  f"${ventas_r/1_000_000:,.1f}M", f"{pct_v:.1f}% del objetivo", color_v),
                ("EBIT Real",    f"${ebit_r/1_000_000:,.1f}M",   f"Margen {pct_e:.1f}%",       "#555"),
                ("Utilidad Neta",f"${un_r/1_000_000:,.1f}M",     f"Margen {pct_un:.1f}%",      "#555"),
            ]
            for col, (label, valor, sub, color) in zip([kc1, kc2, kc3], kpis):
                with col:
                    st.markdown(f"""
                    <div style="background:#f8f9fc; border-radius:8px; padding:10px 14px;
                                border:1px solid #e8eaf0; text-align:center;">
                        <div style="font-size:10px; color:#999; margin-bottom:2px;">{label}</div>
                        <div style="font-size:17px; font-weight:700; color:#2d0050;">{valor}</div>
                        <div style="font-size:10px; color:{color};">{sub}</div>
                    </div>""", unsafe_allow_html=True)

        # ── Análisis IA (toggle) ──
        if analisis_txt:
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            label_btn = "▲ Ocultar análisis" if st.session_state[toggle_key] else "▼ Ver análisis completo"
            if st.button(label_btn, key=f"toggle_{reporte_id}", use_container_width=False):
                st.session_state[toggle_key] = not st.session_state[toggle_key]
                st.rerun()

            if st.session_state[toggle_key]:
                st.markdown(f"""
                <div style="background:#fafafa; border:1px solid #e2e8f0;
                            border-left:4px solid #2d0050; border-radius:8px;
                            padding:16px 20px; margin-top:8px; font-size:13px;
                            line-height:1.8; color:#333; white-space:pre-wrap;">
{analisis_txt}</div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
