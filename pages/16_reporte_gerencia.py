"""
Reporte de Gerencia — "¿cómo vamos con el presupuesto?" en formato estándar.

Arriba la respuesta (titular, indicadores, tendencia, principales desviaciones,
cierre del año en dos escenarios); abajo el detalle para buscar desviaciones por
cuenta y centro de costo, y el plan de acción con los comentarios de cada
responsable. Se descarga en Excel (para enviar) y HTML (se lee en el celular).
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from utils.auth import login, get_cc_sql_filter, requiere_acceso_total
from utils.components import (
    header, sidebar_kreems, get_soc_sql_filter, ETIQUETA_SOCIEDAD, MESES,
)
from utils import reporte_gerencia as rg
from utils.notas import obtener_notas_desvio, guardar_notas_desvio

_ANO = date.today().year
_FUCSIA, _MORADO2, _MORADO = "#C4007A", "#6B2C91", "#2D0050"
_VERDE, _ROJO = "#0F6E56", "#B42318"

st.set_page_config(page_title="Reporte de Gerencia · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_acceso_total()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header(f"Reporte de Gerencia — Real vs Presupuesto {_ANO}")

filtro_soc = get_soc_sql_filter(sociedad_sel)
filtro_cc = get_cc_sql_filter()


def _md(t: str) -> str:
    """Escapa '$' para que Streamlit no lo interprete como fórmula."""
    return str(t).replace("$", "\\$")


def _html_monto(t: str) -> str:
    return str(t).replace("$", "&#36;")


def _color_desvio(v):
    if not isinstance(v, (int, float)) or pd.isna(v) or abs(v) < 5e4:
        return ""
    return f"color:{_VERDE if v > 0 else _ROJO};font-weight:600"


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

try:
    elim_ic = rg.cargar_eliminaciones_ic(_ANO)
except Exception:
    elim_ic = None
try:
    notas = obtener_notas_desvio(_ANO)
except Exception as e:
    notas = {}
    st.warning(f"No se pudieron leer los comentarios del plan de acción: {e}")

# ── CONTROLES ─────────────────────────────────────────────────
col_mes, col_umbral, col_info = st.columns([1.4, 1.4, 3.2])
with col_mes:
    opciones = diag["meses_con_real"]
    mes_corte = st.selectbox(
        "Acumulado hasta", opciones,
        index=opciones.index(diag["sugerido"]) if diag["sugerido"] in opciones else len(opciones) - 1,
        format_func=lambda m: MESES[m],
        help="El real acumulado se compara contra el presupuesto de estos mismos meses.",
    )
with col_umbral:
    umbral_m = st.number_input(
        "Materialidad (millones)", min_value=0.1, max_value=50.0,
        value=rg.UMBRAL_DEFECTO / 1e6, step=0.5,
        help="Bajo este monto una desviación no se comenta ni entra al plan de acción.",
    )
with col_info:
    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
    st.caption(f"Meses con real cargado: "
               f"{', '.join(rg.ABREV_MES[m] for m in diag['meses_con_real'])}.")

# El error más caro de este reporte: mostrar como ahorro facturas sin cargar
if diag["parcial"] and mes_corte >= diag["ultimo_real"]:
    st.warning(
        f"**{MESES[diag['ultimo_real']]} parece cargado a medias**: ejecutó el "
        f"{diag['ratio']*100:.0f}% de su presupuesto contra {diag['ratio_previo']*100:.0f}% "
        f"típico. Con ese mes incluido aparecen ahorros que probablemente son facturas por "
        f"cargar. Se sugiere cortar en **{MESES[diag['sugerido']]}**.")

if sociedad_sel != "Todas":
    st.error(
        f"Estás viendo solo **{ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)}**. El "
        f"presupuesto es uno solo para el negocio: la comparación solo es válida en "
        f"**Consolidado (ambas)** (barra lateral).")

rep = rg.construir_reporte(
    df, _ANO, int(mes_corte),
    sociedad_lbl=ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel),
    umbral=float(umbral_m) * 1e6, df_soc=df_soc, diag=diag,
    elim_ic=elim_ic, notas=notas,
)
meta, kpi = rep["meta"], rep["kpi"]

# ── DESCARGAS ─────────────────────────────────────────────────
_tag_soc = "Consolidado" if sociedad_sel == "Todas" else sociedad_sel.replace("Ñ", "N")
_nombre = f"Kreems_Reporte_Gerencia_{_tag_soc}_{_ANO}-{int(mes_corte):02d}"
with st.container(border=True):
    col_x, col_h, col_txt = st.columns([1.3, 1.3, 3.4])
    with col_x:
        st.download_button("⬇ Excel para gerencia", data=rg.to_excel(rep),
                           file_name=f"{_nombre}.xlsx", type="primary",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with col_h:
        st.download_button("⬇ Versión web (HTML)", data=rg.to_html(rep).encode("utf-8"),
                           file_name=f"{_nombre}.html", mime="text/html",
                           use_container_width=True)
    with col_txt:
        st.caption("**Excel**: hoja «Resumen Gerencia» con la respuesta y los gráficos, más "
                   "el detalle con filtros, plan de acción y proyección.  \n"
                   "**HTML**: una página que se lee en el celular y se imprime a PDF.")

# ── TITULAR + INDICADORES ─────────────────────────────────────
with st.container(border=True):
    st.markdown(f"#### {_md(rep['titular'][0])}")
    for t in rep["titular"][1:]:
        st.markdown(_md(t))

_kpis = [
    ("Ventas", kpi["ventas_r"], kpi["ventas_p"], kpi["ventas_r"] - kpi["ventas_p"], ""),
    ("Utilidad bruta", kpi["ub_r"], kpi["ub_p"], kpi["ub_r"] - kpi["ub_p"], ""),
    ("Gasto controlable", kpi["ctrl_r"], kpi["ctrl_p"], kpi["ctrl_p"] - kpi["ctrl_r"],
     "Costo fijo + OPEX"),
    ("EBIT", kpi["ebit_r"], kpi["ebit_p"], kpi["ebit_r"] - kpi["ebit_p"], ""),
]
for col, (label, r, p, desv, nota) in zip(st.columns(4), _kpis):
    pct = rg._pct(r, p)
    pie = f"Presupuesto {rg.fmt_m(p)}" + (f" · {rg.fmt_pct(pct)} ejecutado" if pct else "")
    color = _VERDE if desv >= 0 else _ROJO
    with col:
        st.markdown(_html_monto(f"""
        <div style="background:#fff;border:1px solid #EDE4F3;border-radius:12px;padding:14px 16px;">
          <div style="font-size:11px;color:#6B6B7B;text-transform:uppercase;font-weight:600;">{label}</div>
          <div style="font-size:24px;font-weight:800;color:{_MORADO};">{rg.fmt_m(r)}</div>
          <div style="font-size:13px;font-weight:700;color:{color};">
            {'▲' if desv >= 0 else '▼'} {rg.fmt_m(desv, signo=True)} vs presupuesto</div>
          <div style="font-size:11.5px;color:#9A9AAA;">{pie}</div>
          {f'<div style="font-size:11.5px;color:#9A9AAA;">{nota}</div>' if nota else ''}
        </div>"""), unsafe_allow_html=True)

if rep["alertas"]:
    with st.expander(f"Base de comparación ({len(rep['alertas'])} notas)"):
        for a in rep["alertas"]:
            st.markdown(f"- {_md(a)}")

st.markdown("<br>", unsafe_allow_html=True)


# ── VISTAS ────────────────────────────────────────────────────
def _fmt_tabla(df_v: pd.DataFrame, montos: list, pcts: list = (), desvios: list = ()):
    fmt = {c: (lambda v: rg.fmt_m(v)) for c in montos}
    fmt.update({c: (lambda v: rg.fmt_m(v, signo=True)) for c in desvios})
    fmt.update({c: (lambda v: rg.fmt_pct(v)) for c in pcts})
    sty = df_v.style.format(fmt, na_rep="—")
    if desvios:
        sty = sty.map(_color_desvio, subset=list(desvios))
    return sty


def _grafico_mes(col_r: str, col_p: str, titulo: str):
    s = rep["serie"]
    fig = go.Figure()
    fig.add_bar(x=s["Mes"], y=s[col_r] / 1e6, name="Real", marker_color=_FUCSIA,
                hovertemplate="%{x} · real $%{y:,.1f}M<extra></extra>")
    fig.add_scatter(x=s["Mes"], y=s[col_p] / 1e6, name="Presupuesto", mode="markers",
                    marker=dict(symbol="line-ew", size=26, line=dict(width=3, color=_MORADO2)),
                    hovertemplate="%{x} · presupuesto $%{y:,.1f}M<extra></extra>")
    fig.update_layout(title=dict(text=titulo, font=dict(size=14, color=_MORADO)),
                      height=300, margin=dict(l=10, r=10, t=40, b=10), separators=",.",
                      plot_bgcolor="#fff", legend=dict(orientation="h", y=1.12, x=1, xanchor="right"),
                      bargap=0.45)
    fig.update_yaxes(ticksuffix="M", tickprefix="$", gridcolor="#F0EAF4", zerolinecolor="#CFC3DA")
    return fig


(tab_mes, tab_desv, tab_cierre, tab_puente, tab_cc, tab_accion,
 tab_det) = st.tabs(["📈  Mes a mes", "⚖️  Desviaciones", "🔮  Cierre del año", "🌉  Puente EBIT",
                     "🏢  Centros de costo", "📌  Plan de acción", "🔎  Detalle"])

with tab_mes:
    c1, c2 = st.columns(2)
    c1.plotly_chart(_grafico_mes("Ventas real", "Ventas ppto", "Ventas por mes"),
                    use_container_width=True)
    c2.plotly_chart(_grafico_mes("EBIT real", "EBIT ppto", "EBIT por mes"),
                    use_container_width=True)
    st.caption("Barra = real · marca = presupuesto del mes. Los meses sin barra aún no cierran.")
    with st.expander("Estado de resultados mes a mes"):
        df_mpl = rep["mes_pl"]
        st.dataframe(_fmt_tabla(df_mpl, montos=[c for c in df_mpl.columns
                                                 if c not in ("Línea", "Concepto")]),
                     use_container_width=True, hide_index=True)

with tab_desv:
    st.caption("Positivo = suma al resultado (se vendió más o se gastó menos). El costo de "
               "venta no se lista: su variación se explica por el volumen en el puente de EBIT.")
    c1, c2 = st.columns(2)
    cols_top = ["Cuenta", "Centro de costo", "Real YTD", "Ppto YTD", "Desvío",
                "Tipo de brecha", "Comentario"]
    for col, titulo, df_t in [(c1, "Lo que más resta", rep["top_desfav"]),
                              (c2, "Lo que más suma", rep["top_fav"])]:
        with col:
            st.markdown(f"##### {titulo}")
            if df_t.empty:
                st.info("Sin desviaciones sobre la materialidad.")
            else:
                st.dataframe(_fmt_tabla(df_t[cols_top], ["Real YTD", "Ppto YTD"],
                                        desvios=["Desvío"]),
                             use_container_width=True, hide_index=True)
    if rep["conclusiones"]:
        st.markdown("##### Lectura del análisis")
        for c in rep["conclusiones"]:
            st.markdown(f"- {_md(c)}")

with tab_cierre:
    c1, c2, c3 = st.columns(3)
    for col, lbl, ebit, vtas in [
        (c1, f"Si se mantiene el ritmo de {meta['rec_lbl']}", kpi["ebit_cierre_tend"],
         kpi["ventas_cierre_tend"]),
        (c2, "Si se cumple el presupuesto que falta", kpi["ebit_cierre_ppto"],
         kpi["ventas_cierre_ppto"]),
        (c3, "Presupuesto anual", kpi["ebit_ppto_ano"], kpi["ventas_ppto_ano"]),
    ]:
        col.metric(lbl, rg.fmt_m(ebit), help=f"EBIT al cierre · ventas {rg.fmt_m(vtas)}")
        col.caption(_md(f"Ventas {rg.fmt_m(vtas)}"))
    df_pr = rep["proyeccion"].drop(columns=["_subtotal"])
    col_ritmo = [c for c in df_pr.columns if c.startswith("Ritmo")]
    st.dataframe(_fmt_tabla(df_pr, ["Real YTD", "Ppto restante", "Cierre según ppto",
                                    "Cierre según tendencia", "Ppto Año"],
                            pcts=col_ritmo,
                            desvios=["Desvío (según ppto)", "Desvío (según tendencia)"]),
                 use_container_width=True, hide_index=True)
    st.caption(f"Tendencia: el presupuesto de los meses que faltan se ajusta por el ritmo "
               f"real/presupuesto de cada línea en {meta['rec_lbl']}.")

with tab_puente:
    pu = rep["puente"]
    medidas = ["absolute" if t == "inicio" else ("total" if t == "fin" else "relative")
               for t in pu["Tipo"]]
    fig = go.Figure(go.Waterfall(
        orientation="h", measure=medidas, y=pu["Concepto"], x=pu["Efecto"] / 1e6,
        text=[rg.fmt_m(v) if t != "efecto" else rg.fmt_m(v, signo=True)
              for v, t in zip(pu["Efecto"], pu["Tipo"])],
        textposition="outside",
        increasing=dict(marker=dict(color=_VERDE)), decreasing=dict(marker=dict(color=_FUCSIA)),
        totals=dict(marker=dict(color=_MORADO2)), connector=dict(line=dict(color="#E6DCEF")),
        hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_layout(height=max(380, 34 * len(pu)), margin=dict(l=10, r=60, t=10, b=10),
                      plot_bgcolor="#fff", separators=",.", yaxis=dict(autorange="reversed"))
    fig.update_xaxes(ticksuffix="M", tickprefix="$", gridcolor="#F0EAF4")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Verde suma al EBIT, fucsia lo resta. El efecto de ventas está valorizado al "
               "margen de contribución presupuestado.")
    if abs(rep["descuadre"]) > 1:
        st.error(f"El puente descuadra en ${rep['descuadre']:,.0f}. Revisar clasificaciones.")

with tab_cc:
    st.caption("Gasto controlable (costo fijo + OPEX). Desvío positivo = bajo presupuesto.")
    st.dataframe(_fmt_tabla(rep["cc"].drop(columns=["Código"]),
                            ["Real YTD", "Ppto YTD", "Ppto Año", "Cierre según ppto",
                             "Cierre según tendencia"],
                            pcts=["% Ejec.", "% Ppto Año consumido"], desvios=["Desvío"]),
                 use_container_width=True, hide_index=True)
    st.markdown("##### Apertura por línea")
    st.dataframe(_fmt_tabla(rep["cc_linea"], ["Real YTD", "Ppto YTD"], pcts=["% Ejec."],
                            desvios=["Desvío"]),
                 use_container_width=True, hide_index=True)

with tab_accion:
    st.markdown("##### Comentarios del plan de acción")
    st.caption(
        "Completa qué pasó, la acción y el responsable de cada desviación. Se guardan para "
        "todo el año (siguen a la cuenta de un mes a otro) y salen en el Excel y el HTML. "
        "Incluye las desviaciones desfavorables que explican el 80% y las favorables "
        "principales, para confirmar si son ahorro real.")
    filas_ed, claves = [], []
    vistos = set()
    for origen, df_o in [("En contra", rep["accion"]), ("A favor", rep["top_fav"])]:
        for _, r in df_o.iterrows():
            clave = (r["_cuenta"], r["_cc"])
            if clave in vistos:
                continue
            vistos.add(clave)
            n = notas.get(clave, {})
            claves.append(clave)
            filas_ed.append({
                "Sentido": origen,
                "Cuenta": r["Cuenta"],
                "Centro de costo": r["Centro de costo"],
                "Desvío": rg.fmt_m(r["Desvío"], signo=True),
                "Explicación": n.get("explicacion", ""),
                "Acción comprometida": n.get("accion", ""),
                "Responsable": n.get("responsable", ""),
                "Fecha compromiso": pd.to_datetime(n["fecha"]).date() if n.get("fecha") else None,
            })
    if not filas_ed:
        st.info("Sin desviaciones sobre la materialidad.")
    else:
        df_ed = pd.DataFrame(filas_ed)
        editado = st.data_editor(
            df_ed, hide_index=True, use_container_width=True, num_rows="fixed",
            disabled=["Sentido", "Cuenta", "Centro de costo", "Desvío"],
            column_config={
                "Explicación": st.column_config.TextColumn(width="large"),
                "Acción comprometida": st.column_config.TextColumn(width="medium"),
                "Fecha compromiso": st.column_config.DateColumn(format="DD-MM-YYYY"),
            },
            key=f"editor_notas_{mes_corte}",
        )
        if st.button("Guardar comentarios", type="primary"):
            filas = []
            for (cuenta, cc), (_, r) in zip(claves, editado.iterrows()):
                filas.append({"codigo_cuenta": cuenta, "codigo_cc": cc,
                              "explicacion": r["Explicación"], "accion": r["Acción comprometida"],
                              "responsable": r["Responsable"],
                              "fecha": r["Fecha compromiso"] if pd.notna(r["Fecha compromiso"]) else None})
            try:
                n_ok = guardar_notas_desvio(_ANO, filas, st.session_state.get("usuario", ""))
                st.session_state["notas_msg"] = f"✓ {n_ok} comentarios guardados"
                st.rerun()
            except Exception as e:
                st.error(f"No se pudieron guardar los comentarios: {e}")
        msg = st.session_state.pop("notas_msg", None)
        if msg:
            st.success(msg)

    if not rep["accion"].empty:
        st.markdown("##### Desviaciones desfavorables")
        cols_ac = ["Centro de costo", "Cuenta", "Sociedad", "Real YTD", "Ppto YTD", "Desvío",
                   "Tipo de brecha", "Meses desfavorables", "Si se mantiene 12m"]
        st.dataframe(_fmt_tabla(rep["accion"][cols_ac], ["Real YTD", "Ppto YTD"],
                                desvios=["Desvío", "Si se mantiene 12m"]),
                     use_container_width=True, hide_index=True)

with tab_det:
    det = rep["detalle"]
    if det.empty:
        st.info("Sin datos.")
    else:
        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 1.6])
        sel_cc = f1.multiselect("Centro de costo", sorted(det["Centro de costo"].unique()))
        sel_lin = f2.multiselect("Línea", sorted(det["Línea P&L"].unique()))
        sel_tipo = f3.multiselect("Tipo de brecha", sorted(det["Tipo de brecha"].unique()))
        buscar = f4.text_input("Buscar cuenta", placeholder="ej. honorarios o 3.1.01")
        v = det
        if sel_cc:
            v = v[v["Centro de costo"].isin(sel_cc)]
        if sel_lin:
            v = v[v["Línea P&L"].isin(sel_lin)]
        if sel_tipo:
            v = v[v["Tipo de brecha"].isin(sel_tipo)]
        if buscar:
            v = v[v["Cuenta"].str.contains(buscar, case=False, regex=False)]
        cols_det = ["Centro de costo", "Cuenta", "Sociedad", "Línea P&L", "Real YTD", "Ppto YTD",
                    "Desvío", "% Ejec.", "Tipo de brecha", "Meses desfavorables", *rep["cols_mes"]]
        st.dataframe(_fmt_tabla(v[cols_det], ["Real YTD", "Ppto YTD"], pcts=["% Ejec."],
                                desvios=["Desvío", *rep["cols_mes"]]),
                     use_container_width=True, hide_index=True, height=520)
        st.caption(f"{len(v)} de {len(det)} líneas · ordenado por tamaño del desvío.")

with st.expander("Cómo leer las cifras y criterios"):
    for x in rep["escalas"] + rep["bases"]:
        st.markdown(f"- {_md(x)}")
