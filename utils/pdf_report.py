"""
Generación de reporte PDF del Estado de Resultados.
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


def _try_get_chart_png(fig, width: int = 550, height: int = 280) -> bytes | None:
    """Intenta renderizar figura Plotly como PNG. Retorna None si falla."""
    try:
        import plotly.io as pio
        return pio.to_image(fig, format="png", width=width, height=height, scale=2)
    except Exception:
        return None


def generar_pdf_eerr(datos: dict, analisis_texto: str = "", fig_bridge=None) -> bytes:
    """
    Genera PDF del Estado de Resultados.

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
    periodo   = p_desde if p_desde == p_hasta else f"{p_desde} — {p_hasta}"

    mb_r    = (ub_r   / ventas_r * 100) if ventas_r else 0
    mb_p    = (ub_p   / ventas_p * 100) if ventas_p else 0
    mebit_r = (ebit_r / ventas_r * 100) if ventas_r else 0
    mebit_p = (ebit_p / ventas_p * 100) if ventas_p else 0
    mnet_r  = (un_r   / ventas_r * 100) if ventas_r else 0
    mnet_p  = (un_p   / ventas_p * 100) if ventas_p else 0

    # ── clase PDF personalizada ────────────────────────────────
    class KreemsPDF(FPDF):
        def header(self):
            pass  # header manual por sección

        def footer(self):
            self.set_y(-14)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(*C_GRAY)
            self.cell(0, 6, f"Kreems FP&A  ·  Generado el {_date.today().strftime('%d/%m/%Y')}  ·  Pág. {self.page_no()}", align="C")

    pdf = KreemsPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    pdf.set_margins(14, 14, 14)

    # ── Cabecera ───────────────────────────────────────────────
    pdf.set_fill_color(*C_PURPLE)
    pdf.rect(0, 0, 210, 28, style="F")
    pdf.set_y(7)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(0, 8, "KREEMS FP&A", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Estado de Resultados — Real vs Presupuesto", ln=True, align="C")
    pdf.ln(4)

    # ── Metadatos ──────────────────────────────────────────────
    pdf.set_fill_color(*C_LIGHT)
    pdf.rect(14, 30, 182, 10, style="F")
    pdf.set_y(32)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_PURPLE)
    pdf.cell(60, 6, f"Período:  {periodo}", ln=False)
    pdf.cell(60, 6, f"Sociedad:  {sociedad}", ln=False, align="C")
    pdf.cell(62, 6, f"Fecha:  {_date.today().strftime('%d/%m/%Y')}", ln=False, align="R")
    pdf.ln(12)

    # ── Sección KPIs ───────────────────────────────────────────
    def _section_title(txt: str):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*C_PURPLE)
        pdf.set_fill_color(*C_PURPLE)
        pdf.rect(14, pdf.get_y(), 4, 6, style="F")
        pdf.set_x(20)
        pdf.cell(0, 6, txt, ln=True)
        pdf.ln(2)

    _section_title("INDICADORES CLAVE")

    kpis = [
        ("Ventas",         ventas_r, ventas_p, False),
        ("Util. Bruta",    ub_r,     ub_p,     False),
        ("EBIT",           ebit_r,   ebit_p,   False),
        ("Util. Neta",     un_r,     un_p,     False),
    ]
    box_w = 43
    box_h = 22
    x0    = 14
    y0    = pdf.get_y()

    for i, (label, real, ppto, inv) in enumerate(kpis):
        x = x0 + i * (box_w + 2)
        variacion = real - ppto
        pct_v     = (real / ppto * 100) if ppto else 0
        color     = C_GREEN if variacion >= 0 else C_RED
        signo     = "▲" if variacion >= 0 else "▼"

        # borde
        pdf.set_draw_color(*C_BORDER)
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(x, y0, box_w, box_h, style="FD")

        # label
        pdf.set_xy(x, y0 + 2)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(box_w, 4, label.upper(), align="C")

        # valor real
        pdf.set_xy(x, y0 + 6)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(box_w, 6, _fmt_m(real), align="C")

        # variacion
        pdf.set_xy(x, y0 + 13)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*color)
        pdf.cell(box_w, 4, f"{signo} {_fmt_m(abs(variacion))} ({pct_v:.1f}%)", align="C")

        # objetivo
        pdf.set_xy(x, y0 + 18)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(box_w, 3, f"Obj: {_fmt_m(ppto)}", align="C")

    pdf.set_y(y0 + box_h + 6)

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

    col_w = [62, 32, 32, 32, 24]
    headers_t = ["Concepto", "Real", "Presupuesto", "Varianza", "% Ejec."]

    # encabezado tabla
    pdf.set_fill_color(*C_PURPLE)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for i, (h, w) in enumerate(zip(headers_t, col_w)):
        align = "L" if i == 0 else "R"
        pdf.cell(w, 7, h, border=0, fill=True, align=align)
    pdf.ln()

    for idx, (nombre, real, ppto, inv, subtotal) in enumerate(filas_eerr):
        variacion = real - ppto
        pct_v     = (real / ppto * 100) if ppto else 0
        c_var     = _color_var(variacion, inv)

        fill = C_LIGHT if idx % 2 == 0 else C_WHITE
        if subtotal:
            fill = (240, 235, 250)

        pdf.set_fill_color(*fill)
        pdf.set_text_color(*C_PURPLE if subtotal else (30, 30, 30))
        pdf.set_font("Helvetica", "B" if subtotal else "", 8)

        pdf.cell(col_w[0], 6.5, nombre, fill=True, align="L")
        pdf.cell(col_w[1], 6.5, _fmt_m(real),        fill=True, align="R")
        pdf.cell(col_w[2], 6.5, _fmt_m(ppto),        fill=True, align="R")

        # varianza coloreada
        pdf.set_text_color(*c_var)
        signo = "+" if variacion >= 0 else ""
        pdf.cell(col_w[3], 6.5, f"{signo}{_fmt_m(variacion)}", fill=True, align="R")

        # % ejecución
        pdf.set_text_color(*(C_GREEN if pct_v <= 100 else C_RED))
        pdf.cell(col_w[4], 6.5, _fmt_pct(pct_v), fill=True, align="R")
        pdf.ln()

    pdf.ln(4)

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

    r_w = 36
    y_r = pdf.get_y()
    for i, (label, rv, pv, inv) in enumerate(ratios):
        x = 14 + i * (r_w + 2)
        diff  = rv - pv
        ok    = (diff <= 0) if inv else (diff >= 0)
        color = C_GREEN if ok else C_RED
        icono = "▼" if diff < 0 else "▲"

        pdf.set_draw_color(*C_BORDER)
        pdf.set_fill_color(*C_WHITE)
        pdf.rect(x, y_r, r_w, 16, style="FD")

        pdf.set_xy(x, y_r + 1)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*C_GRAY)
        pdf.cell(r_w, 4, label, align="C")

        pdf.set_xy(x, y_r + 5)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*C_PURPLE)
        pdf.cell(r_w, 5, f"{rv:.1f}%", align="C")

        pdf.set_xy(x, y_r + 10)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*color)
        pdf.cell(r_w, 4, f"{icono} {abs(diff):.1f}pp  |  Obj: {pv:.1f}%", align="C")

    pdf.set_y(y_r + 22)

    # ── Puente de Varianzas (gráfico PNG) ──────────────────────
    if fig_bridge is not None:
        png = _try_get_chart_png(fig_bridge, width=700, height=320)
        if png:
            _section_title("PUENTE DE VARIANZAS")
            pdf.image(io.BytesIO(png), x=14, y=pdf.get_y(), w=182)
            pdf.set_y(pdf.get_y() + 82)

    # ── Análisis IA ────────────────────────────────────────────
    if analisis_texto.strip():
        if pdf.get_y() > 220:
            pdf.add_page()
        _section_title("ANÁLISIS IA")
        pdf.set_fill_color(*C_LIGHT)
        pdf.set_draw_color(*C_PURPLE)
        y_ia = pdf.get_y()
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(50, 50, 50)
        pdf.set_left_margin(18)
        pdf.set_right_margin(14)
        pdf.multi_cell(0, 5, analisis_texto, border=0)
        # borde lateral izquierdo
        h_ia = pdf.get_y() - y_ia
        pdf.set_fill_color(*C_PURPLE)
        pdf.rect(14, y_ia, 3, h_ia, style="F")
        pdf.set_left_margin(14)
        pdf.set_right_margin(14)

    # ── Output ─────────────────────────────────────────────────
    return bytes(pdf.output())
