"""
Componentes reutilizables para todas las páginas.
"""
import streamlit as st
import base64
import os
from datetime import date

FONT_FAMILY = "Inter, sans-serif"

# ── FUENTE GLOBAL ─────────────────────────────────────────────

def inject_font():
    """Inyecta Inter desde Google Fonts como fuente global de la app."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

        html, body, [class*="css"], [class*="st-"],
        .stMarkdown, .stText, .stDataFrame,
        button, input, select, textarea,
        h1, h2, h3, h4, h5, h6, p, span, div, label {
            font-family: 'Inter', sans-serif !important;
            font-variant-ligatures: none !important;
            font-feature-settings: "liga" 0, "clig" 0 !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ── LOGO ──────────────────────────────────────────────────────

@st.cache_data
def _logo_b64() -> str | None:
    """Carga el logo como base64. Retorna None si no existe el archivo."""
    logo_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
    )
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


def _logo_html(altura: int = 40) -> str:
    """Retorna el HTML del logo: imagen si existe, texto de fallback si no."""
    b64 = _logo_b64()
    if b64:
        return f"<img src='data:image/png;base64,{b64}' style='height:{altura}px;'/>"
    # Fallback: texto estilizado
    return "<span style='color:#c4007a; font-size:2rem; font-weight:800; letter-spacing:-1px;'>kreems</span>"

MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

MESES_PERIODOS = {
    "Enero": "2026-01", "Febrero": "2026-02", "Marzo": "2026-03",
    "Abril": "2026-04", "Mayo": "2026-05", "Junio": "2026-06",
    "Julio": "2026-07", "Agosto": "2026-08", "Septiembre": "2026-09",
    "Octubre": "2026-10", "Noviembre": "2026-11", "Diciembre": "2026-12"
}

# Mes actual del sistema (para labels CERRADO / ACTUAL / PROYECTADO)
_HOY = date.today()
MES_NUM_ACTUAL = _HOY.month  # 5 en mayo 2026


def _estado_mes(num: int) -> tuple[str, str, str]:
    """Retorna (label, color, icono) según el estado del mes."""
    if num < MES_NUM_ACTUAL:
        return ("CERRADO", "#0F6E56", "✓")
    elif num == MES_NUM_ACTUAL:
        return ("ACTUAL", "#c4007a", "●")
    else:
        return ("PROYEC.", "#aaa", "◌")


# ── HEADER ────────────────────────────────────────────────────

def header(titulo: str):
    """Header con logo Kreems y título de página."""
    inject_font()
    st.markdown(f"""
    <div style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: linear-gradient(90deg, #fff 0%, #fdf5fb 100%);
        border-bottom: 2px solid #f0c0e0;
        padding: 12px 24px;
        margin: -1rem -1rem 1.5rem -1rem;
    ">
        {_logo_html(altura=42)}
        <span style="color:#2d0050; font-size:1.3rem; font-weight:600;">{titulo}</span>
        <span style="color:#bbb; font-size:12px;">Control Presupuestario 2026</span>
    </div>
    """, unsafe_allow_html=True)


# ── SELECTOR MESES ────────────────────────────────────────────

def selector_meses(key: str = "mes", default: str = "Mayo") -> tuple:
    """
    Selector de meses con etiquetas CERRADO / ACTUAL / PROYECTADO.
    Retorna (periodo_desde, periodo_hasta) en formato 'YYYY-MM'.
    """
    if f"mes_{key}" not in st.session_state:
        st.session_state[f"mes_{key}"] = default

    mes_actual = st.session_state[f"mes_{key}"]

    # CSS botones compactos
    st.markdown("""
    <style>
        div[data-testid="column"] button {
            width: 100% !important;
            padding: 4px 2px !important;
            font-size: 10px !important;
            white-space: nowrap !important;
            overflow: hidden !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # Fila de etiquetas de estado
    col_lbl_ytd, *cols_lbl = st.columns([0.8] + [1] * 12)
    with col_lbl_ytd:
        st.markdown(
            "<div style='font-size:8px; color:#aaa; text-align:center; "
            "font-weight:700; letter-spacing:0.5px; padding-bottom:1px;'>ACUM.</div>",
            unsafe_allow_html=True
        )
    for i, (num, _) in enumerate(MESES.items()):
        lbl, color, icono = _estado_mes(num)
        with cols_lbl[i]:
            st.markdown(
                f"<div style='font-size:8px; color:{color}; text-align:center; "
                f"font-weight:700; letter-spacing:0.3px; padding-bottom:1px;'>"
                f"{icono} {lbl}</div>",
                unsafe_allow_html=True
            )

    # Fila de botones
    col_ytd, *cols_meses = st.columns([0.8] + [1] * 12)
    with col_ytd:
        if st.button(
            "YTD",
            key=f"btn_mes_{key}_ytd",
            type="primary" if mes_actual == "YTD" else "secondary",
            use_container_width=True
        ):
            st.session_state[f"mes_{key}"] = "YTD"
            st.rerun()

    for i, (num, nombre) in enumerate(MESES.items()):
        with cols_meses[i]:
            if st.button(
                nombre[:3],
                key=f"btn_mes_{key}_{num}",
                type="primary" if nombre == mes_actual else "secondary",
                use_container_width=True
            ):
                st.session_state[f"mes_{key}"] = nombre
                st.rerun()

    if mes_actual == "YTD":
        return ("2026-01", "2026-12")
    else:
        p = MESES_PERIODOS[mes_actual]
        return (p, p)


# ── KPI CARD ──────────────────────────────────────────────────

def kpi_card(label: str, valor: float, referencia: float = None,
             prefijo: str = "$", sufijo: str = "", decimales: int = 0,
             invertir_color: bool = False):
    """Tarjeta KPI con valor, referencia y variación %."""
    fmt = f"{{:,.{decimales}f}}"
    val_fmt = prefijo + fmt.format(abs(valor) / 1_000_000) + "M" + sufijo

    if referencia and referencia != 0:
        variacion = ((valor - referencia) / abs(referencia)) * 100
        ref_fmt = prefijo + fmt.format(abs(referencia) / 1_000_000) + "M"

        if invertir_color:
            color = "#0F6E56" if variacion <= 0 else "#c4007a"
            icono = "↓" if variacion <= 0 else "↑"
        else:
            color = "#0F6E56" if variacion >= 0 else "#c4007a"
            icono = "↑" if variacion >= 0 else "↓"

        sub_html = f"""
        <div style="font-size:12px; color:{color}; margin-top:4px;">
            {icono} {abs(variacion):.1f}%
        </div>
        <div style="font-size:11px; color:#aaa; margin-top:2px;">Obj: {ref_fmt}</div>
        """
    else:
        sub_html = ""

    st.markdown(f"""
    <div style="background:#fff; border:1px solid #f0dff0; border-radius:12px;
                padding:16px 18px; text-align:center; height:100%;">
        <div style="font-size:11px; color:#999; margin-bottom:6px;">{label}</div>
        <div style="font-size:22px; font-weight:700; color:#2d0050;">{val_fmt}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────

def sidebar_kreems(mostrar_sociedad: bool = True, mostrar_cc: bool = False):
    """Sidebar estándar con logo, navegación y filtros."""
    with st.sidebar:
        # Logo
        st.markdown(f"""
        <div style="text-align:center; padding:20px 0 14px;">
            {_logo_html(altura=44)}
            <div style="color:#aaa; font-size:11px; margin-top:8px;">
                Control Presupuestario 2026
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Sección VISTA
        st.markdown("""
        <div style="font-size:9px; color:#bbb; font-weight:700; letter-spacing:1.5px;
                    padding:0 4px 4px; text-transform:uppercase;">VISTA</div>
        """, unsafe_allow_html=True)

        st.page_link("app.py",                    label="Inicio",                      use_container_width=True)
        st.page_link("pages/1_dashboard.py",      label="Resumen Ejecutivo",           use_container_width=True)
        st.page_link("pages/2_eerr.py",           label="Estado de Resultados",        use_container_width=True)
        st.page_link("pages/3_centro_costos.py",  label="Centro de Costos",            use_container_width=True)
        st.page_link("pages/4_control_cuentas.py",label="Control por Cuenta Contable", use_container_width=True)
        st.page_link("pages/6_reportes.py",        label="Reportes Guardados",          use_container_width=True)

        rol = st.session_state.get("rol", "")
        if rol == "admin":
            st.markdown("""
            <div style="font-size:9px; color:#bbb; font-weight:700; letter-spacing:1.5px;
                        padding:10px 4px 4px; text-transform:uppercase;">ADMINISTRACIÓN</div>
            """, unsafe_allow_html=True)
            st.page_link("pages/5_cargar_datos.py", label="⬆️  Cargar Datos", use_container_width=True)

        st.markdown("<hr style='border:none; border-top:1px solid #f0dff0; margin:14px 0;'>",
                    unsafe_allow_html=True)

        sociedad_sel = "Todas"
        cc_sel = []

        if mostrar_sociedad:
            st.markdown("**🏭 Sociedad**")
            sociedad_sel = st.radio(
                "sociedad",
                ["Todas", "GRAN_NATURAL", "ACUÑA"],
                label_visibility="collapsed"
            )

        if mostrar_cc:
            st.markdown("**🏢 Centro de Costo**")
            opciones_cc = {
                "Administración": "CC-01",
                "Comercial":      "CC-02",
                "Distribución":   "CC-03",
                "Producción":     "CC-04",
            }
            for nombre_cc, codigo in opciones_cc.items():
                if st.checkbox(nombre_cc, value=True, key=f"cc_{codigo}"):
                    cc_sel.append(codigo)

        st.markdown("<hr style='border:none; border-top:1px solid #f0dff0; margin:14px 0;'>",
                    unsafe_allow_html=True)

        # Usuario
        nombre = st.session_state.get("nombre", "")
        rol_display = st.session_state.get("rol", "").capitalize()
        st.markdown(f"""
        <div style="background:#fdf5fb; border-radius:8px; padding:10px 12px; margin-bottom:10px;">
            <div style="font-size:12px; font-weight:600; color:#2d0050;">👤 {nombre}</div>
            <div style="font-size:11px; color:#888;">{rol_display}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Cerrar sesión", use_container_width=True):
            for k in ["usuario", "rol", "nombre", "cc_permitidos"]:
                st.session_state.pop(k, None)
            st.rerun()

    return sociedad_sel, cc_sel


# ── HELPERS VISUALES ──────────────────────────────────────────

def badge_html(texto: str, tipo: str = "normal") -> str:
    """
    Retorna HTML de un badge de estado.
    tipos: 'ok'=verde, 'warn'=rosa/rojo, 'neutral'=gris, 'normal'=morado
    """
    estilos = {
        "ok":      ("rgba(15,110,86,0.12)",  "#0F6E56"),
        "warn":    ("rgba(196,0,122,0.12)",  "#c4007a"),
        "neutral": ("#f0f0f0",              "#888"),
        "normal":  ("#f0e6f8",              "#7b2d8b"),
    }
    bg, txt = estilos.get(tipo, estilos["normal"])
    return (
        f"<span style='background:{bg}; color:{txt}; border-radius:20px; "
        f"padding:2px 10px; font-size:11px; font-weight:600; "
        f"white-space:nowrap;'>{texto}</span>"
    )


def progress_bar_html(pct: float, max_pct: float = 150) -> str:
    """Barra de progreso + porcentaje para usar en celdas."""
    clamp = min(abs(pct), max_pct)
    color = "#0F6E56" if pct <= 100 else "#c4007a"
    width = (clamp / max_pct) * 100
    return (
        f"<div style='background:#f5eef8; border-radius:4px; "
        f"height:7px; width:100%; margin-bottom:2px;'>"
        f"<div style='background:{color}; width:{width:.1f}%; "
        f"height:7px; border-radius:4px;'></div></div>"
        f"<div style='font-size:11px; color:{color}; font-weight:600;'>"
        f"{pct:.1f}%</div>"
    )


def cc_card(nombre: str, codigo: str, real: float, ppto: float) -> str:
    """Card HTML para un Centro de Costo."""
    pct       = (real / ppto * 100) if ppto else 0
    variacion = real - ppto
    is_over   = pct > 100

    COLOR_GOOD = "#0F6E56"
    COLOR_BAD  = "#cc0000"

    color_pct  = COLOR_BAD if is_over else COLOR_GOOD
    color_var  = COLOR_BAD if variacion > 0 else COLOR_GOOD
    icono_var  = "&#9650;" if variacion > 0 else "&#9660;"   # ▲ ▼ como entidades HTML
    bar_fill   = min(pct, 100)
    bar_color  = COLOR_BAD if is_over else "#c4007a"
    border_col = "#ffd0d0" if is_over else "#f0dff0"
    badge_bg   = "rgba(204,0,0,0.10)" if is_over else "rgba(15,110,86,0.10)"
    badge_pre  = "&#9650; " if is_over else ""
    over_note  = (
        f"<div style='font-size:10px; color:{COLOR_BAD}; margin-bottom:6px; font-weight:600;'>"
        f"Sobre presupuesto en {pct-100:.1f}%</div>"
    ) if is_over else "<div style='margin-bottom:12px;'></div>"

    return (
        f"<div style='background:#fff; border:1px solid {border_col}; border-radius:14px;"
        f"padding:18px 20px;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:flex-start;"
        f"margin-bottom:10px;'>"
        f"<div>"
        f"<div style='font-size:11px; color:#aaa; font-weight:600; text-transform:uppercase;"
        f"letter-spacing:0.5px;'>{codigo}</div>"
        f"<div style='font-size:15px; font-weight:700; color:#2d0050; margin-top:2px;'>{nombre}</div>"
        f"</div>"
        f"<span style='background:{badge_bg}; color:{color_pct}; border-radius:20px;"
        f"padding:3px 10px; font-size:12px; font-weight:700;'>{badge_pre}{pct:.1f}%</span>"
        f"</div>"
        f"<div style='background:#f0f0f0; border-radius:6px; height:8px; margin-bottom:6px;'>"
        f"<div style='background:{bar_color}; width:{bar_fill:.1f}%; height:8px; border-radius:6px;'>"
        f"</div></div>"
        f"{over_note}"
        f"<div style='display:flex; justify-content:space-between;'>"
        f"<div><div style='font-size:10px; color:#bbb;'>Ejecutado</div>"
        f"<div style='font-size:14px; font-weight:700; color:#2d0050;'>${real/1_000_000:,.2f}M</div></div>"
        f"<div style='text-align:right;'><div style='font-size:10px; color:#bbb;'>Presupuesto</div>"
        f"<div style='font-size:14px; font-weight:600; color:#888;'>${ppto/1_000_000:,.2f}M</div></div>"
        f"</div>"
        f"<div style='margin-top:8px; font-size:11px; color:{color_var}; font-weight:600;'>"
        f"{icono_var} ${abs(variacion)/1_000_000:,.2f}M vs ppto</div>"
        f"</div>"
    )


# ── FORMATTERS ────────────────────────────────────────────────

def fmt_mill(v: float) -> str:
    """Formatea como millones con 2 decimales."""
    if v is None:
        return "—"
    return f"${v/1_000_000:,.2f}M"


def fmt_clp(v: float) -> str:
    """Formatea como CLP con separador de miles."""
    if v is None:
        return "—"
    return f"${v:,.0f}"
