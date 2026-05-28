"""
Proyección al Cierre — Forecast año completo
Proyecta las líneas del P&L al 31/12 usando tres métodos:
  1. Tendencia Lineal   — extrapola el promedio mensual actual
  2. Estacionalidad     — real YTD ajustado por ritmo vs presupuesto restante
  3. Manual             — el usuario ingresa su propio estimado de cierre
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from utils.auth import login, get_cc_sql_filter, requiere_acceso_total
from utils.db import query
from utils.components import header, sidebar_kreems, fmt_mill, boton_excel

st.set_page_config(page_title="Proyección al Cierre · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()
requiere_acceso_total()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True, mostrar_cc=False)
header("Proyección al Cierre")

_HOY           = date.today()
_ANO           = _HOY.year
MES_ACTUAL     = _HOY.month          # meses con datos reales (1-12)
MESES_RESTANTES = 12 - MES_ACTUAL    # meses sin datos aún

NOMBRES_MESES = {
    1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
    7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"
}

filtro_soc = f"AND sociedad = '{sociedad_sel}'" if sociedad_sel != "Todas" else ""
filtro_cc  = get_cc_sql_filter()

st.markdown(f"""
<p style="color:#888; font-size:13px; margin-bottom:20px;">
    Proyección basada en los <b>{MES_ACTUAL} meses</b> con datos reales ({NOMBRES_MESES[1]} – {NOMBRES_MESES[MES_ACTUAL]}).
    Quedan <b>{MESES_RESTANTES} meses</b> por proyectar hasta el cierre del año.
</p>
""", unsafe_allow_html=True)

# ── DATOS ─────────────────────────────────────────────────────
# Serie mensual completa del año (real + presupuesto mes a mes)
df_mensual = query(f"""
    SELECT
        periodo,
        clasificacion,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta
      {filtro_soc}
      {filtro_cc}
    GROUP BY periodo, clasificacion
    ORDER BY periodo, clasificacion
""", {"desde": f"{_ANO}-01", "hasta": f"{_ANO}-12"})

if df_mensual.empty:
    st.info("Sin datos disponibles para el año en curso.")
    st.stop()

# ── HELPERS ───────────────────────────────────────────────────
CLASIFS = {
    "INGRESO":       "Ventas",
    "COSTO_VAR":     "Costo Variable",
    "COSTO_FIJO":    "Costo Fijo",
    "OPEX":          "OPEX",
    "FINANCIERO":    "Gastos Financieros",
    "NO_OPERACIONAL":"Gastos No Operacionales",
}

def ytd(df, clasif, col):
    """Suma acumulada YTD hasta MES_ACTUAL."""
    mask = (df["clasificacion"] == clasif) & \
           (df["periodo"].astype(str).str[5:7].astype(int) <= MES_ACTUAL)
    v = df.loc[mask, col].sum()
    return float(v) if v else 0.0

def anual(df, clasif, col):
    """Suma del año completo (presupuesto 12 meses)."""
    mask = df["clasificacion"] == clasif
    v = df.loc[mask, col].sum()
    return float(v) if v else 0.0

def restante(df, clasif, col):
    """Suma de meses restantes (MES_ACTUAL+1 a 12) del presupuesto."""
    mask = (df["clasificacion"] == clasif) & \
           (df["periodo"].astype(str).str[5:7].astype(int) > MES_ACTUAL)
    v = df.loc[mask, col].sum()
    return float(v) if v else 0.0

# ── MÉTODO DE PROYECCIÓN ──────────────────────────────────────
st.markdown("##### Método de proyección")
metodo = st.radio(
    "método",
    ["📐 Tendencia Lineal", "📊 Estacionalidad Presupuestada", "✏️ Ingreso Manual"],
    horizontal=True,
    label_visibility="collapsed",
    key="metodo_forecast",
)

st.markdown("""
<div style="background:#f8f5ff; border:1px solid #e8dff5; border-radius:8px;
            padding:12px 18px; font-size:12px; color:#555; margin-bottom:8px; line-height:1.8;">
    <b>📐 Tendencia Lineal</b> — Promedio mensual real × meses restantes &nbsp;·&nbsp;
    <b>📊 Estacionalidad</b> — Real YTD + Presupuesto restante ajustado por ritmo actual &nbsp;·&nbsp;
    <b>✏️ Manual</b> — Tú ingresas el estimado de cierre por línea
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── CALCULAR FORECAST ─────────────────────────────────────────
filas_pl = []   # lista de dicts para la tabla principal

# Inputs manuales (solo se muestran si el método es Manual)
inputs_manual = {}
if "✏️ Ingreso Manual" in metodo:
    st.markdown("##### Ingresa tu estimado de cierre por línea (en millones $)")
    cols_inp = st.columns(3)
    items_input = [
        ("Ventas",              "INGRESO"),
        ("Costo Variable",      "COSTO_VAR"),
        ("Costo Fijo",          "COSTO_FIJO"),
        ("OPEX",                "OPEX"),
        ("Gastos Financieros",  "FINANCIERO"),
        ("Gtos No Operacionales","NO_OPERACIONAL"),
    ]
    for i, (label, clasif) in enumerate(items_input):
        r_ytd  = ytd(df_mensual, clasif, "real")
        p_anual = anual(df_mensual, clasif, "ppto")
        with cols_inp[i % 3]:
            val = st.number_input(
                label,
                value=round(p_anual / 1_000_000, 2),
                step=0.1,
                format="%.2f",
                key=f"manual_{clasif}",
            )
            inputs_manual[clasif] = val * 1_000_000
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# Construir tabla de proyección
for clasif, nombre in CLASIFS.items():
    r_ytd    = ytd(df_mensual,    clasif, "real")
    p_ytd    = ytd(df_mensual,    clasif, "ppto")
    p_anual  = anual(df_mensual,  clasif, "ppto")
    p_rest   = restante(df_mensual, clasif, "ppto")

    if "Tendencia Lineal" in metodo:
        prom_mensual = r_ytd / MES_ACTUAL if MES_ACTUAL else 0
        forecast     = r_ytd + prom_mensual * MESES_RESTANTES

    elif "Estacionalidad" in metodo:
        if p_ytd:
            factor   = r_ytd / p_ytd
            forecast = r_ytd + p_rest * factor
        else:
            forecast = r_ytd + p_rest

    else:  # Manual
        forecast = inputs_manual.get(clasif, p_anual)

    desviacion = forecast - p_anual
    pct_fc     = (forecast / p_anual * 100) if p_anual else 0

    filas_pl.append({
        "clasif":    clasif,
        "Concepto":  nombre,
        "Real YTD":  r_ytd,
        "Ppto YTD":  p_ytd,
        "Forecast Cierre": forecast,
        "Presupuesto Anual": p_anual,
        "Desviación": desviacion,
        "% Forecast": pct_fc,
    })

df_pl = pd.DataFrame(filas_pl)

# Calcular subtotales derivados
def get_fc(clasif):
    row = df_pl[df_pl["clasif"] == clasif]
    return float(row["Forecast Cierre"].iloc[0]) if not row.empty else 0.0

def get_pa(clasif):
    row = df_pl[df_pl["clasif"] == clasif]
    return float(row["Presupuesto Anual"].iloc[0]) if not row.empty else 0.0

def get_ytd(clasif):
    row = df_pl[df_pl["clasif"] == clasif]
    return float(row["Real YTD"].iloc[0]) if not row.empty else 0.0

def get_pytd(clasif):
    row = df_pl[df_pl["clasif"] == clasif]
    return float(row["Ppto YTD"].iloc[0]) if not row.empty else 0.0

# Subtotales
ub_fc  = get_fc("INGRESO")  - get_fc("COSTO_VAR")
ub_pa  = get_pa("INGRESO")  - get_pa("COSTO_VAR")
ub_ytd = get_ytd("INGRESO") - get_ytd("COSTO_VAR")
ub_pytd= get_pytd("INGRESO")- get_pytd("COSTO_VAR")

ebit_fc  = ub_fc  - get_fc("COSTO_FIJO")  - get_fc("OPEX")
ebit_pa  = ub_pa  - get_pa("COSTO_FIJO")  - get_pa("OPEX")
ebit_ytd = ub_ytd - get_ytd("COSTO_FIJO") - get_ytd("OPEX")
ebit_pytd= ub_pytd- get_pytd("COSTO_FIJO")- get_pytd("OPEX")

un_fc  = ebit_fc  - get_fc("FINANCIERO")  - get_fc("NO_OPERACIONAL")
un_pa  = ebit_pa  - get_pa("FINANCIERO")  - get_pa("NO_OPERACIONAL")
un_ytd = ebit_ytd - get_ytd("FINANCIERO") - get_ytd("NO_OPERACIONAL")
un_pytd= ebit_pytd- get_pytd("FINANCIERO")- get_pytd("NO_OPERACIONAL")

# ── KPI CARDS ─────────────────────────────────────────────────
ventas_fc = get_fc("INGRESO")
ventas_pa = get_pa("INGRESO")

kpis = [
    ("Ventas — Forecast Cierre", ventas_fc, ventas_pa),
    ("Utilidad Bruta — Forecast", ub_fc, ub_pa),
    ("EBIT — Forecast Cierre",   ebit_fc, ebit_pa),
    ("Utilidad Neta — Forecast", un_fc, un_pa),
]

cols_kpi = st.columns(4)
for col, (label, fc, pa) in zip(cols_kpi, kpis):
    pct_v = (fc / pa * 100) if pa else 0
    desv  = fc - pa
    color = "#0F6E56" if desv >= 0 else "#cc0000"
    icono = "↑" if desv >= 0 else "↓"
    with col:
        st.markdown(f"""
        <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                    padding:16px 18px; text-align:center; margin-bottom:4px;">
            <div style="font-size:10px; color:#999; margin-bottom:4px;">{label}</div>
            <div style="font-size:22px; font-weight:700; color:#2d0050;">${fc/1_000_000:,.2f}M</div>
            <div style="font-size:11px; color:{color}; margin-top:4px;">
                {icono} {abs(desv)/1_000_000:,.2f}M vs ppto anual</div>
            <div style="font-size:10px; color:#aaa;">{pct_v:.1f}% del objetivo</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── GRÁFICO: Barras apiladas Real YTD + Forecast Restante vs Presupuesto Anual ──
st.markdown("##### Forecast vs Presupuesto Anual por línea P&L")

etiquetas  = ["Ventas", "Ut. Bruta", "EBIT", "Ut. Neta"]
real_vals  = [get_ytd("INGRESO"), ub_ytd, ebit_ytd, un_ytd]
rest_vals  = [ventas_fc - get_ytd("INGRESO"),
              ub_fc - ub_ytd,
              ebit_fc - ebit_ytd,
              un_fc - un_ytd]
ppto_vals  = [ventas_pa, ub_pa, ebit_pa, un_pa]

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Real YTD",
    x=etiquetas, y=[v/1_000_000 for v in real_vals],
    marker_color="#c4007a", opacity=0.9,
    text=[f"${v/1_000_000:,.1f}M" for v in real_vals],
    textposition="inside", textfont=dict(size=10, color="white"),
))
fig.add_trace(go.Bar(
    name="Forecast restante",
    x=etiquetas, y=[v/1_000_000 for v in rest_vals],
    marker_color="#e8a0cc", opacity=0.85,
    text=[f"${v/1_000_000:,.1f}M" for v in rest_vals],
    textposition="inside", textfont=dict(size=10, color="#5a003d"),
))
fig.add_trace(go.Scatter(
    name="Presupuesto Anual",
    x=etiquetas, y=[v/1_000_000 for v in ppto_vals],
    mode="markers",
    marker=dict(symbol="line-ns", size=18, color="#2d0050",
                line=dict(width=3, color="#2d0050")),
))
fig.update_layout(
    barmode="stack",
    height=320,
    margin=dict(t=20, b=10, l=10, r=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    yaxis=dict(tickprefix="$", ticksuffix="M", gridcolor="#f5eef8", zeroline=False),
    xaxis=dict(gridcolor="#f5eef8"),
    legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
    font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"),
)
st.plotly_chart(fig, use_container_width=True)

# ── TABLA COMPLETA ────────────────────────────────────────────
col_tit, col_exp = st.columns([4, 1])
with col_tit:
    st.markdown("##### Detalle P&L — Proyección al Cierre")

# Construir tabla completa con subtotales
COLOR_GOOD = "#0F6E56"
COLOR_BAD  = "#cc0000"

def fila(concepto, r_ytd, p_ytd, fc, pa, es_sub=False):
    return {
        "Concepto":          concepto,
        "Real YTD":          r_ytd,
        "Ppto YTD":          p_ytd,
        "Forecast Cierre":   fc,
        "Presupuesto Anual": pa,
        "Desviación":        fc - pa,
        "% Forecast":        (fc / pa * 100) if pa else 0,
        "_sub":              es_sub,
    }

tabla_rows = [
    fila("Ventas",               get_ytd("INGRESO"),  get_pytd("INGRESO"),  ventas_fc, ventas_pa),
    fila("Costo Variable",       get_ytd("COSTO_VAR"),get_pytd("COSTO_VAR"),get_fc("COSTO_VAR"), get_pa("COSTO_VAR")),
    fila("Utilidad Bruta",       ub_ytd, ub_pytd, ub_fc, ub_pa, True),
    fila("Costo Fijo",           get_ytd("COSTO_FIJO"),get_pytd("COSTO_FIJO"),get_fc("COSTO_FIJO"),get_pa("COSTO_FIJO")),
    fila("OPEX",                 get_ytd("OPEX"),     get_pytd("OPEX"),     get_fc("OPEX"),     get_pa("OPEX")),
    fila("EBIT",                 ebit_ytd, ebit_pytd, ebit_fc, ebit_pa, True),
    fila("Gastos Financieros",   get_ytd("FINANCIERO"),get_pytd("FINANCIERO"),get_fc("FINANCIERO"),get_pa("FINANCIERO")),
    fila("Gtos No Operacionales",get_ytd("NO_OPERACIONAL"),get_pytd("NO_OPERACIONAL"),get_fc("NO_OPERACIONAL"),get_pa("NO_OPERACIONAL")),
    fila("Utilidad Neta",        un_ytd, un_pytd, un_fc, un_pa, True),
]

df_tabla = pd.DataFrame(tabla_rows)
sub_idx  = df_tabla.index[df_tabla["_sub"]].tolist()
df_show  = df_tabla.drop(columns=["_sub"])

# Botón export
with col_exp:
    boton_excel({"Proyección Cierre": df_show}, f"Forecast_{_ANO}")

def _estilo_sub(row):
    if row.name in sub_idx:
        return ["font-weight:bold; background:#fdf5fb; color:#2d0050"] * len(row)
    return [""] * len(row)

def _color_desv(val):
    if not isinstance(val, (int, float)): return ""
    return f"color:{COLOR_GOOD};font-weight:500" if val >= 0 else f"color:{COLOR_BAD};font-weight:500"

def _color_pct(val):
    if not isinstance(val, (int, float)): return ""
    if val >= 100: return f"color:{COLOR_GOOD};font-weight:600"
    if val >= 90:  return "color:#d97706;font-weight:500"
    return f"color:{COLOR_BAD};font-weight:600"

def _semaforo(val):
    """Agrega un indicador visual al % Forecast."""
    if not isinstance(val, (int, float)): return val
    if val >= 100: return f"✅ {val:.1f}%"
    if val >= 90:  return f"⚠️ {val:.1f}%"
    return f"🔴 {val:.1f}%"

st.dataframe(
    df_show.style
        .format({
            "Real YTD":          lambda v: fmt_mill(v),
            "Ppto YTD":          lambda v: fmt_mill(v),
            "Forecast Cierre":   lambda v: fmt_mill(v),
            "Presupuesto Anual": lambda v: fmt_mill(v),
            "Desviación":        lambda v: fmt_mill(v),
            "% Forecast":        _semaforo,
        })
        .apply(_estilo_sub, axis=1)
        .map(_color_desv, subset=["Desviación"])
        .map(_color_pct,  subset=["% Forecast"]),
    use_container_width=True,
    hide_index=True,
    height=420,
)

# ── NOTA AL PIE ───────────────────────────────────────────────
metodo_label = metodo.split(" ", 1)[1]
st.markdown(f"""
<div style="font-size:11px; color:#aaa; margin-top:8px;">
    Método aplicado: <b>{metodo_label}</b> ·
    Datos reales: {NOMBRES_MESES[1]}–{NOMBRES_MESES[MES_ACTUAL]} ({MES_ACTUAL} meses) ·
    Meses proyectados: {MESES_RESTANTES}
</div>
""", unsafe_allow_html=True)
