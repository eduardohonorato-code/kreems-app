"""
Presupuesto Detalle — Edición a nivel de item/persona, cuenta y centro de costo.
Fuente: staging.ppto_detalle (reagrega a marts.fact_presupuesto, solo CC <> CC-00).
Solo admin.
"""
import streamlit as st
import pandas as pd
from datetime import date
from utils.auth import login, requiere_admin
from utils.db import query, query_live
from utils.components import header, sidebar_kreems, boton_excel, ANO_FISCAL, NOMBRES_CC
from utils.etl import run_etl_ppto_detalle, reemplazar_ppto_detalle, sincronizar_ppto_detalle

st.set_page_config(page_title="Presupuesto Detalle · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_admin()

sidebar_kreems(mostrar_sociedad=False)
header("Presupuesto Detalle — por Item, Cuenta y CC")

_ANO = ANO_FISCAL
_MESES = ["ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic"]
_MESES_LBL = {m: m.capitalize() for m in _MESES}
_SOCIEDADES = ["Consolidado", "ACUÑA", "GRAN_NATURAL"]
_TIPOS = ["Fijo", "Esporádico", "Variable"]
_CC_OPTS = list(NOMBRES_CC.keys())  # CC-01..CC-04

st.markdown(f"""
<div style="background:#f5f0fb; border:1px solid #e0d0f0; border-radius:10px;
            padding:10px 18px; margin-bottom:18px; font-size:13px; color:#2d0050;">
    ✏️ Edita el presupuesto <b>por persona / item</b>. Al guardar se reagrega
    automáticamente a las cuentas y centros de costo del resto de la app
    (Ventas y Costo Variable de CC-00 no se ven afectados).
</div>
""", unsafe_allow_html=True)

tab_edit, tab_carga = st.tabs(["✏️  Editar detalle", "⬆️  Cargar Excel plano"])

# ════════════════════════════════════════════════════════════
# TAB: EDITAR
# ════════════════════════════════════════════════════════════
with tab_edit:
    col_soc, col_info = st.columns([1.2, 3])
    with col_soc:
        sociedad_sel = st.selectbox("Sociedad", _SOCIEDADES, key="det_soc")

    # Cargar items de la sociedad/año
    df = query_live("""
        SELECT d.id, d.codigo_cc, d.codigo_cuenta, dc.nombre_cuenta,
               d.item, d.tipo, d.notas,
               d.ene, d.feb, d.mar, d.abr, d.may, d.jun,
               d.jul, d.ago, d.sep, d.oct, d.nov, d.dic
        FROM staging.ppto_detalle d
        LEFT JOIN master.dim_cuentas dc ON dc.codigo_cuenta = d.codigo_cuenta
        WHERE d.ano = :a AND d.sociedad = :s
        ORDER BY d.codigo_cc, d.codigo_cuenta, d.item
    """, {"a": _ANO, "s": sociedad_sel})

    if df.empty:
        st.info(
            f"No hay items para **{sociedad_sel}** en {_ANO}. "
            "Agrégalos abajo (botón ➕ en la tabla) o carga el Excel plano en la otra pestaña."
        )
        # Estructura vacía editable
        df = pd.DataFrame(columns=[
            "id", "codigo_cc", "codigo_cuenta", "nombre_cuenta",
            "item", "tipo", "notas", *_MESES
        ])

    # Total anual por fila (informativo)
    df_calc = df.copy()
    for m in _MESES:
        df_calc[m] = pd.to_numeric(df_calc[m], errors="coerce").fillna(0) if m in df_calc else 0
    total_actual = float(df_calc[_MESES].sum().sum()) if not df_calc.empty else 0.0

    c1, c2 = st.columns(2)
    with c1:
        st.metric(f"Total presupuestado {sociedad_sel} {_ANO}", f"${total_actual/1_000_000:,.2f}M")
    with c2:
        st.metric("Items", len(df))

    st.caption("Agrega filas con ➕, edita los montos y presiona **Guardar cambios**. "
               "El «Nombre Cuenta» se completa solo al guardar según el código.")

    # Preparar df para el editor (sin id; nombre_cuenta solo lectura)
    df_ed = df.drop(columns=["id"], errors="ignore").copy()
    for m in _MESES:
        if m not in df_ed:
            df_ed[m] = 0.0
        df_ed[m] = pd.to_numeric(df_ed[m], errors="coerce").fillna(0.0)
    orden = ["codigo_cc", "codigo_cuenta", "nombre_cuenta", "item", "tipo", "notas", *_MESES]
    df_ed = df_ed.reindex(columns=orden)

    col_conf = {
        "codigo_cc": st.column_config.SelectboxColumn("CC", options=_CC_OPTS, width="small", required=True),
        "codigo_cuenta": st.column_config.TextColumn("Código Cuenta", width="small", required=True),
        "nombre_cuenta": st.column_config.TextColumn("Nombre Cuenta (auto)", disabled=True, width="medium"),
        "item": st.column_config.TextColumn("Item / Nombre", width="medium"),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=_TIPOS, width="small"),
        "notas": st.column_config.TextColumn("Notas", width="medium"),
    }
    for m in _MESES:
        col_conf[m] = st.column_config.NumberColumn(_MESES_LBL[m], format="$%d", min_value=0, width="small")

    df_edit = st.data_editor(
        df_ed,
        column_config=col_conf,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key=f"editor_det_{sociedad_sel}",
        height=460,
    )

    col_g, col_e, _ = st.columns([1.4, 1.4, 3])
    with col_g:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True, key="det_guardar"):
            df_rows = df_edit.drop(columns=["nombre_cuenta"], errors="ignore").copy()
            df_rows = df_rows[df_rows["codigo_cuenta"].notna() & (df_rows["codigo_cuenta"].astype(str).str.strip() != "")]
            with st.spinner("Guardando y reagregando..."):
                res = reemplazar_ppto_detalle(_ANO, sociedad_sel, df_rows)
            if res["ok"]:
                query.clear()
                st.success(f"✓ Guardado. {res['n_registros']} items · presupuesto reagregado a las cuentas.")
                with st.expander("Ver detalle de la reagregación"):
                    st.code("\n".join(res["logs"]), language=None)
                st.rerun()
            else:
                st.error(f"Error: {res['error']}")
                st.code("\n".join(res["logs"]), language=None)
    with col_e:
        if not df.empty:
            boton_excel({"PptoDetalle": df.drop(columns=["id"], errors="ignore")},
                        f"PptoDetalle_{sociedad_sel}_{_ANO}")

# ════════════════════════════════════════════════════════════
# TAB: CARGAR EXCEL PLANO
# ════════════════════════════════════════════════════════════
with tab_carga:
    st.markdown("#### Cargar Presupuesto Detalle (Excel plano)")
    st.caption(
        "Sube el archivo con la hoja **PPTO_DETALLE** (columnas: Sociedad, Código CC, "
        "Centro de Costo, Código Cuenta, Nombre Cuenta, Item / Nombre, Tipo, Notas, Ene–Dic). "
        "Reemplaza todos los items del año y reagrega a las cuentas."
    )

    col_up, col_info2 = st.columns([1.6, 1])
    with col_up:
        archivo = st.file_uploader("Archivo Excel detalle", type=["xlsx"],
                                   key="up_det", label_visibility="collapsed")
    with col_info2:
        st.markdown("""
        <div style="background:#fff8e8; border:1px solid #f0d878; border-radius:10px;
                    padding:14px 16px; font-size:12px; line-height:1.7;">
            <b style="color:#7a5200;">Ojo</b><br>
            • Reemplaza <b>todo el detalle del año</b>.<br>
            • Reagrega solo CC-01 a CC-04 (Ventas y Costo Variable de CC-00 no se tocan).<br>
            • Las cuentas deben existir en <code>dim_cuentas</code>.
        </div>
        """, unsafe_allow_html=True)

    if archivo:
        file_bytes = archivo.read()
        st.markdown(f"📄 **{archivo.name}** · {len(file_bytes)/1024:.1f} KB")
        confirmar = st.checkbox(f"Confirmo reemplazar el presupuesto detalle {_ANO}", key="conf_det")
        if confirmar and st.button("Ejecutar carga", type="primary", key="btn_det_carga"):
            with st.spinner("Cargando y reagregando..."):
                res = run_etl_ppto_detalle(file_bytes, _ANO)
            if res["ok"]:
                query.clear()
                st.success(f"✓ Carga exitosa — {res['n_registros']} items · {res['periodo']}")
            else:
                st.error(f"✗ Error: {res['error']}")
            with st.expander("Ver log de ejecución", expanded=not res["ok"]):
                st.code("\n".join(res["logs"]), language=None)

    st.markdown("---")
    st.caption("¿Editaste el detalle directo en la BD? Vuelve a reagregar a las cuentas:")
    if st.button("🔄 Reagregar a fact_presupuesto", key="btn_resync_det"):
        with st.spinner("Reagregando..."):
            res = sincronizar_ppto_detalle(_ANO)
        if res["ok"]:
            query.clear()
            st.success(f"✓ Reagregado · {res['n_registros']} filas en fact_presupuesto.")
        else:
            st.error(f"Error: {res['error']}")
        with st.expander("Ver log"):
            st.code("\n".join(res["logs"]), language=None)
