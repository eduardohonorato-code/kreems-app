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
from utils.db import query, query_live
from utils.etl import run_etl_acuna, run_etl_gn, run_etl_cv_sync, guardar_cv_staging, eliminar_cv_staging

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
    avisos = [l.strip() for l in resultado["logs"] if "⚠" in l]
    if resultado["ok"] and avisos:
        st.warning("\n\n".join(avisos))
    with st.expander("Ver log de ejecución", expanded=not resultado["ok"]):
        st.code("\n".join(resultado["logs"]), language=None)


# ── TABS ──────────────────────────────────────────────────────
tab_acuna, tab_gn, tab_cv, tab_log = st.tabs([
    "🏭  ACUÑA",
    "🌿  Gran Natural",
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
            • Estado de Resultados por centro de costo de Obuma
              ACUÑA (.xlsx), un mes completo<br>
            • Columnas CC por nombre, con o sin código
              (ej. "14885 Administracion"): Ninguno, Administracion,
              Gerencia, Costo Fabrica, Distribucion,
              Maquina Comodato, Ventas → se homologan a los
              5 CC de Gran Natural (Costo Vendi y Otros Productos
              se excluyen)<br>
            • Se valida el cuadre contra las columnas y filas Total<br>
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
            • Estado de Resultados por centro de costo de Obuma
              GN (.xlsx), un mes completo<br>
            • Columnas CC por nombre, con o sin código
              (ej. "1 Administracion"): Ninguno, Administracion,
              Comercial, Distribucion, Produccion<br>
            • Se valida el cuadre contra las columnas y filas Total<br>
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
# TAB: COSTO VARIABLE REAL
# ────────────────────────────────────────────────────────────────
with tab_cv:
    st.markdown("#### Costo Variable Real — Ingreso Manual")
    st.caption(
        "Ingresa el costo variable real por sociedad y periodo. Al guardar queda "
        "en staging y en el EERR al mismo tiempo (cuenta 3.1.01.001, CC-00)."
    )
    st.markdown("")

    # Sin caché: la tabla debe reflejar lo recién guardado
    try:
        df_cv = query_live("""
            WITH stg AS (
                SELECT TO_CHAR(periodo, 'YYYY-MM') AS periodo, sociedad, SUM(monto) AS monto
                FROM staging.cv_real_manual
                GROUP BY 1, 2
            ), fr AS (
                SELECT periodo, sociedad,
                       SUM(valor) FILTER (WHERE codigo_cuenta = '3.1.01.001') AS en_eerr,
                       COUNT(*) FILTER (WHERE fuente = 'OBUMA') > 0 AS hay_obuma,
                       COALESCE(SUM(valor) FILTER (WHERE codigo_cuenta LIKE '4.1.%'), 0) > 0
                           AS hay_ventas
                FROM marts.fact_real
                WHERE periodo LIKE :anio
                GROUP BY 1, 2
            )
            SELECT COALESCE(stg.periodo, fr.periodo)   AS periodo,
                   COALESCE(stg.sociedad, fr.sociedad) AS sociedad,
                   COALESCE(stg.monto, 0)              AS monto,
                   COALESCE(fr.en_eerr, 0)             AS en_eerr,
                   COALESCE(fr.hay_obuma, FALSE)       AS hay_obuma,
                   COALESCE(fr.hay_ventas, FALSE)      AS hay_ventas
            FROM stg FULL JOIN fr ON fr.periodo = stg.periodo AND fr.sociedad = stg.sociedad
            WHERE COALESCE(stg.periodo, fr.periodo) LIKE :anio
            ORDER BY 1, 2
        """, {"anio": f"{_ANO}-%"})
        df_cv["monto"] = df_cv["monto"].astype(float)
        df_cv["en_eerr"] = df_cv["en_eerr"].astype(float)
    except Exception as e:
        st.warning(f"No se pudo leer el costo variable: {e}")
        df_cv = pd.DataFrame(columns=["periodo", "sociedad", "monto", "en_eerr", "hay_obuma", "hay_ventas"])

    # Meses con ventas cargadas desde Obuma y sin costo variable
    pendientes = df_cv[df_cv["hay_ventas"].astype(bool) & (df_cv["monto"] <= 0)]

    col_tabla, col_form = st.columns([1.4, 1])

    with col_tabla:
        st.markdown("##### Costo variable ingresado")
        if not pendientes.empty:
            st.warning("Meses con ventas y **sin costo variable**: " + ", ".join(
                f"{r.sociedad} {r.periodo}" for r in pendientes.itertuples()))
        df_show = df_cv[(df_cv["monto"] > 0) | (df_cv["en_eerr"] != 0)].copy()
        if not df_show.empty:
            df_show["estado"] = ((df_show["monto"] - df_show["en_eerr"]).abs() < 1).map(
                {True: "✓ en EERR", False: "⚠ distinto al EERR"})
            df_show = df_show[["periodo", "sociedad", "monto", "en_eerr", "estado"]].rename(columns={
                "periodo": "Periodo", "sociedad": "Sociedad", "monto": "Monto CV Real",
                "en_eerr": "En EERR", "estado": "Estado",
            })
            st.dataframe(
                df_show.style.format({"Monto CV Real": "${:,.0f}", "En EERR": "${:,.0f}"}),
                use_container_width=True,
                hide_index=True,
                height=320,
            )
        else:
            st.info("No hay datos ingresados aún.")

    with col_form:
        # Mensaje del último guardado (sobrevive al st.rerun)
        msg = st.session_state.pop("cv_msg", None)
        if msg:
            st.success(msg)

        st.markdown("##### Agregar / actualizar registro")

        MESES_OPTS = {
            f"Enero ({_ANO}-01)":       f"{_ANO}-01", f"Febrero ({_ANO}-02)":     f"{_ANO}-02",
            f"Marzo ({_ANO}-03)":       f"{_ANO}-03", f"Abril ({_ANO}-04)":       f"{_ANO}-04",
            f"Mayo ({_ANO}-05)":        f"{_ANO}-05", f"Junio ({_ANO}-06)":       f"{_ANO}-06",
            f"Julio ({_ANO}-07)":       f"{_ANO}-07", f"Agosto ({_ANO}-08)":      f"{_ANO}-08",
            f"Septiembre ({_ANO}-09)":  f"{_ANO}-09", f"Octubre ({_ANO}-10)":     f"{_ANO}-10",
            f"Noviembre ({_ANO}-11)":   f"{_ANO}-11", f"Diciembre ({_ANO}-12)":   f"{_ANO}-12",
        }

        # Por defecto, el primer mes pendiente; si no hay, el último con EERR cargado
        _periodos = list(MESES_OPTS.values())
        _con_obuma = df_cv[df_cv["hay_obuma"].astype(bool)]
        if not pendientes.empty:
            _fila = pendientes.iloc[0]
        elif not _con_obuma.empty:
            _fila = _con_obuma.iloc[-1]
        else:
            _fila = None
        _idx_mes = _periodos.index(_fila["periodo"]) if _fila is not None else date.today().month - 1
        _idx_soc = 0 if _fila is not None and _fila["sociedad"] == "ACUÑA" else 1

        with st.form("form_cv", clear_on_submit=True):
            mes_lbl   = st.selectbox("Periodo", list(MESES_OPTS.keys()), index=_idx_mes)
            sociedad  = st.radio("Sociedad", ["ACUÑA", "GRAN_NATURAL"], index=_idx_soc,
                                 horizontal=True)
            monto     = st.number_input("Monto CV Real ($)", min_value=0.0,
                                        step=100_000.0, format="%.0f")
            submitted = st.form_submit_button("Guardar y actualizar EERR", type="primary",
                                              use_container_width=True)

        if submitted:
            periodo_sel = MESES_OPTS[mes_lbl]
            if monto <= 0:
                st.error("El monto debe ser mayor a 0.")
            else:
                with st.spinner("Guardando..."):
                    res = guardar_cv_staging(periodo_sel, sociedad, monto,
                                             st.session_state.get("usuario"))
                if res["ok"]:
                    st.session_state["cv_msg"] = (
                        f"✓ Guardado: {sociedad} {periodo_sel} → ${monto:,.0f} (ya está en el EERR)")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Error: {res['error']}")

        st.markdown("---")
        st.markdown("##### Eliminar registro")
        with st.form("form_cv_del", clear_on_submit=True):
            mes_del = st.selectbox("Periodo a eliminar", list(MESES_OPTS.keys()), key="cv_del_mes")
            soc_del = st.radio("Sociedad", ["ACUÑA", "GRAN_NATURAL"],
                               horizontal=True, key="cv_del_soc")
            del_btn = st.form_submit_button("Eliminar", type="secondary",
                                            use_container_width=True)
        if del_btn:
            with st.spinner("Eliminando..."):
                res_del = eliminar_cv_staging(MESES_OPTS[mes_del], soc_del)
            if res_del["ok"]:
                st.session_state["cv_msg"] = (
                    f"Eliminado: {soc_del} {MESES_OPTS[mes_del]} (staging y EERR)")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Error: {res_del['error']}")

    st.markdown("---")
    with st.expander("Resincronizar todo el staging (mantención)"):
        st.caption(
            "Normalmente no hace falta: guardar y eliminar ya actualizan el EERR. "
            "Úsalo solo si se editó staging.cv_real_manual directamente en la BD."
        )
        if st.button("Sincronizar CV Real", key="btn_cv_sync"):
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
