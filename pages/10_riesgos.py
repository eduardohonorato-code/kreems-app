"""
Gestión de Riesgos y Oportunidades
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from utils.auth import login
from utils.components import header, sidebar_kreems, ANO_FISCAL, MESES, MES_NUM_ACTUAL
from utils.ai import generar_analisis_riesgos
from utils.riesgos import (
    obtener_riesgos, guardar_riesgo, actualizar_riesgo, eliminar_riesgo,
    PROB_NUM, IMPACT_NUM, CATEGORIAS, PROBABILIDADES, IMPACTOS, ESTADOS, ESTADOS_LABEL,
)

st.set_page_config(
    page_title="Riesgos y Oportunidades · Kreems",
    page_icon="💜",
    layout="wide",
)

if not login():
    st.stop()

sociedad_sel, _ = sidebar_kreems(mostrar_sociedad=True)
header("Gestión de Riesgos y Oportunidades")

_usuario = st.session_state.get("nombre", "")

# ── Selector de período de referencia ────────────────────────
# Riesgos son prospectivos: se muestran todos los meses del año,
# incluyendo futuros (ej. registrar un riesgo para julio desde mayo).
meses_lista = list(MESES.items())          # 12 meses sin filtro
meses_nombres = [nom for _, nom in meses_lista]
mes_default_idx = MES_NUM_ACTUAL - 1      # posiciona en el mes actual

col_per, col_sp = st.columns([2, 4])
with col_per:
    mes_ref = st.selectbox(
        "Período de referencia",
        meses_nombres,
        index=mes_default_idx,
        key="rio_mes",
    )
mes_num = next(n for n, nom in MESES.items() if nom == mes_ref)
periodo_ref = f"{ANO_FISCAL}-{mes_num:02d}"

filtro_soc = sociedad_sel if sociedad_sel != "Todas" else "Todas"
df_rio = obtener_riesgos(periodo_ref, filtro_soc)

# ── Métricas ──────────────────────────────────────────────────
df_abiertos  = df_rio[df_rio["estado"].isin(["ABIERTO", "EN_GESTION"])]
df_riesgos   = df_abiertos[df_abiertos["tipo"] == "RIESGO"]
df_oport     = df_abiertos[df_abiertos["tipo"] == "OPORTUNIDAD"]

exposicion   = df_riesgos["impacto_monto"].fillna(0).sum()
upside       = df_oport["impacto_monto"].fillna(0).sum()
balance_neto = upside - exposicion

c1, c2, c3, c4, c5 = st.columns(5)
_card = lambda col, lbl, val, color: col.markdown(f"""
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;
            padding:14px 18px;text-align:center;height:100%;">
    <div style="font-size:11px;color:#999;margin-bottom:4px;">{lbl}</div>
    <div style="font-size:24px;font-weight:700;color:{color};">{val}</div>
</div>""", unsafe_allow_html=True)

_card(c1, "Riesgos activos",       len(df_riesgos),    "#cc0000")
_card(c2, "Oportunidades activas", len(df_oport),       "#0F6E56")
_card(c3, "Exposición total",
    f"${exposicion/1_000_000:,.1f}M" if exposicion else "—",    "#cc0000")
_card(c4, "Potencial upside",
    f"${upside/1_000_000:,.1f}M" if upside else "—",            "#0F6E56")
_card(c5, "Balance neto",
    f"${balance_neto/1_000_000:,.1f}M" if (exposicion or upside) else "—",
    "#0F6E56" if balance_neto >= 0 else "#cc0000")

st.markdown("<br>", unsafe_allow_html=True)

# ── TABS ──────────────────────────────────────────────────────
tab_hm, tab_lista, tab_ia, tab_nuevo = st.tabs([
    "🗺️  Heat Map",
    "📋  Registro",
    "🤖  Análisis IA",
    "➕  Nuevo",
])

# ╔══════════════════════════════════════════╗
# ║  TAB 1 — HEAT MAP                        ║
# ╚══════════════════════════════════════════╝
with tab_hm:
    st.markdown("##### Mapa de Riesgos y Oportunidades")
    st.caption(
        "Posición según probabilidad × impacto. "
        "El tamaño del punto representa el monto estimado. "
        "🔴 Riesgos · 🟢 Oportunidades"
    )

    # Fondo del heat map: 9 zonas de color
    fig_hm = go.Figure()

    # Zonas de color (bajo=1, medio=2, alto=3 en x=prob, y=impacto)
    _zonas = [
        # (x0, x1, y0, y1, color, label)
        (0.5, 1.5, 0.5, 1.5, "rgba(200,230,200,0.35)", "Bajo"),
        (1.5, 2.5, 0.5, 1.5, "rgba(255,235,180,0.35)", ""),
        (2.5, 3.5, 0.5, 1.5, "rgba(255,200,180,0.35)", ""),
        (0.5, 1.5, 1.5, 2.5, "rgba(255,235,180,0.35)", ""),
        (1.5, 2.5, 1.5, 2.5, "rgba(255,220,140,0.35)", "Moderado"),
        (2.5, 3.5, 1.5, 2.5, "rgba(255,150,130,0.35)", ""),
        (0.5, 1.5, 2.5, 3.5, "rgba(255,200,180,0.35)", ""),
        (1.5, 2.5, 2.5, 3.5, "rgba(255,150,130,0.35)", ""),
        (2.5, 3.5, 2.5, 3.5, "rgba(220,60,60,0.22)",   "Crítico"),
    ]
    for x0, x1, y0, y1, color, lbl in _zonas:
        fig_hm.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                         fillcolor=color, line_width=0, layer="below")
        if lbl:
            fig_hm.add_annotation(
                x=(x0+x1)/2, y=(y0+y1)/2, text=lbl,
                showarrow=False, font=dict(size=9, color="#aaa"),
            )

    if not df_abiertos.empty:
        for tipo, color, symbol in [
            ("RIESGO",      "#cc0000", "circle"),
            ("OPORTUNIDAD", "#0F6E56", "diamond"),
        ]:
            df_t = df_abiertos[df_abiertos["tipo"] == tipo].copy()
            if df_t.empty:
                continue
            df_t["px"] = df_t["probabilidad"].map(PROB_NUM)
            df_t["py"] = df_t["impacto_nivel"].map(IMPACT_NUM)
            monto_max = df_t["impacto_monto"].fillna(0).max() or 1
            df_t["sz"] = (df_t["impacto_monto"].fillna(0) / monto_max * 30 + 12).clip(12, 42)
            df_t["hover"] = df_t.apply(lambda r: (
                f"<b>{r['nombre']}</b><br>"
                f"Categoría: {r['categoria']}<br>"
                f"Prob: {r['probabilidad']} · Impacto: {r['impacto_nivel']}<br>"
                f"Monto: {'${:,.0f}'.format(r['impacto_monto']) if pd.notna(r['impacto_monto']) else 'N/D'}<br>"
                f"Estado: {ESTADOS_LABEL.get(r['estado'], r['estado'])}<br>"
                f"Resp.: {r['responsable'] or '—'}"
            ), axis=1)

            # Agregar jitter pequeño para separar puntos superpuestos
            import random, hashlib
            def jitter(s):
                h = int(hashlib.md5(str(s).encode()).hexdigest()[:4], 16)
                return (h % 20 - 10) / 100
            df_t["jx"] = df_t["nombre"].apply(jitter)
            df_t["jy"] = df_t["descripcion"].apply(jitter)

            fig_hm.add_trace(go.Scatter(
                x=df_t["px"] + df_t["jx"],
                y=df_t["py"] + df_t["jy"],
                mode="markers+text",
                marker=dict(
                    size=df_t["sz"], color=color,
                    symbol=symbol, opacity=0.82,
                    line=dict(color="white", width=1.5),
                ),
                text=df_t["nombre"].apply(lambda n: n[:18] + "…" if len(n) > 18 else n),
                textposition="top center",
                textfont=dict(size=9, color="#444"),
                hovertemplate=df_t["hover"] + "<extra></extra>",
                name="Riesgos" if tipo == "RIESGO" else "Oportunidades",
            ))
    else:
        fig_hm.add_annotation(
            x=2, y=2, text="Sin registros activos para este período",
            showarrow=False, font=dict(size=13, color="#aaa"),
        )

    fig_hm.update_layout(
        height=420,
        margin=dict(t=20, b=60, l=60, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            range=[0.5, 3.5], tickvals=[1, 2, 3],
            ticktext=["Baja", "Media", "Alta"],
            title="Probabilidad", title_font=dict(size=11, color="#888"),
            showgrid=False, zeroline=False,
        ),
        yaxis=dict(
            range=[0.5, 3.5], tickvals=[1, 2, 3],
            ticktext=["Bajo", "Medio", "Alto"],
            title="Impacto", title_font=dict(size=11, color="#888"),
            showgrid=False, zeroline=False,
        ),
        legend=dict(orientation="h", y=-0.15, x=0.3),
        font=dict(family="Inter, Arial, sans-serif", size=11, color="#555"),
    )
    col_hm, col_imp = st.columns([3, 2])
    with col_hm:
        st.plotly_chart(fig_hm, use_container_width=True)

    with col_imp:
        st.markdown("**Impacto potencial en Utilidad Neta**")
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # Escenarios: pesimista, base, optimista
        # Pesimista: todos los riesgos se materializan, 0 oportunidades
        # Base: 50% prob-ponderado de cada item
        # Optimista: todos los riesgos evitados, todas las oportunidades
        def pct_prob(p): return {"ALTA": 0.75, "MEDIA": 0.45, "BAJA": 0.20}.get(p, 0.5)

        exp_pesi = -exposicion
        exp_base = sum(
            -r["impacto_monto"] * pct_prob(r["probabilidad"])
            for _, r in df_riesgos.iterrows() if pd.notna(r["impacto_monto"])
        ) + sum(
            r["impacto_monto"] * pct_prob(r["probabilidad"])
            for _, r in df_oport.iterrows() if pd.notna(r["impacto_monto"])
        )
        exp_opti = upside

        scenarios = [
            ("Pesimista", exp_pesi, "#cc0000"),
            ("Base (prob. pond.)", exp_base, "#d97706"),
            ("Optimista", exp_opti, "#0F6E56"),
        ]
        for label, val, color in scenarios:
            signo = "+" if val >= 0 else ""
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center;
                        padding:10px 14px; margin-bottom:6px;
                        background:{'rgba(15,110,86,0.06)' if val >= 0 else 'rgba(204,0,0,0.06)'};
                        border-radius:8px; border-left:3px solid {color};">
                <div style="font-size:12px; font-weight:600; color:#444;">{label}</div>
                <div style="font-size:15px; font-weight:700; color:{color};">
                    {signo}${abs(val)/1_000_000:,.2f}M
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.caption("Los escenarios muestran el impacto acumulado estimado sobre la Utilidad Neta del período.")

        # Distribución por categoría
        if not df_abiertos.empty:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.markdown("**Por categoría**")
            cat_counts = df_abiertos.groupby(["categoria","tipo"]).size().unstack(fill_value=0)
            for cat in cat_counts.index:
                n_r = int(cat_counts.loc[cat, "RIESGO"]) if "RIESGO" in cat_counts.columns else 0
                n_o = int(cat_counts.loc[cat, "OPORTUNIDAD"]) if "OPORTUNIDAD" in cat_counts.columns else 0
                badges = ""
                if n_r:
                    badges += f'<span style="color:#cc0000;font-weight:600;margin-right:4px;">{n_r}R</span>'
                if n_o:
                    badges += f'<span style="color:#0F6E56;font-weight:600;">{n_o}O</span>'
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                    f'font-size:12px;border-bottom:0.5px solid #f0f0f0;">'
                    f'<span style="color:#555;">{cat.capitalize()}</span>'
                    f'<div style="display:flex;gap:2px;">{badges}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ╔══════════════════════════════════════════╗
# ║  TAB 2 — REGISTRO                        ║
# ╚══════════════════════════════════════════╝
with tab_lista:
    st.markdown("##### Registro Completo")

    if df_rio.empty:
        st.info("No hay registros para este período. Ve a '➕ Nuevo' para agregar el primero.")
    else:
        # Filtros
        col_tf, col_cf, col_ef = st.columns([1, 1, 1])
        with col_tf:
            tipo_fil = st.selectbox("Tipo", ["Todos","RIESGO","OPORTUNIDAD"], key="rio_tf")
        with col_cf:
            cat_fil = st.selectbox("Categoría", ["Todas"] + CATEGORIAS, key="rio_cf")
        with col_ef:
            est_fil = st.selectbox("Estado", ["Todos"] + ESTADOS, key="rio_ef")

        df_fil = df_rio.copy()
        if tipo_fil != "Todos":   df_fil = df_fil[df_fil["tipo"] == tipo_fil]
        if cat_fil  != "Todas":  df_fil = df_fil[df_fil["categoria"] == cat_fil]
        if est_fil  != "Todos":  df_fil = df_fil[df_fil["estado"] == est_fil]

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        for _, row in df_fil.iterrows():
            rid         = int(row["id"])
            es_r        = row["tipo"] == "RIESGO"
            color_borde = "#cc0000" if es_r else "#0F6E56"
            color_bg    = "rgba(204,0,0,0.04)" if es_r else "rgba(15,110,86,0.04)"
            tipo_pill   = ("RIESGO" if es_r else "OPRTD.")
            pill_bg     = "rgba(204,0,0,0.12)" if es_r else "rgba(15,110,86,0.12)"
            monto_txt   = f"${row['impacto_monto']/1_000_000:,.2f}M" if pd.notna(row["impacto_monto"]) else "N/D"
            estado_txt  = ESTADOS_LABEL.get(row["estado"], row["estado"])
            vcto_txt    = pd.Timestamp(row["fecha_vcto"]).strftime("%d/%m/%Y") if pd.notna(row.get("fecha_vcto")) else "—"
            toggle_key  = f"rio_show_{rid}"
            if toggle_key not in st.session_state:
                st.session_state[toggle_key] = False

            with st.container(border=True):
                # ── Encabezado ──
                col_hdr, col_btn = st.columns([6, 1])
                with col_hdr:
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:10px;padding:2px 0;'>"
                        f"<span style='background:{pill_bg};color:{color_borde};font-size:10px;"
                        f"font-weight:700;padding:2px 8px;border-radius:4px;letter-spacing:.5px;'>"
                        f"{tipo_pill}</span>"
                        f"<span style='font-weight:600;font-size:14px;color:#0F172A;'>{row['nombre']}</span>"
                        f"<span style='font-size:12px;color:#94A3B8;'>· {row['categoria']} · {estado_txt}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    lbl_toggle = "▲ Cerrar" if st.session_state[toggle_key] else "▼ Ver"
                    if st.button(lbl_toggle, key=f"tog_{rid}", use_container_width=True):
                        st.session_state[toggle_key] = not st.session_state[toggle_key]
                        st.rerun()

                # ── Detalle (colapsable) ──
                if st.session_state[toggle_key]:
                    col_info, col_accion = st.columns([3, 1])

                    with col_info:
                        st.markdown(f"""
                        <div style="background:{color_bg}; border-left:3px solid {color_borde};
                                    border-radius:6px; padding:12px 16px; margin-top:8px;">
                            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:8px;">
                                <div>
                                    <div style="font-size:10px;color:#aaa;">Probabilidad</div>
                                    <div style="font-size:13px;font-weight:600;color:#333;">{row['probabilidad']}</div>
                                </div>
                                <div>
                                    <div style="font-size:10px;color:#aaa;">Impacto</div>
                                    <div style="font-size:13px;font-weight:600;color:#333;">{row['impacto_nivel']}</div>
                                </div>
                                <div>
                                    <div style="font-size:10px;color:#aaa;">Monto estimado</div>
                                    <div style="font-size:13px;font-weight:600;color:{color_borde};">{monto_txt}</div>
                                </div>
                                <div>
                                    <div style="font-size:10px;color:#aaa;">Responsable</div>
                                    <div style="font-size:13px;color:#333;">{row['responsable'] or '—'}</div>
                                </div>
                                <div>
                                    <div style="font-size:10px;color:#aaa;">Vencimiento</div>
                                    <div style="font-size:13px;color:#333;">{vcto_txt}</div>
                                </div>
                                <div>
                                    <div style="font-size:10px;color:#aaa;">Creado por</div>
                                    <div style="font-size:13px;color:#333;">{row['creado_por'] or '—'}</div>
                                </div>
                            </div>
                            {f'<div style="font-size:12px;color:#555;margin-top:6px;"><b>Descripción:</b> {row["descripcion"]}</div>' if row.get("descripcion") else ''}
                            {f'<div style="font-size:12px;color:#555;margin-top:4px;"><b>Plan de acción:</b> {row["plan_accion"]}</div>' if row.get("plan_accion") else ''}
                        </div>
                        """, unsafe_allow_html=True)

                    with col_accion:
                        nuevo_estado = st.selectbox(
                            "Cambiar estado",
                            ESTADOS,
                            index=ESTADOS.index(row["estado"]),
                            key=f"est_{rid}",
                        )
                        if st.button("💾 Actualizar", key=f"upd_{rid}", use_container_width=True):
                            actualizar_riesgo(rid, {
                                "tipo":          row["tipo"],
                                "categoria":     row["categoria"],
                                "nombre":        row["nombre"],
                                "descripcion":   row["descripcion"],
                                "probabilidad":  row["probabilidad"],
                                "impacto_nivel": row["impacto_nivel"],
                                "impacto_monto": float(row["impacto_monto"]) if pd.notna(row["impacto_monto"]) else None,
                                "estado":        nuevo_estado,
                                "responsable":   row["responsable"],
                                "plan_accion":   row["plan_accion"],
                                "fecha_vcto":    row["fecha_vcto"],
                            })
                            st.success("✓ Estado actualizado")
                            st.rerun()

                        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                        if st.button("🗑 Eliminar", key=f"del_{rid}", use_container_width=True):
                            eliminar_riesgo(rid)
                            st.rerun()

            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)


# ╔══════════════════════════════════════════╗
# ║  TAB 3 — ANÁLISIS IA                     ║
# ╚══════════════════════════════════════════╝
with tab_ia:

    st.markdown("##### Análisis FP&A del Portafolio de Riesgos")
    st.markdown(
        "<p style='font-size:13px;color:#888;margin-bottom:16px;'>"
        "El modelo analiza el portafolio completo — exposición financiera, valor esperado ajustado "
        "por probabilidad, escenarios de impacto en Utilidad Neta y señales de alerta temprana. "
        "Diseñado para presentación a CFO y Gerencia General."
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Resumen del portafolio actual ────────────────────────────
    col_res1, col_res2, col_res3, col_res4 = st.columns(4)
    PROB_PCT_IA = {"ALTA": 0.75, "MEDIA": 0.45, "BAJA": 0.20}

    ve_r_ia = sum(
        (r["impacto_monto"] or 0) * PROB_PCT_IA.get(r["probabilidad"], 0.45)
        for _, r in df_riesgos.iterrows() if pd.notna(r["impacto_monto"])
    )
    ve_o_ia = sum(
        (o["impacto_monto"] or 0) * PROB_PCT_IA.get(o["probabilidad"], 0.45)
        for _, o in df_oport.iterrows() if pd.notna(o["impacto_monto"])
    )
    ve_neto_ia = ve_o_ia - ve_r_ia

    def _kpi_ia(col, lbl, val, color, fmt_fn):
        col.markdown(f"""
        <div style="background:#fff;border:1px solid #e2e8f0;border-left:3px solid {color};
                    border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="font-size:10px;color:#999;margin-bottom:3px;">{lbl}</div>
            <div style="font-size:17px;font-weight:700;color:{color};">{fmt_fn(val)}</div>
        </div>""", unsafe_allow_html=True)

    _kpi_ia(col_res1, "Exposición total",     exposicion,  "#cc0000",
            lambda v: f"${v/1e6:,.1f}M" if v else "—")
    _kpi_ia(col_res2, "VE riesgos (pond.)",   ve_r_ia,     "#d97706",
            lambda v: f"-${v/1e6:,.1f}M" if v else "—")
    _kpi_ia(col_res3, "VE oportunidades (pond.)", ve_o_ia, "#0F6E56",
            lambda v: f"+${v/1e6:,.1f}M" if v else "—")
    color_ve = "#0F6E56" if ve_neto_ia >= 0 else "#cc0000"
    _kpi_ia(col_res4, "VE neto portafolio",   abs(ve_neto_ia), color_ve,
            lambda v: f"{'+'  if ve_neto_ia >= 0 else '-'}${v/1e6:,.1f}M" if v else "—")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Botón generar ────────────────────────────────────────────
    cache_key = f"rio_ia_{periodo_ref}_{filtro_soc}"

    col_btn_ia, col_info_ia = st.columns([2, 4])
    with col_btn_ia:
        btn_ia = st.button(
            "🤖 Generar análisis FP&A",
            use_container_width=True,
            type="primary",
            disabled=df_abiertos.empty,
        )
    with col_info_ia:
        if df_abiertos.empty:
            st.warning("No hay riesgos u oportunidades activos para el período seleccionado.")
        else:
            st.markdown(
                f"<div style='padding-top:8px;font-size:12px;color:#888;'>"
                f"Analizará {len(df_riesgos)} riesgo(s) y {len(df_oport)} oportunidad(es) "
                f"registrados para <b>{mes_ref} {ANO_FISCAL}</b> — {filtro_soc}."
                f"</div>",
                unsafe_allow_html=True,
            )

    if btn_ia and not df_abiertos.empty:
        # Construir payload completo
        def _row_to_dict(r):
            return {
                "nombre":        r.get("nombre", ""),
                "categoria":     r.get("categoria", ""),
                "probabilidad":  r.get("probabilidad", "MEDIA"),
                "impacto_nivel": r.get("impacto_nivel", "MEDIO"),
                "impacto_monto": float(r["impacto_monto"]) if pd.notna(r.get("impacto_monto")) else 0,
                "descripcion":   r.get("descripcion") or "",
                "plan_accion":   r.get("plan_accion") or "",
                "responsable":   r.get("responsable") or "",
                "fecha_vcto":    str(r["fecha_vcto"]) if pd.notna(r.get("fecha_vcto")) else "",
            }

        payload = {
            "periodo":          periodo_ref,
            "sociedad":         filtro_soc,
            "n_riesgos":        len(df_riesgos),
            "n_oportunidades":  len(df_oport),
            "exposicion_total": float(exposicion),
            "upside_total":     float(upside),
            "balance_neto":     float(balance_neto),
            "riesgos":          [_row_to_dict(r) for _, r in df_riesgos.iterrows()],
            "oportunidades":    [_row_to_dict(o) for _, o in df_oport.iterrows()],
        }

        with st.spinner("Generando análisis FP&A del portafolio... (puede tardar 10-15 s)"):
            analisis_ia = generar_analisis_riesgos(payload)
        st.session_state[cache_key] = analisis_ia

    analisis_ia_txt = st.session_state.get(cache_key, "")

    # ── Mostrar análisis ─────────────────────────────────────────
    if analisis_ia_txt:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Parsear secciones para renderizado visual
        SECCIONES = [
            ("POSICIÓN DE RIESGO DEL PERÍODO",        "#2d0050", "📌"),
            ("RIESGOS CRÍTICOS",                       "#cc0000", "🔴"),
            ("OPORTUNIDADES DE CAPTURA",               "#0F6E56", "🟢"),
            ("ANÁLISIS DE ESCENARIOS",                 "#1e40af", "📊"),
            ("SEÑALES DE ALERTA TEMPRANA",             "#d97706", "⚠️"),
            ("RECOMENDACIONES EJECUTIVAS",             "#2d0050", "✅"),
        ]

        bloques = analisis_ia_txt.split("\n\n")
        texto_restante = analisis_ia_txt

        for titulo_sec, color_sec, icono_sec in SECCIONES:
            # Buscar si la sección existe en el texto
            idx = analisis_ia_txt.upper().find(titulo_sec.upper())
            if idx == -1:
                continue

            # Extraer contenido hasta la siguiente sección conocida
            start = idx + len(titulo_sec)
            # Saltar posible separador/newline
            while start < len(analisis_ia_txt) and analisis_ia_txt[start] in "\n\r: ":
                start += 1

            end = len(analisis_ia_txt)
            for otro_titulo, _, _ in SECCIONES:
                if otro_titulo == titulo_sec:
                    continue
                idx2 = analisis_ia_txt.upper().find(otro_titulo.upper(), start)
                if idx2 != -1 and idx2 < end:
                    end = idx2

            contenido = analisis_ia_txt[start:end].strip()
            if not contenido:
                continue

            # Renderizar sección
            st.markdown(f"""
            <div style="margin-bottom:12px;border-radius:10px;overflow:hidden;
                        border:1px solid #E2E8F0;">
                <div style="background:{color_sec};padding:8px 16px;
                            display:flex;align-items:center;gap:8px;">
                    <span style="font-size:14px;">{icono_sec}</span>
                    <span style="color:#fff;font-size:12px;font-weight:700;
                                 letter-spacing:.5px;text-transform:uppercase;">{titulo_sec}</span>
                </div>
                <div style="padding:14px 18px;background:#FAFAFA;
                            font-size:13px;line-height:1.8;color:#1e293b;
                            white-space:pre-wrap;">{contenido}</div>
            </div>""", unsafe_allow_html=True)

        # Botón guardar en Reportes IA
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        col_sv1, col_sv2 = st.columns([2, 4])
        with col_sv1:
            if st.button("💾 Guardar en Reportes IA", use_container_width=True):
                try:
                    from sqlalchemy import text as sqlt
                    from utils.db import get_engine
                    import json as _json
                    titulo_rpt = f"Riesgos y Oportunidades — {mes_ref} {ANO_FISCAL} — {filtro_soc}"
                    datos_json = _json.dumps({
                        "n_riesgos":    len(df_riesgos),
                        "n_oport":      len(df_oport),
                        "exposicion":   float(exposicion),
                        "upside":       float(upside),
                        "ve_neto":      float(ve_neto_ia),
                    })
                    with get_engine().begin() as conn:
                        conn.execute(sqlt("""
                            INSERT INTO reports.reportes_guardados
                                (titulo, tipo, periodo_desde, periodo_hasta,
                                 sociedad, datos_json, analisis_ia, creado_por)
                            VALUES
                                (:titulo, 'RIESGOS', :desde, :hasta,
                                 :soc, :datos, :analisis, :usr)
                        """), {
                            "titulo":   titulo_rpt,
                            "desde":    periodo_ref,
                            "hasta":    periodo_ref,
                            "soc":      filtro_soc,
                            "datos":    datos_json,
                            "analisis": analisis_ia_txt,
                            "usr":      _usuario,
                        })
                    st.success("✓ Análisis guardado en Reportes IA.")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")


# ╔══════════════════════════════════════════╗
# ║  TAB 4 — NUEVO REGISTRO                  ║
# ╚══════════════════════════════════════════╝
with tab_nuevo:
    st.markdown("##### Registrar Riesgo u Oportunidad")

    with st.form("form_nuevo_rio", clear_on_submit=True):
        col_tipo, col_cat = st.columns(2)
        with col_tipo:
            tipo_nuevo  = st.radio("Tipo", ["RIESGO", "OPORTUNIDAD"], horizontal=True)
        with col_cat:
            cat_nuevo   = st.selectbox("Categoría", CATEGORIAS)

        nombre_nuevo = st.text_input("Nombre *", placeholder="Ej: Caída de demanda en temporada alta")
        desc_nuevo   = st.text_area("Descripción", placeholder="Detalla el contexto y causas...", height=80)

        col_p, col_i, col_m = st.columns(3)
        with col_p:
            prob_nuevo   = st.selectbox("Probabilidad *", PROBABILIDADES)
        with col_i:
            imp_nuevo    = st.selectbox("Nivel de Impacto *", IMPACTOS)
        with col_m:
            monto_nuevo  = st.number_input(
                "Monto estimado ($)", min_value=0.0, step=1_000_000.0,
                format="%.0f", help="Impacto económico estimado en pesos"
            )

        col_resp, col_vcto = st.columns(2)
        with col_resp:
            resp_nuevo  = st.text_input("Responsable", placeholder="Nombre del responsable")
        with col_vcto:
            vcto_nuevo  = st.date_input(
                "Fecha de vencimiento",
                value=None,
                min_value=date.today(),
            )

        plan_nuevo = st.text_area("Plan de acción / Mitigación", height=80,
                                  placeholder="Describe las acciones a tomar...")

        est_nuevo  = st.selectbox("Estado inicial", ESTADOS, index=0)

        submitted = st.form_submit_button("➕ Registrar", type="primary", use_container_width=True)

    if submitted:
        if not nombre_nuevo.strip():
            st.warning("El nombre es obligatorio.")
        else:
            guardar_riesgo({
                "periodo_ref":   periodo_ref,
                "sociedad":      filtro_soc,
                "tipo":          tipo_nuevo,
                "categoria":     cat_nuevo,
                "nombre":        nombre_nuevo.strip(),
                "descripcion":   desc_nuevo.strip() or None,
                "probabilidad":  prob_nuevo,
                "impacto_nivel": imp_nuevo,
                "impacto_monto": monto_nuevo if monto_nuevo > 0 else None,
                "estado":        est_nuevo,
                "responsable":   resp_nuevo.strip() or None,
                "plan_accion":   plan_nuevo.strip() or None,
                "fecha_vcto":    vcto_nuevo if vcto_nuevo else None,
                "creado_por":    _usuario,
            })
            st.success(f"✓ {'Riesgo' if tipo_nuevo == 'RIESGO' else 'Oportunidad'} registrado correctamente.")
            st.rerun()
