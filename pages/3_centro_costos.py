"""
Centro de Costos — tarjetas + gráfico + resumen por CC
"""
import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from utils.auth import login
from utils.db import query
from utils.components import header, selector_meses, sidebar_kreems, fmt_mill, cc_card, boton_excel
from utils.ai import generar_analisis_cc
from utils.notas import guardar_nota, obtener_notas, eliminar_nota

st.set_page_config(page_title="Centro de Costos · Kreems", page_icon="💜", layout="wide")

if not login():
    st.stop()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True, mostrar_cc=False)
header("Centro de Costos")
periodo_desde, periodo_hasta = selector_meses(key="cc")
st.markdown("<br>", unsafe_allow_html=True)

filtro_soc = f"AND sociedad = '{sociedad_sel}'" if sociedad_sel != "Todas" else ""
COLOR_GOOD = "#0F6E56"
COLOR_BAD  = "#cc0000"

NOMBRES_CC = {
    "CC-01": "Administración",
    "CC-02": "Comercial",
    "CC-03": "Distribución",
    "CC-04": "Producción",
}

df_cc = query(f"""
    SELECT
        codigo_cc,
        nombre_cc,
        SUM(valor_real) AS real,
        SUM(valor_ppto) AS ppto
    FROM marts.vw_real_vs_ppto
    WHERE periodo BETWEEN :desde AND :hasta
      AND codigo_cc <> 'CC-00'
      AND clasificacion <> 'INGRESO'
      {filtro_soc}
    GROUP BY codigo_cc, nombre_cc
    ORDER BY codigo_cc
""", {"desde": periodo_desde, "hasta": periodo_hasta})

if df_cc.empty:
    st.info("Sin datos para el periodo y filtros seleccionados.")
    st.stop()

# TARJETAS
cc_data = {row["codigo_cc"]: row for _, row in df_cc.iterrows()}
cols_cards = st.columns(4)
for i, (codigo, nombre) in enumerate(NOMBRES_CC.items()):
    with cols_cards[i]:
        if codigo in cc_data:
            r = cc_data[codigo]
            st.markdown(cc_card(nombre, codigo, float(r["real"]), float(r["ppto"])), unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#fafafa;border:1px solid #f0dff0;border-radius:14px;
                        padding:18px 20px;text-align:center;">
                <div style="font-size:11px;color:#aaa;font-weight:600;text-transform:uppercase;">{codigo}</div>
                <div style="font-size:14px;font-weight:600;color:#ccc;margin-top:4px;">{nombre}</div>
                <div style="font-size:12px;color:#ddd;margin-top:12px;">Sin datos</div>
            </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# GRÁFICO + RESUMEN
col_graf, col_res = st.columns([1, 1.3])

with col_graf:
    st.markdown("##### Real vs Presupuesto por CC")
    labels  = [NOMBRES_CC.get(r["codigo_cc"], r["nombre_cc"]) for _, r in df_cc.iterrows()]
    reales  = [float(r["real"]) / 1_000_000 for _, r in df_cc.iterrows()]
    pptos   = [float(r["ppto"]) / 1_000_000 for _, r in df_cc.iterrows()]
    pcts    = [(float(r["real"]) / float(r["ppto"]) * 100) if r["ppto"] else 0 for _, r in df_cc.iterrows()]
    colores = [COLOR_BAD if p > 100 else "#c4007a" for p in pcts]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=reales, name="Real", orientation="h",
        marker_color=colores, opacity=0.9,
        text=[f"${v:.2f}M" for v in reales], textposition="outside",
        textfont={"size": 11, "color": "#444"}))
    fig.add_trace(go.Scatter(y=labels, x=pptos, name="Presupuesto", mode="markers",
        marker=dict(symbol="line-ns", size=16, color="#2d0050", line=dict(width=2.5, color="#2d0050"))))
    fig.update_layout(height=260, margin=dict(t=10,b=10,l=10,r=80),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(tickprefix="$", ticksuffix="M", gridcolor="#f0f0f0", zeroline=False),
        yaxis=dict(gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=1.22, x=0, font=dict(size=11)),
        font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"))
    st.plotly_chart(fig, use_container_width=True)

with col_res:
    col_tit_res, col_exp_res = st.columns([3, 1])
    with col_tit_res:
        st.markdown("##### Resumen por CC")
    with col_exp_res:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    df_r = df_cc.copy()
    df_r["variacion"] = df_r["real"] - df_r["ppto"]
    df_r["pct"]       = (df_r["real"] / df_r["ppto"] * 100).round(1).fillna(0)
    df_r["nombre"]    = df_r["codigo_cc"].map(NOMBRES_CC).fillna(df_r["nombre_cc"])
    total = pd.DataFrame([{
        "nombre": "TOTAL", "real": df_r["real"].sum(), "ppto": df_r["ppto"].sum(),
        "variacion": df_r["real"].sum() - df_r["ppto"].sum(),
        "pct": round(df_r["real"].sum() / df_r["ppto"].sum() * 100, 1) if df_r["ppto"].sum() else 0
    }])

    df_show = pd.concat([df_r[["nombre","real","ppto","variacion","pct"]], total], ignore_index=True)
    df_show = df_show.rename(columns={"nombre":"CC","real":"Real","ppto":"Presupuesto","variacion":"Varianza","pct":"% Ejec."})

    def _cv(val):
        if not isinstance(val, (int, float)): return ""
        return f"color:{COLOR_GOOD};font-weight:500" if val <= 0 else f"color:{COLOR_BAD};font-weight:500"
    def _cp(val):
        if not isinstance(val, (int, float)): return ""
        return f"color:{COLOR_GOOD}" if val <= 100 else f"color:{COLOR_BAD};font-weight:600"
    def _tot(row):
        if row["CC"] == "TOTAL": return ["font-weight:bold;background:#fdf5fb"]*len(row)
        return [""]*len(row)

    st.dataframe(df_show.style
        .format({"Real": lambda v: fmt_mill(v), "Presupuesto": lambda v: fmt_mill(v),
                 "Varianza": lambda v: fmt_mill(v),
                 "% Ejec.": lambda v: f"{v:.1f}%" if isinstance(v, float) else v})
        .apply(_tot, axis=1).map(_cv, subset=["Varianza"]).map(_cp, subset=["% Ejec."]),
        use_container_width=True, hide_index=True, height=255)

    with col_exp_res:
        boton_excel(
            {"Centro de Costos": df_show},
            f"CC_{periodo_desde}_{periodo_hasta}",
        )

st.markdown("<br>", unsafe_allow_html=True)

# ── NOTAS DE GESTIÓN ──────────────────────────────────────────
st.markdown("---")
st.markdown("##### 📝 Notas de Gestión")

_usuario = st.session_state.get("nombre", "")
_notas_cc = obtener_notas(periodo_desde, periodo_hasta, sociedad_sel, tipo="CC")

col_form_cc, col_notas_cc = st.columns([1, 1])

with col_form_cc:
    st.markdown("**Agregar / editar nota**")
    opciones_nota = {v: k for k, v in NOMBRES_CC.items()}   # nombre → código
    cc_nota_sel = st.selectbox(
        "Centro de Costo",
        list(NOMBRES_CC.values()),
        key="cc_nota_sel",
        label_visibility="collapsed",
    )
    texto_nota = ""
    # Pre-cargar nota existente si hay
    if not _notas_cc.empty:
        cc_codigo = opciones_nota.get(cc_nota_sel, cc_nota_sel)
        fila = _notas_cc[_notas_cc["referencia"] == cc_codigo]
        if not fila.empty:
            texto_nota = fila.iloc[0]["nota"]

    nota_input = st.text_area(
        "Nota",
        value=texto_nota,
        placeholder="Ej: Incremento por contratación de personal temporal en temporada alta...",
        height=110,
        key="cc_nota_input",
        label_visibility="collapsed",
    )
    col_save_cc, col_clear_cc = st.columns([2, 1])
    with col_save_cc:
        if st.button("💾 Guardar nota", type="primary", use_container_width=True, key="cc_nota_guardar"):
            if nota_input.strip():
                cc_codigo = opciones_nota.get(cc_nota_sel, cc_nota_sel)
                guardar_nota(
                    periodo_desde, periodo_hasta, sociedad_sel,
                    "CC", cc_codigo, nota_input.strip(), _usuario,
                )
                st.success(f"✓ Nota guardada para {cc_nota_sel}")
                st.rerun()
            else:
                st.warning("Escribe una nota antes de guardar.")

with col_notas_cc:
    st.markdown("**Notas registradas en este período**")
    if _notas_cc.empty:
        st.markdown(
            "<div style='color:#aaa; font-size:13px; padding:12px 0;'>Sin notas para este período.</div>",
            unsafe_allow_html=True,
        )
    else:
        for _, nr in _notas_cc.iterrows():
            nombre_ref = NOMBRES_CC.get(nr["referencia"], nr["referencia"])
            fecha_fmt  = pd.Timestamp(nr["actualizado_en"]).strftime("%d/%m %H:%M") if pd.notna(nr["actualizado_en"]) else ""
            col_nota_txt, col_nota_del = st.columns([10, 1])
            with col_nota_txt:
                st.markdown(f"""
                <div style="background:#fafafa; border:1px solid #e2e8f0;
                            border-left:4px solid #c4007a; border-radius:8px;
                            padding:10px 14px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                        <span style="font-size:12px; font-weight:700; color:#2d0050;">{nombre_ref}</span>
                        <span style="font-size:10px; color:#aaa;">{nr['creado_por']} · {fecha_fmt}</span>
                    </div>
                    <div style="font-size:12px; color:#444; line-height:1.5;">{nr['nota']}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_nota_del:
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                if st.button("🗑", key=f"del_nota_cc_{nr['id']}", help="Eliminar esta nota"):
                    eliminar_nota(int(nr["id"]))
                    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# ── ANÁLISIS IA ────────────────────────────────────────────────
st.markdown("##### Análisis IA")

if "cc_analisis_texto" not in st.session_state:
    st.session_state["cc_analisis_texto"] = ""

col_ia_cc, col_cerrar_cc, _ = st.columns([2, 1, 2])

with col_ia_cc:
    generar_cc = st.button("Generar Análisis con IA", type="primary", key="btn_ia_cc", use_container_width=True)

if generar_cc:
    centros = [
        {"nombre": NOMBRES_CC.get(r["codigo_cc"], r["nombre_cc"]),
         "real": float(r["real"]), "ppto": float(r["ppto"])}
        for _, r in df_cc.iterrows()
    ]
    datos_ia = {
        "sociedad":      sociedad_sel,
        "periodo_desde": periodo_desde,
        "periodo_hasta": periodo_hasta,
        "centros":       centros,
    }
    with st.spinner("Analizando datos con IA..."):
        st.session_state["cc_analisis_texto"] = generar_analisis_cc(datos_ia)
        st.session_state["cc_analisis_datos"] = datos_ia

if st.session_state["cc_analisis_texto"]:
    with col_cerrar_cc:
        if st.button("✕ Cerrar", use_container_width=True, key="cc_cerrar"):
            st.session_state["cc_analisis_texto"] = ""
            st.rerun()

if st.session_state["cc_analisis_texto"]:
    st.markdown(f"""
    <div style="background:#fafafa; border:1px solid #e2e8f0; border-left:4px solid #2d0050;
                border-radius:8px; padding:20px 24px; margin-top:12px;
                font-size:13px; line-height:1.8; color:#333; white-space:pre-wrap;">
{st.session_state["cc_analisis_texto"]}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**Guardar este análisis**")
        col_input, col_save = st.columns([4, 1])
        with col_input:
            titulo_cc = st.text_input(
                "Título",
                value=f"CC {periodo_desde} – {periodo_hasta} · {sociedad_sel}",
                label_visibility="collapsed",
                key="cc_titulo_rpt",
            )
        with col_save:
            if st.button("Guardar", type="primary", use_container_width=True, key="cc_guardar_btn"):
                try:
                    from sqlalchemy import text as sqlt
                    from utils.db import get_engine
                    datos_snap = st.session_state.get("cc_analisis_datos", {})
                    with get_engine().begin() as conn:
                        conn.execute(sqlt("""
                            INSERT INTO reports.reportes_guardados
                                (titulo, tipo, periodo_desde, periodo_hasta,
                                 sociedad, datos_json, analisis_ia, creado_por)
                            VALUES
                                (:titulo, 'CC', :pdesde, :phasta,
                                 :sociedad, :datos, :analisis, :usuario)
                        """), {
                            "titulo":   titulo_cc,
                            "pdesde":   periodo_desde,
                            "phasta":   periodo_hasta,
                            "sociedad": sociedad_sel,
                            "datos":    json.dumps(datos_snap),
                            "analisis": st.session_state["cc_analisis_texto"],
                            "usuario":  st.session_state.get("nombre", ""),
                        })
                    st.success("✓ Reporte guardado. Ve a **Reportes Guardados** para revisarlo.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
