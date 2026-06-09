"""
Carga de Datos — Solo admin
Permite subir los Excel de ACUÑA, Gran Natural y Presupuesto
y ejecutar el ETL directamente desde la webapp.
"""
import streamlit as st
import pandas as pd
from datetime import date
from utils.auth import login, requiere_admin
from utils.components import header, sidebar_kreems
from utils.db import query
from utils.etl import run_etl_acuna, run_etl_gn, run_etl_presupuesto, run_etl_cv_sync, guardar_cv_staging, eliminar_cv_staging

_ANO = date.today().year

st.set_page_config(page_title="Cargar Datos · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

requiere_admin()
sidebar_kreems(mostrar_sociedad=False)
header("Carga de Datos")

# ── CSS extra ─────────────────────────────────────────────────
st.markdown("""
<style>
    .info-box {
        background: #fdf5fb;
        border: 1px solid #f0dff0;
        border-radius: 10px;
        padding: 14px 16px;
        font-size: 12px;
        line-height: 1.7;
    }
    .warn-box {
        background: #fff8e8;
        border: 1px solid #f0d878;
        border-radius: 10px;
        padding: 14px 16px;
        font-size: 12px;
        line-height: 1.7;
    }
</style>
""", unsafe_allow_html=True)


# ── HELPER ────────────────────────────────────────────────────
def mostrar_resultado(resultado: dict):
    if resultado["ok"]:
        st.success(
            f"✓ Carga exitosa — **{resultado['n_registros']} registros** cargados · "
            f"Periodo: **{resultado['periodo']}**"
        )
    else:
        st.error(f"✗ Error en la carga: {resultado['error']}")
    with st.expander("Ver log de ejecución", expanded=not resultado["ok"]):
        st.code("\n".join(resultado["logs"]), language=None)


# ── TABS ──────────────────────────────────────────────────────
tab_acuna, tab_gn, tab_ppto, tab_cv, tab_log = st.tabs([
    "🏭  ACUÑA",
    "🌿  Gran Natural",
    "📋  Presupuesto",
    "💰  Costo Variable Real",
    "📜  Historial de Cargas",
])


# ────────────────────────────────────────────────────────────────
# TAB: ACUÑA
# ────────────────────────────────────────────────────────────────
with tab_acuna:
    st.markdown("#### Cargar EERR ACUÑA — Excel Obuma")
    st.caption(
        "Sube el archivo mensual de ACUÑA. El sistema detecta el periodo "
        "automáticamente y reemplaza solo los datos de ese mes."
    )
    st.markdown("")

    col_up, col_info = st.columns([1.6, 1])

    with col_up:
        archivo_acuna = st.file_uploader(
            "Seleccionar archivo Excel ACUÑA",
            type=["xlsx"], key="upload_acuna",
            label_visibility="hidden",
        )

    with col_info:
        st.markdown("""
        <div class="info-box">
            <b style="color:#2d0050;">Formato esperado</b><br>
            • Archivo Excel Obuma ACUÑA (.xlsx)<br>
            • Fila 3: encabezado con rango de fechas<br>
            • Fila 6: nombres de columnas CC<br>
            • Columnas CC válidas: Ninguno, Administracion,
              Costo Fabrica, Distribución, Ventas, Gerencia,
              Maquina Comodato<br>
            • Las cuentas se mapean via <code>dim_homologacion</code>
        </div>
        """, unsafe_allow_html=True)

    if archivo_acuna:
        file_bytes = archivo_acuna.read()
        st.markdown(
            f"📄 **{archivo_acuna.name}** · {len(file_bytes)/1024:.1f} KB"
        )
        st.markdown("")

        if st.button("Ejecutar ETL ACUÑA", type="primary", key="btn_etl_acuna"):
            with st.spinner("Procesando archivo y cargando a Supabase..."):
                resultado = run_etl_acuna(file_bytes)
            mostrar_resultado(resultado)
            if resultado["ok"]:
                st.cache_data.clear()


# ────────────────────────────────────────────────────────────────
# TAB: GRAN NATURAL
# ────────────────────────────────────────────────────────────────
with tab_gn:
    st.markdown("#### Cargar EERR Gran Natural — Excel Obuma")
    st.caption(
        "Sube el archivo mensual de Gran Natural. El periodo se detecta "
        "automáticamente y reemplaza solo los datos de ese mes."
    )
    st.markdown("")

    col_up2, col_info2 = st.columns([1.6, 1])

    with col_up2:
        archivo_gn = st.file_uploader(
            "Seleccionar archivo Excel Gran Natural",
            type=["xlsx"], key="upload_gn",
            label_visibility="hidden",
        )

    with col_info2:
        st.markdown("""
        <div class="info-box">
            <b style="color:#2d0050;">Formato esperado</b><br>
            • Archivo Excel Obuma GN (.xlsx)<br>
            • Fila 3: encabezado con rango de fechas<br>
            • 7 columnas: Cuenta, Ninguno, Administracion,
              Comercial, Distribucion, Produccion, Total<br>
            • Las cuentas se cargan directamente
              (mismo plan de cuentas GN)
        </div>
        """, unsafe_allow_html=True)

    if archivo_gn:
        file_bytes_gn = archivo_gn.read()
        st.markdown(
            f"📄 **{archivo_gn.name}** · {len(file_bytes_gn)/1024:.1f} KB"
        )
        st.markdown("")

        if st.button("Ejecutar ETL Gran Natural", type="primary", key="btn_etl_gn"):
            with st.spinner("Procesando archivo y cargando a Supabase..."):
                resultado_gn = run_etl_gn(file_bytes_gn)
            mostrar_resultado(resultado_gn)
            if resultado_gn["ok"]:
                st.cache_data.clear()


# ────────────────────────────────────────────────────────────────
# TAB: PRESUPUESTO
# ────────────────────────────────────────────────────────────────
with tab_ppto:
    st.markdown("#### Cargar Presupuesto Maestro")
    st.caption(
        "Esta carga reemplaza el presupuesto anual completo. "
        "Úsala solo cuando el archivo maestro cambie."
    )
    st.markdown("")

    col_up3, col_info3 = st.columns([1.6, 1])

    with col_up3:
        archivo_ppto = st.file_uploader(
            "Seleccionar Presupuesto_Maestro.xlsx",
            type=["xlsx"], key="upload_ppto",
            label_visibility="hidden",
        )

    with col_info3:
        st.markdown("""
        <div class="warn-box">
            <b style="color:#7a5200;">Hojas requeridas</b><br>
            • <code>ADMINISTRACIÓN</code> → CC-01<br>
            • <code>PRODUCCIÓN</code> → CC-04<br>
            • <code>COMERCIAL</code> → CC-02<br>
            • <code>DISTRIBUCIÓN</code> → CC-03<br>
            • <code>Consolidado_Automatico</code> → Ventas + CV<br><br>
            ⚠ <b>Se elimina todo el presupuesto {_ANO}</b>
            antes de insertar los nuevos datos.
        </div>
        """, unsafe_allow_html=True)

    if archivo_ppto:
        file_bytes_ppto = archivo_ppto.read()
        st.markdown(
            f"📄 **{archivo_ppto.name}** · {len(file_bytes_ppto)/1024:.1f} KB"
        )
        st.markdown("")

        st.warning(
            f"⚠ **Atención:** Se eliminarán todos los registros de presupuesto {_ANO} "
            "y se reemplazarán con los datos del archivo subido."
        )

        confirmar = st.checkbox(
            f"Confirmo que quiero reemplazar el presupuesto completo {_ANO}",
            key="confirm_ppto"
        )

        if confirmar:
            if st.button("Ejecutar ETL Presupuesto", type="primary", key="btn_etl_ppto"):
                with st.spinner("Procesando presupuesto anual..."):
                    resultado_ppto = run_etl_presupuesto(file_bytes_ppto)
                mostrar_resultado(resultado_ppto)
                if resultado_ppto["ok"]:
                    st.cache_data.clear()


# ────────────────────────────────────────────────────────────────
# TAB: COSTO VARIABLE REAL
# ────────────────────────────────────────────────────────────────
with tab_cv:
    st.markdown("#### Costo Variable Real — Ingreso Manual")
    st.caption(
        "Ingresa el costo variable real por sociedad y periodo. "
        "Los datos se guardan en staging y luego se sincronizan a fact_real."
    )
    st.markdown("")

    col_tabla, col_form = st.columns([1.4, 1])

    with col_tabla:
        st.markdown("##### Datos actuales en staging")
        try:
            df_cv = query("""
                SELECT
                    TO_CHAR(periodo, 'YYYY-MM') AS periodo,
                    sociedad,
                    monto
                FROM staging.cv_real_manual
                ORDER BY periodo, sociedad
            """, {})

            if not df_cv.empty:
                df_cv_show = df_cv.rename(columns={
                    "periodo": "Periodo", "sociedad": "Sociedad", "monto": "Monto CV Real"
                })
                st.dataframe(
                    df_cv_show.style.format({"Monto CV Real": lambda v: f"${v:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                )
                st.caption(f"{len(df_cv)} registros en staging.cv_real_manual")
            else:
                st.info("No hay datos ingresados aún.")

        except Exception as e:
            st.warning(f"No se pudo cargar staging: {e}")

    with col_form:
        st.markdown("##### Agregar / actualizar registro")

        MESES_OPTS = {
            f"Enero ({_ANO}-01)":       f"{_ANO}-01", f"Febrero ({_ANO}-02)":     f"{_ANO}-02",
            f"Marzo ({_ANO}-03)":       f"{_ANO}-03", f"Abril ({_ANO}-04)":       f"{_ANO}-04",
            f"Mayo ({_ANO}-05)":        f"{_ANO}-05", f"Junio ({_ANO}-06)":       f"{_ANO}-06",
            f"Julio ({_ANO}-07)":       f"{_ANO}-07", f"Agosto ({_ANO}-08)":      f"{_ANO}-08",
            f"Septiembre ({_ANO}-09)":  f"{_ANO}-09", f"Octubre ({_ANO}-10)":     f"{_ANO}-10",
            f"Noviembre ({_ANO}-11)":   f"{_ANO}-11", f"Diciembre ({_ANO}-12)":   f"{_ANO}-12",
        }

        with st.form("form_cv", clear_on_submit=True):
            mes_lbl   = st.selectbox("Periodo", list(MESES_OPTS.keys()), key="cv_mes")
            sociedad  = st.radio("Sociedad", ["ACUÑA", "GRAN_NATURAL"],
                                 horizontal=True, key="cv_soc")
            monto     = st.number_input("Monto CV Real ($)", min_value=0.0,
                                        step=100_000.0, format="%.0f", key="cv_monto")
            submitted = st.form_submit_button("Guardar en staging", type="primary",
                                              use_container_width=True)

        if submitted:
            periodo_sel = MESES_OPTS[mes_lbl]
            if monto <= 0:
                st.error("El monto debe ser mayor a 0.")
            else:
                res = guardar_cv_staging(periodo_sel, sociedad, monto)
                if res["ok"]:
                    st.success(f"Guardado: {sociedad} {periodo_sel} -> ${monto:,.0f}")
                    st.rerun()
                else:
                    st.error(f"Error: {res['error']}")

        st.markdown("---")
        st.markdown("##### Eliminar registro")
        with st.form("form_cv_del", clear_on_submit=True):
            mes_del = st.selectbox("Periodo a eliminar", list(MESES_OPTS.keys()), key="cv_del_mes")
            soc_del = st.radio("Sociedad", ["ACUÑA", "GRAN_NATURAL"],
                               horizontal=True, key="cv_del_soc")
            del_btn = st.form_submit_button("Eliminar de staging", type="secondary",
                                            use_container_width=True)
        if del_btn:
            res_del = eliminar_cv_staging(MESES_OPTS[mes_del], soc_del)
            if res_del["ok"]:
                st.success(f"Eliminado: {soc_del} {MESES_OPTS[mes_del]}")
                st.rerun()
            else:
                st.error(f"Error: {res_del['error']}")

    st.markdown("---")
    st.markdown("##### Sincronizar staging a fact_real")
    st.caption(
        "Toma todos los registros de staging.cv_real_manual y los escribe "
        "en marts.fact_real como COSTO_VAR (cuenta 3.1.01.001, CC-00)."
    )
    col_sync, _ = st.columns([1, 2])
    with col_sync:
        if st.button("Sincronizar CV Real", type="primary", key="btn_cv_sync",
                     use_container_width=True):
            with st.spinner("Sincronizando..."):
                res_sync = run_etl_cv_sync()
            mostrar_resultado({**res_sync, "periodo": "staging completo"})
            if res_sync["ok"]:
                st.cache_data.clear()


# ────────────────────────────────────────────────────────────────
# TAB: HISTORIAL
# ────────────────────────────────────────────────────────────────
with tab_log:
    st.markdown("#### Historial de Cargas")

    if st.button("Actualizar", key="btn_refresh_log"):
        st.rerun()

    try:
        df_log = query("""
            SELECT
                fecha_carga,
                tabla_destino,
                periodo,
                registros_cargados,
                estado,
                observaciones
            FROM audit.log_carga
            ORDER BY fecha_carga DESC
            LIMIT 60
        """, {})

        if not df_log.empty:
            df_log["fecha_carga"] = pd.to_datetime(df_log["fecha_carga"]).dt.strftime("%Y-%m-%d %H:%M")
            df_log = df_log.rename(columns={
                "fecha_carga":        "Fecha",
                "tabla_destino":      "Tabla",
                "periodo":            "Periodo",
                "registros_cargados": "Registros",
                "estado":             "Estado",
                "observaciones":      "Observaciones",
            })

            def _color_estado(val):
                return "color:#0F6E56;font-weight:600" if val == "OK" \
                       else "color:#cc0000;font-weight:600"

            def _color_tabla(val):
                if "fact_real" in str(val):
                    return "color:#2d0050"
                if "presupuesto" in str(val):
                    return "color:#c4007a"
                return ""

            st.dataframe(
                df_log.style
                    .map(_color_estado, subset=["Estado"])
                    .map(_color_tabla, subset=["Tabla"]),
                use_container_width=True,
                hide_index=True,
                height=520,
            )
            st.caption(f"{len(df_log)} registros mas recientes")
        else:
            st.info("No hay registros en el historial de cargas.")

    except Exception as e:
        st.warning(f"No se pudo cargar el historial: {e}")
