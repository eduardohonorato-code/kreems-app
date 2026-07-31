"""
Reporte de Gerencia — un solo entregable con el Real vs Presupuesto por centro
de costo, el análisis de brechas y su origen.

Consolida en dos archivos descargables (Excel corporativo + HTML de insights) lo
que hoy está repartido entre EERR, EERR Acumulado, Centro de Costos y Control por
Cuenta. Pensada para responder "necesito el resultado contra presupuesto ahora":
se abre, se elige el mes de corte y se descarga.
"""
import streamlit as st
import pandas as pd
from datetime import date

from utils.auth import login, get_cc_sql_filter, requiere_acceso_total
from utils.db import query
from utils.components import (
    header, sidebar_kreems, fmt_mill, get_soc_sql_filter,
    ETIQUETA_SOCIEDAD, MESES,
)
from utils import reporte_gerencia as rg

_ANO = date.today().year

st.set_page_config(page_title="Reporte de Gerencia · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_acceso_total()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header(f"Reporte de Gerencia — Real vs Presupuesto {_ANO}")

filtro_soc = get_soc_sql_filter(sociedad_sel)
filtro_cc = get_cc_sql_filter()

st.caption(
    "Entregable único para comité: P&L acumulado contra el presupuesto de los "
    "mismos meses, puente de EBIT, apertura por centro de costo y clasificación "
    "de cada brecha (recurrente / puntual / desfase / no presupuestada)."
)

# ── DATOS ─────────────────────────────────────────────────────
df = rg.cargar_movimientos(_ANO, filtro_soc, filtro_cc)
if df.empty:
    st.info("Sin datos para el año y los filtros seleccionados.")
    st.stop()

df_soc = rg.cargar_por_sociedad(_ANO, filtro_cc)
diag = rg.diagnostico_corte(df, _ANO)

if not diag["meses_con_real"]:
    st.info("No hay meses con datos reales cargados para este año.")
    st.stop()

# ── CONTROLES ─────────────────────────────────────────────────
col_mes, col_umbral, col_info = st.columns([1.4, 1.4, 3.2])

with col_mes:
    opciones = diag["meses_con_real"]
    mes_corte = st.selectbox(
        "Acumulado hasta",
        opciones,
        index=opciones.index(diag["sugerido"]) if diag["sugerido"] in opciones else len(opciones) - 1,
        format_func=lambda m: MESES[m],
        help="El real acumulado se compara contra el presupuesto de estos mismos meses.",
    )

with col_umbral:
    umbral_m = st.number_input(
        "Materialidad (millones)",
        min_value=0.1, max_value=50.0,
        value=rg.UMBRAL_DEFECTO / 1e6, step=0.5,
        help="Bajo este monto una brecha no se comenta ni entra al plan de acción.",
    )

with col_info:
    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
    st.caption(
        f"Meses con real cargado: "
        f"{', '.join(rg.ABREV_MES[m] for m in diag['meses_con_real'])} · "
        f"presupuesto disponible para los 12 meses."
    )

# Advertencia de mes parcial: es el error más caro de este reporte (mostrar
# como "ahorro" lo que en realidad son facturas todavía sin cargar).
if diag["parcial"] and mes_corte >= diag["ultimo_real"]:
    st.warning(
        f"**{MESES[diag['ultimo_real']]} parece cargado a medias**: ejecutó el "
        f"{diag['ratio']*100:.0f}% del presupuesto del mes, contra "
        f"{diag['ratio_previo']*100:.0f}% típico de los meses cerrados. "
        f"Con ese mes incluido el reporte muestra ahorros que probablemente son "
        f"facturas pendientes de cargar. Se sugiere cortar en "
        f"**{MESES[diag['sugerido']]}**."
    )

if sociedad_sel != "Todas":
    s = df_soc.copy()
    s["ppto"] = pd.to_numeric(s["ppto"], errors="coerce").fillna(0.0)
    sin_ppto = s[(s["ppto"] == 0) & (pd.to_numeric(s["real"], errors="coerce").fillna(0) > 0)]
    if sociedad_sel in list(sin_ppto["sociedad"]):
        st.error(
            f"**{ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)} no tiene presupuesto "
            f"propio cargado**: todo el presupuesto {_ANO} está bajo la otra sociedad. "
            f"Comparar esta sociedad aislada contra presupuesto no es válido — usa "
            f"**Consolidado (ambas)** en la barra lateral."
        )
    else:
        st.info(
            f"Estás viendo solo {ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)}. "
            f"Como la operación se factura en una u otra sociedad según el mes, la "
            f"comparación contra presupuesto solo cierra en **Consolidado (ambas)**."
        )

# ── CONSTRUIR REPORTE ─────────────────────────────────────────
rep = rg.construir_reporte(
    df, _ANO, int(mes_corte),
    sociedad_lbl=ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel),
    umbral=float(umbral_m) * 1e6,
    df_soc=df_soc, diag=diag,
)
meta, kpi = rep["meta"], rep["kpi"]

st.markdown("<br>", unsafe_allow_html=True)

# ── DESCARGAS ─────────────────────────────────────────────────
_tag_soc = "Consolidado" if sociedad_sel == "Todas" else sociedad_sel.replace("Ñ", "N")
_nombre = f"Kreems_Reporte_Gerencia_{_tag_soc}_{_ANO}-{int(mes_corte):02d}"

with st.container(border=True):
    st.markdown("##### 📤 Descargar el reporte")
    col_x, col_h, col_txt = st.columns([1.3, 1.3, 3.4])
    with col_x:
        st.download_button(
            "⬇ Excel de gerencia",
            data=rg.to_excel(rep),
            file_name=f"{_nombre}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with col_h:
        st.download_button(
            "⬇ Insights (HTML)",
            data=rg.to_html(rep).encode("utf-8"),
            file_name=f"{_nombre}.html",
            mime="text/html",
            use_container_width=True,
        )
    with col_txt:
        st.caption(
            "**Excel** — 8 hojas: portada con bases y advertencias, resumen ejecutivo, "
            "puente de EBIT, centros de costo, detalle por cuenta, plan de acción, "
            "mes a mes y proyección al cierre.  \n"
            "**HTML** — una página que se abre en cualquier navegador y se imprime "
            "a PDF; pensada para quien no va a abrir el Excel."
        )

st.markdown("<br>", unsafe_allow_html=True)

# ── VISTA PREVIA ──────────────────────────────────────────────
st.markdown(f"##### Resultado acumulado · {meta['periodo_lbl']} · {meta['sociedad']}")

cols_kpi = st.columns(4)
_kpis = [
    ("Ventas", kpi["ventas_r"], kpi["ventas_p"], False),
    ("Utilidad Bruta", kpi["ub_r"], kpi["ub_p"], False),
    ("EBIT", kpi["ebit_r"], kpi["ebit_p"], False),
    ("Gasto total", kpi["gasto_r"], kpi["gasto_p"], True),
]
for col, (label, r, p, invertir) in zip(cols_kpi, _kpis):
    var = r - p
    favorable = (var <= 0) if invertir else (var >= 0)
    color = "#0F6E56" if favorable else "#cc0000"
    icono = "↑" if var >= 0 else "↓"
    pct_txt = f"{r / p * 100:,.0f}% ejec." if p > 0 else "s/ppto comparable"
    with col:
        st.markdown(f"""
        <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                    padding:16px 18px; text-align:center;">
            <div style="font-size:11px; color:#999; margin-bottom:6px;">{label} · Real vs Ppto</div>
            <div style="font-size:22px; font-weight:700; color:#2d0050;">${r/1_000_000:,.1f}M</div>
            <div style="font-size:12px; color:{color}; margin-top:4px;">
                {icono} {abs(var)/1_000_000:,.1f}M · {pct_txt}</div>
            <div style="font-size:11px; color:#aaa;">Ppto {meta['n_meses']} meses: ${p/1_000_000:,.1f}M</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

if rep["alertas"]:
    with st.container(border=True):
        st.markdown("##### ⚠️ Advertencias sobre la base de comparación")
        for a in rep["alertas"]:
            st.markdown(f"<div style='font-size:13px; color:#444; line-height:1.7; "
                        f"margin-bottom:6px;'>• {a}</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

tab_conc, tab_puente, tab_cc, tab_accion = st.tabs([
    "🎯  Conclusiones", "🌉  Puente EBIT", "🏢  Centros de Costo", "📌  Plan de Acción",
])

with tab_conc:
    st.markdown("##### Hallazgos calculados desde los datos")
    st.caption("Reglas deterministas sobre las cifras del periodo: el mismo dato "
               "produce siempre la misma lectura.")
    for c in rep["conclusiones"]:
        st.markdown(f"""
        <div style="background:#fafafa; border:1px solid #e2e8f0; border-left:4px solid #2d0050;
                    border-radius:8px; padding:12px 16px; margin-bottom:8px;
                    font-size:13px; line-height:1.7; color:#333;">{c}</div>
        """, unsafe_allow_html=True)

with tab_puente:
    st.markdown("##### Del EBIT presupuestado al EBIT real")
    st.caption(
        "El efecto de ventas está valorizado al margen de contribución presupuestado "
        "y el costo variable se mide contra el que correspondería a las ventas reales: "
        "así una caída de ventas no aparece como «ahorro» de costo variable."
    )
    df_pu = rep["puente"].copy()
    df_pu["Efecto"] = df_pu["Efecto"].astype(float)
    st.dataframe(
        df_pu[["Concepto", "Efecto"]].style
            .format({"Efecto": lambda v: fmt_mill(v)})
            .map(lambda v: (f"color:{'#0F6E56' if v >= 0 else '#cc0000'};font-weight:600"
                            if isinstance(v, (int, float)) else ""), subset=["Efecto"]),
        use_container_width=True, hide_index=True,
        height=min(60 + 35 * len(df_pu), 560),
    )
    if abs(rep["descuadre"]) > 1:
        st.error(f"El puente descuadra en ${rep['descuadre']:,.0f}. Revisar clasificaciones.")

with tab_cc:
    st.markdown("##### Gasto por centro de costo")
    df_cc = rep["cc"].copy()
    st.dataframe(
        df_cc[["Centro de costo", "Real YTD", "Ppto YTD", "Varianza",
               "Impacto resultado", "% Ejec.", "% Ppto Año consumido",
               "Proyección cierre"]].style
            .format({
                "Real YTD": fmt_mill, "Ppto YTD": fmt_mill, "Varianza": fmt_mill,
                "Impacto resultado": fmt_mill, "Proyección cierre": fmt_mill,
                "% Ejec.": lambda v: f"{v*100:,.0f}%" if pd.notna(v) else "—",
                "% Ppto Año consumido": lambda v: f"{v*100:,.0f}%" if pd.notna(v) else "—",
            })
            .map(lambda v: (f"color:{'#0F6E56' if v >= 0 else '#cc0000'};font-weight:600"
                            if isinstance(v, (int, float)) else ""),
                 subset=["Impacto resultado"]),
        use_container_width=True, hide_index=True,
    )
    st.caption(
        f"«% Ppto Año consumido» se lee contra {meta['n_meses']}/12 meses "
        f"({meta['n_meses']/12*100:.0f}% del año). Un centro de costo con consumo muy "
        f"por sobre esa proporción va camino a pasarse, salvo que su gasto sea estacional."
    )

with tab_accion:
    st.markdown("##### Desviaciones que explican la brecha")
    if rep["accion"].empty:
        st.info("Sin desviaciones desfavorables sobre el umbral de materialidad.")
    else:
        st.caption(
            f"Brecha desfavorable acumulada: **{fmt_mill(rep['total_desfavorable'])}**. "
            f"Las filas siguientes concentran el 80% (Pareto). En el Excel estas mismas "
            f"líneas traen columnas en blanco para la explicación y el compromiso."
        )
        df_ac = rep["accion"].copy()
        st.dataframe(
            df_ac[["Centro de costo", "Cuenta", "Real YTD", "Ppto YTD",
                   "Impacto resultado", "% acum. brecha", "Tipo de brecha",
                   "Meses con desvío desfavorable", "Impacto anualizado"]].style
                .format({
                    "Real YTD": fmt_mill, "Ppto YTD": fmt_mill,
                    "Impacto resultado": fmt_mill,
                    "Impacto anualizado": lambda v: fmt_mill(v) if v else "—",
                    "% acum. brecha": lambda v: f"{v*100:,.0f}%" if pd.notna(v) else "—",
                })
                .map(lambda v: (f"color:{'#0F6E56' if v >= 0 else '#cc0000'};font-weight:600"
                                if isinstance(v, (int, float)) else ""),
                     subset=["Impacto resultado"]),
            use_container_width=True, hide_index=True,
            column_config={
                "Meses con desvío desfavorable": st.column_config.TextColumn(
                    "Meses con desvío desfavorable", width="medium",
                    help="Meses en que la cuenta se desvió en contra del resultado, con el "
                         "monto de cada uno: en gastos, se gastó más que el presupuesto del "
                         "mes (+); en cuentas de ingreso, se vendió menos (−)."),
            },
        )
        st.caption(
            "**Recurrente**: se repite mes a mes, es estructural y se anualiza · "
            "**Puntual**: concentrado en un mes · **Desfase de calendario**: el acumulado "
            "cuadra pero el gasto cayó en otros meses · **No presupuestado**: hay gasto "
            "sin presupuesto asignado."
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("##### Mes a mes de las cuentas con brecha material")
        st.caption(
            "Real, presupuesto y varianza de cada mes: acá se ve exactamente en qué "
            "mes se produjo la desviación y contra qué presupuesto mensual."
        )
        df_mc = rep["mes_cuenta"]
        if df_mc.empty:
            st.info("Sin cuentas sobre el umbral de materialidad.")
        else:
            _cols_mes = meta["meses"] + ["Total YTD"]

            def _color_var(fila):
                # Solo se colorea la fila de varianza; real y ppto van neutros
                if fila["Concepto"] != "Varianza":
                    return [""] * len(fila)
                return ["" if not isinstance(v, (int, float)) else
                        (f"color:{'#cc0000' if v > 0 else '#0F6E56'}" if v else "color:#bbb")
                        for v in fila]

            st.dataframe(
                df_mc.style
                    .format({c: fmt_mill for c in _cols_mes})
                    .apply(_color_var, axis=1),
                use_container_width=True, hide_index=True,
                height=min(60 + 35 * len(df_mc), 520),
            )
            st.caption(
                "En la fila **Varianza**: rojo = se gastó más que el presupuesto de ese mes, "
                "verde = menos. (En cuentas de ingreso la lectura se invierte.)"
            )
