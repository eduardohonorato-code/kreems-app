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
C_LIGHT    = (245, 240, 251) # fondo filas alternas
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
        pdf.rect(14, pdf.get_y(), 3, 5.5, style="F")
        pdf.set_x(19)
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
            fill = (240, 235, 250)

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
        pdf.set_text_color(50, 50, 50)

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
