"""
Administración de Usuarios — Solo admin
CRUD completo sobre admin.usuarios
"""
import streamlit as st
import pandas as pd
from utils.auth import login, requiere_admin
from utils.components import header, sidebar_kreems
from utils.db import get_engine, query_live
from sqlalchemy import text as sqlt

st.set_page_config(page_title="Admin Usuarios · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

requiere_admin()

sidebar_kreems(mostrar_sociedad=False)
header("Administración de Usuarios")

st.markdown("""
<p style="color:#888; font-size:13px; margin-bottom:20px;">
    Gestiona los usuarios que tienen acceso a la app. Los cambios aplican de inmediato.
    Asegúrate de haber ejecutado <code>sql/07_usuarios.sql</code> antes de usar esta página.
</p>
""", unsafe_allow_html=True)


# ── HELPERS ────────────────────────────────────────────────────
def cargar_usuarios() -> pd.DataFrame:
    try:
        return query_live("""
            SELECT id, usuario, nombre, rol, cc_permitidos, activo, creado_en
            FROM admin.usuarios
            ORDER BY id
        """, {})
    except Exception as e:
        st.error(f"Error al cargar usuarios: {e}")
        st.info("Ejecuta primero: `sql/07_usuarios.sql`")
        return pd.DataFrame()


def ejecutar(sql: str, params: dict):
    try:
        with get_engine().begin() as conn:
            conn.execute(sqlt(sql), params)
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False


# ── TABLA ACTUAL ───────────────────────────────────────────────
df_users = cargar_usuarios()

if df_users.empty:
    st.stop()

st.markdown("##### Usuarios registrados")

# Formatear para mostrar
df_vis = df_users.copy()
df_vis["cc_permitidos"] = df_vis["cc_permitidos"].apply(
    lambda v: ", ".join(v) if v is not None and len(v) > 0 else "Todos"
)
df_vis["activo"] = df_vis["activo"].map({True: "✓ Activo", False: "✗ Inactivo"})
df_vis["creado_en"] = pd.to_datetime(df_vis["creado_en"]).dt.strftime("%d %b %Y")
df_vis = df_vis.rename(columns={
    "id": "ID", "usuario": "Usuario", "nombre": "Nombre",
    "rol": "Rol", "cc_permitidos": "CC Permitidos",
    "activo": "Estado", "creado_en": "Creado"
})

st.dataframe(df_vis, use_container_width=True, hide_index=True, height=220)

st.markdown("<br>", unsafe_allow_html=True)

# ── TABS: CREAR / EDITAR / ELIMINAR ───────────────────────────
tab_crear, tab_editar, tab_pwd, tab_eliminar = st.tabs([
    "➕ Nuevo usuario",
    "✏️ Editar usuario",
    "🔑 Cambiar contraseña",
    "🗑 Eliminar usuario",
])

CC_OPCIONES = ["CC-01", "CC-02", "CC-03", "CC-04"]

# ── TAB: CREAR ─────────────────────────────────────────────────
with tab_crear:
    with st.form("form_crear_usuario", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nu_usuario = st.text_input("Usuario *", placeholder="ej: juan.perez")
            nu_nombre  = st.text_input("Nombre completo *", placeholder="ej: Juan Pérez")
        with c2:
            nu_password = st.text_input("Contraseña *", type="password")
            nu_rol      = st.selectbox("Rol *", ["viewer", "admin"])

        nu_cc_todos = st.checkbox("Acceso a todos los CC", value=True)
        nu_cc_sel   = st.multiselect(
            "CC Permitidos (solo si no es acceso total)",
            CC_OPCIONES,
            disabled=nu_cc_todos,
        )
        nu_activo = st.checkbox("Usuario activo", value=True)
        submitted = st.form_submit_button("Crear usuario", type="primary")

    if submitted:
        if not nu_usuario or not nu_password or not nu_nombre:
            st.warning("Completa los campos obligatorios (*).")
        else:
            cc_val = None if nu_cc_todos else (nu_cc_sel or None)
            ok = ejecutar("""
                INSERT INTO admin.usuarios (usuario, password, nombre, rol, cc_permitidos, activo)
                VALUES (:u, :p, :n, :r, :cc, :a)
            """, {
                "u": nu_usuario.strip(),
                "p": nu_password,
                "n": nu_nombre.strip(),
                "r": nu_rol,
                "cc": cc_val,
                "a": nu_activo,
            })
            if ok:
                st.success(f"✓ Usuario **{nu_usuario}** creado exitosamente.")
                st.rerun()

# ── TAB: EDITAR ────────────────────────────────────────────────
with tab_editar:
    usuarios_lista = df_users["usuario"].tolist()
    ed_sel = st.selectbox("Seleccionar usuario a editar", usuarios_lista, key="ed_sel")
    row_sel = df_users[df_users["usuario"] == ed_sel].iloc[0]

    with st.form("form_editar_usuario"):
        e1, e2 = st.columns(2)
        with e1:
            ed_nombre = st.text_input("Nombre", value=row_sel["nombre"])
            ed_rol    = st.selectbox("Rol", ["viewer", "admin"],
                                     index=0 if row_sel["rol"] == "viewer" else 1)
        with e2:
            ed_activo = st.checkbox("Usuario activo", value=bool(row_sel["activo"]))

        cc_actuales = list(row_sel["cc_permitidos"]) if row_sel["cc_permitidos"] else []
        ed_cc_todos = st.checkbox("Acceso a todos los CC", value=(len(cc_actuales) == 0))
        ed_cc_sel   = st.multiselect(
            "CC Permitidos",
            CC_OPCIONES,
            default=cc_actuales,
            disabled=ed_cc_todos,
        )
        sub_edit = st.form_submit_button("Guardar cambios", type="primary")

    if sub_edit:
        cc_val = None if ed_cc_todos else (ed_cc_sel or None)
        ok = ejecutar("""
            UPDATE admin.usuarios
            SET nombre=:n, rol=:r, cc_permitidos=:cc, activo=:a
            WHERE usuario=:u
        """, {"n": ed_nombre, "r": ed_rol, "cc": cc_val, "a": ed_activo, "u": ed_sel})
        if ok:
            st.success(f"✓ Usuario **{ed_sel}** actualizado.")
            st.rerun()

# ── TAB: CAMBIAR CONTRASEÑA ────────────────────────────────────
with tab_pwd:
    usuarios_lista_p = df_users["usuario"].tolist()
    pwd_sel = st.selectbox("Seleccionar usuario", usuarios_lista_p, key="pwd_sel")

    with st.form("form_pwd"):
        nueva_pwd  = st.text_input("Nueva contraseña", type="password")
        confirmar  = st.text_input("Confirmar contraseña", type="password")
        sub_pwd    = st.form_submit_button("Actualizar contraseña", type="primary")

    if sub_pwd:
        if not nueva_pwd:
            st.warning("Ingresa una contraseña.")
        elif nueva_pwd != confirmar:
            st.warning("Las contraseñas no coinciden.")
        else:
            ok = ejecutar(
                "UPDATE admin.usuarios SET password=:p WHERE usuario=:u",
                {"p": nueva_pwd, "u": pwd_sel}
            )
            if ok:
                st.success(f"✓ Contraseña de **{pwd_sel}** actualizada.")

# ── TAB: ELIMINAR ──────────────────────────────────────────────
with tab_eliminar:
    # No dejar eliminar al usuario actual
    yo = st.session_state.get("usuario", "")
    opciones_eliminar = [u for u in df_users["usuario"].tolist() if u != yo]

    if not opciones_eliminar:
        st.info("No hay otros usuarios para eliminar.")
    else:
        del_sel = st.selectbox("Seleccionar usuario a eliminar", opciones_eliminar, key="del_usr_sel")
        st.warning(f"⚠ Esta acción eliminará permanentemente al usuario **{del_sel}**.")
        confirmar_del = st.checkbox("Confirmo que quiero eliminar este usuario", key="confirm_del_usr")
        if st.button("Eliminar usuario", type="primary", disabled=not confirmar_del):
            ok = ejecutar("DELETE FROM admin.usuarios WHERE usuario=:u", {"u": del_sel})
            if ok:
                st.success(f"✓ Usuario **{del_sel}** eliminado.")
                st.rerun()
