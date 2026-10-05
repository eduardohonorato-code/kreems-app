"""
Reporte de Gerencia — Real vs Presupuesto, con análisis de desviaciones.

Responde primero "¿cómo vamos?" (titular, indicadores, tendencia de los últimos
meses, principales desviaciones a favor y en contra, cierre del año en dos
escenarios) y después entrega el detalle para buscar desviaciones: P&L, puente
de EBIT, gasto controlable por centro de costo, cuenta × centro de costo,
plan de acción comentado y mes a mes.

Dos salidas desde la misma estructura de datos (`construir_reporte`):
  - `to_excel(rep)` → workbook corporativo (hoja 0 = resumen para gerencia).
  - `to_html(rep)`  → página autocontenida, legible en celular e imprimible.

Convenciones:
  - «Desvío» lleva siempre el signo del efecto sobre el resultado:
    positivo = favorable (se vendió más o se gastó menos), negativo = desfavorable.
  - Montos en formato chileno ($804,9M; −$62,7M).
  - Ventas = cuentas de venta (4.1); otros ingresos van en su propia línea.

Toda la lógica de cálculo es pura (recibe DataFrames, no toca Streamlit) para
poder validarla contra la base sin levantar la app.
"""
from __future__ import annotations

import html as _html
import io
import math
import re
from datetime import datetime

import pandas as pd

from utils.db import query
from utils.components import (
    NOMBRES_CC, SOC_ACUNA, SOC_GRAN_NATURAL, ETIQUETA_SOCIEDAD,
)

# CC-00 no es un centro de costo: ahí cuelgan las ventas y el costo variable.
CC_SIN_ASIGNAR = "CC-00"
ETIQUETA_CC_SIN_ASIGNAR = "Sin centro de costo"


def _label_cc(codigo: str, nombre_fallback: str = "") -> str:
    if codigo == CC_SIN_ASIGNAR:
        return ETIQUETA_CC_SIN_ASIGNAR
    return NOMBRES_CC.get(codigo, nombre_fallback or codigo)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


# ── CONSTANTES ────────────────────────────────────────────────

ABREV_MES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

# Líneas del P&L: (etiqueta, clasificacion | None si es subtotal, clave_subtotal)
LINEAS_PL = [
    ("Ventas",                  "INGRESO",        None),
    ("Costo de Venta",          "COSTO_VAR",      None),
    ("Utilidad Bruta",          None,             "UB"),
    ("Otros Ingresos",          "OTRO_INGRESO",   None),
    ("Costo Fijo",              "COSTO_FIJO",     None),
    ("OPEX",                    "OPEX",           None),
    ("EBIT",                    None,             "EBIT"),
    ("Gastos Financieros",      "FINANCIERO",     None),
    ("Gastos No Operacionales", "NO_OPERACIONAL", None),
    ("Utilidad Neta",           None,             "UN"),
]

CLASIFS = ["INGRESO", "OTRO_INGRESO", "COSTO_VAR", "COSTO_FIJO", "OPEX",
           "FINANCIERO", "NO_OPERACIONAL"]
INGRESOS = ("INGRESO", "OTRO_INGRESO")
# Gasto que se controla por centro de costo (sin costo variable ni financieros)
CONTROLABLE = ("COSTO_FIJO", "OPEX")

ETIQUETA_LINEA = {
    "INGRESO": "Ventas",
    "OTRO_INGRESO": "Otros Ingresos",
    "COSTO_VAR": "Costo de Venta",
    "COSTO_FIJO": "Costo Fijo",
    "OPEX": "OPEX",
    "FINANCIERO": "Gastos Financieros",
    "NO_OPERACIONAL": "Gastos No Operacionales",
}

# Umbral de materialidad por defecto: bajo esto una brecha no se comenta.
UMBRAL_DEFECTO = 1_000_000
# Meses que definen la "tendencia reciente" para el segundo escenario de cierre
MESES_TENDENCIA = 3

# Paleta corporativa (misma de la app)
C_MORADO = "2D0050"
C_MORADO2 = "6B2C91"
C_FUCSIA = "C4007A"
C_VERDE = "0F6E56"
C_ROJO = "CC0000"
C_LILA_BG = "F3E9F7"
C_GRIS = "94A3B8"

_ACRONIMOS = {"I+D", "EPP", "IVA", "AFP", "LC", "T/C", "SII", "CC"}


# ── FORMATO (chileno) ─────────────────────────────────────────

def _num(x: float, dec: int = 1) -> str:
    """1234567.8 → '1.234.567,8'."""
    s = f"{abs(x):,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _es_nulo(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def fmt_m(v, signo: bool = False) -> str:
    """Millones: '$804,9M', '−$62,7M'; con signo=True los positivos llevan '+'."""
    if _es_nulo(v):
        return "—"
    r = round(float(v) / 1e6, 1)
    if r == 0:
        return "$0,0M"
    pre = "−" if r < 0 else ("+" if signo else "")
    return f"{pre}${_num(r)}M"


def fmt_pct(v, dec: int = 0) -> str:
    if _es_nulo(v):
        return "—"
    pct = float(v) * 100
    if 0 < abs(pct) < 1:
        dec = max(dec, 1)
    pre = "−" if round(pct, dec) < 0 else ""
    return f"{pre}{_num(pct, dec)}%"


def nombre_legible(nombre: str) -> str:
    """'MANTENCION EQUIPOS DE PRODUCCION' → 'Mantencion equipos de produccion'."""
    palabras = str(nombre).split()
    out = []
    for i, p in enumerate(palabras):
        if p.upper() in _ACRONIMOS:
            out.append(p.upper())
        else:
            out.append(p.capitalize() if i == 0 else p.lower())
    return " ".join(out)


# ── CARGA DE DATOS ────────────────────────────────────────────

def cargar_movimientos(ano: int, filtro_soc: str = "", filtro_cc: str = "") -> pd.DataFrame:
    """
    Trae el año completo a nivel periodo × cuenta × centro de costo.
    Se pide el año entero (no solo el YTD) porque el reporte necesita tanto el
    presupuesto comparable de los meses cerrados como el presupuesto anual y el
    de los meses que faltan para la proyección al cierre.
    """
    return query(f"""
        SELECT periodo, sociedad, codigo_cc, nombre_cc, codigo_cuenta, nombre_cuenta,
               clasificacion, categoria_eerr,
               SUM(valor_real) AS real,
               SUM(valor_ppto) AS ppto
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :d AND :h {filtro_soc} {filtro_cc}
        GROUP BY periodo, sociedad, codigo_cc, nombre_cc, codigo_cuenta, nombre_cuenta,
                 clasificacion, categoria_eerr
    """, {"d": f"{ano}-01", "h": f"{ano}-12"})


def cargar_por_sociedad(ano: int, filtro_cc: str = "") -> pd.DataFrame:
    """Real y presupuesto por sociedad — sirve para advertir si el presupuesto
    está cargado solo bajo una sociedad (comparación consolidada obligatoria)."""
    return query(f"""
        SELECT sociedad,
               SUM(valor_real) AS real,
               SUM(valor_ppto) AS ppto
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :d AND :h {filtro_cc}
        GROUP BY sociedad
        ORDER BY sociedad
    """, {"d": f"{ano}-01", "h": f"{ano}-12"})


def cargar_eliminaciones_ic(ano: int) -> pd.DataFrame:
    """Eliminaciones intercompany del año (para declararlas en la base del reporte)."""
    return query("""
        SELECT periodo, monto
        FROM staging.eliminaciones_ic
        WHERE periodo LIKE :a
        ORDER BY periodo
    """, {"a": f"{ano}-%"})


def diagnostico_corte(df: pd.DataFrame, ano: int) -> dict:
    """
    Determina hasta qué mes conviene acumular.

    El mes calendario no sirve: puede haber reales cargados a medias (una carga
    en curso). Se compara el ratio real/ppto del último mes con datos contra la
    mediana de los meses anteriores; si cae muy por debajo, el mes se marca como
    parcial y se sugiere el anterior.
    """
    if df.empty:
        return {"ultimo_real": 0, "sugerido": 0, "parcial": False,
                "ratio": 0.0, "ratio_previo": 0.0, "meses_con_real": []}

    m = df.copy()
    m["mes"] = m["periodo"].astype(str).str[5:7].astype(int)
    agg = m.groupby("mes", as_index=False)[["real", "ppto"]].sum()
    con_real = agg[agg["real"] != 0]["mes"].tolist()
    if not con_real:
        return {"ultimo_real": 0, "sugerido": 0, "parcial": False,
                "ratio": 0.0, "ratio_previo": 0.0, "meses_con_real": []}

    ultimo = int(max(con_real))
    ratios = {int(r.mes): (float(r.real) / float(r.ppto)) if r.ppto else None
              for r in agg.itertuples() if int(r.mes) in con_real}
    ratio_ult = ratios.get(ultimo) or 0.0
    previos = [v for k, v in ratios.items() if k < ultimo and v]
    ratio_prev = float(pd.Series(previos).median()) if previos else 0.0

    # Parcial si el último mes ejecutó menos del 60% de lo que ejecutan los meses
    # anteriores en promedio (y hay al menos un mes anterior para comparar).
    parcial = bool(previos) and ratio_ult < 0.60 * ratio_prev
    sugerido = (ultimo - 1) if (parcial and (ultimo - 1) in con_real) else ultimo

    return {"ultimo_real": ultimo, "sugerido": sugerido, "parcial": parcial,
            "ratio": ratio_ult, "ratio_previo": ratio_prev,
            "meses_con_real": sorted(con_real)}


# ── HELPERS DE CÁLCULO ────────────────────────────────────────

def _mes(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str[5:7].astype(int)


def _pct(r: float, p: float) -> float | None:
    """
    % de ejecución (real sobre presupuesto).

    None cuando el presupuesto es cero o negativo: dividir por un presupuesto
    negativo (el plan contempla EBIT negativo en los meses de baja temporada)
    produce porcentajes que no significan nada.
    """
    return (r / p) if p and p > 0 else None


def _efecto(clasificacion: str, var: float) -> float:
    """
    Efecto de una diferencia real − presupuesto sobre el resultado.
    En ingresos vender más suma; en cualquier gasto, gastar más resta.
    """
    return var if clasificacion in INGRESOS else -var


def _derivados(x: dict) -> dict:
    ub = x["INGRESO"] - x["COSTO_VAR"]
    ebit = ub + x["OTRO_INGRESO"] - x["COSTO_FIJO"] - x["OPEX"]
    un = ebit - x["FINANCIERO"] - x["NO_OPERACIONAL"]
    return {"UB": ub, "EBIT": ebit, "UN": un}


def _clasificar_brecha(r_mes: list, p_mes: list, umbral: float) -> tuple:
    """
    Clasifica el comportamiento de una cuenta a lo largo de los meses cerrados.

    Devuelve (tipo, mes_pico, meses_desviados). El objetivo es distinguir lo que
    un gerente necesita separar: gasto que se repite todos los meses (estructural,
    anualizable), un evento único, o plata que simplemente se movió de mes.
    """
    n = len(r_mes)
    tot_r, tot_p = sum(r_mes), sum(p_mes)
    var = tot_r - tot_p
    difs = [r_mes[i] - p_mes[i] for i in range(n)]
    disp = sum(abs(d) for d in difs)          # varianza bruta, sin compensar
    i_pico = max(range(n), key=lambda i: abs(difs[i])) if n else 0
    mes_pico = i_pico + 1

    if tot_p == 0 and tot_r == 0:
        return "Sin movimiento", mes_pico, 0
    if tot_p == 0:
        return "No presupuestado", mes_pico, sum(1 for d in difs if abs(d) > 0)
    if tot_r == 0:
        return "No ejecutado", mes_pico, n

    if abs(var) < umbral:
        # El acumulado cuadra: si igual hubo vaivén mes a mes, es desfase.
        if disp > max(2 * abs(var), umbral):
            return "Desfase de calendario", mes_pico, sum(
                1 for d in difs if abs(d) > umbral / max(n, 1))
        return "En línea", mes_pico, 0

    conc = (abs(difs[i_pico]) / disp) if disp else 0.0
    signo = 1 if var > 0 else -1
    piso = umbral / max(n, 1)
    meses_desv = sum(1 for d in difs if d * signo > piso)

    if conc >= 0.70:
        return "Puntual", mes_pico, meses_desv
    if meses_desv >= math.ceil(0.60 * n):
        return "Recurrente", mes_pico, meses_desv
    return "Mixto", mes_pico, meses_desv


def _label_sociedad(ac: float, gn: float) -> str:
    """
    De qué sociedad viene el monto: 'ACUÑA 81%', 'Gran Natural 63%' o 'ACUÑA'.

    Siempre lleva el porcentaje de la sociedad que predomina; el nombre a secas
    queda reservado para el 100%. Se usa el valor absoluto para el reparto,
    porque hay cuentas con reversas (notas de crédito).
    """
    ac, gn = abs(ac), abs(gn)
    total = ac + gn
    if total == 0:
        return "—"
    p_ac = ac / total
    if p_ac >= 0.5:
        dominante, p = ETIQUETA_SOCIEDAD[SOC_ACUNA], p_ac
    else:
        dominante, p = ETIQUETA_SOCIEDAD[SOC_GRAN_NATURAL], 1 - p_ac
    return dominante if p >= 0.995 else f"{dominante} {p*100:.0f}%"


def _texto_meses(pares: list) -> str:
    """'Abr −$11,4M · May −$11,0M' — meses en que la cuenta se desvió en contra."""
    if not pares:
        return "—"
    return " · ".join(f"{ABREV_MES[m]} {fmt_m(v, signo=True)}" for m, v in pares)


# ── CONSTRUCCIÓN DEL REPORTE ──────────────────────────────────

def construir_reporte(df: pd.DataFrame, ano: int, mes_corte: int,
                      sociedad_lbl: str, umbral: float = UMBRAL_DEFECTO,
                      df_soc: pd.DataFrame | None = None,
                      diag: dict | None = None,
                      elim_ic: pd.DataFrame | None = None,
                      notas: dict | None = None) -> dict:
    """
    Arma todos los bloques del reporte a partir del detalle anual.

    `df` viene de `cargar_movimientos` (año completo). `mes_corte` define el YTD:
    el real se compara contra el presupuesto de esos MISMOS meses, nunca contra
    el presupuesto anual. `notas` = {(codigo_cuenta, codigo_cc): {...}} con los
    comentarios del plan de acción (utils.notas.obtener_notas_desvio).
    """
    notas = notas or {}
    d = df.copy()
    d["mes"] = _mes(d["periodo"])
    d["real"] = pd.to_numeric(d["real"], errors="coerce").fillna(0.0)
    d["ppto"] = pd.to_numeric(d["ppto"], errors="coerce").fillna(0.0)
    d["clasificacion"] = d["clasificacion"].fillna("SIN_CLASIFICAR")
    # Ventas = cuentas de venta; el resto de los ingresos operacionales va aparte
    es_oi = (d["clasificacion"] == "INGRESO") & (d["categoria_eerr"] != "Ventas Brutas")
    d.loc[es_oi, "clasificacion"] = "OTRO_INGRESO"
    # Ingresos clasificados como no operacionales (4.2.x): restan del gasto no operacional
    ing_noop = (d["clasificacion"] == "NO_OPERACIONAL") & d["codigo_cuenta"].str.startswith("4.")
    d.loc[ing_noop, ["real", "ppto"]] *= -1

    meses = list(range(1, mes_corte + 1))
    etiquetas_mes = [ABREV_MES[m] for m in meses]
    ytd = d[d["mes"] <= mes_corte]
    resto = d[d["mes"] > mes_corte]
    k = min(MESES_TENDENCIA, mes_corte)
    reciente = d[(d["mes"] > mes_corte - k) & (d["mes"] <= mes_corte)]
    rec_lbl = (f"{ABREV_MES[mes_corte - k + 1]}–{ABREV_MES[mes_corte]}"
               if k > 1 else ABREV_MES.get(mes_corte, ""))

    def _mix(claves: list, frame: pd.DataFrame) -> pd.DataFrame:
        piv = frame.pivot_table(index=claves, columns="sociedad", values="real",
                                aggfunc="sum", fill_value=0.0)
        for soc in (SOC_ACUNA, SOC_GRAN_NATURAL):
            if soc not in piv.columns:
                piv[soc] = 0.0
        return piv

    mix_cta = _mix(["codigo_cc", "codigo_cuenta"], ytd)
    ctrl_ytd = ytd[ytd["clasificacion"].isin(CONTROLABLE)]
    mix_cc = _mix(["codigo_cc"], ctrl_ytd)
    _vta = ytd[ytd["clasificacion"] == "INGRESO"]
    vta_ac = float(_vta.loc[_vta["sociedad"] == SOC_ACUNA, "real"].sum())
    vta_gn = float(_vta.loc[_vta["sociedad"] == SOC_GRAN_NATURAL, "real"].sum())

    # ── 1. P&L YTD por clasificación ──────────────────────────
    def _tot(frame: pd.DataFrame, col: str) -> dict:
        return {c: float(frame.loc[frame["clasificacion"] == c, col].sum()) for c in CLASIFS}

    R, P = _tot(ytd, "real"), _tot(ytd, "ppto")
    PA, PR = _tot(d, "ppto"), _tot(resto, "ppto")
    RK, PK = _tot(reciente, "real"), _tot(reciente, "ppto")
    # Ritmo reciente de cada línea: real / presupuesto de los últimos k meses
    RITMO = {c: (RK[c] / PK[c]) if PK[c] > 0 else 1.0 for c in CLASIFS}
    TR = {c: PR[c] * RITMO[c] for c in CLASIFS}             # restante según tendencia
    CP = {c: R[c] + PR[c] for c in CLASIFS}                  # cierre según ppto
    CT = {c: R[c] + TR[c] for c in CLASIFS}                  # cierre según tendencia

    DR, DP, DPA = _derivados(R), _derivados(P), _derivados(PA)
    DRK, DPK = _derivados(RK), _derivados(PK)
    DCP, DCT = _derivados(CP), _derivados(CT)

    filas_pl = []
    for etiqueta, clasif, sub in LINEAS_PL:
        rv = R[clasif] if clasif else DR[sub]
        pv = P[clasif] if clasif else DP[sub]
        pa = PA[clasif] if clasif else DPA[sub]
        filas_pl.append({
            "Línea": etiqueta,
            "Real YTD": rv,
            "Ppto YTD": pv,
            "Desvío": _efecto(clasif, rv - pv) if clasif else rv - pv,
            "% Ejec.": _pct(rv, pv),
            "% s/Ventas": (rv / R["INGRESO"]) if R["INGRESO"] else None,
            "Ppto Año": pa,
            # Con resultado negativo, "% del presupuesto anual consumido" no significa nada
            "% Ppto Año consumido": _pct(rv, pa) if (clasif or rv > 0) else None,
            "_subtotal": sub is not None,
            "_clasif": clasif or sub,
        })
    df_pl = pd.DataFrame(filas_pl)
    # Una línea sin real ni presupuesto en el año no aporta (p. ej. otros ingresos)
    df_pl = df_pl[df_pl["_subtotal"] | (df_pl["Real YTD"] != 0) | (df_pl["Ppto Año"] != 0)]
    df_pl = df_pl.reset_index(drop=True)

    margenes = []
    for nombre, clave in [("Margen Bruto", "UB"), ("Margen EBIT", "EBIT"), ("Margen Neto", "UN")]:
        mr = (DR[clave] / R["INGRESO"]) if R["INGRESO"] else 0.0
        mp = (DP[clave] / P["INGRESO"]) if P["INGRESO"] else 0.0
        margenes.append({"Margen": nombre, "Real": mr, "Ppto": mp, "Δ pp": (mr - mp) * 100})
    df_margenes = pd.DataFrame(margenes)

    # ── 2. Puente de EBIT ─────────────────────────────────────
    # El efecto de volumen se valoriza al margen de contribución presupuestado y
    # el costo variable se mide contra el que correspondería a las ventas reales:
    # así una caída de ventas no aparece como "ahorro" de costo variable.
    tasa_cv = (P["COSTO_VAR"] / P["INGRESO"]) if P["INGRESO"] else 0.0
    ef_volumen = (R["INGRESO"] - P["INGRESO"]) * (1 - tasa_cv)
    ef_cv = -(R["COSTO_VAR"] - R["INGRESO"] * tasa_cv)
    ef_otros_ing = R["OTRO_INGRESO"] - P["OTRO_INGRESO"]

    puente = [
        {"Concepto": "EBIT presupuestado", "Efecto": DP["EBIT"], "Tipo": "inicio"},
        {"Concepto": "Ventas (volumen y precio)", "Efecto": ef_volumen, "Tipo": "efecto"},
        {"Concepto": "Costo variable (eficiencia y mix)", "Efecto": ef_cv, "Tipo": "efecto"},
    ]
    if abs(ef_otros_ing) > 0:
        puente.append({"Concepto": "Otros ingresos", "Efecto": ef_otros_ing, "Tipo": "efecto"})

    ccs = sorted(set(d["codigo_cc"].dropna()) - {CC_SIN_ASIGNAR})
    ef_ctrl = 0.0
    for clasif, etiqueta in [("COSTO_FIJO", "Costo fijo"), ("OPEX", "OPEX")]:
        for cc in ccs:
            sub = ytd[(ytd["clasificacion"] == clasif) & (ytd["codigo_cc"] == cc)]
            v = float(sub["real"].sum() - sub["ppto"].sum())
            if abs(v) < 1:
                continue
            puente.append({"Concepto": f"{etiqueta} {NOMBRES_CC.get(cc, cc)}",
                           "Efecto": -v, "Tipo": "efecto"})
            ef_ctrl -= v
        sub0 = ytd[(ytd["clasificacion"] == clasif) & (~ytd["codigo_cc"].isin(ccs))]
        v0 = float(sub0["real"].sum() - sub0["ppto"].sum())
        if abs(v0) >= 1:
            puente.append({"Concepto": f"{etiqueta} sin centro de costo",
                           "Efecto": -v0, "Tipo": "efecto"})
            ef_ctrl -= v0

    puente.append({"Concepto": "EBIT real", "Efecto": DR["EBIT"], "Tipo": "fin"})
    df_puente = pd.DataFrame(puente)
    suma_efectos = float(df_puente.loc[df_puente["Tipo"] == "efecto", "Efecto"].sum())
    descuadre = DP["EBIT"] + suma_efectos - DR["EBIT"]

    # ── 3. Gasto controlable por centro de costo ──────────────
    ctrl = d[d["clasificacion"].isin(CONTROLABLE)]
    filas_cc = []
    for cc in sorted(set(ctrl["codigo_cc"].dropna())):
        s = ctrl[ctrl["codigo_cc"] == cc]
        sy = s[s["mes"] <= mes_corte]
        rv, pv = float(sy["real"].sum()), float(sy["ppto"].sum())
        pa = float(s["ppto"].sum())
        pr = float(s.loc[s["mes"] > mes_corte, "ppto"].sum())
        sk = s[(s["mes"] > mes_corte - k) & (s["mes"] <= mes_corte)]
        rk, pk = float(sk["real"].sum()), float(sk["ppto"].sum())
        ritmo = (rk / pk) if pk > 0 else 1.0
        if rv == 0 and pv == 0 and pa == 0:
            continue
        filas_cc.append({
            "Centro de costo": _label_cc(cc, s["nombre_cc"].iloc[0] if len(s) else cc),
            "Código": cc,
            "Sociedad": (_label_sociedad(mix_cc.loc[cc, SOC_ACUNA],
                                         mix_cc.loc[cc, SOC_GRAN_NATURAL])
                         if cc in mix_cc.index else "—"),
            "Real YTD": rv,
            "Ppto YTD": pv,
            "Desvío": pv - rv,
            "% Ejec.": _pct(rv, pv),
            "Ppto Año": pa,
            "% Ppto Año consumido": _pct(rv, pa),
            "Cierre según ppto": rv + pr,
            "Cierre según tendencia": rv + pr * ritmo,
        })
    df_cc = (pd.DataFrame(filas_cc).sort_values("Código").reset_index(drop=True)
             if filas_cc else pd.DataFrame())

    filas_ccl = []
    for cc in sorted(set(ctrl_ytd["codigo_cc"].dropna())):
        for clasif in CONTROLABLE:
            s = ctrl_ytd[(ctrl_ytd["codigo_cc"] == cc) & (ctrl_ytd["clasificacion"] == clasif)]
            rv, pv = float(s["real"].sum()), float(s["ppto"].sum())
            if rv == 0 and pv == 0:
                continue
            filas_ccl.append({
                "Centro de costo": _label_cc(cc),
                "Línea": ETIQUETA_LINEA[clasif],
                "Real YTD": rv, "Ppto YTD": pv, "Desvío": pv - rv, "% Ejec.": _pct(rv, pv),
            })
    df_cc_linea = pd.DataFrame(filas_ccl)

    # ── 4. Detalle por cuenta × centro de costo ───────────────
    piv_r = ytd.pivot_table(index=["codigo_cc", "codigo_cuenta"], columns="mes",
                            values="real", aggfunc="sum", fill_value=0.0)
    piv_p = ytd.pivot_table(index=["codigo_cc", "codigo_cuenta"], columns="mes",
                            values="ppto", aggfunc="sum", fill_value=0.0)
    meta_cta = (d.groupby(["codigo_cc", "codigo_cuenta"])
                  .agg(nombre_cuenta=("nombre_cuenta", "first"),
                       nombre_cc=("nombre_cc", "first"),
                       clasificacion=("clasificacion", "first"),
                       categoria_eerr=("categoria_eerr", "first"),
                       ppto_anual=("ppto", "sum")))
    ppto_resto = resto.groupby(["codigo_cc", "codigo_cuenta"])["ppto"].sum()
    cols_mes = [f"Desvío {ABREV_MES[m]}" for m in meses]
    piso = umbral / max(mes_corte, 1)

    filas_det = []
    for idx in piv_r.index.union(piv_p.index):
        r_mes = [float(piv_r.loc[idx, m]) if (idx in piv_r.index and m in piv_r.columns) else 0.0
                 for m in meses]
        p_mes = [float(piv_p.loc[idx, m]) if (idx in piv_p.index and m in piv_p.columns) else 0.0
                 for m in meses]
        rv, pv = sum(r_mes), sum(p_mes)
        if (rv == 0 and pv == 0) or idx not in meta_cta.index:
            continue
        info = meta_cta.loc[idx]
        cc, cuenta = idx
        clasif = info["clasificacion"]
        tipo, mes_pico, _ = _clasificar_brecha(r_mes, p_mes, umbral)
        desvio = _efecto(clasif, rv - pv)
        desv_mes = [_efecto(clasif, r_mes[i] - p_mes[i]) for i in range(len(meses))]
        exceso = [(meses[i], desv_mes[i]) for i in range(len(meses)) if desv_mes[i] < -piso]
        # Solo se anualizan los gastos recurrentes: extrapolar ventas x12 en un
        # negocio estacional daría una cifra sin sentido.
        anualizado = (desvio / mes_corte * 12) if (
            tipo == "Recurrente" and mes_corte and clasif not in INGRESOS) else None
        nota = notas.get((cuenta, cc), {})

        fila = {
            "Centro de costo": _label_cc(cc, info["nombre_cc"]),
            "Código CC": cc,
            "Cuenta": f"{cuenta} {info['nombre_cuenta']}",
            "Sociedad": (_label_sociedad(mix_cta.loc[idx, SOC_ACUNA],
                                         mix_cta.loc[idx, SOC_GRAN_NATURAL])
                         if idx in mix_cta.index else "—"),
            "Línea P&L": ETIQUETA_LINEA.get(clasif, clasif),
            "Categoría EERR": info["categoria_eerr"],
            "Real YTD": rv,
            "Ppto YTD": pv,
            "Desvío": desvio,
            "% Ejec.": _pct(rv, pv),
            "Tipo de brecha": tipo,
            "Meses desfavorables": _texto_meses(exceso),
            "Mes pico": ABREV_MES.get(mes_pico, ""),
            "Si se mantiene 12m": anualizado,
            "Ppto Año": float(info["ppto_anual"]),
            "Cierre según ppto": rv + float(ppto_resto.get(idx, 0.0)),
            "Comentario": nota.get("explicacion", ""),
            "_clasif": clasif,
            "_cuenta": cuenta,
            "_cc": cc,
            "_nombre": nombre_legible(info["nombre_cuenta"]),
            "_meses_desfav": exceso,
            "_real_mes": r_mes,
            "_ppto_mes": p_mes,
        }
        for i, mm in enumerate(meses):
            fila[f"Desvío {ABREV_MES[mm]}"] = desv_mes[i]
        filas_det.append(fila)

    df_det = pd.DataFrame(filas_det)
    if not df_det.empty:
        df_det = (df_det.reindex(df_det["Desvío"].abs().sort_values(ascending=False).index)
                  .reset_index(drop=True))

    # ── 5. Principales desviaciones y plan de acción ──────────
    # El costo variable se explica por el volumen en el puente: no se lista aquí.
    cols_top = ["Cuenta", "Centro de costo", "Real YTD", "Ppto YTD", "Desvío",
                "Tipo de brecha", "Comentario", "_cuenta", "_cc", "_nombre", "_clasif"]
    if not df_det.empty:
        base_top = df_det[df_det["_clasif"] != "COSTO_VAR"]
        top_desf = base_top[base_top["Desvío"] <= -umbral].nsmallest(5, "Desvío")[cols_top]
        top_fav = base_top[base_top["Desvío"] >= umbral].nlargest(5, "Desvío")[cols_top]
        desfav = df_det[df_det["Desvío"] <= -umbral].sort_values("Desvío").copy()
    else:
        top_desf = top_fav = desfav = pd.DataFrame()

    if not desfav.empty:
        total_desfav = float(-desfav["Desvío"].sum())
        acum = (-desfav["Desvío"]).cumsum()
        # Corte Pareto: hasta explicar el 80% de lo desfavorable (mínimo 5 líneas)
        n_pareto = max(int((acum <= 0.80 * total_desfav).sum()) + 1, min(5, len(desfav)))
        df_accion = desfav.head(n_pareto).copy()
        claves = list(zip(df_accion["_cuenta"], df_accion["_cc"]))
        for col, campo in [("Explicación", "explicacion"), ("Acción comprometida", "accion"),
                           ("Responsable", "responsable"), ("Fecha compromiso", "fecha")]:
            df_accion[col] = [notas.get(c, {}).get(campo, None if campo == "fecha" else "")
                              for c in claves]
        df_accion = df_accion[[
            "Centro de costo", "Cuenta", "Sociedad", "Línea P&L", "Real YTD", "Ppto YTD",
            "Desvío", "Tipo de brecha", "Meses desfavorables", "Si se mantiene 12m",
            "Explicación", "Acción comprometida", "Responsable", "Fecha compromiso",
            *cols_mes, "_cuenta", "_cc", "_nombre", "_clasif", "_real_mes", "_ppto_mes",
        ]].reset_index(drop=True)
    else:
        total_desfav = 0.0
        df_accion = pd.DataFrame()

    # ── 6. Mes a mes ──────────────────────────────────────────
    filas_mm = []
    for cc in sorted(set(ctrl_ytd["codigo_cc"].dropna())):
        s = ctrl_ytd[ctrl_ytd["codigo_cc"] == cc]
        vals = {}
        for concepto, col in [("Real", "real"), ("Ppto", "ppto")]:
            fila = {"Centro de costo": _label_cc(cc), "Concepto": concepto}
            for m in meses:
                fila[ABREV_MES[m]] = float(s.loc[s["mes"] == m, col].sum())
            fila["Total YTD"] = sum(fila[ABREV_MES[m]] for m in meses)
            vals[concepto] = fila
            filas_mm.append(fila)
        fila_v = {"Centro de costo": _label_cc(cc), "Concepto": "Desvío"}
        for c in [ABREV_MES[m] for m in meses] + ["Total YTD"]:
            fila_v[c] = vals["Ppto"][c] - vals["Real"][c]
        filas_mm.append(fila_v)
    df_mes_cc = pd.DataFrame(filas_mm)

    def _por_mes(frame: pd.DataFrame, col: str, m: int) -> dict:
        mm = frame[frame["mes"] == m]
        base = {c: float(mm.loc[mm["clasificacion"] == c, col].sum()) for c in CLASIFS}
        return {**base, **_derivados(base)}

    filas_plm = []
    for etiqueta, clasif, sub in LINEAS_PL:
        if etiqueta not in set(df_pl["Línea"]):
            continue
        for concepto, col in [("Real", "real"), ("Ppto", "ppto")]:
            fila = {"Línea": etiqueta, "Concepto": concepto}
            for m in meses:
                fila[ABREV_MES[m]] = _por_mes(ytd, col, m)[clasif or sub]
            fila["Total YTD"] = sum(fila[ABREV_MES[m]] for m in meses)
            filas_plm.append(fila)
    df_mes_pl = pd.DataFrame(filas_plm)

    filas_ctam = []
    if not df_det.empty:
        for _, r in df_det[df_det["Desvío"].abs() >= umbral].iterrows():
            desv = [_efecto(r["_clasif"], r["_real_mes"][i] - r["_ppto_mes"][i])
                    for i in range(len(meses))]
            for concepto, serie in [("Real", r["_real_mes"]), ("Ppto", r["_ppto_mes"]),
                                    ("Desvío", desv)]:
                fila = {"Centro de costo": r["Centro de costo"], "Cuenta": r["Cuenta"],
                        "Concepto": concepto}
                for i, mm in enumerate(meses):
                    fila[ABREV_MES[mm]] = float(serie[i])
                fila["Total YTD"] = float(sum(serie))
                filas_ctam.append(fila)
    df_mes_cuenta = pd.DataFrame(filas_ctam)

    # Serie de los 12 meses para los gráficos: real hasta el corte, ppto todo el año
    serie = []
    for m in range(1, 13):
        rr, pp = _por_mes(d, "real", m), _por_mes(d, "ppto", m)
        serie.append({
            "Mes": ABREV_MES[m], "mes": m,
            "Ventas real": rr["INGRESO"] if m <= mes_corte else None,
            "Ventas ppto": pp["INGRESO"],
            "EBIT real": rr["EBIT"] if m <= mes_corte else None,
            "EBIT ppto": pp["EBIT"],
        })
    df_serie = pd.DataFrame(serie)

    # ── 7. Cierre del año en dos escenarios ───────────────────
    filas_proy = []
    for etiqueta, clasif, sub in LINEAS_PL:
        if etiqueta not in set(df_pl["Línea"]):
            continue
        rv = R[clasif] if clasif else DR[sub]
        pa = PA[clasif] if clasif else DPA[sub]
        cp = CP[clasif] if clasif else DCP[sub]
        ct = CT[clasif] if clasif else DCT[sub]
        signo = 1 if (clasif in INGRESOS or not clasif) else -1
        filas_proy.append({
            "Línea": etiqueta,
            "Real YTD": rv,
            "Ppto restante": PR[clasif] if clasif else _derivados(PR)[sub],
            f"Ritmo {rec_lbl}": RITMO[clasif] if clasif and PK[clasif] > 0 else None,
            "Cierre según ppto": cp,
            "Cierre según tendencia": ct,
            "Ppto Año": pa,
            "Desvío (según ppto)": signo * (cp - pa),
            "Desvío (según tendencia)": signo * (ct - pa),
            "_subtotal": sub is not None,
        })
    df_proy = pd.DataFrame(filas_proy)

    # ── 8. Base de comparación, escalas y criterios ───────────
    alertas = []
    corte_parcial = bool(diag and diag.get("parcial")
                         and mes_corte >= diag.get("ultimo_real", 0))
    if diag and diag.get("parcial"):
        mes_p = ABREV_MES.get(diag["ultimo_real"], "")
        if corte_parcial:
            alertas.append(
                f"{mes_p} está cargado a medias ({diag['ratio']*100:.0f}% de su presupuesto "
                f"contra {diag['ratio_previo']*100:.0f}% típico) y este reporte lo INCLUYE: "
                f"los ahorros de gasto están sobrestimados. Para una lectura firme, cortar en "
                f"{ABREV_MES.get(diag['sugerido'], '')}.")
        else:
            alertas.append(
                f"{mes_p} está cargado a medias ({diag['ratio']*100:.0f}% de su presupuesto "
                f"contra {diag['ratio_previo']*100:.0f}% típico): el reporte se corta en "
                f"{ABREV_MES.get(mes_corte, '')} para no mostrar como ahorro facturas por cargar.")

    if elim_ic is not None and not elim_ic.empty:
        e = elim_ic.copy()
        e["mes"] = _mes(e["periodo"])
        e["monto"] = pd.to_numeric(e["monto"], errors="coerce").fillna(0.0)
        e = e[e["mes"] <= mes_corte]
        if not e.empty:
            detalle_ic = " · ".join(f"{ABREV_MES[int(r.mes)]} {fmt_m(r.monto)}" for r in e.itertuples())
            alertas.append(
                f"Las ventas y el costo de personal excluyen {fmt_m(e['monto'].sum())} de "
                f"facturas intercompany ACUÑA → Gran Natural ({detalle_ic}). No son ventas "
                f"del negocio: comparar con reportes anteriores puede mostrar diferencias.")

    if df_soc is not None and not df_soc.empty:
        s = df_soc.copy()
        s["real"] = pd.to_numeric(s["real"], errors="coerce").fillna(0.0)
        s["ppto"] = pd.to_numeric(s["ppto"], errors="coerce").fillna(0.0)
        sin_ppto = s[(s["ppto"] == 0) & (s["real"] > 0)]["sociedad"].tolist()
        if sin_ppto:
            alertas.append(
                "El presupuesto es uno solo para el negocio (cargado bajo Gran Natural): "
                "la comparación válida es la consolidada. Una sociedad sola contra "
                "presupuesto no es comparable.")

    if not df_det.empty:
        sin_p = df_det[(df_det["Tipo de brecha"] == "No presupuestado") &
                       (~df_det["_clasif"].isin(INGRESOS))]
        if not sin_p.empty:
            alertas.append(
                f"{_plural(len(sin_p), 'cuenta de gasto', 'cuentas de gasto')} con real y sin "
                f"presupuesto ({fmt_m(sin_p['Real YTD'].sum())} acumulado): requieren "
                f"presupuesto o reclasificación.")
    if abs(descuadre) > 1:
        alertas.append(f"Descuadre en el puente de EBIT: ${descuadre:,.0f}. Revisar clasificaciones.")

    escalas = [
        f"Acumulado Ene–{ABREV_MES.get(mes_corte, '')} ({mes_corte} de 12 meses): «Real YTD», "
        f"«Ppto YTD», «Desvío» y «% Ejec.». El real se compara siempre contra el presupuesto "
        f"de esos mismos meses, nunca contra el anual.",
        "Valor de cada mes (no acumulado): gráficos, tablas mes a mes y columnas «Desvío <mes>».",
        "Año completo: «Ppto Año», «% Ppto Año consumido» y los cierres proyectados. Un centro "
        "de costo puede ir sobre su presupuesto de los meses transcurridos y, a la vez, llevar "
        "consumido menos de la mitad del anual: ambas cifras son correctas.",
    ]

    bases = [
        "«Desvío» lleva el signo del efecto sobre el resultado: positivo = favorable "
        "(se vendió más o se gastó menos), negativo = desfavorable.",
        "Ventas = cuentas de venta (4.1), registradas sin centro de costo. Otros ingresos "
        "operacionales van en su propia línea.",
        "Gasto controlable = costo fijo + OPEX, abierto por centro de costo. El costo de venta "
        "se explica por el volumen en el puente de EBIT.",
        f"Cierre según tendencia: el presupuesto de los meses que faltan se ajusta por el ritmo "
        f"real/presupuesto de cada línea en {rec_lbl}. Cierre según presupuesto: los meses que "
        f"faltan se cumplen al 100%.",
        f"Materialidad: {fmt_m(umbral)} por cuenta y centro de costo.",
        "El margen bruto es un margen de contribución: parte del costo de fábrica está en el "
        "costo fijo de Producción. El costo de venta proviene de carga manual.",
        "Fuente: marts.vw_real_vs_ppto (real desde Obuma; presupuesto editable en la app). "
        "Cifras en pesos chilenos; «M» = millones.",
    ]

    # ── 9. Titular y conclusiones ─────────────────────────────
    titular = _titular(R, P, DR, DP, DPA, DRK, DPK, DCP, DCT, RK, PK, rec_lbl, k,
                       ef_volumen + ef_cv, ef_ctrl, ef_otros_ing, mes_corte,
                       corte_parcial, diag)
    conclusiones = _conclusiones(df_cc, df_det, umbral, mes_corte)

    _tot_soc = abs(vta_ac) + abs(vta_gn)
    mix_lbl = (f"{ETIQUETA_SOCIEDAD[SOC_ACUNA]} {fmt_m(vta_ac)} "
               f"({abs(vta_ac)/_tot_soc*100:.0f}%) · "
               f"{ETIQUETA_SOCIEDAD[SOC_GRAN_NATURAL]} {fmt_m(vta_gn)} "
               f"({abs(vta_gn)/_tot_soc*100:.0f}%)") if _tot_soc else "—"

    return {
        "meta": {
            "ano": ano, "mes_corte": mes_corte, "n_meses": mes_corte,
            "mix_sociedad": mix_lbl,
            "mes_corte_nombre": ABREV_MES.get(mes_corte, ""),
            "periodo_lbl": f"Ene–{ABREV_MES.get(mes_corte, '')} {ano}",
            "sociedad": sociedad_lbl,
            "umbral": umbral,
            "generado": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "meses": etiquetas_mes,
            "rec_lbl": rec_lbl, "k": k,
        },
        "kpi": {
            "ventas_r": R["INGRESO"], "ventas_p": P["INGRESO"],
            "ub_r": DR["UB"], "ub_p": DP["UB"],
            "ctrl_r": R["COSTO_FIJO"] + R["OPEX"], "ctrl_p": P["COSTO_FIJO"] + P["OPEX"],
            "ebit_r": DR["EBIT"], "ebit_p": DP["EBIT"],
            "un_r": DR["UN"], "un_p": DP["UN"],
            "ebit_cierre_ppto": DCP["EBIT"], "ebit_cierre_tend": DCT["EBIT"],
            "ebit_ppto_ano": DPA["EBIT"],
            "ventas_cierre_ppto": CP["INGRESO"], "ventas_cierre_tend": CT["INGRESO"],
            "ventas_ppto_ano": PA["INGRESO"],
            "ritmo_ventas": RITMO["INGRESO"],
            "ebit_rec_r": DRK["EBIT"], "ebit_rec_p": DPK["EBIT"],
        },
        "titular": titular,
        "conclusiones": conclusiones,
        "pl": df_pl,
        "margenes": df_margenes,
        "puente": df_puente,
        "descuadre": descuadre,
        "cc": df_cc,
        "cc_linea": df_cc_linea,
        "detalle": df_det,
        "top_desfav": top_desf,
        "top_fav": top_fav,
        "accion": df_accion,
        "total_desfavorable": total_desfav,
        "mes_cc": df_mes_cc,
        "mes_pl": df_mes_pl,
        "mes_cuenta": df_mes_cuenta,
        "serie": df_serie,
        "cols_mes": cols_mes,
        "proyeccion": df_proy,
        "alertas": alertas,
        "escalas": escalas,
        "bases": bases,
    }


def _titular(R, P, DR, DP, DPA, DRK, DPK, DCP, DCT, RK, PK, rec_lbl, k,
             ef_ventas, ef_ctrl, ef_oi, mes_corte, corte_parcial, diag) -> list:
    """
    La respuesta a "¿cómo vamos con el presupuesto?" en 3-4 frases: resultado
    acumulado, qué lo explica, hacia dónde va la tendencia y cómo cerraría el año.
    Reglas deterministas: el mismo dato produce siempre el mismo texto.
    """
    if not any(P.values()):
        return [f"Esta selección no tiene presupuesto cargado: el EBIT real acumulado es "
                f"{fmt_m(DR['EBIT'])} y no hay contra qué medirlo. Usa la vista consolidada."]

    out = []
    gap = DR["EBIT"] - DP["EBIT"]
    out.append(
        f"EBIT acumulado {fmt_m(DR['EBIT'])} contra {fmt_m(DP['EBIT'])} presupuestado: "
        f"vamos {fmt_m(abs(gap))} {'mejor' if gap >= 0 else 'peor'} que el presupuesto "
        f"de Ene–{ABREV_MES.get(mes_corte, '')}.")

    pct_v = _pct(R["INGRESO"], P["INGRESO"])
    piezas = [(f"ventas y costo de venta {fmt_m(ef_ventas, signo=True)}"
               f" (ventas al {fmt_pct(pct_v)} del presupuesto)", ef_ventas),
              (f"gasto controlable {fmt_m(ef_ctrl, signo=True)}"
               f" ({'bajo' if ef_ctrl >= 0 else 'sobre'} presupuesto)", ef_ctrl)]
    if abs(ef_oi) >= 1e6:
        piezas.append((f"otros ingresos {fmt_m(ef_oi, signo=True)}", ef_oi))
    piezas.sort(key=lambda x: abs(x[1]), reverse=True)
    out.append("Lo explican: " + "; ".join(p for p, _ in piezas) + ".")

    if k >= 2 and PK["INGRESO"] > 0:
        gap_k = DRK["EBIT"] - DPK["EBIT"]
        ritmo = RK["INGRESO"] / PK["INGRESO"]
        frase = (f"Últimos {k} meses ({rec_lbl}): ventas al {fmt_pct(ritmo)} del presupuesto "
                 f"y EBIT {fmt_m(gap_k, signo=True)} contra el presupuesto de esos meses")
        if (gap_k < 0) != (gap < 0):
            frase += " — la tendencia reciente va en sentido contrario al acumulado"
        out.append(frase + ".")

    out.append(
        f"Cierre del año: EBIT {fmt_m(DCT['EBIT'])} si se mantiene el ritmo de {rec_lbl}, "
        f"{fmt_m(DCP['EBIT'])} si se cumple el presupuesto de los meses que faltan "
        f"(presupuesto anual {fmt_m(DPA['EBIT'])}).")

    if corte_parcial and diag:
        out.insert(0, f"Lectura condicionada: {ABREV_MES.get(diag['ultimo_real'], '')} está "
                      f"cargado a medias, los ahorros de gasto están sobrestimados.")
    return out


def _conclusiones(df_cc, df_det, umbral, mes_corte) -> list:
    """Hallazgos del análisis detallado (complementan el titular)."""
    out = []
    if not df_cc.empty:
        cc_op = df_cc[df_cc["Código"] != CC_SIN_ASIGNAR]
        if not cc_op.empty:
            top = cc_op.loc[cc_op["Desvío"].abs().idxmax()]
            imp = float(top["Desvío"])
            out.append(
                f"{top['Centro de costo']} es el centro de costo con mayor desvío: "
                f"{fmt_m(imp, signo=True)} ({fmt_pct(top['% Ejec.'])} de ejecución); lleva "
                f"consumido el {fmt_pct(top['% Ppto Año consumido'])} de su presupuesto anual "
                f"con {mes_corte} de 12 meses.")

    if df_det.empty:
        return out
    desf = df_det[(df_det["Desvío"] <= -umbral) & (~df_det["_clasif"].isin(INGRESOS))]
    if not desf.empty:
        partes = []
        for tipo, txt in [("Recurrente", "recurrente"),
                          ("Puntual", "puntual"), ("No presupuestado", "sin presupuesto")]:
            sub = desf[desf["Tipo de brecha"] == tipo]
            if not sub.empty:
                extra = ""
                if tipo == "Recurrente":
                    anual = sub["Si se mantiene 12m"].fillna(0).sum()
                    extra = f", {fmt_m(anual)} en el año si se mantiene"
                partes.append(f"{fmt_m(sub['Desvío'].sum())} {txt} "
                              f"({_plural(len(sub), 'cuenta', 'cuentas')}{extra})")
        if partes:
            out.append("Sobregasto sobre la materialidad: " + "; ".join(partes) + ".")

    fav = df_det[(df_det["Desvío"] >= umbral) & (~df_det["_clasif"].isin(INGRESOS))
                 & (df_det["_clasif"] != "COSTO_VAR")]
    if not fav.empty:
        out.append(
            f"Gasto bajo presupuesto: {fmt_m(fav['Desvío'].sum())} en "
            f"{_plural(len(fav), 'cuenta', 'cuentas')}. Antes de leerlo como ahorro, confirmar "
            f"con contabilidad que no sean facturas pendientes de registrar.")

    desfase = df_det[df_det["Tipo de brecha"] == "Desfase de calendario"]
    if not desfase.empty:
        out.append(
            f"{_plural(len(desfase), 'cuenta muestra', 'cuentas muestran')} desfase de "
            f"calendario: el acumulado cuadra pero el gasto cayó en otros meses. No es ahorro "
            f"ni sobregasto; conviene corregir la mensualización del presupuesto.")
    return out


# ── EXPORT EXCEL ──────────────────────────────────────────────

_FMT_M = '#,##0.0,, "M"'
_FMT_MS = '+#,##0.0,, "M";-#,##0.0,, "M";0.0,, "M"'   # desvío con signo
_FMT_PCT = "0%"
_FMT_PP = '+0.0" pp";-0.0" pp"'
_FMT_FECHA = "dd-mm-yyyy"


class _Hoja:
    """Escritor de hojas con el estilo corporativo (encabezados morados,
    subtotales resaltados, cifras en millones, impresión horizontal a 1 página de ancho)."""

    def __init__(self, wb, nombre: str, ancho_col_a: int = 34):
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.properties import PageSetupProperties
        self.ws = wb.create_sheet(title=nombre[:31])
        self.r = 1
        self.ancho_col_a = ancho_col_a
        self._gcl = get_column_letter
        self.fila_cabecera = None   # fila de encabezados de la primera tabla
        ws = self.ws
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.page_margins.left = ws.page_margins.right = 0.4
        ws.page_margins.top = ws.page_margins.bottom = 0.5
        ws.oddFooter.center.text = "&P / &N"

    def titulo(self, texto: str, sub: str = ""):
        from openpyxl.styles import Font
        c = self.ws.cell(row=self.r, column=1, value=texto)
        c.font = Font(bold=True, size=15, color=C_MORADO)
        self.r += 1
        if sub:
            c = self.ws.cell(row=self.r, column=1, value=sub)
            c.font = Font(size=10, italic=True, color=C_MORADO2)
            self.r += 1
        self.r += 1

    def seccion(self, texto: str):
        from openpyxl.styles import Font
        c = self.ws.cell(row=self.r, column=1, value=texto)
        c.font = Font(bold=True, size=12, color=C_MORADO)
        self.r += 1

    def texto(self, lineas: list, vinetas: bool = True, color: str = "333333",
              negrita_primera: bool = False, ancho_merge: int = 0):
        from openpyxl.styles import Font, Alignment
        for i, t in enumerate(lineas):
            c = self.ws.cell(row=self.r, column=1, value=(f"•  {t}" if vinetas else t))
            c.font = Font(size=11 if (negrita_primera and i == 0) else 10,
                          bold=(negrita_primera and i == 0), color=color)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if ancho_merge > 1:
                self.ws.merge_cells(start_row=self.r, start_column=1,
                                    end_row=self.r, end_column=ancho_merge)
            chars = 150 if ancho_merge > 1 else 110
            self.ws.row_dimensions[self.r].height = max(16, 14 * (1 + len(str(t)) // chars))
            self.r += 1
        self.r += 1

    def tabla(self, df: pd.DataFrame, formatos: dict | None = None,
              subtotales: list | None = None, resaltar_signo: list | None = None,
              anchos: dict | None = None, autofiltro: bool = False,
              envolver: list | None = None):
        """Escribe un DataFrame con encabezado morado. Retorna (fila_encabezado, fila_final)."""
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        if df is None or df.empty:
            self.texto(["Sin datos para este bloque con los filtros aplicados."])
            return None, None

        cols = [c for c in df.columns if not str(c).startswith("_")]
        formatos = formatos or {}
        resaltar_signo = resaltar_signo or []
        envolver = envolver or []
        borde = Border(bottom=Side(style="thin", color="E6DCEF"))
        fill_h = PatternFill("solid", fgColor=C_MORADO2)
        fill_sub = PatternFill("solid", fgColor=C_LILA_BG)

        if self.fila_cabecera is None:
            self.fila_cabecera = self.r
        fila_h = self.r
        for j, col in enumerate(cols, start=1):
            c = self.ws.cell(row=self.r, column=j, value=str(col))
            c.font = Font(bold=True, color="FFFFFF", size=10)
            c.fill = fill_h
            c.alignment = Alignment(horizontal="left" if j == 1 else "right",
                                    wrap_text=True, vertical="center")
        self.ws.row_dimensions[self.r].height = 30
        self.r += 1

        for i, (_, fila) in enumerate(df.iterrows()):
            es_sub = bool(subtotales and i in subtotales)
            for j, col in enumerate(cols, start=1):
                v = fila[col]
                if isinstance(v, (list, tuple, dict)):
                    v = str(v)
                elif v is None or (not isinstance(v, str) and pd.isna(v)):
                    v = None
                elif hasattr(v, "item"):
                    v = v.item()
                c = self.ws.cell(row=self.r, column=j, value=v)
                c.border = borde
                c.font = Font(size=10, bold=es_sub, color=C_MORADO if es_sub else "222222")
                if col in envolver:
                    c.alignment = Alignment(wrap_text=True, vertical="top")
                if es_sub:
                    c.fill = fill_sub
                if col in formatos:
                    c.number_format = formatos[col]
                if col in resaltar_signo and isinstance(v, (int, float)) and abs(v) >= 0.5:
                    c.font = Font(size=10, bold=True, color=(C_VERDE if v >= 0 else C_ROJO))
            self.r += 1
        fila_fin = self.r - 1
        self.r += 1

        if autofiltro:
            self.ws.auto_filter.ref = f"A{fila_h}:{self._gcl(len(cols))}{fila_fin}"
            self.ws.print_title_rows = f"{fila_h}:{fila_h}"

        self.ws.column_dimensions["A"].width = max(
            self.ws.column_dimensions["A"].width or 0, self.ancho_col_a)
        for j in range(2, len(cols) + 1):
            letra = self._gcl(j)
            ancho = (anchos or {}).get(cols[j - 1], 14)
            actual = self.ws.column_dimensions[letra].width or 0
            self.ws.column_dimensions[letra].width = max(actual, ancho)
        return fila_h, fila_fin

    def congelar(self, columna: str = "A"):
        fila = (self.fila_cabecera + 1) if self.fila_cabecera else 1
        self.ws.freeze_panes = f"{columna}{fila}"


def _grafico_barras(ws, titulo: str, col_cat: int, cols_val: list, fila_h: int,
                    fila_fin: int, ancla: str, colores: list):
    """Barras agrupadas (real vs presupuesto) con un solo eje."""
    from openpyxl.chart import BarChart, Reference
    ch = BarChart()
    ch.type = "col"
    ch.grouping = "clustered"
    ch.title = titulo
    ch.height, ch.width = 7.2, 15.5
    ch.y_axis.numFmt = '#,##0,, "M"'
    ch.y_axis.majorGridlines = None
    ch.legend.position = "b"
    for col in cols_val:
        ch.add_data(Reference(ws, min_col=col, min_row=fila_h, max_row=fila_fin),
                    titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=col_cat, min_row=fila_h + 1, max_row=fila_fin))
    for s, color in zip(ch.series, colores):
        s.graphicalProperties.solidFill = color
        s.graphicalProperties.line.noFill = True
    ch.gapWidth = 60
    ws.add_chart(ch, ancla)


def to_excel(rep: dict) -> bytes:
    """Genera el workbook completo del reporte de gerencia."""
    from openpyxl import Workbook

    meta, kpi = rep["meta"], rep["kpi"]
    wb = Workbook()
    wb.remove(wb.active)
    sub = f"Kreems · {meta['sociedad']} · {meta['periodo_lbl']} · generado {meta['generado']}"

    fmt_basic = {"Real YTD": _FMT_M, "Ppto YTD": _FMT_M, "Desvío": _FMT_MS,
                 "% Ejec.": _FMT_PCT, "Ppto Año": _FMT_M, "% Ppto Año consumido": _FMT_PCT,
                 "% s/Ventas": _FMT_PCT, "Cierre según ppto": _FMT_M,
                 "Cierre según tendencia": _FMT_M, "Si se mantiene 12m": _FMT_MS,
                 "Real": _FMT_M, "Presupuesto": _FMT_M}

    # ── 0. Resumen para gerencia ──────────────────────────────
    h = _Hoja(wb, "Resumen Gerencia", ancho_col_a=34)
    h.titulo("¿Cómo vamos con el presupuesto?", sub)
    h.texto(rep["titular"], vinetas=False, negrita_primera=True, color="222222", ancho_merge=7)

    filas_kpi = [
        ("Ventas", kpi["ventas_r"], kpi["ventas_p"], kpi["ventas_r"] - kpi["ventas_p"],
         _pct(kpi["ventas_r"], kpi["ventas_p"])),
        ("Utilidad bruta", kpi["ub_r"], kpi["ub_p"], kpi["ub_r"] - kpi["ub_p"],
         _pct(kpi["ub_r"], kpi["ub_p"])),
        ("Gasto controlable (costo fijo + OPEX)", kpi["ctrl_r"], kpi["ctrl_p"],
         kpi["ctrl_p"] - kpi["ctrl_r"], _pct(kpi["ctrl_r"], kpi["ctrl_p"])),
        ("EBIT", kpi["ebit_r"], kpi["ebit_p"], kpi["ebit_r"] - kpi["ebit_p"],
         _pct(kpi["ebit_r"], kpi["ebit_p"])),
    ]
    h.seccion(f"Indicadores — acumulado {meta['periodo_lbl']}")
    h.tabla(pd.DataFrame(filas_kpi, columns=["Indicador", "Real", "Presupuesto", "Desvío",
                                             "% Ejec."]),
            formatos=fmt_basic, resaltar_signo=["Desvío"])

    cols_t = ["Cuenta", "Centro de costo", "Real YTD", "Ppto YTD", "Desvío",
              "Tipo de brecha", "Comentario"]
    h.seccion("Lo que más resta al resultado")
    h.tabla(rep["top_desfav"][cols_t] if not rep["top_desfav"].empty else rep["top_desfav"],
            formatos=fmt_basic, resaltar_signo=["Desvío"],
            anchos={"Centro de costo": 18, "Tipo de brecha": 18, "Comentario": 50},
            envolver=["Comentario"])
    h.seccion("Lo que más suma al resultado")
    h.tabla(rep["top_fav"][cols_t] if not rep["top_fav"].empty else rep["top_fav"],
            formatos=fmt_basic, resaltar_signo=["Desvío"], envolver=["Comentario"])

    h.seccion("Cierre del año")
    esc = pd.DataFrame([
        ("Según presupuesto de los meses que faltan", kpi["ventas_cierre_ppto"],
         kpi["ebit_cierre_ppto"]),
        (f"Según ritmo de {meta['rec_lbl']}", kpi["ventas_cierre_tend"], kpi["ebit_cierre_tend"]),
        ("Presupuesto anual", kpi["ventas_ppto_ano"], kpi["ebit_ppto_ano"]),
    ], columns=["Escenario", "Ventas", "EBIT"])
    h.tabla(esc, formatos={"Ventas": _FMT_M, "EBIT": _FMT_M})

    h.seccion("Mes a mes — real vs presupuesto")
    serie = rep["serie"][["Mes", "Ventas real", "Ventas ppto", "EBIT real", "EBIT ppto"]]
    fh, ff = h.tabla(serie, formatos={c: _FMT_M for c in serie.columns if c != "Mes"},
                     anchos={c: 13 for c in serie.columns})
    if fh:
        _grafico_barras(h.ws, "Ventas por mes", 1, [2, 3], fh, ff, f"I{fh - 1}",
                        [C_FUCSIA, C_MORADO2])
        _grafico_barras(h.ws, "EBIT por mes", 1, [4, 5], fh, ff, f"I{fh + 15}",
                        [C_FUCSIA, C_MORADO2])
    for col in "BCDEFG":
        h.ws.column_dimensions[col].width = max(h.ws.column_dimensions[col].width or 0, 15)

    # ── 1. Estado de resultados ───────────────────────────────
    h = _Hoja(wb, "1 Estado de Resultados", ancho_col_a=26)
    h.titulo("Estado de Resultados acumulado", sub)
    df_pl = rep["pl"]
    h.tabla(df_pl, formatos=fmt_basic,
            subtotales=[i for i, v in enumerate(df_pl["_subtotal"]) if v],
            resaltar_signo=["Desvío"], anchos={"% Ppto Año consumido": 19})
    h.seccion("Márgenes")
    h.tabla(rep["margenes"], formatos={"Real": "0.0%", "Ppto": "0.0%", "Δ pp": _FMT_PP},
            resaltar_signo=["Δ pp"])
    if rep["conclusiones"]:
        h.seccion("Lectura")
        h.texto(rep["conclusiones"], ancho_merge=8)
    h.congelar("B")

    # ── 2. Puente EBIT ────────────────────────────────────────
    h = _Hoja(wb, "2 Puente EBIT", ancho_col_a=40)
    h.titulo("Puente de EBIT — del presupuesto al real", sub)
    h.texto(["El efecto de ventas está valorizado al margen de contribución presupuestado y "
             "el costo variable se compara contra el que correspondería a las ventas reales.",
             "Positivo = suma al EBIT. Negativo = lo resta."])
    h.tabla(rep["puente"][["Concepto", "Efecto"]],
            formatos={"Efecto": _FMT_MS}, resaltar_signo=["Efecto"], anchos={"Efecto": 16})

    # ── 3. Centros de costo ───────────────────────────────────
    h = _Hoja(wb, "3 Centros de Costo", ancho_col_a=22)
    h.titulo("Gasto controlable por centro de costo (costo fijo + OPEX)", sub)
    h.tabla(rep["cc"], formatos=fmt_basic, resaltar_signo=["Desvío"],
            anchos={"Sociedad": 17, "% Ppto Año consumido": 19, "Cierre según ppto": 17,
                    "Cierre según tendencia": 19})
    h.seccion("Apertura por línea")
    h.tabla(rep["cc_linea"], formatos=fmt_basic, resaltar_signo=["Desvío"])
    h.congelar("C")

    # ── 4. Detalle cuentas ────────────────────────────────────
    h = _Hoja(wb, "4 Detalle Cuentas", ancho_col_a=20)
    h.titulo("Detalle por cuenta y centro de costo", sub)
    h.texto(["Usa los filtros del encabezado para buscar por centro de costo, cuenta, línea o "
             "tipo de brecha. Ordenado por tamaño del desvío.",
             "Tipo de brecha: Recurrente = se repite mes a mes · Puntual = concentrado en un mes · "
             "Desfase de calendario = el acumulado cuadra pero el gasto cayó en otros meses · "
             "No presupuestado = gasto sin presupuesto · No ejecutado = presupuesto sin gasto."])
    fmt_det = {**fmt_basic, **{c: _FMT_MS for c in rep["cols_mes"]}}
    anchos_det = {"Cuenta": 40, "Sociedad": 17, "Línea P&L": 15, "Categoría EERR": 19,
                  "Tipo de brecha": 20, "Meses desfavorables": 40, "Si se mantiene 12m": 16,
                  "Cierre según ppto": 16, "Comentario": 40, **{c: 12 for c in rep["cols_mes"]}}
    h.tabla(rep["detalle"], formatos=fmt_det, resaltar_signo=["Desvío"],
            anchos=anchos_det, autofiltro=True)
    h.congelar("D")

    # ── 5. Plan de acción ─────────────────────────────────────
    h = _Hoja(wb, "5 Plan de Accion", ancho_col_a=20)
    h.titulo("Plan de acción — desviaciones desfavorables", sub)
    h.texto([f"Desvío desfavorable sobre la materialidad: {fmt_m(-rep['total_desfavorable'])}. "
             f"Las líneas siguientes explican al menos el 80%.",
             "Los comentarios se registran en la app (Reporte de Gerencia → Plan de acción) y "
             "se mantienen de un mes a otro hasta que se editen."])
    fmt_ac = {**fmt_basic, "Fecha compromiso": _FMT_FECHA,
              **{c: _FMT_MS for c in rep["cols_mes"]}}
    h.tabla(rep["accion"], formatos=fmt_ac, resaltar_signo=["Desvío"],
            anchos={"Cuenta": 40, "Sociedad": 17, "Tipo de brecha": 18,
                    "Meses desfavorables": 40, "Explicación": 45, "Acción comprometida": 40,
                    "Responsable": 18, "Fecha compromiso": 14,
                    **{c: 12 for c in rep["cols_mes"]}},
            autofiltro=True, envolver=["Explicación", "Acción comprometida"])
    h.congelar("C")

    # ── 6. Mes a mes ──────────────────────────────────────────
    h = _Hoja(wb, "6 Mes a Mes", ancho_col_a=22)
    h.titulo("Mes a mes", sub)
    fmt_meses = {m: _FMT_M for m in meta["meses"]}
    fmt_meses["Total YTD"] = _FMT_M
    h.seccion("Líneas del P&L")
    h.tabla(rep["mes_pl"], formatos=fmt_meses, anchos={"Concepto": 12})
    h.seccion("Gasto controlable por centro de costo (Desvío = presupuesto − real)")
    h.tabla(rep["mes_cc"], formatos=fmt_meses, anchos={"Concepto": 12})
    h.seccion("Cuentas con desvío material")
    h.tabla(rep["mes_cuenta"], formatos=fmt_meses, anchos={"Cuenta": 40, "Concepto": 12})
    h.ws.freeze_panes = "D1"

    # ── 7. Proyección ─────────────────────────────────────────
    h = _Hoja(wb, "7 Proyeccion Cierre", ancho_col_a=26)
    h.titulo("Cierre del año en dos escenarios", sub)
    h.texto(["Según presupuesto: real acumulado + presupuesto de los meses que faltan.",
             f"Según tendencia: el presupuesto de los meses que faltan se ajusta por el ritmo "
             f"real/presupuesto de cada línea en {meta['rec_lbl']}.",
             "Desvío con signo del efecto sobre el resultado (positivo = favorable)."])
    df_pr = rep["proyeccion"]
    col_ritmo = [c for c in df_pr.columns if c.startswith("Ritmo")]
    h.tabla(df_pr, formatos={**fmt_basic, "Ppto restante": _FMT_M,
                             "Desvío (según ppto)": _FMT_MS, "Desvío (según tendencia)": _FMT_MS,
                             **{c: _FMT_PCT for c in col_ritmo}},
            subtotales=[i for i, v in enumerate(df_pr["_subtotal"]) if v],
            resaltar_signo=["Desvío (según ppto)", "Desvío (según tendencia)"],
            anchos={"Cierre según tendencia": 19, "Desvío (según ppto)": 18,
                    "Desvío (según tendencia)": 21})

    # ── 8. Bases ──────────────────────────────────────────────
    h = _Hoja(wb, "8 Bases", ancho_col_a=130)
    h.titulo("Base de comparación y criterios", sub)
    if rep["alertas"]:
        h.seccion("Base de comparación")
        h.texto(rep["alertas"])
    h.seccion("Cómo leer las cifras")
    h.texto(rep["escalas"])
    h.seccion("Criterios")
    h.texto(rep["bases"])
    h.seccion("Contenido")
    h.texto([
        "Resumen Gerencia — titular, indicadores, principales desviaciones, cierre y mes a mes.",
        "1 Estado de Resultados — P&L acumulado contra el presupuesto de los mismos meses.",
        "2 Puente EBIT — de dónde sale la diferencia entre el EBIT presupuestado y el real.",
        "3 Centros de Costo — gasto controlable por centro de costo y cierre proyectado.",
        "4 Detalle Cuentas — cada cuenta × centro de costo con filtros y tipo de brecha.",
        "5 Plan de Acción — desvíos desfavorables con explicación, acción y responsable.",
        "6 Mes a Mes — perfil mensual del P&L, de cada centro de costo y de cada cuenta material.",
        "7 Proyección Cierre — el año completo según presupuesto y según tendencia.",
    ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── EXPORT HTML ───────────────────────────────────────────────

def _e(t) -> str:
    return _html.escape(str(t))


_RE_MONTO = re.compile(r"[−+]?\$[\d.,]+M")


def _et(t) -> str:
    """Escapa texto y evita que un monto quede partido en dos líneas."""
    return _RE_MONTO.sub(lambda m: f'<span class="nw">{m.group(0)}</span>', _e(t))


def _clase_signo(v: float) -> str:
    if _es_nulo(v) or abs(float(v)) < 0.5e5:
        return ""
    return "pos" if float(v) > 0 else "neg"


def _grafico_meses(serie: pd.DataFrame, col_r: str, col_p: str, titulo: str,
                   mes_corte: int) -> str:
    """
    Columnas mensuales: barra = real, marca horizontal = presupuesto. Responsivo
    (HTML/CSS, no SVG escalado) para que las etiquetas se lean en celular.
    """
    vals = [v for v in list(serie[col_r]) + list(serie[col_p]) if not _es_nulo(v)] + [0.0]
    vmax, vmin = max(vals), min(vals)
    rango = (vmax - vmin) or 1.0

    def pos(v):  # % desde abajo
        return (float(v) - vmin) / rango * 100

    z = pos(0.0)
    cols = []
    for _, r in serie.iterrows():
        m, real, ppto = int(r["mes"]), r[col_r], r[col_p]
        futuro = m > mes_corte
        partes = []
        if not futuro and not _es_nulo(real):
            alto = abs(pos(real) - z)
            base = min(pos(real), z)
            clase = "bar" if real >= 0 else "bar negb"
            partes.append(f'<div class="{clase}" style="bottom:{base:.2f}%;height:{max(alto, .6):.2f}%"></div>')
        partes.append(f'<div class="tk" style="bottom:{pos(ppto):.2f}%"></div>')
        if m == mes_corte and not _es_nulo(real):
            arriba = max(pos(real), z, pos(ppto))
            partes.append(f'<div class="dl" style="bottom:calc({arriba:.2f}% + 4px)">{fmt_m(real)}</div>')
        if futuro:
            tip = f"{r['Mes']} · presupuesto {fmt_m(ppto)}"
        else:
            tip = (f"{r['Mes']} · real {fmt_m(real)} · ppto {fmt_m(ppto)} · "
                   f"{fmt_m(float(real) - float(ppto), signo=True)}")
        cols.append(
            f'<div class="mc{" fut" if futuro else ""}" tabindex="0">'
            f'<div class="ar">{"".join(partes)}</div>'
            f'<div class="xl">{_e(r["Mes"])}</div>'
            f'<div class="tip">{_e(tip)}</div></div>')
    ejes = (f'<div class="yl" style="bottom:{pos(vmax):.2f}%">{fmt_m(vmax)}</div>'
            f'<div class="gl" style="bottom:{pos(vmax):.2f}%"></div>'
            f'<div class="zl" style="bottom:{z:.2f}%"></div>'
            f'<div class="yl" style="bottom:{z:.2f}%">0</div>')
    if vmin < 0:
        ejes += (f'<div class="yl" style="bottom:{pos(vmin):.2f}%">{fmt_m(vmin)}</div>'
                 f'<div class="gl" style="bottom:{pos(vmin):.2f}%"></div>')
    return (f'<figure class="chart"><figcaption>{_e(titulo)}</figcaption>'
            f'<div class="plot"><div class="axis">{ejes}</div>'
            f'<div class="cols">{"".join(cols)}</div></div></figure>')


def to_html(rep: dict) -> str:
    """Página autocontenida: resumen para gerencia arriba, análisis detallado abajo."""
    meta, kpi = rep["meta"], rep["kpi"]

    def kpi_card(label, real, ppto, desvio, nota=""):
        pct = _pct(real, ppto)
        pie = f"Presupuesto {fmt_m(ppto)}" + (f" · {fmt_pct(pct)} ejecutado" if pct else "")
        flecha = "▲" if desvio >= 0 else "▼"
        return (f'<div class="kpi"><div class="kpi-l">{_e(label)}</div>'
                f'<div class="kpi-v">{fmt_m(real)}</div>'
                f'<div class="kpi-d {_clase_signo(desvio)}">{flecha} {fmt_m(desvio, signo=True)} '
                f'vs presupuesto</div><div class="kpi-o">{_e(pie)}</div>'
                + (f'<div class="kpi-o">{_e(nota)}</div>' if nota else "") + '</div>')

    kpis = "".join([
        kpi_card("Ventas", kpi["ventas_r"], kpi["ventas_p"], kpi["ventas_r"] - kpi["ventas_p"]),
        kpi_card("Utilidad bruta", kpi["ub_r"], kpi["ub_p"], kpi["ub_r"] - kpi["ub_p"]),
        kpi_card("Gasto controlable", kpi["ctrl_r"], kpi["ctrl_p"], kpi["ctrl_p"] - kpi["ctrl_r"],
                 "Costo fijo + OPEX"),
        kpi_card("EBIT", kpi["ebit_r"], kpi["ebit_p"], kpi["ebit_r"] - kpi["ebit_p"]),
    ])

    titular = rep["titular"]
    tit_html = (f'<p class="lead">{_et(titular[0])}</p>' +
                "".join(f"<p>{_et(t)}</p>" for t in titular[1:]))

    serie = rep["serie"]
    graficos = (_grafico_meses(serie, "Ventas real", "Ventas ppto", "Ventas por mes",
                               meta["mes_corte"]) +
                _grafico_meses(serie, "EBIT real", "EBIT ppto", "EBIT por mes",
                               meta["mes_corte"]))
    filas_serie = "".join(
        f"<tr><td>{_e(r['Mes'])}</td><td class='num'>{fmt_m(r['Ventas real'])}</td>"
        f"<td class='num'>{fmt_m(r['Ventas ppto'])}</td><td class='num'>{fmt_m(r['EBIT real'])}</td>"
        f"<td class='num'>{fmt_m(r['EBIT ppto'])}</td></tr>" for _, r in serie.iterrows())

    def lista_top(df_top: pd.DataFrame, favorable: bool) -> str:
        if df_top.empty:
            return '<div class="vacio">Sin desviaciones sobre la materialidad.</div>'
        items = []
        for _, r in df_top.iterrows():
            com = str(r["Comentario"] or "").strip()
            if com:
                com_html = f'<div class="com">{_e(com)}</div>'
            elif favorable:
                com_html = '<div class="com mute">Sin comentario · confirmar si es ahorro o factura por registrar</div>'
            else:
                com_html = '<div class="com mute">Sin comentario · completar en el plan de acción</div>'
            items.append(
                f'<div class="ti"><div class="ti-h"><span class="ti-n">{_e(r["_nombre"])}</span>'
                f'<span class="ti-v {_clase_signo(r["Desvío"])}">{fmt_m(r["Desvío"], signo=True)}</span></div>'
                f'<div class="sub">{_e(r["Centro de costo"])} · real {fmt_m(r["Real YTD"])} · '
                f'ppto {fmt_m(r["Ppto YTD"])} · {_e(str(r["Tipo de brecha"]).lower())}</div>'
                f'{com_html}</div>')
        return "".join(items)

    escenarios = f"""
      <div class="esc"><div class="kpi-l">Si se mantiene el ritmo de {_e(meta['rec_lbl'])}</div>
        <div class="kpi-v">{fmt_m(kpi['ebit_cierre_tend'])}</div>
        <div class="kpi-o">EBIT al cierre · ventas {fmt_m(kpi['ventas_cierre_tend'])}</div></div>
      <div class="esc"><div class="kpi-l">Si se cumple el presupuesto que falta</div>
        <div class="kpi-v">{fmt_m(kpi['ebit_cierre_ppto'])}</div>
        <div class="kpi-o">EBIT al cierre · ventas {fmt_m(kpi['ventas_cierre_ppto'])}</div></div>
      <div class="esc ref"><div class="kpi-l">Presupuesto anual</div>
        <div class="kpi-v">{fmt_m(kpi['ebit_ppto_ano'])}</div>
        <div class="kpi-o">EBIT · ventas {fmt_m(kpi['ventas_ppto_ano'])}</div></div>"""

    # P&L
    filas_pl = []
    for _, r in rep["pl"].iterrows():
        filas_pl.append(
            f'<tr class="{"sub" if r["_subtotal"] else ""}"><td>{_e(r["Línea"])}</td>'
            f'<td class="num">{fmt_m(r["Real YTD"])}</td><td class="num">{fmt_m(r["Ppto YTD"])}</td>'
            f'<td class="num {_clase_signo(r["Desvío"])}">{fmt_m(r["Desvío"], signo=True)}</td>'
            f'<td class="num hm">{fmt_pct(r["% Ejec."])}</td>'
            f'<td class="num hm">{fmt_pct(r["% Ppto Año consumido"])}</td></tr>')
    filas_mg = "".join(
        f"<tr><td>{_e(r['Margen'])}</td><td class='num'>{fmt_pct(r['Real'], 1)}</td>"
        f"<td class='num'>{fmt_pct(r['Ppto'], 1)}</td>"
        f"<td class='num {_clase_signo(r['Δ pp'] * 1e6)}'>{'+' if r['Δ pp'] >= 0 else '−'}"
        f"{_num(abs(r['Δ pp']))} pp</td></tr>" for _, r in rep["margenes"].iterrows())

    # Puente horizontal: etiquetas completas y legible en celular
    pu = rep["puente"]
    acum, filas = float(pu.iloc[0]["Efecto"]), []
    for _, r in pu.iterrows():
        v = float(r["Efecto"])
        if r["Tipo"] == "efecto":
            lo, hi = sorted([acum, acum + v])
            acum += v
        else:
            lo, hi = min(0.0, v), max(0.0, v)
        filas.append((str(r["Concepto"]), lo, hi, v, r["Tipo"]))
    vmin = min([f[1] for f in filas] + [0.0])
    vmax = max([f[2] for f in filas] + [0.0])
    rango = (vmax - vmin) or 1.0
    z = (0 - vmin) / rango * 100
    puente_html = "".join(
        f'<div class="pr{" tot" if t != "efecto" else ""}"><div class="pr-l">{_e(n)}</div>'
        f'<div class="pr-t"><div class="pr-z" style="left:{z:.2f}%"></div>'
        f'<div class="pr-b {"tb" if t != "efecto" else ("gb" if v >= 0 else "rb")}" '
        f'style="left:{(lo - vmin) / rango * 100:.2f}%;width:{max((hi - lo) / rango * 100, .4):.2f}%"></div></div>'
        f'<div class="pr-v {"" if t != "efecto" else _clase_signo(v)}">'
        f'{fmt_m(v) if t != "efecto" else fmt_m(v, signo=True)}</div></div>'
        for n, lo, hi, v, t in filas)

    # Centros de costo
    df_cc = rep["cc"]
    filas_cc = []
    if not df_cc.empty:
        tope = max(float(df_cc[["Real YTD", "Ppto YTD"]].max().max()), 1)
        for _, r in df_cc.iterrows():
            filas_cc.append(
                f'<div class="ccrow"><div class="ccname">{_e(r["Centro de costo"])}'
                f'<span class="sub">{fmt_pct(r["% Ppto Año consumido"])} del presupuesto anual · '
                f'{_e(r["Sociedad"])}</span></div>'
                f'<div class="ccbars"><div class="ccb" style="width:{float(r["Real YTD"])/tope*100:.1f}%"></div>'
                f'<div class="cct" style="left:{float(r["Ppto YTD"])/tope*100:.1f}%"></div></div>'
                f'<div class="ccval">{fmt_m(r["Real YTD"])}<span class="sub"> / {fmt_m(r["Ppto YTD"])}</span></div>'
                f'<div class="ccimp {_clase_signo(r["Desvío"])}">{fmt_m(r["Desvío"], signo=True)}</div></div>')

    # Plan de acción (tarjetas)
    piso_mes = meta["umbral"] / max(meta["n_meses"], 1)
    filas_ac = []
    for _, r in rep["accion"].iterrows():
        chips = []
        for i, et in enumerate(meta["meses"]):
            dm = _efecto(r["_clasif"], float(r["_real_mes"][i]) - float(r["_ppto_mes"][i]))
            clase = "dn" if dm < -piso_mes else ("up" if dm > piso_mes else "")
            chips.append(f'<span class="mchip {clase}" title="{_e(et)}: {fmt_m(dm, signo=True)}">{_e(et)}</span>')
        tipo = str(r["Tipo de brecha"])
        clase_t = {"Recurrente": "tag-rec", "Puntual": "tag-pun", "No presupuestado": "tag-nop",
                   "Desfase de calendario": "tag-des"}.get(tipo, "tag-mix")
        anual = r["Si se mantiene 12m"]
        compromiso = " · ".join(x for x in [
            str(r["Acción comprometida"] or "").strip(),
            str(r["Responsable"] or "").strip(),
            (pd.Timestamp(r["Fecha compromiso"]).strftime("%d-%m-%Y")
             if not _es_nulo(r["Fecha compromiso"]) and r["Fecha compromiso"] else "")] if x)
        expl = str(r["Explicación"] or "").strip()
        filas_ac.append(f"""
        <div class="ac">
          <div class="ac-h"><b>{_e(r['_nombre'])}</b>
            <span class="tag {clase_t}">{_e(tipo)}</span></div>
          <div class="sub">{_e(r['Centro de costo'])} · {_e(r['Cuenta'].split(' ')[0])} ·
            <span class="soc">{_e(r['Sociedad'])}</span></div>
          <div class="ac-n"><span>Real <b>{fmt_m(r['Real YTD'])}</b></span>
            <span>Ppto <b>{fmt_m(r['Ppto YTD'])}</b></span>
            <span>Desvío <b class="neg">{fmt_m(r['Desvío'], signo=True)}</b></span>
            {f"<span>En 12 meses <b>{fmt_m(anual, signo=True)}</b></span>" if not _es_nulo(anual) else ""}</div>
          <div class="strip">{''.join(chips)}</div>
          {f'<div class="com"><b>Qué pasó:</b> {_e(expl)}</div>' if expl else '<div class="com mute">Sin explicación registrada</div>'}
          {f'<div class="com"><b>Acción:</b> {_e(compromiso)}</div>' if compromiso else ''}
        </div>""")

    alertas = "".join(f"<li>{_et(a)}</li>" for a in rep["alertas"])
    escalas = "".join(f"<li>{_e(x)}</li>" for x in rep["escalas"])
    bases = "".join(f"<li>{_e(b)}</li>" for b in rep["bases"])
    conclusiones = "".join(f"<li>{_et(c)}</li>" for c in rep["conclusiones"])

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reporte de Gerencia · Kreems · {_e(meta['periodo_lbl'])}</title>
<style>
  :root {{
    --morado:#2D0050; --morado2:#6B2C91; --fucsia:#C4007A; --verde:#0F6E56; --rojo:#B42318;
    --borde:#EDE4F3; --gris:#6B6B7B; --tenue:#9A9AAA; --fondo:#F7F5FA; --surface:#FFFFFF;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--fondo); color:#22222E;
         font-family:'Inter',-apple-system,'Segoe UI',Roboto,sans-serif; font-size:14px; line-height:1.45; }}
  .wrap {{ max-width:1120px; margin:0 auto; padding:0 16px 56px; }}
  header {{ background:var(--morado); color:#fff; padding:22px 0 18px; margin-bottom:20px; }}
  header .wrap {{ padding-bottom:0; }}
  h1 {{ margin:0 0 4px; font-size:22px; font-weight:800; }}
  .hsub {{ opacity:.75; font-size:13px; }}
  h2 {{ font-size:16px; color:var(--morado); margin:30px 0 10px; }}
  h3 {{ font-size:13px; color:var(--gris); text-transform:uppercase; letter-spacing:.4px; margin:0 0 8px; }}
  .card {{ background:var(--surface); border:1px solid var(--borde); border-radius:12px; padding:16px 18px; }}
  .titular p {{ margin:0 0 8px; }}
  .titular .lead {{ font-size:18px; font-weight:700; color:var(--morado); line-height:1.35; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:14px; }}
  .kpi, .esc {{ background:var(--surface); border:1px solid var(--borde); border-radius:12px; padding:14px 16px; }}
  .kpi-l {{ font-size:11px; color:var(--gris); text-transform:uppercase; letter-spacing:.4px; font-weight:600; }}
  .kpi-v {{ font-size:24px; font-weight:800; color:var(--morado); margin:4px 0 2px; }}
  .kpi-d {{ font-size:13px; font-weight:700; }}
  .kpi-o {{ font-size:11.5px; color:var(--tenue); margin-top:2px; }}
  .pos {{ color:var(--verde); }} .neg {{ color:var(--rojo); }}
  .nw {{ white-space:nowrap; }}
  .sub {{ font-size:11.5px; color:var(--gris); font-weight:400; }}
  .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  .chart {{ margin:0; background:var(--surface); border:1px solid var(--borde); border-radius:12px; padding:14px 14px 10px; }}
  .chart figcaption {{ font-weight:700; color:var(--morado); font-size:13.5px; margin-bottom:8px; }}
  .legend {{ display:flex; gap:16px; font-size:12px; color:var(--gris); margin:4px 0 10px; flex-wrap:wrap; }}
  .lg-bar {{ display:inline-block; width:10px; height:12px; background:var(--fucsia); border-radius:3px 3px 0 0; vertical-align:-1px; margin-right:5px; }}
  .lg-tk {{ display:inline-block; width:14px; height:3px; background:var(--morado2); vertical-align:3px; margin-right:5px; }}
  .plot {{ position:relative; height:190px; margin-left:48px; }}
  .axis {{ position:absolute; inset:0 0 20px 0; pointer-events:none; }}
  .gl {{ position:absolute; left:0; right:0; height:1px; background:#F0EAF4; }}
  .zl {{ position:absolute; left:0; right:0; height:1px; background:#CFC3DA; }}
  .yl {{ position:absolute; left:-50px; width:44px; text-align:right; font-size:10.5px; color:var(--tenue); transform:translateY(50%); }}
  .cols {{ position:absolute; inset:0; display:flex; gap:2px; }}
  .mc {{ flex:1; display:flex; flex-direction:column; position:relative; outline:none; }}
  .mc .ar {{ position:relative; flex:1; }}
  .mc .bar {{ position:absolute; left:22%; right:22%; background:var(--fucsia); border-radius:4px 4px 0 0; }}
  .mc .bar.negb {{ border-radius:0 0 4px 4px; }}
  .mc .tk {{ position:absolute; left:8%; right:8%; height:3px; margin-bottom:-1.5px; background:var(--morado2); border-radius:2px; box-shadow:0 0 0 1px var(--surface); }}
  .mc.fut .xl {{ color:#C2BBCB; }}
  .mc.fut .tk {{ opacity:.55; }}
  .mc .dl {{ position:absolute; left:50%; transform:translateX(-50%); font-size:10.5px; font-weight:700; color:#22222E; white-space:nowrap; }}
  .mc .xl {{ height:20px; line-height:20px; text-align:center; font-size:10.5px; color:var(--gris); }}
  .mc .tip {{ display:none; position:absolute; bottom:100%; left:50%; transform:translateX(-50%); z-index:5;
             background:#22222E; color:#fff; font-size:11.5px; padding:6px 8px; border-radius:6px; white-space:nowrap; }}
  .mc:hover .tip, .mc:focus .tip {{ display:block; }}
  .mc:hover {{ background:#FAF6FC; border-radius:4px; }}
  details {{ margin-top:8px; font-size:12.5px; }}
  summary {{ cursor:pointer; color:var(--morado2); font-weight:600; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  .ti {{ padding:10px 0; border-bottom:1px solid #F2ECF6; }}
  .ti:last-child {{ border-bottom:none; }}
  .ti-h {{ display:flex; justify-content:space-between; gap:10px; font-weight:600; }}
  .ti-v {{ white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .com {{ font-size:12.5px; margin-top:4px; color:#33333F; }}
  .com.mute {{ color:var(--tenue); font-style:italic; }}
  .vacio {{ color:var(--tenue); font-size:13px; }}
  .escs {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; }}
  .esc.ref {{ background:#FBF9FC; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:var(--morado2); color:#fff; text-align:right; padding:8px 10px; font-size:11.5px; font-weight:600; }}
  th:first-child {{ text-align:left; }}
  td {{ padding:7px 10px; border-bottom:1px solid #F2ECF6; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  td.pos, td.neg {{ font-weight:600; }}
  tr.sub td {{ background:#FAF5FD; font-weight:700; color:var(--morado); }}
  .scroll {{ overflow-x:auto; }}
  .pr {{ display:grid; grid-template-columns:230px 1fr 90px; gap:10px; align-items:center; padding:5px 0; font-size:12.5px; }}
  .pr.tot {{ font-weight:700; color:var(--morado); }}
  .pr-t {{ position:relative; height:14px; }}
  .pr-z {{ position:absolute; top:-4px; bottom:-4px; width:1px; background:#CFC3DA; }}
  .pr-b {{ position:absolute; top:0; height:14px; border-radius:3px; }}
  .pr-b.tb {{ background:var(--morado2); }} .pr-b.gb {{ background:var(--verde); }} .pr-b.rb {{ background:var(--fucsia); }}
  .pr-v {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .ccrow {{ display:grid; grid-template-columns:200px 1fr 170px 90px; align-items:center; gap:12px;
            padding:9px 0; border-bottom:1px solid #F2ECF6; }}
  .ccname {{ font-weight:600; font-size:13px; }} .ccname .sub {{ display:block; }}
  .ccbars {{ position:relative; height:14px; background:#F4EFF8; border-radius:7px; }}
  .ccb {{ position:absolute; left:0; top:0; height:14px; background:var(--fucsia); border-radius:7px; }}
  .cct {{ position:absolute; top:-3px; width:3px; height:20px; background:var(--morado2); border-radius:2px; box-shadow:0 0 0 1px var(--surface); }}
  .ccval {{ text-align:right; font-weight:600; font-variant-numeric:tabular-nums; }}
  .ccimp {{ text-align:right; font-weight:700; font-variant-numeric:tabular-nums; }}
  .ac {{ padding:12px 0; border-bottom:1px solid #F2ECF6; }}
  .ac-h {{ display:flex; justify-content:space-between; gap:10px; align-items:center; }}
  .ac-n {{ display:flex; flex-wrap:wrap; gap:6px 18px; font-size:12.5px; margin-top:6px; color:var(--gris); }}
  .ac-n b {{ color:#22222E; }}
  .tag {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:10.5px; font-weight:700; white-space:nowrap; }}
  .tag-rec {{ background:#FDE8E8; color:#B01919; }} .tag-pun {{ background:#FFF2DC; color:#8A5A08; }}
  .tag-nop {{ background:#F0E6FA; color:#5B2A87; }} .tag-des {{ background:#E6F1FB; color:#1B5E96; }}
  .tag-mix {{ background:#EFEFF3; color:#55555F; }}
  .soc {{ font-size:10.5px; background:#F1EDF6; color:var(--morado2); padding:1px 6px; border-radius:4px; font-weight:600; white-space:nowrap; }}
  .strip {{ display:flex; gap:3px; margin:8px 0 2px; flex-wrap:wrap; }}
  .mchip {{ font-size:10px; font-weight:700; padding:2px 6px; border-radius:4px; background:#F1EFF4; color:#9A9AA8; }}
  .mchip.dn {{ background:#FDE8E8; color:#B01919; }} .mchip.up {{ background:#E4F3EE; color:#0F6E56; }}
  .leyenda {{ font-size:11.5px; color:var(--gris); margin-top:10px; line-height:1.6; }}
  ul.ins {{ margin:0; padding-left:18px; }} ul.ins li {{ margin-bottom:8px; }}
  footer {{ margin-top:34px; font-size:12px; color:var(--gris); }}
  footer ul {{ padding-left:18px; }}
  .alerta {{ border-left:4px solid var(--fucsia); }}
  @media (max-width:820px) {{
    .kpis {{ grid-template-columns:1fr 1fr; }}
    .charts, .two, .escs {{ grid-template-columns:1fr; }}
  }}
  @media (max-width:560px) {{
    h1 {{ font-size:19px; }}
    .titular .lead {{ font-size:16px; }}
    .kpi-v {{ font-size:20px; }}
    .hm {{ display:none; }}
    .pr {{ grid-template-columns:1fr 78px; }}
    .pr-t {{ grid-column:1 / -1; grid-row:2; }}
    .ccrow {{ grid-template-columns:1fr auto; }}
    .ccbars {{ grid-column:1 / -1; grid-row:2; }}
    .ccval {{ grid-column:1; grid-row:3; text-align:left; }}
    .ccimp {{ grid-column:2; grid-row:3; }}
    .plot {{ height:160px; margin-left:42px; }}
    .yl {{ left:-44px; width:40px; font-size:9.5px; }}
    .mc .xl {{ font-size:9.5px; }}
    .mc .dl {{ font-size:9.5px; }}
  }}
  @media print {{ body {{ background:#fff; }} .card, .chart, .kpi, .ac {{ break-inside:avoid; }} header {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
</style></head><body>
<header><div class="wrap">
  <h1>¿Cómo vamos con el presupuesto?</h1>
  <div class="hsub">Kreems · {_e(meta['sociedad'])} · acumulado {_e(meta['periodo_lbl'])}
    ({meta['n_meses']} de 12 meses) · generado {_e(meta['generado'])}</div>
</div></header>
<div class="wrap">

  <div class="card titular">{tit_html}</div>
  <div class="kpis">{kpis}</div>

  <h2>Mes a mes</h2>
  <div class="legend"><span><span class="lg-bar"></span>Real</span>
    <span><span class="lg-tk"></span>Presupuesto</span>
    <span>Toca o pasa el cursor sobre un mes para ver el detalle</span></div>
  <div class="charts">{graficos}</div>
  <details><summary>Ver cifras mensuales</summary>
    <div class="scroll"><table><thead><tr><th>Mes</th><th>Ventas real</th><th>Ventas ppto</th>
      <th>EBIT real</th><th>EBIT ppto</th></tr></thead><tbody>{filas_serie}</tbody></table></div>
  </details>

  <h2>Principales desviaciones</h2>
  <div class="two">
    <div class="card"><h3>Lo que más resta al resultado</h3>{lista_top(rep['top_desfav'], False)}</div>
    <div class="card"><h3>Lo que más suma al resultado</h3>{lista_top(rep['top_fav'], True)}</div>
  </div>

  <h2>Cierre del año (EBIT)</h2>
  <div class="escs">{escenarios}</div>
  <div class="leyenda">El escenario de tendencia ajusta el presupuesto de los meses que faltan
    por el ritmo real/presupuesto de cada línea en {_e(meta['rec_lbl'])}.</div>

  <h2>Estado de resultados acumulado</h2>
  <div class="card scroll">
    <table><thead><tr><th>Línea</th><th>Real</th><th>Presupuesto</th><th>Desvío</th>
      <th class="hm">% Ejec.</th><th class="hm">% del año</th></tr></thead>
      <tbody>{''.join(filas_pl)}</tbody></table>
    <table style="margin-top:14px"><thead><tr><th>Margen</th><th>Real</th><th>Presupuesto</th><th>Δ</th></tr></thead>
      <tbody>{filas_mg}</tbody></table>
    <div class="leyenda">Presupuesto = el de los mismos meses acumulados, no el anual.
      Desvío positivo = favorable al resultado.</div>
  </div>

  <h2>Puente de EBIT — de dónde sale la diferencia</h2>
  <div class="card">{puente_html}
    <div class="leyenda">Verde suma al EBIT, fucsia lo resta. El efecto de ventas está valorizado
      al margen de contribución presupuestado, para que una caída de ventas no aparezca como
      ahorro de costo variable.</div></div>

  <h2>Gasto controlable por centro de costo</h2>
  <div class="card">{''.join(filas_cc) or '<div class="vacio">Sin datos.</div>'}
    <div class="leyenda">Costo fijo + OPEX. Barra = real acumulado · marca = presupuesto de
      los mismos meses · a la derecha, el desvío (positivo = bajo presupuesto).</div></div>

  {f'<h2>Lectura del análisis</h2><div class="card"><ul class="ins">{conclusiones}</ul></div>' if conclusiones else ''}

  <h2>Plan de acción</h2>
  <div class="card">{''.join(filas_ac) or '<div class="vacio">Sin desviaciones desfavorables sobre la materialidad.</div>'}
    <div class="leyenda">Desvío desfavorable sobre la materialidad: {fmt_m(-rep['total_desfavorable'])};
      estas líneas explican al menos el 80%. Meses en <span class="mchip dn">rojo</span> = en contra
      del presupuesto, <span class="mchip up">verde</span> = a favor.</div></div>

  <footer>
    {f'<b>Base de comparación</b><ul>{alertas}</ul>' if alertas else ''}
    <b>Cómo leer las cifras</b><ul>{escalas}</ul>
    <b>Criterios</b><ul>{bases}</ul>
  </footer>
</div></body></html>"""
