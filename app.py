"""
Kreems FP&A — Inicio
"""
import streamlit as st
from datetime import date
from utils.auth import login
from utils.components import header, sidebar_kreems

_ANO = date.today().year

st.set_page_config(
    page_title="Inicio · Kreems",
    page_icon="💜",
    layout="wide",
    initial_sidebar_state="expanded"
)

if not login():
    st.stop()

sidebar_kreems(mostrar_sociedad=False)
header("Inicio")

nombre = st.session_state.get("nombre", "")

st.markdown(f"""
<div style="padding:24px 0 8px;">
    <span style="font-size:1.1rem;color:#888;">Bienvenido,</span>
    <span style="font-size:1.3rem;font-weight:700;color:#2d0050;margin-left:8px;">{nombre}</span>
</div>
<p style="color:#999;font-size:14px;margin-bottom:32px;">
    Selecciona una sección para comenzar el análisis presupuestario {_ANO}.
</p>
""", unsafe_allow_html=True)

cards = [
    ("📊", "Resumen Ejecutivo",
     "Ventas reales vs presupuesto, gauge de cumplimiento y ejecución por CC.",
     "pages/1_dashboard.py"),
    ("📋", "Estado de Resultados",
     "P&L completo: Ventas, Costo Variable, Costo Fijo, OPEX, EBIT y Utilidad Neta.",
     "pages/2_eerr.py"),
    ("🏢", "Centro de Costos",
     "Tarjetas por centro de costo y gráfico de ejecución real vs presupuesto.",
     "pages/3_centro_costos.py"),
    ("📑", "Control por Cuenta Contable",
     "Detalle por cuenta con alertas, KPIs de ejecución y filtros por CC y clasificación.",
     "pages/4_control_cuentas.py"),
    ("🤖", "Reportes Guardados",
     "Análisis IA guardados del Estado de Resultados. Revisa y compara períodos.",
     "pages/6_reportes.py"),
]

# Tarjeta de admin solo visible para admins
if st.session_state.get("rol") == "admin":
    cards.append((
        "👤", "Admin Usuarios",
        "Gestiona los usuarios de la app: crear, editar, cambiar contraseña y eliminar.",
        "pages/7_admin_usuarios.py",
    ))

n_cols = len(cards)
cols = st.columns(n_cols)
for col, (icono, titulo, desc, path) in zip(cols, cards):
    with col:
        st.markdown(f"""
        <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;
                    padding:22px 20px;height:160px;
                    box-shadow:0 1px 4px rgba(0,0,0,0.06);">
            <div style="font-size:2rem;margin-bottom:10px;">{icono}</div>
            <div style="font-size:15px;font-weight:700;color:#0F172A;margin-bottom:8px;">{titulo}</div>
            <div style="font-size:12px;color:#94A3B8;line-height:1.5;">{desc}</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.page_link(path, label=f"Ir a {titulo} →", use_container_width=True)
