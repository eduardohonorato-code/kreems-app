"""
EERR por Centro de Costo — Estado de Resultados con los centros de costo en columnas.

Las ventas y el costo variable se registran sin centro de costo (CC-00), por lo
que la Utilidad Bruta aparece en esa columna y cada CC (Administración,
Comercial, Distribución, Producción) resta su gasto hasta el EBIT total.
Vistas: Real, Presupuesto y Desvío (signo del efecto sobre el resultado).
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from utils.auth import login, get_cc_sql_filter
from utils.components import (
    header, sidebar_kreems, selector_meses, boton_excel, get_soc_sql_filter,
    ETIQUETA_SOCIEDAD, MESES, SOC_ACUNA, SOC_GRAN_NATURAL,
)
from utils import reporte_gerencia as rg
from utils import eerr_cc as ec

_ANO = date.today().year
_MORADO, _FUCSIA = "#2D0050", "#C4007A"
_VERDE, _ROJO = "#0F6E56", "#B42318"

st.set_page_config(page_title="EERR por Centro de Costo · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header(f"EERR por Centro de Costo {_ANO}")

filtro_soc = get_soc_sql_filter(sociedad_sel)
filtro_cc = get_cc_sql_filter()


def _md(t: str) -> str:
    """Escapa '$' para que Streamlit no lo interprete como fórmula."""
    return str(t).replace("$", "\\$")


def _estilo_fila(row):
    if row["Línea"] in ec.LINEAS_SUBTOTAL:
        return [f"font-weight:700;background:#F3E9F7;color:{_MORADO}"] * len(row)
    return [""] * len(row)


def _color_desvio(v):
    if not isinstance(v, (int, float)) or pd.isna(v) or abs(v) < 5e4:
        return ""
    return f"color:{_VERDE if v > 0 else _ROJO};font-weight:600"


def _estilo(df_v: pd.DataFrame, montos: list, desvios: list = (), pcts: list = ()):
    fmt = {c: (lambda v: rg.fmt_m(v)) for c in montos}
    fmt.update({c: (lambda v: rg.fmt_m(v, signo=True)) for c in desvios})
    fmt.update({c: (lambda v: rg.fmt_pct(v)) for c in pcts})
    sty = df_v.style.format(fmt).apply(_estilo_fila, axis=1)
    if desvios:
        sty = sty.map(_color_desvio, subset=list(desvios))
    return sty


def _lbl_mes(per: str) -> str:
    return f"{MESES[int(per[5:7])]} {per[:4]}"


def render_mes_a_mes():
    """P&L con los meses en columnas, rango libre (puede cruzar años), por sociedad."""
    hoy = date.today()
    per_actual = f"{hoy.year}-{hoy.month:02d}"
    opciones = ec.periodos_rango(f"{hoy.year - 1}-01", per_actual)

    # Por defecto: 12 meses terminando en el último mes completo del año en curso
    diag = rg.diagnostico_corte(rg.cargar_movimientos(_ANO, "", filtro_cc), _ANO)
    hasta_def = f"{_ANO}-{diag['sugerido']:02d}" if diag["sugerido"] else per_actual
    desde_def = ec.sumar_meses(hasta_def, -11)

    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.6, 1.4])
    with c1:
        desde = st.selectbox("Desde", opciones, index=opciones.index(desde_def),
                             format_func=_lbl_mes, key="eerrcc_mm_desde")
    with c2:
        hasta = st.selectbox("Hasta", opciones, index=opciones.index(hasta_def),
                             format_func=_lbl_mes, key="eerrcc_mm_hasta")
    if desde > hasta:
        st.error("«Desde» debe ser anterior o igual a «Hasta».")
        st.stop()
    periodos = ec.periodos_rango(desde, hasta)

    raw = ec.cargar_rango(desde, hasta, filtro_cc)
    if raw.empty:
        st.info(f"No hay movimientos cargados entre {_lbl_mes(desde)} y {_lbl_mes(hasta)}.")
        st.stop()
    d_all = rg.normalizar_movimientos(raw)

    ccs = ec.columnas_cc(d_all)
    with c3:
        cc_sel = st.selectbox("Centro de costo", [None] + ccs, key="eerrcc_mm_cc",
                              format_func=lambda c: "Todos (empresa)" if c is None
                              else ec.etiqueta_cc(c))
    with c4:
        vista = st.radio("Vista", ec.VISTAS, horizontal=True, key="eerrcc_mm_vista")

    def _filtrar(soc: str | None, cc: str | None) -> pd.DataFrame:
        x = d_all if soc in (None, "Todas") else d_all[d_all["sociedad"] == soc]
        return x if cc is None else x[x["codigo_cc"] == cc]

    # Cobertura: meses sin real por sociedad
    huecos = {s: ec.meses_sin_real(d_all, periodos, s) for s in (SOC_GRAN_NATURAL, SOC_ACUNA)}
    faltan = [f"**{ETIQUETA_SOCIEDAD[s]}**: " + ", ".join(ec.etiqueta_periodo(p) for p in h)
              for s, h in huecos.items() if h]
    if faltan:
        st.warning("Meses sin real cargado (aparecen en cero): " + " · ".join(faltan))
    if vista != "Real":
        st.caption("El presupuesto está cargado solo bajo Gran Natural y solo para "
                   f"{_ANO}; el real contra presupuesto es válido en Consolidado.")

    d = _filtrar(sociedad_sel, cc_sel)
    mat = ec.matriz_mensual(d, vista, periodos)
    num = [c for c in mat.columns if c != "Línea"]
    _cc_lbl = "Todos los centros de costo" if cc_sel is None else ec.etiqueta_cc(cc_sel)
    st.markdown(f"##### {vista} · {_lbl_mes(desde)} a {_lbl_mes(hasta)} · "
                f"{ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)} · {_cc_lbl}")
    es_desv = vista == "Desvío"
    st.dataframe(
        _estilo(mat, montos=[] if es_desv else num, desvios=num if es_desv else []),
        use_container_width=True, hide_index=True, height=(len(mat) + 1) * 35 + 3,
        column_config={"Línea": st.column_config.TextColumn("Línea", width="medium",
                                                            pinned=True)},
    )
    st.caption("La sociedad se elige en el menú lateral. El Excel trae siempre Gran Natural, "
               "ACUÑA y Consolidado por separado, más el detalle por cuenta de cada sociedad.")

    with st.expander("Detalle por cuenta (real)", expanded=False):
        det = ec.cuentas_mensual(d, periodos, "real")
        if det.empty:
            st.info("Sin cuentas con movimiento.")
        else:
            cols_m = [c for c in det.columns if c not in ("Línea", "Centro de costo", "Cuenta")]
            st.dataframe(det.style.format({c: rg.fmt_m for c in cols_m}),
                         use_container_width=True, hide_index=True,
                         height=min(600, (len(det) + 1) * 35 + 3))

    # ── Excel: una hoja por sociedad + consolidado + cuentas por sociedad ──
    col_v = vista
    hojas = {}
    for soc, nombre in ((SOC_GRAN_NATURAL, "Gran Natural"), (SOC_ACUNA, "ACUÑA"),
                        ("Todas", "Consolidado")):
        hojas[nombre] = ec.matriz_mensual(_filtrar(soc, cc_sel), col_v, periodos)
    for soc, nombre in ((SOC_GRAN_NATURAL, "Cuentas Gran Natural"), (SOC_ACUNA, "Cuentas ACUÑA")):
        hojas[nombre] = ec.cuentas_mensual(_filtrar(soc, cc_sel),
                                           periodos, "ppto" if col_v == "Presupuesto" else "real")
    _tag_cc = "" if cc_sel is None else f"_{ec.etiqueta_cc(cc_sel)}"
    boton_excel(hojas, f"EERR_mensual_{col_v.replace('í', 'i')}_{desde}_a_{hasta}{_tag_cc}",
                label=f"⬇ Exportar Excel mes a mes ({col_v}, por sociedad)")


formato = st.radio(
    "Formato", ["Por centro de costo", "Mes a mes"], horizontal=True, key="eerrcc_formato",
    help="«Mes a mes» pone los meses en columnas y permite un rango que cruza años "
         "(ej. noviembre 2025 a octubre 2026).",
)

if formato == "Mes a mes":
    render_mes_a_mes()
    st.stop()

# ── DATOS (año completo; el período se filtra en memoria) ─────
df = rg.cargar_movimientos(_ANO, filtro_soc, filtro_cc)
if df.empty:
    st.info("Sin datos para el año y los filtros seleccionados.")
    st.stop()

diag = rg.diagnostico_corte(df, _ANO)
_mes_def = MESES.get(diag["sugerido"] or 1, "Enero")
periodo_desde, periodo_hasta = selector_meses(key="eerrcc", default=_mes_def)

d = rg.normalizar_movimientos(df)
d = d[(d["periodo"] >= periodo_desde) & (d["periodo"] <= periodo_hasta)]
if d.empty:
    _ult = diag["ultimo_real"]
    st.info("Sin movimientos en el período seleccionado"
            + (f" para {ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)}; "
               f"el último mes con real es {MESES[_ult]}." if _ult else "."))
    st.stop()

mes_desde, mes_hasta = int(periodo_desde[5:7]), int(periodo_hasta[5:7])
_periodo_lbl = (MESES[mes_hasta] if mes_desde == mes_hasta
                else f"{MESES[mes_desde]}–{MESES[mes_hasta]}")
_soc_lbl = ETIQUETA_SOCIEDAD.get(sociedad_sel, sociedad_sel)

# ── AVISOS ────────────────────────────────────────────────────
if diag["parcial"] and mes_hasta >= diag["ultimo_real"]:
    st.warning(
        f"{MESES[diag['ultimo_real']]} parece cargado a medias "
        f"(real al {rg.fmt_pct(diag['ratio'])} del presupuesto, contra "
        f"{rg.fmt_pct(diag['ratio_previo'])} en los meses anteriores). "
        f"Para comparar con presupuesto conviene cortar en {MESES.get(diag['sugerido'], '—')}."
    )
if sociedad_sel == SOC_ACUNA:
    st.info("ACUÑA no tiene presupuesto cargado: usa la vista **Real**. "
            "El presupuesto está solo bajo Gran Natural; compara en Consolidado.")
elif sociedad_sel == SOC_GRAN_NATURAL:
    st.info("El presupuesto está cargado solo bajo Gran Natural, pero cubre la operación "
            "de ambas sociedades: el real contra presupuesto es válido en **Consolidado**.")

# ── SELECTOR DE VISTA ─────────────────────────────────────────
col_vista, col_exp = st.columns([3, 1])
with col_vista:
    vista = st.radio("Vista", ec.VISTAS, horizontal=True, key="eerrcc_vista",
                     help="Desvío positivo = favorable (más venta o menos gasto que el presupuesto).")

mat = ec.matriz(d, vista)
num_cols = [c for c in mat.columns if c != "Línea"]
es_desvio = vista == "Desvío"

st.markdown(f"##### {vista} · {_periodo_lbl} {_ANO} · {_soc_lbl}")
st.dataframe(
    _estilo(mat, montos=[] if es_desvio else num_cols, desvios=num_cols if es_desvio else []),
    use_container_width=True, hide_index=True, height=(len(mat) + 1) * 35 + 3,
    column_config={"Línea": st.column_config.TextColumn("Línea", width="medium")},
)
st.caption(
    "Las ventas y el costo variable se registran **sin centro de costo**, por eso la Utilidad "
    "Bruta aparece en esa columna; cada centro de costo resta su gasto y el EBIT de la "
    "empresa se lee en **Total**."
)

# ── GRÁFICO: resultado de cada CC, real vs presupuesto ────────
real_m = ec.matriz(d, "Real").set_index("Línea")
ppto_m = ec.matriz(d, "Presupuesto").set_index("Línea")
ccs_graf = [c for c in real_m.columns if c != ec.COL_TOTAL]

col_g, col_t = st.columns([1.3, 1])
with col_g:
    st.markdown("##### Aporte de cada centro de costo al EBIT")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=ccs_graf, y=[real_m.loc["EBIT", c] / 1e6 for c in ccs_graf], name="Real",
        marker_color=_FUCSIA,
        text=[rg.fmt_m(real_m.loc["EBIT", c]) for c in ccs_graf], textposition="outside"))
    fig.add_trace(go.Bar(
        x=ccs_graf, y=[ppto_m.loc["EBIT", c] / 1e6 for c in ccs_graf], name="Presupuesto",
        marker_color=_MORADO, opacity=0.55))
    fig.update_layout(
        barmode="group", height=320, margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(tickprefix="$", ticksuffix="M", gridcolor="#f0f0f0", zeroline=True,
                   zerolinecolor="#ccc"),
        legend=dict(orientation="h", y=1.12, x=0),
        font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"))
    st.plotly_chart(fig, use_container_width=True)

with col_t:
    st.markdown("##### EBIT por centro de costo")
    df_ebit = pd.DataFrame({
        "Centro de costo": list(real_m.columns),
        "Real": [real_m.loc["EBIT", c] for c in real_m.columns],
        "Presupuesto": [ppto_m.loc["EBIT", c] for c in real_m.columns],
    })
    df_ebit["Desvío"] = df_ebit["Real"] - df_ebit["Presupuesto"]
    st.dataframe(
        df_ebit.style.format({"Real": rg.fmt_m, "Presupuesto": rg.fmt_m,
                              "Desvío": lambda v: rg.fmt_m(v, signo=True)})
        .map(_color_desvio, subset=["Desvío"])
        .apply(lambda r: [f"font-weight:700;background:#F3E9F7"] * len(r)
               if r["Centro de costo"] == ec.COL_TOTAL else [""] * len(r), axis=1),
        use_container_width=True, hide_index=True)

# ── DETALLE DE UN CENTRO DE COSTO ─────────────────────────────
st.markdown("---")
st.markdown("##### Detalle de un centro de costo")
_ccs = ec.columnas_cc(d)
_opts = [None] + _ccs
cc_sel = st.selectbox("Centro de costo", _opts, key="eerrcc_cc",
                      format_func=lambda c: "Total empresa" if c is None else ec.etiqueta_cc(c))

res = ec.resumen_cc(d, cc_sel)
st.dataframe(_estilo(res, ["Real", "Presupuesto"], desvios=["Desvío"], pcts=["% Ejec."]),
             use_container_width=True, hide_index=True, height=(len(res) + 1) * 35 + 3)

det = ec.detalle_cuentas(d, cc_sel)
with st.expander(f"Cuentas ({len(det)})", expanded=False):
    if det.empty:
        st.info("Sin cuentas con movimiento.")
    else:
        cols_det = det.columns if cc_sel is None else [c for c in det.columns if c != "Centro de costo"]
        st.dataframe(
            det[cols_det].style
            .format({"Real": rg.fmt_m, "Presupuesto": rg.fmt_m,
                     "Desvío": lambda v: rg.fmt_m(v, signo=True), "% Ejec.": rg.fmt_pct})
            .map(_color_desvio, subset=["Desvío"]),
            use_container_width=True, hide_index=True, height=min(600, (len(det) + 1) * 35 + 3))

# ── EXPORTAR ──────────────────────────────────────────────────
det_todo = ec.detalle_cuentas(d)
det_todo["% Ejec."] = (pd.to_numeric(det_todo["% Ejec."], errors="coerce") * 100).round(1)
with col_exp:
    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
    _tag_soc = "Consolidado" if sociedad_sel == "Todas" else sociedad_sel.replace("Ñ", "N")
    boton_excel(
        {"Real": ec.matriz(d, "Real"),
         "Presupuesto": ec.matriz(d, "Presupuesto"),
         "Desvio": ec.matriz(d, "Desvío"),
         "Detalle cuentas": det_todo},
        f"EERR_por_CC_{_tag_soc}_{periodo_desde}_{periodo_hasta}",
        label="⬇ Exportar Excel",
    )
