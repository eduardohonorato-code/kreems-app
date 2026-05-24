"""
Generación de reporte PDF del Estado de Resultados — 1 página.
Dependencias: fpdf2, kaleido (para gráficos Plotly → PNG)
"""
from __future__ import annotations
import io
from datetime import date as _date

# ── colores brand ─────────────────────────────────────────────
C_PURPLE   = (45,  0,  80)   # #2d0050
C_PINK     = (196, 0, 122)   # #c4007a
C_GREEN    = (15, 110, 86)   # #0F6E56
C_RED      = (204, 0,   0)   # #cc0000
C_GRAY     = (148, 163, 184) # slate-400
C_LIGHT    = (252, 252, 254) # fondo filas alternas — casi blanco
C_WHITE    = (255, 255, 255)
C_BORDER   = (226, 232, 240)


def _fmt_m(v: float) -> str:
    return f"${v / 1_000_000:,.2f}M"

def _fmt_pct(v: float) -> str:
    return f"{v:.1f}%"

def _color_var(v: float, inv: bool = False) -> tuple:
    """Verde si favorable, rojo si desfavorable."""
    if inv:
        return C_GREEN if v <= 0 else C_RED
    return C_GREEN if v >= 0 else C_RED


def _try_get_chart_png(fig, width: int = 550, height: int = 260) -> bytes | None:
    """Intenta renderizar figura Plotly como PNG. Retorna None si falla."""
    try:
        import plotly.io as pio
        return pio.to_image(fig, format="png", width=width, height=height, scale=2)
    except Exception:
        return None


def generar_pdf_eerr(datos: dict, analisis_texto: str = "", fig_bridge=None) -> bytes:
    """
    Genera PDF del Estado de Resultados (1 página).

    datos debe contener:
        ventas_r, ventas_p, cv_r, cv_p, cf_r, cf_p,
        opex_r, opex_p, fin_r, fin_p, nooper_r, nooper_p,
        ub_r, ub_p, ebit_r, ebit_p, un_r, un_p,
        periodo_desde, periodo_hasta, sociedad
    fig_bridge: figura Plotly del puente de varianzas (opcional)
    """
    from fpdf import FPDF

    # ── valores ────────────────────────────────────────────────
    ventas_r  = datos["ventas_r"];  ventas_p  = datos["ventas_p"]
    cv_r      = datos["cv_r"];      cv_p      = datos["cv_p"]
    cf_r      = datos["cf_r"];      cf_p      = datos["cf_p"]
    opex_r    = datos["opex_r"];    opex_p    = datos["opex_p"]
    fin_r     = datos["fin_r"];     fin_p     = datos["fin_p"]
    nooper_r  = datos["nooper_r"];  nooper_p  = datos["nooper_p"]
    ub_r      = datos["ub_r"];      ub_p      = datos["ub_p"]
    ebit_r    = datos["ebit_r"];    ebit_p    = datos["ebit_p"]
    un_r      = datos["un_r"];      un_p      = datos["un_p"]
    sociedad  = datos.get("sociedad", "Consolidado")
    p_desde   = datos.get("periodo_desde", "")
    p_hasta   = datos.get("periodo_hasta", "")
    periodo   = p_desde if p_desde == p_hasta else f"{p_desde} - {p_hasta}"

    mb_r    = (ub_r   / ventas_r * 100) if ventas_r else 0
    mb_p    = (ub_p   / ventas_p * 100) if ventas_p else 0
    mebit_r = (ebit_r / ventas_r * 100) if ventas_r else 0
    mebit_p = (ebit_p / ventas_p * 100) if ventas_p else 0
    mnet_r  = (un_r   / ventas_r * 100) if ventas_r else 0
    mnet_p  = (un_p   / ventas_p * 100) if ventas_p else 0

    # ── fuentes Unicode (DejaVu disponible en Streamlit Cloud / Linux) ──
    FONT_PATHS = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    FONT_NAME = "Helvetica"  # fallback si no hay TTF

    def _safe(txt: str) -> str:
        """Reemplaza caracteres no-Latin1 si no hay fuente Unicode disponible."""
        return (txt
            .replace("—", "-").replace("–", "-")
            .replace("▲", "+").replace("▼", "-")
            .replace("△", "D").replace("✓", "OK")
            .replace("✕", "X").replace("●", "*")
            .encode("latin-1", errors="replace").decode("latin-1"))

    # ── clase PDF personalizada ────────────────────────────────
    class KreemsPDF(FPDF):
        def header(self):
            pass

        def footer(self):
            self.set_y(-12)
            self.set_font(FONT_NAME, "I", 7)
            self.set_text_color(*C_GRAY)
            txt = f"Kreems FP&A  -  Generado el {_date.today().strftime('%d/%m/%Y')}  -  Pag. {self.page_no()}"
            self.cell(0, 5, txt, align="C")

    pdf = KreemsPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)   # control manual: 1 sola página

    # Intentar cargar fuente TTF Unicode
    _unicode_ok = False
    for reg_path, bold_path in FONT_PATHS:
        try:
            import os
            if os.path.exists(reg_path) and os.path.exists(bold_path):
                pdf.add_font("KreemsFont",  "",  reg_path)
                pdf.add_font("KreemsFont", "B", bold_path)
                pdf.add_font("KreemsFont", "I",  reg_path)
                FONT_NAME = "KreemsFont"
                _unicode_ok = True
                break
        except Exception:
            pass

    # Si no hay TTF, _safe() sanitiza strings a Latin-1
    def T(txt: str) -> str:
        return txt if _unicode_ok else _safe(txt)

    pdf.add_page()
    pdf.set_margins(14, 14, 14)

    # ── Cabecera (altura reducida a 24mm) ──────────────────────
    pdf.set_fill_color(*C_PURPLE)
    pdf.rect(0, 0, 210, 24, style="F")
    pdf.set_y(5)
    pdf.set_font(FONT_NAME, "B", 14)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 7, T("KREEMS FP&A"), ln=True, align="C")
    pdf.set_font(FONT_NAME, "", 9)
    pdf.cell(0, 5, T("Estado de Resultados - Real vs Presupuesto"), ln=True, align="C")
    pdf.ln(2)

    # ── Metadatos ──────────────────────────────────────────────
    pdf.set_fill_color(*C_LIGHT)
    pdf.rect(14, 26, 182, 9, style="F")
    pdf.set_y(28)
    pdf.set_font(FONT_NAME, "", 8.5)
    pdf.set_text_color(*C_PURPLE)
    pdf.cell(60, 5, T(f"Periodo:  {periodo}"), ln=False)
    pdf.cell(60, 5, T(f"Sociedad:  {sociedad}"), ln=False, align="C")
    pdf.cell(62, 5, T(f"Fecha:  {_date.today().strftime('%d/%m/%Y')}"), ln=False, align="R")
    pdf.ln(9)

    # ── helper título de sección ──────────────────────────────
    def _section_title(txt: str):
        pdf.set_font(FONT_NAME, "B", 9)
        pdf.set_text_color(*C_PURPLE)
        pdf.set_fill_color(*C_PURPLE)
        pdf.rect(14, pdf.get_y(), 2, 5.5, style="F")
        pdf.set_x(18)
        pdf.cell(0, 5.5, T(txt), ln=True)
        pdf.ln(1)

    # ── KPIs ──────────────────────────────────────────────────
    _section_title("INDICADORES CLAVE")

    kpis = [
        ("Ventas",      ventas_r, ventas_p, False),
        ("Util. Bruta", ub_r,     ub_p,     False),
        ("EBIT",        ebit_r,   ebit_p,   False),
        ("Util. Neta",  un_r,     un_p,     False),
    ]
    box_w = 43
    box_h = 20
    x0    = 14
    y0    = pdf.get_y()

    for i, (label, real, ppto, inv) in enumerate(kpis):
        x         = x0 + i * (box_w + 2)
        variacion = real - ppto
        pct_v     = (real / ppto * 100) if ppto else 0
        color     = C_GREEN if variacion >= 0 else C_RED

        pdf.set_draw_color(*C_BORDER)
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(x, y0, box_w, box_h, style="FD")

        pdf.set_xy(x, y0 + 1.5)
        pdf.set_font(FONT_NAME, "", 6.5)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(box_w, 3.5, T(label.upper()), align="C")

        pdf.set_xy(x, y0 + 5)
        pdf.set_font(FONT_NAME, "B", 10)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(box_w, 5.5, T(_fmt_m(real)), align="C")

        pdf.set_xy(x, y0 + 11)
        pdf.set_font(FONT_NAME, "", 7.5)
        pdf.set_text_color(*color)
        signo_txt = "(+)" if variacion >= 0 else "(-)"
        pdf.cell(box_w, 4, T(f"{signo_txt} {_fmt_m(abs(variacion))} ({pct_v:.1f}%)"), align="C")

        pdf.set_xy(x, y0 + 16)
        pdf.set_font(FONT_NAME, "", 6.5)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(box_w, 3, T(f"Obj: {_fmt_m(ppto)}"), align="C")

    pdf.set_y(y0 + box_h + 4)

    # ── Tabla P&L ──────────────────────────────────────────────
    _section_title("ESTADO DE RESULTADOS")

    filas_eerr = [
        ("Ventas",                  ventas_r, ventas_p, False, True),
        ("Costo de Venta",          cv_r,     cv_p,     True,  False),
        ("Utilidad Bruta",          ub_r,     ub_p,     False, True),
        ("Costo Fijo",              cf_r,     cf_p,     True,  False),
        ("OPEX",                    opex_r,   opex_p,   True,  False),
        ("EBIT",                    ebit_r,   ebit_p,   False, True),
        ("Gastos Financieros",      fin_r,    fin_p,    True,  False),
        ("Gastos No Operacionales", nooper_r, nooper_p, True,  False),
        ("Utilidad Neta",           un_r,     un_p,     False, True),
    ]

    col_w    = [62, 32, 32, 32, 24]
    headers_t = ["Concepto", "Real", "Presupuesto", "Varianza", "% Ejec."]

    pdf.set_fill_color(*C_PURPLE)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font(FONT_NAME, "B", 7.5)
    for i, (h, w) in enumerate(zip(headers_t, col_w)):
        align = "L" if i == 0 else "R"
        pdf.cell(w, 6, T(h), border=0, fill=True, align=align)
    pdf.ln()

    ROW_H = 6.0
    for idx, (nombre, real, ppto, inv, subtotal) in enumerate(filas_eerr):
        variacion = real - ppto
        pct_v     = (real / ppto * 100) if ppto else 0
        c_var     = _color_var(variacion, inv)

        fill = C_LIGHT if idx % 2 == 0 else C_WHITE
        if subtotal:
            fill = (244, 241, 252)  # morado muy suave para subtotales

        pdf.set_fill_color(*fill)
        pdf.set_text_color(*C_PURPLE if subtotal else (30, 30, 30))
        pdf.set_font(FONT_NAME, "B" if subtotal else "", 7.5)

        pdf.cell(col_w[0], ROW_H, T(nombre),       fill=True, align="L")
        pdf.cell(col_w[1], ROW_H, T(_fmt_m(real)), fill=True, align="R")
        pdf.cell(col_w[2], ROW_H, T(_fmt_m(ppto)), fill=True, align="R")

        pdf.set_text_color(*c_var)
        signo = "+" if variacion >= 0 else ""
        pdf.cell(col_w[3], ROW_H, T(f"{signo}{_fmt_m(variacion)}"), fill=True, align="R")

        pdf.set_text_color(*(C_GREEN if pct_v <= 100 else C_RED))
        pdf.cell(col_w[4], ROW_H, T(_fmt_pct(pct_v)), fill=True, align="R")
        pdf.ln()

    pdf.ln(3)

    # ── Ratios ─────────────────────────────────────────────────
    _section_title("RATIOS FINANCIEROS")

    ratios = [
        ("Margen Bruto",  mb_r,    mb_p,    False),
        ("Margen EBIT",   mebit_r, mebit_p, False),
        ("Margen Neto",   mnet_r,  mnet_p,  False),
        ("CV / Ventas",   (cv_r / ventas_r * 100) if ventas_r else 0,
                          (cv_p / ventas_p * 100) if ventas_p else 0, True),
        ("OPEX / Ventas", (opex_r / ventas_r * 100) if ventas_r else 0,
                          (opex_p / ventas_p * 100) if ventas_p else 0, True),
    ]

    r_w  = 36
    r_h  = 14          # altura de cada cajita de ratio
    y_r  = pdf.get_y()
    for i, (label, rv, pv, inv) in enumerate(ratios):
        x     = 14 + i * (r_w + 2)
        diff  = rv - pv
        ok    = (diff <= 0) if inv else (diff >= 0)
        color = C_GREEN if ok else C_RED

        pdf.set_draw_color(*C_BORDER)
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(x, y_r, r_w, r_h, style="FD")

        pdf.set_xy(x, y_r + 1)
        pdf.set_font(FONT_NAME, "", 6.5)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(r_w, 3.5, T(label), align="C")

        pdf.set_xy(x, y_r + 4.5)
        pdf.set_font(FONT_NAME, "B", 9.5)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(r_w, 4.5, T(f"{rv:.1f}%"), align="C")

        pdf.set_xy(x, y_r + 9)
        pdf.set_font(FONT_NAME, "", 7)
        pdf.set_text_color(*color)
        icono_txt = "(-)" if diff < 0 else "(+)"
        pdf.cell(r_w, 4, T(f"{icono_txt} {abs(diff):.1f}pp  |  Obj: {pv:.1f}%"), align="C")

    pdf.set_y(y_r + r_h + 3)

    # ── Puente de Varianzas (gráfico PNG) ──────────────────────
    if fig_bridge is not None:
        png = _try_get_chart_png(fig_bridge, width=700, height=260)
        if png and pdf.get_y() < 230:
            _section_title("PUENTE DE VARIANZAS")
            chart_h = min(68, 282 - pdf.get_y())  # no sobrepasar página
            pdf.image(io.BytesIO(png), x=14, y=pdf.get_y(), w=182, h=chart_h)
            pdf.set_y(pdf.get_y() + chart_h + 3)

    # ── Análisis IA — sin salto de página, se corta al borde ───
    if analisis_texto.strip() and pdf.get_y() < 275:
        _section_title("ANALISIS IA")
        y_ia       = pdf.get_y()
        page_limit = 283  # margen inferior efectivo (A4=297, footer≈14)

        # Ancho explícito: margen izquierdo 19mm (espacio para barra), derecho 14mm
        x_text = 19
        w_text = 210 - x_text - 14  # = 177mm

        pdf.set_font(FONT_NAME, "", 7.5)
        pdf.set_text_color(15, 15, 15)   # casi negro — máxima legibilidad

        line_h = 4.2
        for line in T(analisis_texto).split("\n"):
            if pdf.get_y() + line_h > page_limit:
                break
            pdf.set_x(x_text)
            pdf.multi_cell(w_text, line_h, line, border=0)

        # Barra lateral morada proporcional al texto escrito
        h_ia = pdf.get_y() - y_ia
        if h_ia > 0:
            pdf.set_fill_color(*C_PURPLE)
            pdf.rect(14, y_ia, 3, h_ia, style="F")

    # ── Output ─────────────────────────────────────────────────
    return bytes(pdf.output())


# ═══════════════════════════════════════════════════════════════
# Flash Report Mensual — 1 página ejecutiva
# ═══════════════════════════════════════════════════════════════

def generar_flash_report(
    datos: dict,
    df_top,
    analisis_texto: str = "",
    titulo_mes: str = "",
) -> bytes:
    """
    Genera PDF del Flash Report Mensual (1 página A4).

    datos: ventas_r/p, cv_r/p, cf_r/p, opex_r/p, fin_r/p, nooper_r/p,
           ub_r/p, ebit_r/p, un_r/p, gastos_r/p, periodo, sociedad
    df_top: DataFrame columnas cuenta, real, ppto, varianza
    """
    from fpdf import FPDF
    import pandas as _pd

    v_r = datos["ventas_r"]; v_p = datos["ventas_p"]
    e_r = datos["ebit_r"];   e_p = datos["ebit_p"]
    u_r = datos["un_r"];     u_p = datos["un_p"]
    g_r = datos["gastos_r"]; g_p = datos["gastos_p"]
    ub_r= datos["ub_r"];     ub_p= datos["ub_p"]
    sociedad = datos.get("sociedad", "Consolidado")
    periodo  = datos.get("periodo", "")
    titulo   = titulo_mes or periodo

    pct_v = v_r / v_p * 100 if v_p else 0
    pct_e = e_r / e_p * 100 if e_p else 0
    pct_u = u_r / u_p * 100 if u_p else 0
    pct_g = g_r / g_p * 100 if g_p else 0

    # Fuentes
    FONT_PATHS = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    FONT_NAME = "Helvetica"

    def _safe(txt: str) -> str:
        return (txt.replace("—", "-").replace("–", "-")
                   .replace("▲", "+").replace("▼", "-")
                   .encode("latin-1", errors="replace").decode("latin-1"))

    class FlashPDF(FPDF):
        def header(self): pass
        def footer(self):
            self.set_y(-10)
            self.set_font(FONT_NAME, "I", 6.5)
            self.set_text_color(*C_GRAY)
            self.cell(0, 4, f"Kreems FP&A  -  Flash Report {titulo}  -  {_date.today().strftime('%d/%m/%Y')}", align="C")

    pdf = FlashPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)

    _unicode_ok = False
    for reg, bold in FONT_PATHS:
        try:
            import os
            if os.path.exists(reg) and os.path.exists(bold):
                pdf.add_font("FF", "",  reg)
                pdf.add_font("FF", "B", bold)
                pdf.add_font("FF", "I", reg)
                FONT_NAME = "FF"
                _unicode_ok = True
                break
        except Exception:
            pass

    def T(txt: str) -> str:
        return txt if _unicode_ok else _safe(txt)

    pdf.add_page()
    pdf.set_margins(0, 0, 0)

    # ── CABECERA PURPLE ──────────────────────────────────────────
    pdf.set_fill_color(*C_PURPLE)
    pdf.rect(0, 0, 210, 22, style="F")
    pdf.set_y(4)
    pdf.set_font(FONT_NAME, "B", 13)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 6, T("KREEMS FP&A"), ln=True, align="C")
    pdf.set_font(FONT_NAME, "", 8)
    pdf.cell(0, 5, T(f"Flash Report Mensual  |  {titulo}  |  {sociedad}"), ln=True, align="C")
    pdf.set_font(FONT_NAME, "", 7)
    pdf.set_text_color(220, 180, 255)
    pdf.cell(0, 4, T(f"Generado: {_date.today().strftime('%d/%m/%Y')}"), ln=True, align="C")

    # ── KPI CARDS ────────────────────────────────────────────────
    kpis = [
        ("VENTAS",     v_r, v_p, pct_v, False),
        ("EBIT",       e_r, e_p, pct_e, False),
        ("UT. NETA",   u_r, u_p, pct_u, False),
        ("GASTOS TOT", g_r, g_p, pct_g, True),
    ]
    card_w = 49; card_h = 26; x0 = 7; y0 = 24

    for i, (lbl, r, p, pct, inv) in enumerate(kpis):
        x = x0 + i * (card_w + 2)
        # color semáforo
        if not inv:
            cvar = C_GREEN if pct >= 100 else (C_RED if pct < 90 else (181, 69, 9))
        else:
            cvar = C_GREEN if pct <= 90 else (C_RED if pct > 100 else (181, 69, 9))

        pdf.set_draw_color(*C_BORDER)
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(x, y0, card_w, card_h, style="FD")

        # Barra color superior
        pdf.set_fill_color(*cvar)
        pdf.rect(x, y0, card_w, 2, style="F")

        pdf.set_xy(x, y0 + 3)
        pdf.set_font(FONT_NAME, "", 6.5)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(card_w, 3.5, T(lbl), align="C")

        pdf.set_xy(x, y0 + 7)
        pdf.set_font(FONT_NAME, "B", 10.5)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(card_w, 5.5, T(_fmt_m(r)), align="C")

        pdf.set_xy(x, y0 + 13)
        pdf.set_font(FONT_NAME, "B", 8)
        pdf.set_text_color(*cvar)
        pdf.cell(card_w, 4, T(f"{pct:.1f}% ppto"), align="C")

        pdf.set_xy(x, y0 + 18)
        pdf.set_font(FONT_NAME, "", 6.5)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(card_w, 3.5, T(f"Obj: {_fmt_m(p)}"), align="C")

    # ── SEMÁFORO GLOBAL ──────────────────────────────────────────
    y_sem = y0 + card_h + 3
    sem_color = C_GREEN if pct_v >= 100 else (C_RED if pct_v < 90 else (181, 69, 9))
    sem_label = "OK" if pct_v >= 100 else ("Alerta" if pct_v < 90 else "Atencion")
    estado_txt = f"ESTADO GENERAL: {sem_label}  |  Ejecucion ventas {pct_v:.1f}%  |  EBIT {pct_e:.1f}%  |  Ut.Neta {pct_u:.1f}%"

    pdf.set_fill_color(248, 249, 251)
    pdf.rect(0, y_sem, 210, 10, style="F")
    pdf.set_draw_color(*C_BORDER)
    pdf.line(0, y_sem, 210, y_sem)
    pdf.line(0, y_sem + 10, 210, y_sem + 10)

    pdf.set_fill_color(*sem_color)
    pdf.rect(7, y_sem + 2.5, 5, 5, style="F")
    pdf.set_xy(14, y_sem + 1.5)
    pdf.set_font(FONT_NAME, "B", 8)
    pdf.set_text_color(*sem_color)
    pdf.cell(40, 5, T(sem_label.upper()), ln=False)
    pdf.set_font(FONT_NAME, "", 7.5)
    pdf.set_text_color(*C_GRAY)
    pdf.cell(0, 5, T(f"Ejecucion ventas {pct_v:.1f}%  |  EBIT {pct_e:.1f}%  |  Ut.Neta {pct_u:.1f}%  |  Gastos {pct_g:.1f}%"), ln=True)

    # ── SECCIÓN: 2 COLUMNAS ──────────────────────────────────────
    y_body   = y_sem + 12
    col_mid  = 7 + 95   # separador en x=102

    def _section_hdr(x, y, txt, w):
        pdf.set_fill_color(*C_PURPLE)
        pdf.rect(x, y, w, 6, style="F")
        pdf.set_xy(x + 2, y + 0.5)
        pdf.set_font(FONT_NAME, "B", 7)
        pdf.set_text_color(*C_WHITE)
        pdf.cell(w - 4, 5, T(txt), ln=False)

    # ── LEFT: Top Desviaciones ───────────────────────────────────
    _section_hdr(7, y_body, "TOP DESVIACIONES (COSTOS)", 93)
    y_tbl = y_body + 7

    # Header tabla
    hdrs   = ["Cuenta", "Real", "Ppto", "Var $", "% Ejec."]
    h_w    = [44, 14, 14, 14, 11]
    pdf.set_fill_color(240, 240, 248)
    pdf.set_draw_color(*C_BORDER)
    for j, (h, w) in enumerate(zip(hdrs, h_w)):
        align = "L" if j == 0 else "R"
        pdf.set_xy(7 + sum(h_w[:j]), y_tbl)
        pdf.set_font(FONT_NAME, "B", 6.5)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(w, 5, T(h), fill=True, align=align)
    y_tbl += 5

    rows_shown = 0
    for _, row in (df_top.head(7) if not df_top.empty else _pd.DataFrame()).iterrows():
        if y_tbl + 5 > 240:
            break
        real_v = float(row["monto_r"])
        ppto_v = float(row["monto_p"])
        var_v  = float(row["varianza"])
        pct_row = real_v / ppto_v * 100 if ppto_v else 0
        cvar   = C_RED if var_v > 0 else C_GREEN
        fill   = C_LIGHT if rows_shown % 2 == 0 else C_WHITE
        cuenta_txt = str(row["cuenta"])[:28]

        pdf.set_fill_color(*fill)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font(FONT_NAME, "", 6.5)

        vals = [cuenta_txt, _fmt_m(real_v), _fmt_m(ppto_v), "", f"{pct_row:.1f}%"]
        for j, (val, w) in enumerate(zip(vals, h_w)):
            pdf.set_xy(7 + sum(h_w[:j]), y_tbl)
            if j == 3:
                pdf.set_text_color(*cvar)
                signo = "+" if var_v >= 0 else ""
                pdf.cell(w, 4.5, T(f"{signo}{_fmt_m(var_v)}"), fill=True, align="R")
                pdf.set_text_color(30, 30, 30)
            else:
                pdf.cell(w, 4.5, T(val), fill=True, align="L" if j == 0 else "R")

        y_tbl   += 4.5
        rows_shown += 1

    # ── RIGHT: Ejecución P&L mini-barras ────────────────────────
    _section_hdr(col_mid + 2, y_body, "EJECUCION P&L", 99)
    y_bar = y_body + 9

    lineas_pl = [
        ("Ventas",       v_r,   v_p,   pct_v,  False),
        ("Ut. Bruta",    ub_r,  ub_p,  (ub_r/ub_p*100) if ub_p else 0, False),
        ("EBIT",         e_r,   e_p,   pct_e,  False),
        ("Ut. Neta",     u_r,   u_p,   pct_u,  False),
        ("Gastos Total", g_r,   g_p,   pct_g,  True),
    ]
    bar_area_w = 88
    bar_h_px   = 4

    for lbl, r, p, pct, inv in lineas_pl:
        if y_bar + 12 > 245:
            break
        if not inv:
            cbar = C_GREEN if pct >= 100 else (C_RED if pct < 90 else (181, 69, 9))
        else:
            cbar = C_GREEN if pct <= 90 else (C_RED if pct > 100 else (181, 69, 9))

        # Label + porcentaje
        pdf.set_xy(col_mid + 3, y_bar)
        pdf.set_font(FONT_NAME, "", 7)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(45, 4, T(lbl))
        pdf.set_xy(col_mid + 50, y_bar)
        pdf.set_font(FONT_NAME, "B", 7)
        pdf.set_text_color(*cbar)
        pdf.cell(30, 4, T(f"{pct:.1f}%"), align="R")

        # Barra de fondo (gris)
        y_bar += 5
        pdf.set_fill_color(*C_BORDER)
        pdf.rect(col_mid + 3, y_bar, bar_area_w, bar_h_px, style="F")
        # Barra de progreso
        bar_fill = min(pct / 100.0, 1.5) * bar_area_w
        pdf.set_fill_color(*cbar)
        pdf.rect(col_mid + 3, y_bar, min(bar_fill, bar_area_w), bar_h_px, style="F")
        # Valores Real / Ppto
        y_bar += bar_h_px + 1
        pdf.set_xy(col_mid + 3, y_bar)
        pdf.set_font(FONT_NAME, "", 6)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(bar_area_w, 3.5, T(f"Real {_fmt_m(r)}  /  Obj {_fmt_m(p)}"), align="L")
        y_bar += 5

    # Línea divisoria vertical
    y_end_body = max(y_tbl, y_bar) + 2
    pdf.set_draw_color(*C_BORDER)
    pdf.line(col_mid + 1, y_body, col_mid + 1, y_end_body)

    # ── ANÁLISIS IA ──────────────────────────────────────────────
    y_ia_start = y_end_body + 3
    page_limit = 284

    if analisis_texto.strip() and y_ia_start < 260:
        pdf.set_fill_color(*C_PURPLE)
        pdf.rect(7, y_ia_start, 196, 6, style="F")
        pdf.set_xy(9, y_ia_start + 0.5)
        pdf.set_font(FONT_NAME, "B", 7)
        pdf.set_text_color(*C_WHITE)
        pdf.cell(190, 5, T("COMENTARIO EJECUTIVO (IA)"), ln=True)

        y_txt = y_ia_start + 7
        pdf.set_font(FONT_NAME, "", 7.5)
        pdf.set_text_color(15, 15, 15)
        line_h = 4.2
        y_barra = y_txt
        for line in T(analisis_texto).split("\n"):
            if pdf.get_y() + line_h > page_limit:
                break
            pdf.set_xy(12, y_txt if pdf.get_y() < y_txt else pdf.get_y())
            pdf.multi_cell(191, line_h, line, border=0)

        h_ia = pdf.get_y() - y_barra
        if h_ia > 0:
            pdf.set_fill_color(*C_PURPLE)
            pdf.rect(7, y_barra, 2.5, h_ia, style="F")

    # ── OUTPUT ──────────────────────────────────────────────────
    return bytes(pdf.output())
