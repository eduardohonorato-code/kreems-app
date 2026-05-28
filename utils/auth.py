"""
Autenticación — lee usuarios desde admin.usuarios (PostgreSQL).
Si la tabla no existe, cae back a .streamlit/secrets.toml.
"""
import streamlit as st
from utils.components import _logo_html, inject_font
from datetime import date


def _subtitulo_login() -> str:
    return f"Control Presupuestario {date.today().year}"


def _get_user_from_db(usuario: str, password: str) -> dict | None:
    """
    Busca el usuario en admin.usuarios.
    Retorna dict con {rol, nombre, cc_permitidos} o None si no existe / inactivo.
    """
    try:
        from utils.db import get_engine
        from sqlalchemy import text
        with get_engine().connect() as conn:
            row = conn.execute(text("""
                SELECT nombre, rol, cc_permitidos
                FROM admin.usuarios
                WHERE usuario = :u AND password = :p AND activo = TRUE
            """), {"u": usuario, "p": password}).fetchone()
        if row:
            return {
                "nombre": row[0],
                "rol": row[1],
                "cc_permitidos": list(row[2]) if row[2] else None,
            }
    except Exception:
        pass
    return None


def _get_user_from_secrets(usuario: str, password: str) -> dict | None:
    """Fallback: lee desde secrets.toml."""
    users = st.secrets.get("users", {})
    if usuario in users and users[usuario]["password"] == password:
        return {
            "nombre": users[usuario]["nombre"],
            "rol": users[usuario]["rol"],
            "cc_permitidos": users[usuario].get("cc", None),
        }
    return None


def login() -> bool:
    """Muestra el formulario de login. Retorna True si el usuario está autenticado."""
    if "usuario" in st.session_state:
        return True

    inject_font()
    st.markdown(f"""
        <div style="text-align:center; margin-top:80px; margin-bottom:8px;">
            {_logo_html(altura=72)}
            <div style="color:#888; font-size:14px; margin-top:12px;">
                {_subtitulo_login()}
            </div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        usuario = st.text_input("Usuario", placeholder="tu usuario")
        password = st.text_input("Contraseña", type="password", placeholder="••••••••")
        if st.button("Ingresar", use_container_width=True):
            # Intentar BD primero, luego secrets como fallback
            user_data = _get_user_from_db(usuario, password)
            if user_data is None:
                user_data = _get_user_from_secrets(usuario, password)

            if user_data:
                st.session_state["usuario"] = usuario
                st.session_state["rol"] = user_data["rol"]
                st.session_state["nombre"] = user_data["nombre"]
                st.session_state["cc_permitidos"] = user_data["cc_permitidos"]
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


def get_cc_sql_filter() -> str:
    """Fragmento SQL para filtrar por CCs permitidos.
    Retorna '' si el usuario tiene acceso a todos los CCs.
    Retorna 'AND codigo_cc IN (...)'  si tiene restricción.
    """
    cc_list = st.session_state.get("cc_permitidos", None)
    if not cc_list:
        return ""
    in_clause = ", ".join(f"'{cc}'" for cc in cc_list)
    return f"AND codigo_cc IN ({in_clause})"
