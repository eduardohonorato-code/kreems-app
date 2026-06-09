"""
Presupuesto Ventas & Costo Variable — edición por categoría (consolidado).
Fuente: staging.ppto_ventas_cv → marts.fact_presupuesto (4.1.01.001 / 3.1.01.001, CC-00).
Solo admin.
"""
import streamlit as st
import pandas as pd
from utils.auth import login, requiere_admin
from utils.db import query, query_live
from utils.components import header, sidebar_kreems, boton_excel, fmt_mill, ANO_FISCAL
from utils.etl_vcv import (
    run_etl_ppto_ventas_cv, reemplazar_ppto_ventas_cv, sincronizar_ppto_ventas_cv,
)

st.set_page_config(page_title="Ppto Ventas & CV · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_admin()

sidebar_kreems(mostrar_sociedad=False)
header("Presupuesto Ventas & Costo Variable")

_ANO = ANO_FISCAL
_MESES = ["ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic"]
_MESES_LBL = {m: m.capitalize() for m in _MESES}

st.markdown(f"""
<div style="background:#f5f0fb; border:1px solid #e0d0f0; border-radius:10px;
            padding:10px 18px; margin-bottom:18px; font-size:13px; color:#2d0050;">
    📈 Edita las <b>ventas</b> y el <b>costo variable</b> presupuestados por categoría.
    Al guardar se reagregan a las cuentas 4.1.01.001 (ventas) y 3.1.01.001 (CV) en CC-00.
</div>
""", unsafe_allow_html=True)


# ── Cargar todo para KPIs ─────────────────────────────────────
def _cargar(tipo: str | None = None) -> pd.DataFrame:
    filtro = "AND tipo = :t" if tipo else ""
    params = {"a": _ANO}
    if tipo:
        params["t"] = tipo
    return query_live(f"""
        SELECT id, tipo, categoria, notas,
               ene, feb, mar, abr, may, jun, jul, ago, sep, oct, nov, dic
        FROM staging.ppto_ventas_cv
        WHERE ano = :a {filtro}
        ORDER BY tipo, categoria
    """, params)


df_all = _cargar()
if not df_all.empty:
    df_all[_MESES] = df_all[_MESES].apply(pd.to_numeric, errors="coerce").fillna(0)
tot_ventas = float(df_all.loc[df_all["tipo"] == "VENTA", _MESES].sum().sum()) if not df_all.empty else 0.0
tot_cv     = float(df_all.loc[df_all["tipo"] == "COSTO_VARIABLE", _MESES].sum().sum()) if not df_all.empty else 0.0
util_bruta = tot_ventas - tot_cv
margen_cv  = (tot_cv / tot_ventas * 100) if tot_ventas else 0
margen_ub  = (util_bruta / tot_ventas * 100) if tot_ventas else 0

k1, k2, k3, k4 = st.columns(4)
for col, (lbl, val, sub) in zip(
    [k1, k2, k3, k4],
    [("Ventas presupuestadas", tot_ventas, f"{_ANO} anual"),
     ("Costo Variable", tot_cv, f"{margen_cv:.1f}% de ventas"),
     ("Utilidad Bruta", util_bruta, f"Margen {margen_ub:.1f}%"),
     ("Margen Bruto", None, None)],
):
    with col:
        if lbl == "Margen Bruto":
            st.markdown(f"""
            <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                        padding:16px 18px; text-align:center;">
                <div style="font-size:11px; color:#999;">Margen Bruto</div>
                <div style="font-size:24px; font-weight:700; color:#0F6E56;">{margen_ub:.1f}%</div>
                <div style="font-size:11px; color:#aaa;">Ventas − CV</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                        padding:16px 18px; text-align:center;">
                <div style="font-size:11px; color:#999;">{lbl}</div>
                <div style="font-size:22px; font-weight:700; color:#2d0050;">${val/1_000_000:,.1f}M</div>
                <div style="font-size:11px; color:#aaa;">{sub}</div>
            </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

tab_v, tab_cv, tab_carga = st.tabs([
    "🟢  Ventas (categorías)",
    "🔻  Costo Variable (categorías)",
    "⬆️  Cargar Excel",
])


# ── Editor reutilizable ───────────────────────────────────────
def render_editor(tipo: str, color_total: str, key: str):
    df = _cargar(tipo)
    if df.empty:
        df = pd.DataFrame(columns=["id", "tipo", "categoria", "notas", *_MESES])
    df_ed = df.drop(columns=["id", "tipo"], errors="ignore").copy()
    for m in _MESES:
        if m not in df_ed:
            df_ed[m] = 0.0
        df_ed[m] = pd.to_numeric(df_ed[m], errors="coerce").fillna(0.0)
    df_ed = df_ed.reindex(columns=["categoria", "notas", *_MESES])

    total_actual = float(df_ed[_MESES].sum().sum()) if not df_ed.empty else 0.0
    st.metric(f"Total {tipo.replace('_', ' ').title()} {_ANO}", f"${total_actual/1_000_000:,.2f}M")
    st.caption("Agrega categorías con ➕, edita los montos y presiona **Guardar cambios**.")

    col_conf = {
        "categoria": st.column_config.TextColumn("Categoría / Producto", width="medium", required=True),
        "notas":     st.column_config.TextColumn("Notas", width="medium"),
    }
    for m in _MESES:
        col_conf[m] = st.column_config.NumberColumn(_MESES_LBL[m], format="$%d", min_value=0, width="small")

    df_edit = st.data_editor(
        df_ed, column_config=col_conf, use_container_width=True,
        hide_index=True, num_rows="dynamic", key=f"editor_{key}", height=320,
    )

    col_g, col_e, _ = st.columns([1.4, 1.4, 3])
    with col_g:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True, key=f"save_{key}"):
            with st.spinner("Guardando y reagregando..."):
                res = reemplazar_ppto_ventas_cv(_ANO, tipo, df_edit)
            if res["ok"]:
                query.clear()
                st.success(f"✓ Guardado. {res['n_registros']} categorías · reagregado a las cuentas.")
                st.rerun()
            else:
                st.error(f"Error: {res['error']}")
                st.code("\n".join(res["logs"]), language=None)
    with col_e:
        if not df.empty:
            boton_excel({tipo: df.drop(columns=["id"], errors="ignore")}, f"Ppto_{tipo}_{_ANO}")


with tab_v:
    st.markdown("##### Ventas presupuestadas por categoría")
    render_editor("VENTA", "#0F6E56", "ventas")

with tab_cv:
    st.markdown("##### Costo Variable presupuestado por categoría")
    render_editor("COSTO_VARIABLE", "#c4007a", "cv")


# ── TAB: CARGAR EXCEL ─────────────────────────────────────────
with tab_carga:
    st.markdown("#### Cargar Ventas & Costo Variable (Excel plano)")
    st.caption(
        "Sube el archivo con la hoja **PPTO_VENTAS_CV** (columnas: Tipo, Categoría, Notas, Ene–Dic). "
        "Tipo debe ser VENTA o COSTO_VARIABLE. Reemplaza todo el año y reagrega."
    )
    archivo = st.file_uploader("Archivo Excel ventas/CV", type=["xlsx"],
                               key="up_vcv", label_visibility="collapsed")
    if archivo:
        file_bytes = archivo.read()
        st.markdown(f"📄 **{archivo.name}** · {len(file_bytes)/1024:.1f} KB")
        confirmar = st.checkbox(f"Confirmo reemplazar ventas y CV {_ANO}", key="conf_vcv")
        if confirmar and st.button("Ejecutar carga", type="primary", key="btn_vcv_carga"):
            with st.spinner("Cargando y reagregando..."):
                res = run_etl_ppto_ventas_cv(file_bytes, _ANO)
            if res["ok"]:
                query.clear()
                st.success(f"✓ Carga exitosa — {res['n_registros']} categorías · {res['periodo']}")
            else:
                st.error(f"✗ Error: {res['error']}")
            with st.expander("Ver log de ejecución", expanded=not res["ok"]):
                st.code("\n".join(res["logs"]), language=None)

    st.markdown("---")
    if st.button("🔄 Reagregar a fact_presupuesto", key="btn_resync_vcv"):
        with st.spinner("Reagregando..."):
            res = sincronizar_ppto_ventas_cv(_ANO)
        if res["ok"]:
            query.clear()
            st.success(f"✓ Reagregado · {res['n_registros']} filas en fact_presupuesto.")
        else:
            st.error(f"Error: {res['error']}")
        with st.expander("Ver log"):
            st.code("\n".join(res["logs"]), language=None)
