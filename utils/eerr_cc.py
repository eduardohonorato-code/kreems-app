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
