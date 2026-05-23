"""
Presupuesto Mensualizado — Vista y edición del presupuesto por mes
"""
import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import text
from utils.auth import login
from utils.db import query, get_engine
from utils.components import header, sidebar_kreems, boton_excel, ANO_FISCAL

st.set_page_config(page_title="Presupuesto Mensual · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=False)
header("Presupuesto Mensualizado")

_ANO = ANO_FISCAL
es_admin = st.session_state.get("rol") == "admin"

NOMBRES_CC = {
    "CC-01": "Administración",
    "CC-02": "Comercial",
    "CC-03": "Distribución",
    "CC-04": "Producción",
}
MESES_COLS = {
    f"{_ANO}-{m:02d}": nom for m, nom in [
        (1,"Ene"),(2,"Feb"),(3,"Mar"),(4,"Abr"),(5,"May"),(6,"Jun"),
        (7,"Jul"),(8,"Ago"),(9,"Sep"),(10,"Oct"),(11,"Nov"),(12,"Dic"),
    ]
}
CLASIFICACIONES = {
    "COSTO_VAR":  "Costo Variable",
    "COSTO_FIJO": "Costo Fijo",
    "OPEX":       "OPEX",
    "FINANCIERO": "Financiero",
}

st.markdown(f"""
<div style="background:#f5f0fb; border:1px solid #e0d0f0; border-radius:10px;
            padding:10px 18px; margin-bottom:20px; font-size:13px; color:#2d0050;">
    {'✏️ <b>Modo edición</b> — Modifica los valores directamente en la tabla y presiona <b>Guardar cambios</b>.' if es_admin
     else '👁 <b>Vista de solo lectura.</b> Solo los administradores pueden editar el presupuesto.'}
</div>
""", unsafe_allow_html=True)

# ── QUERY: presupuesto mensual por cuenta y CC ────────────────
@st.cache_data(ttl=120)
def cargar_presupuesto(ano: int):
    return query("""
        SELECT
            fp.codigo_cc,
            dc.clasificacion,
            dc.nombre_cuenta,
            fp.periodo,
            SUM(fp.valor) AS valor
        FROM marts.fact_presupuesto fp
        JOIN master.dim_cuentas dc ON dc.codigo_cuenta = fp.codigo_cuenta
        WHERE fp.periodo LIKE :anio
          AND fp.codigo_cc <> 'CC-00'
        GROUP BY fp.codigo_cc, dc.clasificacion, dc.nombre_cuenta, fp.periodo
        ORDER BY fp.codigo_cc, dc.clasificacion, dc.nombre_cuenta, fp.periodo
    """, {"anio": f"{ano}-%"})

df_ppto = cargar_presupuesto(_ANO)

if df_ppto.empty:
    st.info("No hay datos de presupuesto cargados para este año.")
    st.stop()

# ── PIVOT por mes ─────────────────────────────────────────────
def build_pivot(df_cc: pd.DataFrame) -> pd.DataFrame:
    """Pivota el DF mensual a columnas de mes."""
    pv = df_cc.pivot_table(
        index=["clasificacion", "nombre_cuenta"],
        columns="periodo",
        values="valor",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    # Asegurar que estén todas las columnas de mes
    for col in MESES_COLS:
        if col not in pv.columns:
            pv[col] = 0.0
    # Renombrar meses a nombres cortos
    pv = pv.rename(columns=MESES_COLS)
    # Renombrar ejes
    pv = pv.rename(columns={"clasificacion": "Clasificación", "nombre_cuenta": "Cuenta"})
    pv["Clasificación"] = pv["Clasificación"].map(CLASIFICACIONES).fillna(pv["Clasificación"])
    # Total anual
    meses_nom = list(MESES_COLS.values())
    pv["Total Anual"] = pv[meses_nom].sum(axis=1)
    # Ordenar columnas
    return pv[["Clasificación", "Cuenta"] + meses_nom + ["Total Anual"]]

# ── TABS por CC ───────────────────────────────────────────────
tabs_labels = [f"🏢 {nombre}" for nombre in NOMBRES_CC.values()]
tabs_labels.append("📋 Consolidado")
tabs = st.tabs(tabs_labels)

def _fmt_mill_num(v):
    return f"${v/1_000_000:,.2f}M" if isinstance(v, (int, float)) else v

# Función para guardar cambios editados
def guardar_cambios(df_original: pd.DataFrame, df_editado: pd.DataFrame, codigo_cc: str):
    """Detecta diferencias y actualiza la BD."""
    meses_nom = list(MESES_COLS.values())
    meses_per = list(MESES_COLS.keys())
    nom_to_per = dict(zip(meses_nom, meses_per))

    cambios = 0
    errores = []
    with get_engine().begin() as conn:
        for i in range(len(df_editado)):
            cuenta = df_editado.iloc[i]["Cuenta"]
            for mes_nom, mes_per in nom_to_per.items():
                val_orig = float(df_original.iloc[i][mes_nom]) if i < len(df_original) else 0.0
                val_edit = float(df_editado.iloc[i][mes_nom])
                if abs(val_orig - val_edit) > 0.01:
                    try:
                        conn.execute(text("""
                            UPDATE marts.fact_presupuesto fp
                            SET valor = :nuevo
                            FROM master.dim_cuentas dc
                            WHERE fp.codigo_cuenta = dc.codigo_cuenta
                              AND dc.nombre_cuenta  = :cuenta
                              AND fp.codigo_cc      = :cc
                              AND fp.periodo        = :periodo
                        """), {
                            "nuevo":   val_edit,
                            "cuenta":  cuenta,
                            "cc":      codigo_cc,
                            "periodo": mes_per,
                        })
                        cambios += 1
                    except Exception as e:
                        errores.append(str(e))
    return cambios, errores

# ── Renderizar cada tab ───────────────────────────────────────
for tab_idx, (codigo_cc, nombre_cc) in enumerate(NOMBRES_CC.items()):
    with tabs[tab_idx]:
        df_cc = df_ppto[df_ppto["codigo_cc"] == codigo_cc].copy()
        if df_cc.empty:
            st.info(f"Sin datos de presupuesto para {nombre_cc}.")
            continue

        df_pivot = build_pivot(df_cc)

        # KPI total anual del CC
        total_cc = df_pivot["Total Anual"].sum()
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        with col_kpi1:
            st.metric("Total Anual Presupuestado", f"${total_cc/1_000_000:,.2f}M")
        with col_kpi2:
            st.metric("Cuentas", len(df_pivot))
        with col_kpi3:
            prom_mes = total_cc / 12
            st.metric("Promedio Mensual", f"${prom_mes/1_000_000:,.2f}M")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        meses_nom = list(MESES_COLS.values())

        if es_admin:
            # Modo edición con st.data_editor
            col_conf = {
                "Clasificación": st.column_config.TextColumn("Clasificación", disabled=True, width="small"),
                "Cuenta":        st.column_config.TextColumn("Cuenta",        disabled=True, width="medium"),
                "Total Anual":   st.column_config.NumberColumn("Total Anual", disabled=True,
                                    format="$%.0f", width="small"),
            }
            for mes in meses_nom:
                col_conf[mes] = st.column_config.NumberColumn(
                    mes, format="$%.0f", min_value=0, width="small"
                )

            df_edit = st.data_editor(
                df_pivot,
                column_config=col_conf,
                use_container_width=True,
                hide_index=True,
                key=f"editor_{codigo_cc}",
                height=min(40 + 35 * len(df_pivot), 520),
            )

            col_guardar, col_export, _ = st.columns([1.5, 1.5, 3])
            with col_guardar:
                if st.button(f"💾 Guardar cambios — {nombre_cc}", type="primary",
                             use_container_width=True, key=f"save_{codigo_cc}"):
                    with st.spinner("Guardando..."):
                        n_cambios, errores = guardar_cambios(df_pivot, df_edit, codigo_cc)
                    if errores:
                        st.error(f"Errores al guardar: {errores[:3]}")
                    elif n_cambios == 0:
                        st.info("Sin cambios para guardar.")
                    else:
                        st.success(f"✓ {n_cambios} valores actualizados.")
                        cargar_presupuesto.clear()
                        st.rerun()
            with col_export:
                boton_excel(
                    {nombre_cc: df_pivot},
                    f"Presupuesto_{nombre_cc}_{_ANO}",
                    label="⬇ Exportar Excel",
                )
        else:
            # Vista solo lectura — tabla formateada
            def _fmt(v):
                return f"${v/1_000_000:,.2f}M" if isinstance(v, (int, float)) else v

            fmt_cols = {c: _fmt for c in meses_nom + ["Total Anual"]}
            st.dataframe(
                df_pivot.style.format(fmt_cols),
                use_container_width=True,
                hide_index=True,
                height=min(40 + 35 * len(df_pivot), 520),
            )
            boton_excel(
                {nombre_cc: df_pivot},
                f"Presupuesto_{nombre_cc}_{_ANO}",
            )

# ── Tab Consolidado ───────────────────────────────────────────
with tabs[4]:
    st.markdown("##### Resumen Anual por CC y Clasificación")

    df_consol = df_ppto.copy()
    df_consol["clasificacion"] = df_consol["clasificacion"].map(CLASIFICACIONES).fillna(df_consol["clasificacion"])
    df_consol["nombre_cc"]     = df_consol["codigo_cc"].map(NOMBRES_CC).fillna(df_consol["codigo_cc"])

    resumen = df_consol.groupby(["nombre_cc", "clasificacion"])["valor"].sum().reset_index()
    resumen_pv = resumen.pivot_table(
        index="clasificacion", columns="nombre_cc", values="valor", aggfunc="sum", fill_value=0
    ).reset_index()
    resumen_pv.columns.name = None
    resumen_pv["Total"] = resumen_pv[[c for c in resumen_pv.columns if c != "clasificacion"]].sum(axis=1)
    resumen_pv = resumen_pv.rename(columns={"clasificacion": "Clasificación"})

    total_row = {"Clasificación": "TOTAL"}
    for c in resumen_pv.columns:
        if c != "Clasificación":
            total_row[c] = resumen_pv[c].sum()
    resumen_pv = pd.concat([resumen_pv, pd.DataFrame([total_row])], ignore_index=True)

    num_cols = [c for c in resumen_pv.columns if c != "Clasificación"]

    def _tot_row(row):
        if row["Clasificación"] == "TOTAL":
            return ["font-weight:bold; background:#f0e8f8; color:#2d0050"] * len(row)
        return [""] * len(row)

    st.dataframe(
        resumen_pv.style
            .format({c: lambda v: f"${v/1_000_000:,.2f}M" for c in num_cols})
            .apply(_tot_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    boton_excel(
        {"Consolidado": resumen_pv},
        f"Presupuesto_Consolidado_{_ANO}",
    )
