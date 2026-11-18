"""
EERR por Centro de Costo — lógica de cálculo (pura, sin Streamlit).

El P&L se arma con las mismas reglas del Reporte de Gerencia
(`reporte_gerencia.normalizar_movimientos` y `LINEAS_PL`), abierto en columnas
por centro de costo:

  - Las ventas y el costo variable se registran sin centro de costo (CC-00),
    así que la Utilidad Bruta vive en esa columna; Administración, Comercial,
    Distribución y Producción solo restan gasto. El EBIT se lee en «Total».
  - «Desvío» lleva el signo del efecto sobre el resultado: positivo = favorable
    (se vendió más o se gastó menos), negativo = desfavorable.
"""
from __future__ import annotations

import pandas as pd

from utils import reporte_gerencia as rg
from utils.db import query

COL_TOTAL = "Total"
VISTAS = ("Real", "Presupuesto", "Desvío")


def columnas_cc(d: pd.DataFrame) -> list[str]:
    """Códigos de CC presentes en los datos: CC-00 primero, luego en orden."""
    codigos = sorted(set(d["codigo_cc"].dropna().astype(str)))
    if rg.CC_SIN_ASIGNAR in codigos:
        codigos.remove(rg.CC_SIN_ASIGNAR)
        codigos.insert(0, rg.CC_SIN_ASIGNAR)
    return codigos


def etiqueta_cc(codigo: str) -> str:
    return rg._label_cc(codigo)


def _por_clasif(frame: pd.DataFrame, col: str) -> dict:
    s = frame.groupby("clasificacion")[col].sum()
    return {c: float(s.get(c, 0.0)) for c in rg.CLASIFS}


def _lineas(x: dict) -> dict:
    """{etiqueta de línea: valor} para un bloque de clasificaciones."""
    der = rg._derivados(x)
    return {lbl: (x[clasif] if clasif else der[clave])
            for lbl, clasif, clave in rg.LINEAS_PL}


def _lineas_desvio(r: dict, p: dict) -> dict:
    """Desvío con signo de efecto: en líneas según su naturaleza, en subtotales R − P."""
    dr, dp = rg._derivados(r), rg._derivados(p)
    out = {}
    for lbl, clasif, clave in rg.LINEAS_PL:
        out[lbl] = (rg._efecto(clasif, r[clasif] - p[clasif]) if clasif
                    else dr[clave] - dp[clave])
    return out


def matriz(d: pd.DataFrame, vista: str) -> pd.DataFrame:
    """
    P&L con líneas en filas y centros de costo en columnas (+ Total).
    `d` debe venir de `rg.normalizar_movimientos` y ya filtrado al período.
    """
    ccs = columnas_cc(d)
    cols = {}
    for cc in ccs + [COL_TOTAL]:
        sub = d if cc == COL_TOTAL else d[d["codigo_cc"] == cc]
        r, p = _por_clasif(sub, "real"), _por_clasif(sub, "ppto")
        if vista == "Real":
            cols[cc] = _lineas(r)
        elif vista == "Presupuesto":
            cols[cc] = _lineas(p)
        else:
            cols[cc] = _lineas_desvio(r, p)
    out = pd.DataFrame(cols)
    out.columns = [etiqueta_cc(c) if c != COL_TOTAL else COL_TOTAL for c in out.columns]
    out.index.name = "Línea"
    return out.reset_index()


def resumen_cc(d: pd.DataFrame, codigo_cc: str | None) -> pd.DataFrame:
    """Real, Presupuesto, Desvío y % de ejecución por línea para un CC (None = total)."""
    sub = d if codigo_cc is None else d[d["codigo_cc"] == codigo_cc]
    r, p = _por_clasif(sub, "real"), _por_clasif(sub, "ppto")
    lr, lp, ld = _lineas(r), _lineas(p), _lineas_desvio(r, p)
    filas = []
    for lbl, _clasif, _clave in rg.LINEAS_PL:
        filas.append({"Línea": lbl, "Real": lr[lbl], "Presupuesto": lp[lbl],
                      "Desvío": ld[lbl], "% Ejec.": rg._pct(lr[lbl], lp[lbl])})
    return pd.DataFrame(filas)


def detalle_cuentas(d: pd.DataFrame, codigo_cc: str | None = None) -> pd.DataFrame:
    """Cuentas con movimiento (real o ppto), agrupadas por línea del P&L."""
    sub = d if codigo_cc is None else d[d["codigo_cc"] == codigo_cc]
    g = (sub.groupby(["clasificacion", "codigo_cc", "codigo_cuenta", "nombre_cuenta"],
                     as_index=False)[["real", "ppto"]].sum())
    g = g[(g["real"].abs() >= 1) | (g["ppto"].abs() >= 1)]
    if g.empty:
        return pd.DataFrame(columns=["Línea", "Centro de costo", "Cuenta",
                                     "Real", "Presupuesto", "Desvío", "% Ejec."])
    orden = {c: i for i, (_l, c, _k) in enumerate(rg.LINEAS_PL) if c}
    g["_ord"] = g["clasificacion"].map(orden).fillna(99)
    g["Línea"] = g["clasificacion"].map(rg.ETIQUETA_LINEA).fillna(g["clasificacion"])
    g["Centro de costo"] = g["codigo_cc"].map(etiqueta_cc)
    g["Cuenta"] = g["codigo_cuenta"] + " " + g["nombre_cuenta"].map(rg.nombre_legible)
    g["Desvío"] = [rg._efecto(c, r - p) for c, r, p in zip(g["clasificacion"], g["real"], g["ppto"])]
    g["% Ejec."] = [rg._pct(r, p) for r, p in zip(g["real"], g["ppto"])]
    g = g.sort_values(["_ord", "codigo_cc", "real"], ascending=[True, True, False])
    return (g.rename(columns={"real": "Real", "ppto": "Presupuesto"})
             [["Línea", "Centro de costo", "Cuenta", "Real", "Presupuesto", "Desvío", "% Ejec."]]
             .reset_index(drop=True))


LINEAS_SUBTOTAL = {lbl for lbl, clasif, _k in rg.LINEAS_PL if clasif is None}


# ── MES A MES (rango que puede cruzar años) ───────────────────

def periodos_rango(desde: str, hasta: str) -> list[str]:
    """'2025-11', '2026-10' → ['2025-11', '2025-12', ..., '2026-10']."""
    a, m = int(desde[:4]), int(desde[5:7])
    fa, fm = int(hasta[:4]), int(hasta[5:7])
    out = []
    while (a, m) <= (fa, fm):
        out.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def sumar_meses(periodo: str, n: int) -> str:
    a, m = int(periodo[:4]), int(periodo[5:7])
    tot = a * 12 + (m - 1) + n
    return f"{tot // 12}-{tot % 12 + 1:02d}"


def etiqueta_periodo(periodo: str) -> str:
    """'2025-11' → 'Nov-25'."""
    return f"{rg.ABREV_MES[int(periodo[5:7])]}-{periodo[2:4]}"


def cargar_rango(desde: str, hasta: str, filtro_cc: str = "") -> pd.DataFrame:
    """Detalle periodo × sociedad × cuenta × CC del rango, todas las sociedades."""
    return query(f"""
        SELECT periodo, sociedad, codigo_cc, nombre_cc, codigo_cuenta, nombre_cuenta,
               clasificacion, categoria_eerr,
               SUM(valor_real) AS real,
               SUM(valor_ppto) AS ppto
        FROM marts.vw_real_vs_ppto
        WHERE periodo BETWEEN :d AND :h {filtro_cc}
        GROUP BY periodo, sociedad, codigo_cc, nombre_cc, codigo_cuenta, nombre_cuenta,
                 clasificacion, categoria_eerr
    """, {"d": desde, "h": hasta})


def matriz_mensual(d: pd.DataFrame, vista: str, periodos: list[str]) -> pd.DataFrame:
    """P&L con líneas en filas y meses en columnas (+ Total del rango)."""
    cols = {}
    for per in periodos + [COL_TOTAL]:
        sub = d if per == COL_TOTAL else d[d["periodo"] == per]
        r, p = _por_clasif(sub, "real"), _por_clasif(sub, "ppto")
        cols[per] = (_lineas(r) if vista == "Real" else
                     _lineas(p) if vista == "Presupuesto" else _lineas_desvio(r, p))
    out = pd.DataFrame(cols)
    out.columns = [etiqueta_periodo(c) if c != COL_TOTAL else COL_TOTAL for c in out.columns]
    out.index.name = "Línea"
    return out.reset_index()


TOTAL_EMPRESA = "Total empresa"
# Líneas que se muestran en cada bloque de CC aunque estén en cero
_LINEAS_SIEMPRE = {"EBIT", "Utilidad Neta"}


def matriz_mensual_por_cc(d: pd.DataFrame, vista: str, periodos: list[str]) -> pd.DataFrame:
    """
    P&L mes a mes abierto por centro de costo: un bloque de líneas por CC
    (solo las líneas con movimiento, más EBIT y Utilidad Neta) y al final el
    bloque «Total empresa» completo. Columnas: Centro de costo, Línea, meses, Total.
    """
    bloques = []
    for cc in columnas_cc(d) + [None]:
        sub = d if cc is None else d[d["codigo_cc"] == cc]
        m = matriz_mensual(sub, vista, periodos)
        if cc is not None:
            num = [c for c in m.columns if c != "Línea"]
            m = m[(m[num].abs() >= 1).any(axis=1) | m["Línea"].isin(_LINEAS_SIEMPRE)]
        m.insert(0, "Centro de costo", TOTAL_EMPRESA if cc is None else etiqueta_cc(cc))
        bloques.append(m)
    return pd.concat(bloques, ignore_index=True)


def cuentas_mensual(d: pd.DataFrame, periodos: list[str], col: str = "real") -> pd.DataFrame:
    """Cuenta × CC en filas, meses en columnas (+ Total). Solo cuentas con movimiento."""
    claves = ["clasificacion", "codigo_cc", "codigo_cuenta", "nombre_cuenta"]
    piv = d.pivot_table(index=claves, columns="periodo", values=col,
                        aggfunc="sum", fill_value=0.0)
    for per in periodos:
        if per not in piv.columns:
            piv[per] = 0.0
    piv = piv[periodos]
    piv = piv[(piv.abs() >= 1).any(axis=1)].reset_index()
    if piv.empty:
        return pd.DataFrame(columns=["Línea", "Centro de costo", "Cuenta"]
                            + [etiqueta_periodo(p) for p in periodos] + [COL_TOTAL])
    orden = {c: i for i, (_l, c, _k) in enumerate(rg.LINEAS_PL) if c}
    piv["_ord"] = piv["clasificacion"].map(orden).fillna(99)
    piv = piv.sort_values(["_ord", "codigo_cc", "codigo_cuenta"])
    out = pd.DataFrame({
        "Línea": piv["clasificacion"].map(rg.ETIQUETA_LINEA).fillna(piv["clasificacion"]),
        "Centro de costo": piv["codigo_cc"].map(etiqueta_cc),
        "Cuenta": piv["codigo_cuenta"] + " " + piv["nombre_cuenta"].map(rg.nombre_legible),
    })
    for per in periodos:
        out[etiqueta_periodo(per)] = piv[per].values
    out[COL_TOTAL] = piv[periodos].sum(axis=1).values
    return out.reset_index(drop=True)


def meses_sin_real(d: pd.DataFrame, periodos: list[str], sociedad: str) -> list[str]:
    """Meses del rango en que la sociedad no tiene ningún real cargado."""
    s = d[d["sociedad"] == sociedad]
    con = set(s.loc[s["real"].abs() >= 1, "periodo"])
    return [p for p in periodos if p not in con]
