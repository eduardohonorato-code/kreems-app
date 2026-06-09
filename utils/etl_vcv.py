"""
ETL Presupuesto VENTAS & COSTO VARIABLE (por categoría).
staging.ppto_ventas_cv → marts.fact_presupuesto (CC-00):
    VENTA          → 4.1.01.001
    COSTO_VARIABLE → 3.1.01.001
Reutiliza helpers de utils.etl.
"""
import io
from datetime import date
import pandas as pd
from sqlalchemy import text
from .db import get_engine
from .etl import _MESES_DET, _norm_txt, _log, _registrar_auditoria

CUENTA_VENTA   = "4.1.01.001"
CUENTA_CV_PPTO = "3.1.01.001"
CC_VENTAS_CV   = "CC-00"

_MAPA_COLS_VCV = {
    "tipo": "tipo",
    "categoria": "categoria",
    "categoria/producto": "categoria",
    "categoría": "categoria",
    "notas": "notas",
    **{m: m for m in _MESES_DET},
}


def _norm_tipo_vcv(v) -> str:
    """Normaliza el tipo a 'VENTA' o 'COSTO_VARIABLE'."""
    t = _norm_txt(v)
    if t.startswith("venta"):
        return "VENTA"
    if ("cost" in t and "var" in t) or t in ("cv", "costo_variable"):
        return "COSTO_VARIABLE"
    return ""


def sincronizar_ppto_ventas_cv(anio=None) -> dict:
    """
    Reagrega staging.ppto_ventas_cv → marts.fact_presupuesto (CC-00).
    Solo toca 4.1.01.001 y 3.1.01.001 en CC-00; el resto queda intacto.
    """
    if anio is None:
        anio = date.today().year
    anio = str(anio)
    logs = []
    engine = get_engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT tipo, ene, feb, mar, abr, may, jun,
                       jul, ago, sep, oct, nov, dic
                FROM staging.ppto_ventas_cv
                WHERE ano = :a
            """), conn, params={"a": int(anio)})

        # Limpiar las dos cuentas CC-00 del año antes de reinsertar
        with engine.begin() as conn:
            r = conn.execute(text("""
                DELETE FROM marts.fact_presupuesto
                WHERE periodo LIKE :a AND codigo_cc = :cc
                  AND codigo_cuenta IN (:cv, :cu)
            """), {"a": f"{anio}-%", "cc": CC_VENTAS_CV,
                   "cv": CUENTA_VENTA, "cu": CUENTA_CV_PPTO})
            _log(logs, f"fact_presupuesto: {r.rowcount} filas ventas/CV (CC-00) eliminadas")

        if df.empty:
            _log(logs, "staging.ppto_ventas_cv sin registros para el año.")
            return {"ok": True, "n_registros": 0, "logs": logs, "error": None}

        registros = []
        for _, row in df.iterrows():
            tipo = _norm_tipo_vcv(row["tipo"])
            if tipo == "VENTA":
                cuenta = CUENTA_VENTA
            elif tipo == "COSTO_VARIABLE":
                cuenta = CUENTA_CV_PPTO
            else:
                continue
            for i, mes in enumerate(_MESES_DET, start=1):
                valor = float(row[mes] or 0)
                if valor == 0:
                    continue
                periodo = f"{anio}-{i:02d}"
                registros.append({
                    "fecha":          pd.to_datetime(f"{periodo}-01"),
                    "codigo_cuenta":  cuenta,
                    "codigo_cc":      CC_VENTAS_CV,
                    "valor":          valor,
                    "periodo":        periodo,
                    "fuente":         "PPTO_VENTAS_CV",
                    "archivo_origen": "staging.ppto_ventas_cv",
                })

        if not registros:
            _log(logs, "Sin montos > 0 para reagregar.")
            return {"ok": True, "n_registros": 0, "logs": logs, "error": None}

        df_long = pd.DataFrame(registros)
        df_agg = (df_long
                  .groupby(["fecha", "codigo_cuenta", "codigo_cc", "periodo",
                            "fuente", "archivo_origen"], as_index=False)["valor"].sum())
        df_agg["fecha_id"] = df_agg["fecha"].apply(lambda d: int(d.strftime("%Y%m%d")))

        with engine.begin() as conn:
            df_agg.to_sql("fact_presupuesto", con=conn, schema="marts",
                          if_exists="append", index=False, method="multi")

        total = df_agg["valor"].sum()
        _log(logs, f"✓ Reagregadas {len(df_agg)} filas (ventas/CV) a fact_presupuesto (${total:,.0f})")
        _registrar_auditoria(engine, "marts.fact_presupuesto", f"{anio}-VCV",
                             len(df_agg), "Reagregacion ppto_ventas_cv")
        return {"ok": True, "n_registros": len(df_agg), "logs": logs, "error": None}

    except Exception as e:
        _log(logs, f"Error: {e}")
        return {"ok": False, "n_registros": 0, "logs": logs, "error": str(e)}


def run_etl_ppto_ventas_cv(file_bytes: bytes, anio=None) -> dict:
    """Carga Excel plano (hoja PPTO_VENTAS_CV) → staging.ppto_ventas_cv y reagrega."""
    if anio is None:
        anio = date.today().year
    anio = str(anio)
    logs = []
    engine = get_engine()
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        hoja = next((h for h in xls.sheet_names
                     if "ventas" in _norm_txt(h) or "vcv" in _norm_txt(h)),
                    xls.sheet_names[0])
        df = pd.read_excel(xls, sheet_name=hoja)
        _log(logs, f"Hoja leida: {hoja} ({len(df)} filas)")

        ren = {}
        for col in df.columns:
            campo = _MAPA_COLS_VCV.get(_norm_txt(col))
            if campo:
                ren[col] = campo
        df = df.rename(columns=ren)

        req = ["tipo"] + _MESES_DET
        faltan = [c for c in req if c not in df.columns]
        if faltan:
            raise ValueError(f"Faltan columnas en el Excel: {faltan}. "
                             f"Revisa que la hoja tenga el formato PPTO_VENTAS_CV.")

        for opt in ["categoria", "notas"]:
            if opt not in df.columns:
                df[opt] = ""

        df["tipo"] = df["tipo"].apply(_norm_tipo_vcv)
        for c in ["categoria", "notas"]:
            df[c] = (df[c].fillna("").astype(str).str.strip()
                     .replace({"nan": "", "None": "", "<NA>": ""}))
        for m in _MESES_DET:
            df[m] = pd.to_numeric(df[m], errors="coerce").fillna(0.0)

        df = df[df["tipo"].isin(["VENTA", "COSTO_VARIABLE"])].copy()
        if df.empty:
            raise ValueError("No se encontraron filas con tipo VENTA o COSTO_VARIABLE.")

        df["ano"] = int(anio)
        cols_final = ["ano", "tipo", "categoria", "notas"] + _MESES_DET
        df_insert = df[cols_final].copy()
        _log(logs, f"Filas validas a cargar: {len(df_insert)}")

        with engine.begin() as conn:
            r = conn.execute(text("DELETE FROM staging.ppto_ventas_cv WHERE ano = :a"),
                             {"a": int(anio)})
            _log(logs, f"staging.ppto_ventas_cv: {r.rowcount} filas anteriores eliminadas")
            df_insert.to_sql("ppto_ventas_cv", con=conn, schema="staging",
                             if_exists="append", index=False, method="multi")

        _log(logs, f"✓ {len(df_insert)} categorias cargadas en staging.ppto_ventas_cv")

        res_sync = sincronizar_ppto_ventas_cv(anio)
        logs.extend(res_sync["logs"])
        if not res_sync["ok"]:
            return {"ok": False, "periodo": f"{anio} (ventas/CV)", "n_registros": len(df_insert),
                    "logs": logs, "error": res_sync["error"]}

        _registrar_auditoria(engine, "staging.ppto_ventas_cv", f"{anio}-VCV",
                             len(df_insert), "Carga ppto_ventas_cv via webapp")
        return {"ok": True, "periodo": f"{anio} (ventas/CV)", "n_registros": len(df_insert),
                "logs": logs, "error": None}

    except Exception as e:
        _log(logs, f"Error: {e}")
        return {"ok": False, "periodo": None, "n_registros": 0, "logs": logs, "error": str(e)}


def reemplazar_ppto_ventas_cv(anio, tipo: str, df_rows: pd.DataFrame) -> dict:
    """
    Reemplaza las categorías de un tipo (VENTA / COSTO_VARIABLE) del año con las filas
    editadas en la web y reagrega. df_rows: categoria, notas, ene..dic.
    """
    anio = str(anio)
    tipo = _norm_tipo_vcv(tipo) or tipo
    logs = []
    engine = get_engine()
    try:
        df = df_rows.copy()
        for c in ["categoria", "notas"]:
            if c not in df.columns:
                df[c] = ""
            df[c] = df[c].fillna("").astype(str).str.strip()
        for m in _MESES_DET:
            df[m] = pd.to_numeric(df.get(m, 0), errors="coerce").fillna(0.0)

        # Descartar filas totalmente vacías
        df = df[(df["categoria"] != "") | (df[_MESES_DET].sum(axis=1) != 0)].copy()

        df["ano"] = int(anio)
        df["tipo"] = tipo
        cols_final = ["ano", "tipo", "categoria", "notas"] + _MESES_DET
        df_insert = df[cols_final]

        with engine.begin() as conn:
            r = conn.execute(text("""
                DELETE FROM staging.ppto_ventas_cv WHERE ano = :a AND tipo = :t
            """), {"a": int(anio), "t": tipo})
            _log(logs, f"Eliminadas {r.rowcount} filas previas — {tipo} {anio}")
            if not df_insert.empty:
                df_insert.to_sql("ppto_ventas_cv", con=conn, schema="staging",
                                 if_exists="append", index=False, method="multi")
        _log(logs, f"Guardadas {len(df_insert)} categorias — {tipo} {anio}")

        res_sync = sincronizar_ppto_ventas_cv(anio)
        logs.extend(res_sync["logs"])
        return {"ok": res_sync["ok"], "n_registros": len(df_insert),
                "logs": logs, "error": res_sync.get("error")}

    except Exception as e:
        _log(logs, f"Error: {e}")
        return {"ok": False, "n_registros": 0, "logs": logs, "error": str(e)}
