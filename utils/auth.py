"""
Autenticación simple por usuario y contraseña.
Los usuarios se definen en .streamlit/secrets.toml
"""
import streamlit as st
from utils.components import _logo_html, inject_font


def login():
    """Muestra el formulario de login. Retorna True si el usuario está autenticado."""
    if "usuario" in st.session_state:
        return True

    inject_font()
    st.markdown(f"""
        <div style="text-align:center; margin-top:80px; margin-bottom:8px;">
            {_logo_html(altura=72)}
            <div style="color:#888; font-size:14px; margin-top:12px;">
                Control Presupuestario 2026
            </div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        usuario = st.text_input("Usuario", placeholder="tu usuario")
        password = st.text_input("Contraseña", type="password", placeholder="••••••••")
        if st.button("Ingresar", use_container_width=True):
            users = st.secrets.get("users", {})
            if usuario in users and users[usuario]["password"] == password:
                st.session_state["usuario"] = usuario
                st.session_state["rol"] = users[usuario]["rol"]
                st.session_state["nombre"] = users[usuario]["nombre"]
                st.session_state["cc_permitidos"] = users[usuario].get("cc", None)
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    return False


def logout():
    """Botón de cerrar sesión en el sidebar."""
    with st.sidebar:
        st.markdown("---")
        nombre = st.session_state.get("nombre", "")
        rol = st.session_state.get("rol", "")
        st.markdown(f"**{nombre}** · {rol}")
        if st.button("Cerrar sesión"):
            for key in ["usuario", "rol", "nombre", "cc_permitidos"]:
                st.session_state.pop(key, None)
            st.rerun()


def requiere_admin():
    """Bloquea la página si el usuario no es admin."""
    if st.session_state.get("rol") != "admin":
        st.error("No tienes permisos para acceder a esta sección.")
        st.stop()


def get_cc_filter() -> list | None:
    """Retorna la lista de CCs permitidos para el usuario actual. None = todos."""
    return st.session_state.get("cc_permitidos", None)
