"""
Análisis IA con Groq (llama-3.3-70b-versatile) — API gratuita.
Requiere st.secrets["groq"]["api_key"] configurado en .streamlit/secrets.toml
"""
import streamlit as st


@st.cache_resource
def _get_client():
    """Retorna cliente Groq. None si no está configurado."""
    try:
        from groq import Groq
        api_key = st.secrets["groq"]["api_key"]
        return Groq(api_key=api_key)
    except Exception:
        return None


def _fmt_m(v: float) -> str:
    return f"${v / 1_000_000:,.2f}M"


def _pct(r: float, p: float) -> str:
    if not p:
        return "N/A"
    return f"{r / p * 100:.1f}%"


def generar_analisis_eerr(datos: dict) -> str:
    """
    Genera un análisis ejecutivo del Estado de Resultados usando Claude Haiku.

    datos debe contener:
        ventas_r, ventas_p, cv_r, cv_p, cf_r, cf_p,
        opex_r, opex_p, ub_r, ub_p, ebit_r, ebit_p,
        un_r, un_p, periodo_desde, periodo_hasta, sociedad
    """
    client = _get_client()
    if client is None:
        return (
            "⚠ **API key no configurada.**\n\n"
            "Agrega en `.streamlit/secrets.toml`:\n"
            "```toml\n[groq]\napi_key = \"gsk_...\"\n```\n\n"
            "Obtén tu key gratis en https://console.groq.com"
        )

    ventas_r = datos["ventas_r"]
    ventas_p = datos["ventas_p"]
    cv_r     = datos["cv_r"]
    cv_p     = datos["cv_p"]
    cf_r     = datos["cf_r"]
    cf_p     = datos["cf_p"]
    opex_r   = datos["opex_r"]
    opex_p   = datos["opex_p"]
    ub_r     = datos["ub_r"]
    ub_p     = datos["ub_p"]
    ebit_r   = datos["ebit_r"]
    ebit_p   = datos["ebit_p"]
    un_r     = datos["un_r"]
    un_p     = datos["un_p"]

    mb_r    = (ub_r   / ventas_r * 100) if ventas_r else 0
    mb_p    = (ub_p   / ventas_p * 100) if ventas_p else 0
    mebit_r = (ebit_r / ventas_r * 100) if ventas_r else 0
    mebit_p = (ebit_p / ventas_p * 100) if ventas_p else 0
    mnet_r  = (un_r   / ventas_r * 100) if ventas_r else 0
    mnet_p  = (un_p   / ventas_p * 100) if ventas_p else 0

    sociedad = datos.get("sociedad", "Consolidado")
    periodo  = f"{datos['periodo_desde']} a {datos['periodo_hasta']}"

    prompt = f"""Eres un controller financiero senior de una empresa chilena.
Analiza el siguiente Estado de Resultados Real vs Presupuesto y redacta un informe ejecutivo breve y directo en español.

REGLAS DE INTERPRETACIÓN (aplícalas siempre):
- VENTAS: ejecución >100% = POSITIVO (se vendió más de lo planeado). Ejecución <100% = NEGATIVO.
- COSTOS (Costo Variable, Costo Fijo, OPEX): ejecución >100% = NEGATIVO (se gastó más de lo presupuestado). Ejecución <100% = POSITIVO (ahorro).
- MÁRGENES y UTILIDADES (Utilidad Bruta, EBIT, Utilidad Neta): ejecución >100% = POSITIVO. Ejecución <100% = NEGATIVO.
- No confundas: un costo con 60% de ejecución es buena noticia, no un problema.

EMPRESA: {sociedad}
PERIODO: {periodo}

| Línea             | Real              | Presupuesto       | % Ejec. |
|-------------------|-------------------|-------------------|---------|
| Ventas            | {_fmt_m(ventas_r)} | {_fmt_m(ventas_p)} | {_pct(ventas_r, ventas_p)} |
| Costo Variable    | {_fmt_m(cv_r)}    | {_fmt_m(cv_p)}    | {_pct(cv_r, cv_p)} |
| Utilidad Bruta    | {_fmt_m(ub_r)}    | {_fmt_m(ub_p)}    | {_pct(ub_r, ub_p)} |
| Margen Bruto      | {mb_r:.1f}%       | {mb_p:.1f}%       | {mb_r - mb_p:+.1f}pp |
| Costo Fijo        | {_fmt_m(cf_r)}    | {_fmt_m(cf_p)}    | {_pct(cf_r, cf_p)} |
| OPEX              | {_fmt_m(opex_r)}  | {_fmt_m(opex_p)}  | {_pct(opex_r, opex_p)} |
| EBIT              | {_fmt_m(ebit_r)}  | {_fmt_m(ebit_p)}  | {_pct(ebit_r, ebit_p)} |
| Margen EBIT       | {mebit_r:.1f}%    | {mebit_p:.1f}%    | {mebit_r - mebit_p:+.1f}pp |
| Utilidad Neta     | {_fmt_m(un_r)}    | {_fmt_m(un_p)}    | {_pct(un_r, un_p)} |
| Margen Neto       | {mnet_r:.1f}%     | {mnet_p:.1f}%     | {mnet_r - mnet_p:+.1f}pp |

Estructura tu respuesta exactamente así (sin asteriscos extra ni markdown innecesario):

RESUMEN EJECUTIVO
(2-3 oraciones que describan la situación financiera global del periodo.)

HALLAZGOS CLAVE
1. (Hallazgo con cifras concretas)
2. (Hallazgo con cifras concretas)
3. (Hallazgo con cifras concretas)

ALERTAS
(Solo si hay desviaciones negativas relevantes >5%. Si todo va bien, escribe "Sin alertas críticas.")

RECOMENDACIONES
1. (Acción concreta)
2. (Acción concreta)

Sé directo. Usa valores en millones con símbolo $M. No repitas datos de la tabla sin interpretarlos."""

    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.3,
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"❌ Error al generar análisis: {e}"


def generar_analisis_cc(datos: dict) -> str:
    """
    Genera análisis ejecutivo de Centro de Costos Real vs Presupuesto.
    datos: sociedad, periodo_desde, periodo_hasta, centros=[{nombre, real, ppto}]
    """
    client = _get_client()
    if client is None:
        return ("⚠ **API key no configurada.**\n\nAgrega `[groq] api_key` en `.streamlit/secrets.toml`.")

    sociedad = datos.get("sociedad", "Consolidado")
    periodo  = f"{datos['periodo_desde']} a {datos['periodo_hasta']}"
    ccs      = datos.get("centros", [])
    total_r  = sum(cc["real"] for cc in ccs)
    total_p  = sum(cc["ppto"] for cc in ccs)

    tabla = "\n".join([
        f"| {cc['nombre']} | ${cc['real']/1e6:,.1f}M | ${cc['ppto']/1e6:,.1f}M | "
        f"{(cc['real']/cc['ppto']*100) if cc['ppto'] else 0:.1f}% |"
        for cc in ccs
    ])

    prompt = f"""Eres un controller financiero senior de una empresa chilena.
Analiza el siguiente cuadro de Centro de Costos Real vs Presupuesto y redacta un análisis ejecutivo breve en español.

REGLA FUNDAMENTAL DE CONTROL DE COSTOS (debes aplicarla siempre):
- En centros de costo, el objetivo es NO gastar más de lo presupuestado.
- Ejecución BAJA (ej. 50-70%) = POSITIVO: la empresa está gastando bien por debajo del límite, hay holgura presupuestaria.
- Ejecución ALTA cercana a 100% = SEÑAL DE ALERTA: el centro está cerca de agotar su presupuesto y cualquier gasto adicional lo superará.
- Ejecución SUPERIOR a 100% = CRÍTICO: el centro ya superó su presupuesto.
- Por lo tanto: el CC con MEJOR comportamiento es el de MENOR % de ejecución. El CC de MAYOR RIESGO es el de ejecución más cercana o superior al 100%.

EMPRESA: {sociedad} | PERIODO: {periodo}

| Centro de Costo | Real | Presupuesto | % Ejec. |
|-----------------|------|-------------|---------|
{tabla}
| **TOTAL** | **${total_r/1e6:,.1f}M** | **${total_p/1e6:,.1f}M** | **{(total_r/total_p*100) if total_p else 0:.1f}%** |

Estructura tu respuesta exactamente así:

RESUMEN EJECUTIVO
(2 oraciones sobre el desempeño global de costos, aplicando la regla de control de costos.)

HALLAZGOS CLAVE
1. (CC con mayor riesgo: el de ejecución más alta, cercana o sobre 100%, con monto concreto)
2. (CC con mejor control: el de menor % de ejecución, destacando la holgura)
3. (Observación relevante sobre el total o tendencia)

ALERTAS
(CCs con ejecución >85%, ordenados de mayor a menor riesgo. Si todos están bajo 85% escribe "Sin alertas críticas.")

RECOMENDACIONES
1. (Acción concreta para el CC de mayor riesgo)
2. (Acción concreta a nivel general)

Sé directo. Usa $M. No repitas datos sin interpretarlos."""

    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3,
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"❌ Error al generar análisis: {e}"


def generar_analisis_cuentas(datos: dict) -> str:
    """
    Genera análisis ejecutivo de Control por Cuenta Contable.
    datos: sociedad, periodo_desde, periodo_hasta, real_total, ppto_total,
           n_cuentas, n_alertas, top_desviacion=[{nombre, real, ppto, pct}]
    """
    client = _get_client()
    if client is None:
        return ("⚠ **API key no configurada.**\n\nAgrega `[groq] api_key` en `.streamlit/secrets.toml`.")

    sociedad  = datos.get("sociedad", "Consolidado")
    periodo   = f"{datos['periodo_desde']} a {datos['periodo_hasta']}"
    total_r   = datos.get("real_total", 0)
    total_p   = datos.get("ppto_total", 0)
    n_cuentas = datos.get("n_cuentas", 0)
    n_alertas = datos.get("n_alertas", 0)
    top_desv  = datos.get("top_desviacion", [])

    tabla = "\n".join([
        f"| {c['nombre']} | ${c['real']/1e6:,.1f}M | ${c['ppto']/1e6:,.1f}M | {c['pct']:.1f}% |"
        for c in top_desv[:5]
    ])

    prompt = f"""Eres un controller financiero senior de una empresa chilena.
Analiza el siguiente resumen de Control por Cuenta Contable y redacta un análisis ejecutivo breve en español.

REGLA FUNDAMENTAL DE CONTROL DE COSTOS (aplícala siempre):
- Estas son cuentas de COSTO/GASTO. El objetivo es no superar el presupuesto asignado.
- Ejecución BAJA (ej. 50-70%) = BUENO: gasto controlado, holgura disponible.
- Ejecución ≥85% = ALERTA: la cuenta está próxima a su límite presupuestario.
- Ejecución ≥100% = CRÍTICO: la cuenta ya superó su presupuesto.
- Las cuentas "bien controladas" son las de menor % de ejecución. Las "críticas" son las de mayor %.

EMPRESA: {sociedad} | PERIODO: {periodo}
TOTAL REAL: ${total_r/1e6:,.1f}M | TOTAL PRESUPUESTO: ${total_p/1e6:,.1f}M | EJECUCIÓN: {(total_r/total_p*100) if total_p else 0:.1f}%
CUENTAS ANALIZADAS: {n_cuentas} | CUENTAS EN ALERTA (≥85%): {n_alertas}

TOP CUENTAS DE MAYOR RIESGO (mayor % de ejecución):
| Cuenta | Real | Presupuesto | % Ejec. |
|--------|------|-------------|---------|
{tabla}

Estructura tu respuesta exactamente así:

RESUMEN EJECUTIVO
(2 oraciones sobre el estado global, aplicando la regla de costos.)

HALLAZGOS CLAVE
1. (Cuenta con mayor % de ejecución, más cercana o sobre presupuesto — es la más riesgosa)
2. (Patrón o tendencia relevante en el conjunto de cuentas)
3. (Observación positiva: cuentas bien controladas o con buena holgura)

ALERTAS
(Cuentas con ejecución ≥85%, de mayor a menor riesgo. Si ninguna llega a 85% escribe "Sin alertas críticas.")

RECOMENDACIONES
1. (Acción concreta para la cuenta más crítica)
2. (Acción preventiva general)

Sé directo. Usa $M. No más de 250 palabras."""

    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.3,
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"❌ Error al generar análisis: {e}"


def generar_analisis_flash(datos: dict, df_top=None) -> str:
    """
    Genera comentario ejecutivo breve para el Flash Report mensual.
    datos: ventas_r/p, ebit_r/p, un_r/p, gastos_r/p, periodo, sociedad
    df_top: DataFrame con columnas cuenta, monto_r, monto_p, varianza (top desviaciones)
    """
    client = _get_client()
    if client is None:
        return "⚠ API key no configurada. Agrega `[groq] api_key` en `.streamlit/secrets.toml`."

    v_r, v_p   = datos["ventas_r"], datos["ventas_p"]
    e_r, e_p   = datos["ebit_r"],   datos["ebit_p"]
    u_r, u_p   = datos["un_r"],     datos["un_p"]
    g_r, g_p   = datos["gastos_r"], datos["gastos_p"]
    sociedad   = datos.get("sociedad", "Consolidado")
    periodo    = datos.get("periodo", "")

    def _ctx(lbl: str, r: float, p: float, es_costo: bool = False) -> str:
        """
        Genera descripción contextual correcta para la IA.
        Maneja presupuestos negativos (ej. EBIT presupuestado como pérdida).
        """
        if p == 0:
            return f"- {lbl}: Real {_fmt_m(r)} | Sin presupuesto definido"
        var = r - p
        pct = r / p * 100

        # Presupuesto negativo en línea de margen/utilidad
        if not es_costo and p < 0:
            if r >= 0:
                return (f"- {lbl}: Presupuesto era PÉRDIDA de {_fmt_m(abs(p))}, "
                        f"Real fue GANANCIA de {_fmt_m(r)} → RESULTADO EXCEPCIONAL, "
                        f"convirtió pérdida presupuestada en ganancia real "
                        f"(varianza favorable: +{_fmt_m(abs(var))})")
            elif abs(r) < abs(p):
                return (f"- {lbl}: Presupuesto era PÉRDIDA de {_fmt_m(abs(p))}, "
                        f"Real fue PÉRDIDA MENOR de {_fmt_m(abs(r))} → MEJOR QUE PRESUPUESTADO "
                        f"(varianza favorable: +{_fmt_m(abs(var))})")
            else:
                return (f"- {lbl}: Presupuesto era PÉRDIDA de {_fmt_m(abs(p))}, "
                        f"Real fue PÉRDIDA MAYOR de {_fmt_m(abs(r))} → PEOR QUE PRESUPUESTADO "
                        f"(varianza desfavorable: {_fmt_m(var)})")

        # Caso normal (ppto positivo)
        if not es_costo:
            estado = "superó el objetivo ✓" if pct >= 100 else f"BAJO presupuesto ✗"
        else:
            estado = "gasto controlado ✓" if pct <= 100 else f"SOBRE presupuesto ✗"
        return f"- {lbl}: Real {_fmt_m(r)} vs Ppto {_fmt_m(p)} → {pct:.1f}% — {estado}"

    # Top 3 desviaciones como texto
    top_txt = ""
    if df_top is not None and not df_top.empty:
        for _, row in df_top.head(3).iterrows():
            var_v = float(row["varianza"])
            signo = "+" if var_v > 0 else ""
            top_txt += (f"  - {row['cuenta'][:40]}: Real {_fmt_m(float(row['monto_r']))}, "
                        f"Ppto {_fmt_m(float(row['monto_p']))}, "
                        f"Var {signo}{_fmt_m(var_v)}\n")

    prompt = f"""Eres un controller financiero senior de una empresa chilena.
Redacta un comentario ejecutivo MUY breve (máximo 5 oraciones) para el Flash Report mensual.
Usa lenguaje directo y de negocios. Sin bullets, solo párrafo corrido.

IMPORTANTE: el contexto de cada línea ya incluye su interpretación correcta.
Lee CUIDADOSAMENTE cada descripción antes de concluir si el resultado fue bueno o malo.
Cuando dice "RESULTADO EXCEPCIONAL" o "superó el objetivo" es positivo.
Cuando dice "PEOR QUE PRESUPUESTADO" o "SOBRE presupuesto" es negativo.

EMPRESA: {sociedad} | PERIODO: {periodo}

RESUMEN FINANCIERO:
{_ctx("Ventas",   v_r, v_p, es_costo=False)}
{_ctx("EBIT",     e_r, e_p, es_costo=False)}
{_ctx("Ut. Neta", u_r, u_p, es_costo=False)}
{_ctx("Gastos",   g_r, g_p, es_costo=True)}

TOP DESVIACIONES EN COSTOS:
{top_txt if top_txt else "  Sin datos de detalle."}

Redacta el comentario ejecutivo (máximo 5 oraciones, en español):"""

    try:
        chat = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"❌ Error al generar análisis: {e}"
