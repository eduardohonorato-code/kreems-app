"""
Control por Cuenta Contable — KPI cards + tabla detalle con alertas
"""
import streamlit as st
import pandas as pd
import json
from utils.auth import login
from utils.db import query
from utils.components import header, selector_meses, sidebar_kreems, fmt_clp, fmt_mill, boton_excel
from utils.ai import generar_analisis_cuentas
from utils.notas import guardar_nota, obtener_notas, eliminar_nota

st.set_page_config(page_title="Control por Cuenta Contable · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True, mostrar_cc=False)
header("Control por Cuenta Contable")
periodo_desde, periodo_hasta = selector_meses(key="cuentas")
st.markdown("<br>", unsafe_allow_html=True)

filtro_soc = f"AND sociedad = '{sociedad_sel}'" if sociedad_sel != "Todas" else ""
COLOR_GOOD = "#0F6E56"
COLOR_BAD  = "#cc0000"
COLOR_WARN = "#d97706"

NOMBRES_CC = {
    "CC-01": "Administración", "CC-02": "Comercial",
    "CC-03": "Distribución",   "CC-04": "Producción",
}

# ── DATOS ─────────────────────────────────────────────────────────────────
df_det = query(f"""
    SELECT
        codigo_cc,
        clasificacion,
        nombre_cuenta,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta
      AND clasificacion <> 'INGRESO'
      {filtro_soc}
    GROUP BY codigo_cc, clasificacion, nombre_cuenta
    ORDER BY clasificacion, nombre_cuenta
""", {"desde": periodo_desde, "hasta": periodo_hasta})

if df_det.empty:
    st.info("Sin datos para el periodo y filtros seleccionados.")
    st.stop()

df_det["variacion"] = df_det["real"] - df_det["ppto"]
df_det["pct"] = df_det.apply(
    lambda r: (r["real"] / r["ppto"] * 100) if r["ppto"] else
              (float("inf") if r["real"] else 0), axis=1
)

# ── FILTROS ────────────────────────────────────────────────────────────────
col_bus, col_cc_fil, col_cls_fil = st.columns([2, 1, 1])
with col_bus:
    busqueda = st.text_input("Buscar cuenta...", placeholder="Ej: honorarios, combustible...",
                             label_visibility="collapsed")
with col_cc_fil:
    opciones_cc = {"Todos los CC": None}
    opciones_cc.update({f"{NOMBRES_CC.get(cc, cc)} ({cc})": cc
                        for cc in sorted(df_det["codigo_cc"].dropna().unique())})
    cc_sel = st.selectbox("CC", list(opciones_cc.keys()), label_visibility="collapsed")
    cc_filtro = opciones_cc[cc_sel]
with col_cls_fil:
    clasifs = ["Todas"] + sorted(df_det["clasificacion"].dropna().unique().tolist())
    clasif_filtro = st.selectbox("Clasificación", clasifs, label_visibility="collapsed")

# Aplicar filtros
df_fil = df_det.copy()
if busqueda:
    df_fil = df_fil[df_fil["nombre_cuenta"].str.contains(busqueda, case=False, na=False)]
if cc_filtro:
    df_fil = df_fil[df_fil["codigo_cc"] == cc_filtro]
if clasif_filtro != "Todas":
    df_fil = df_fil[df_fil["clasificacion"] == clasif_filtro]

if df_fil.empty:
    st.info("Sin resultados para los filtros aplicados.")
    st.stop()

# Agregar por clasificación + nombre_cuenta
df_agg = df_fil.groupby(["clasificacion", "nombre_cuenta"], as_index=False).agg(
    real=("real", "sum"), ppto=("ppto", "sum")
)
df_agg["variacion"] = df_agg["real"] - df_agg["ppto"]
df_agg["pct"] = df_agg.apply(
    lambda r: (r["real"] / r["ppto"] * 100) if r["ppto"] else
              (float("inf") if r["real"] else 0), axis=1
)

# ── KPI CARDS ─────────────────────────────────────────────────────────────
n_cuentas    = len(df_agg)
real_total   = df_agg["real"].sum()
ppto_total   = df_agg["ppto"].sum()
pct_prom     = (real_total / ppto_total * 100) if ppto_total else 0

# Alertas: pct >= 85 y no es INGRESO
df_alertas   = df_agg[df_agg["pct"].apply(lambda x: x != float("inf") and x >= 85)]
n_alertas    = len(df_alertas)
color_alerta = COLOR_GOOD if n_alertas == 0 else (COLOR_WARN if n_alertas <= 3 else COLOR_BAD)
color_prom   = COLOR_GOOD if pct_prom <= 100 else COLOR_BAD

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #f0dff0;border-radius:12px;
                padding:14px 18px;text-align:center;">
        <div style="font-size:11px;color:#999;margin-bottom:4px;">Cuentas mostradas</div>
        <div style="font-size:26px;font-weight:700;color:#2d0050;">{n_cuentas}</div>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #f0dff0;border-radius:12px;
                padding:14px 18px;text-align:center;">
        <div style="font-size:11px;color:#999;margin-bottom:4px;">Real filtrado</div>
        <div style="font-size:22px;font-weight:700;color:#2d0050;">{fmt_mill(real_total)}</div>
    </div>""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #f0dff0;border-radius:12px;
                padding:14px 18px;text-align:center;">
        <div style="font-size:11px;color:#999;margin-bottom:4px;">% Ejec. promedio</div>
        <div style="font-size:26px;font-weight:700;color:{color_prom};">{pct_prom:.1f}%</div>
    </div>""", unsafe_allow_html=True)

with k4:
    icono = "✓" if n_alertas == 0 else "⚠"
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #f0dff0;border-radius:12px;
                padding:14px 18px;text-align:center;">
        <div style="font-size:11px;color:#999;margin-bottom:4px;">Cuentas con alerta ≥85%</div>
        <div style="font-size:26px;font-weight:700;color:{color_alerta};">{icono} {n_alertas}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── TABLA ─────────────────────────────────────────────────────────────────
col_tit_ct, col_exp_ct = st.columns([4, 1])
with col_tit_ct:
    pass  # titulo dinámico más abajo
_placeholder_exp_ct = col_exp_ct.empty()

t_real = df_agg["real"].sum()
t_ppto = df_agg["ppto"].sum()
total_det = pd.DataFrame([{
    "nombre_cuenta": "TOTAL", "clasificacion": "",
    "real": t_real, "ppto": t_ppto,
    "variacion": t_real - t_ppto,
    "pct": round(t_real / t_ppto * 100, 1) if t_ppto else 0
}])
df_show = pd.concat([df_agg, total_det], ignore_index=True)
df_display = df_show[["nombre_cuenta", "clasificacion", "real", "ppto", "variacion", "pct"]].rename(columns={
    "nombre_cuenta": "Cuenta Contable", "clasificacion": "Clasificación",
    "real": "Real", "ppto": "Presupuesto", "variacion": "Varianza", "pct": "% Ejec."
})

def _color_ctx(row):
    val = row["Varianza"]
    if not isinstance(val, (int, float)):
        return [""]*len(row)
    color = COLOR_GOOD if val <= 0 else COLOR_BAD
    styles = [""]*len(row)
    styles[list(row.index).index("Varianza")] = f"color:{color};font-weight:500"
    return styles

def _color_pct(val):
    if not isinstance(val, (int, float)) or val == float("inf"): return "color:#888"
    if val >= 100: return f"color:{COLOR_BAD};font-weight:600"
    if val >= 85:  return f"color:{COLOR_WARN};font-weight:600"
    return f"color:{COLOR_GOOD}"

def _total_row(row):
    if row["Cuenta Contable"] == "TOTAL":
        return ["font-weight:bold;background:#fdf5fb"]*len(row)
    return [""]*len(row)

def _fmt_pct(v):
    if isinstance(v, float):
        return "∞%" if v == float("inf") else f"{v:.1f}%"
    return v

st.dataframe(
    df_display.style
        .format({"Real": lambda v: fmt_clp(v), "Presupuesto": lambda v: fmt_clp(v),
                 "Varianza": lambda v: fmt_clp(v), "% Ejec.": _fmt_pct})
        .apply(_total_row, axis=1)
        .apply(_color_ctx, axis=1)
        .map(_color_pct, subset=["% Ejec."]),
    use_container_width=True,
    hide_index=True,
    height=520
)
st.caption(f"{n_cuentas} cuenta{'s' if n_cuentas != 1 else ''} mostrada{'s' if n_cuentas != 1 else ''}")

with _placeholder_exp_ct:
    boton_excel(
        {"Cuentas Contables": df_display},
        f"CuentasContables_{periodo_desde}_{periodo_hasta}",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── NOTAS DE GESTIÓN ──────────────────────────────────────────
st.markdown("---")
st.markdown("##### 📝 Notas de Gestión")

_usuario_ct = st.session_state.get("nombre", "")
_notas_ct   = obtener_notas(periodo_desde, periodo_hasta, sociedad_sel, tipo="CUENTA")

col_form_ct, col_notas_ct = st.columns([1, 1])

with col_form_ct:
    st.markdown("**Agregar / editar nota**")
    cuentas_para_nota = sorted(df_agg["nombre_cuenta"].tolist())
    cuenta_nota_sel = st.selectbox(
        "Cuenta contable",
        cuentas_para_nota,
        key="ct_nota_sel",
        label_visibility="collapsed",
    )
    texto_nota_ct = ""
    if not _notas_ct.empty:
        fila_ct = _notas_ct[_notas_ct["referencia"] == cuenta_nota_sel]
        if not fila_ct.empty:
            texto_nota_ct = fila_ct.iloc[0]["nota"]

    nota_input_ct = st.text_area(
        "Nota",
        value=texto_nota_ct,
        placeholder="Ej: Gasto puntual por renovación de contrato de software anual...",
        height=110,
        key="ct_nota_input",
        label_visibility="collapsed",
    )
    col_save_ct, _ = st.columns([2, 1])
    with col_save_ct:
        if st.button("💾 Guardar nota", type="primary", use_container_width=True, key="ct_nota_guardar"):
            if nota_input_ct.strip():
                guardar_nota(
                    periodo_desde, periodo_hasta, sociedad_sel,
                    "CUENTA", cuenta_nota_sel, nota_input_ct.strip(), _usuario_ct,
                )
                st.success(f"✓ Nota guardada para «{cuenta_nota_sel[:45]}»")
                st.rerun()
            else:
                st.warning("Escribe una nota antes de guardar.")

with col_notas_ct:
    st.markdown("**Notas registradas en este período**")
    if _notas_ct.empty:
        st.markdown(
            "<div style='color:#aaa; font-size:13px; padding:12px 0;'>Sin notas para este período.</div>",
            unsafe_allow_html=True,
        )
    else:
        for _, nr in _notas_ct.iterrows():
            fecha_fmt = pd.Timestamp(nr["actualizado_en"]).strftime("%d/%m %H:%M") if pd.notna(nr["actualizado_en"]) else ""
            col_nota_txt, col_nota_del = st.columns([10, 1])
            with col_nota_txt:
                st.markdown(f"""
                <div style="background:#fafafa; border:1px solid #e2e8f0;
                            border-left:4px solid #c4007a; border-radius:8px;
                            padding:10px 14px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span style="font-size:12px; font-weight:700; color:#2d0050;
                                     white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                                     max-width:280px;">{nr['referencia']}</span>
                        <span style="font-size:10px; color:#aaa;">{nr['creado_por']} · {fecha_fmt}</span>
                    </div>
                    <div style="font-size:12px; color:#444; line-height:1.5;">{nr['nota']}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_nota_del:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                if st.button("🗑", key=f"del_nota_ct_{nr['id']}", help="Eliminar esta nota"):
                    eliminar_nota(int(nr["id"]))
                    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ── ANÁLISIS IA ────────────────────────────────────────────────
st.markdown("##### Análisis IA")

if "cuentas_analisis_texto" not in st.session_state:
    st.session_state["cuentas_analisis_texto"] = ""

col_ia_ct, col_cerrar_ct, _ = st.columns([2, 1, 2])

with col_ia_ct:
    generar_ct = st.button("Generar Análisis con IA", type="primary", key="btn_ia_cuentas", use_container_width=True)

if generar_ct:
    # Top 5 cuentas con mayor desviación positiva (sobreejecución)
    df_top = df_agg[df_agg["pct"] != float("inf")].nlargest(5, "pct")
    top_desv = [
        {"nombre": r["nombre_cuenta"], "real": float(r["real"]),
         "ppto": float(r["ppto"]), "pct": float(r["pct"])}
        for _, r in df_top.iterrows()
    ]
    datos_ia = {
        "sociedad":      sociedad_sel,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "real_total":    float(real_total),
        "ppto_total":    float(ppto_total),
        "n_cuentas":     n_cuentas,
        "n_alertas":     n_alertas,
        "top_desviacion": top_desv,
    }
    with st.spinner("Analizando datos con IA..."):
        st.session_state["cuentas_analisis_texto"] = generar_analisis_cuentas(datos_ia)
        st.session_state["cuentas_analisis_datos"] = datos_ia

if st.session_state["cuentas_analisis_texto"]:
    with col_cerrar_ct:
        if st.button("✕ Cerrar", use_container_width=True, key="ct_cerrar"):
            st.session_state["cuentas_analisis_texto"] = ""
            st.rerun()

if st.session_state["cuentas_analisis_texto"]:
    st.markdown(f"""
    <div style="background:#fafafa; border:1px solid #e2e8f0; border-left:4px solid #2d0050;
                border-radius:8px; padding:20px 24px; margin-top:12px;
                font-size:13px; line-height:1.8; color:#333; white-space:pre-wrap;">
{st.session_state["cuentas_analisis_texto"]}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**Guardar este análisis**")
        col_input, col_save = st.columns([4, 1])
        with col_input:
            titulo_cuentas = st.text_input(
                "Título",
                value=f"Cuentas {periodo_desde} – {periodo_hasta} · {sociedad_sel}",
                label_visibility="collapsed",
                key="cuentas_titulo_rpt",
            )
        with col_save:
            if st.button("Guardar", type="primary", use_container_width=True, key="cuentas_guardar_btn"):
                try:
                    from sqlalchemy import text as sqlt
                    from utils.db import get_engine
                    datos_snap = st.session_state.get("cuentas_analisis_datos", {})
                    with get_engine().begin() as conn:
                        conn.execute(sqlt("""
                            INSERT INTO reports.reportes_guardados
                                (titulo, tipo, periodo_desde, periodo_hasta,
                                 sociedad, datos_json, analisis_ia, creado_por)
                            VALUES
                                (:titulo, 'CUENTAS', :pdesde, :phasta,
                                 :sociedad, :datos, :analisis, :usuario)
                        """), {
                            "titulo":   titulo_cuentas,
                            "pdesde":   periodo_desde,
                            "phasta":   periodo_hasta,
                            "sociedad": sociedad_sel,
                            "datos":    json.dumps(datos_snap),
                            "analisis": st.session_state["cuentas_analisis_texto"],
                            "usuario":  st.session_state.get("nombre", ""),
                        })
                    st.success("✓ Reporte guardado. Ve a **Reportes Guardados** para revisarlo.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
