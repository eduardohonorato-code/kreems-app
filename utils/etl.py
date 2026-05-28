"""
ETL functions — ACUÑA, Gran Natural, Presupuesto, CV Real Sync
Adaptados para Streamlit: reciben bytes del file_uploader,
usan get_engine() de db.py (Supabase via st.secrets).
"""
import io
import re
import pandas as pd
from sqlalchemy import text
from .db import get_engine

# ── Mapeos CC ─────────────────────────────────────────────────
MAPA_CC_ACUNA = {
    "NINGUNO":          "CC-00",
    "ADMINISTRACION":   "CC-01",
    "COSTO FABRICA":    "CC-04",
    "DISTRIBUCION":     "CC-03",
    "VENTAS":           "CC-02",
    "GERENCIA":         "CC-01",
    "MAQUINA COMODATO": "CC-03",
}

MAPA_CC_GN = {
    "Ninguno":        "CC-00",
    "Administracion": "CC-01",
    "Comercial":      "CC-02",
    "Distribucion":   "CC-03",
    "Produccion":     "CC-04",
}

HOJAS_CC_PPTO = {
    "ADMINISTRACIÓN": "CC-01",
    "PRODUCCIÓN":     "CC-04",
    "COMERCIAL":      "CC-02",
    "DISTRIBUCIÓN":   "CC-03",
}

MESES_PPTO = {
    "Ene": "01", "Enero": "01", "Feb": "02", "Febrero": "02",
    "Mar": "03", "Marzo": "03", "Abr": "04", "Abril": "04",
    "May": "05", "Mayo": "05", "Jun": "06", "Junio": "06",
    "Jul": "07", "Julio": "07", "Ago": "08", "Agosto": "08",
    "Sep": "09", "Septiembre": "09", "Oct": "10", "Octubre": "10",
    "Nov": "11", "Noviembre": "11", "Dic": "12", "Diciembre": "12",
}

FILAS_IGNORAR = {
    "total ingresos", "total gastos", "gastos", "ingresos",
    "cuenta", "resultado del ejercicio", "total"
}


def _log(lines: list, msg: str):
    lines.append(f"  {msg}")


def _extraer_periodo_obuma(ws) -> str:
    """Busca 'Desde el DD-MM-YYYY' en las primeras 5 filas del workbook."""
    for row in ws.iter_rows(max_row=5, values_only=True):
        for cell in row:
            if cell and isinstance(cell, str):
                match = re.search(r"Desde el[\s\xa0]+(\d{2})-(\d{2})-(\d{4})", cell)
                if match:
                    _, mes, anio = match.groups()
                    return f"{anio}-{mes}"
    raise ValueError("No se encontró el periodo en el encabezado. Revisa el formato del archivo.")


def _registrar_auditoria(engine, tabla, periodo, n, observaciones):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO audit.log_carga
                    (tabla_destino, archivo_origen, periodo, registros_cargados, estado, observaciones)
                VALUES (:t, 'webapp_upload', :p, :n, 'OK', :obs)
            """), {"t": tabla, "p": periodo, "n": n, "obs": observaciones})
    except Exception:
        pass  # El log no debe romper la carga principal


# ═══════════════════════════════════════════════════════════════
# ETL ACUÑA
# ═══════════════════════════════════════════════════════════════

def run_etl_acuna(file_bytes: bytes) -> dict:
    """
    Procesa Excel Obuma ACUÑA → marts.fact_real (sociedad = 'ACUÑA').
    Usa dim_homologacion para mapear cuentas ACUÑA → plan cuentas GN.
    """
    import openpyxl
    logs = []
    engine = get_engine()

    try:
        _log(logs, "Abriendo archivo Excel ACUÑA...")
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active

        periodo = _extraer_periodo_obuma(ws)
        _log(logs, f"Periodo detectado: {periodo}")

        # Cargar tabla de homologación
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT codigo_acuna, codigo_gn
                FROM master.dim_homologacion
                WHERE sociedad_origen = 'ACUÑA' AND activo = TRUE
            """)).fetchall()
        homologacion = {r[0]: (r[1] if r[1] else r[0]) for r in rows}
        _log(logs, f"Homologación cargada: {len(homologacion)} cuentas mapeadas")

        # Detectar columnas CC desde encabezado (fila 6, índice 5)
        all_rows = list(ws.iter_rows(values_only=True))
        if len(all_rows) < 7:
            raise ValueError("El archivo no tiene suficientes filas. ¿Es el archivo correcto?")

        headers = [str(h).strip().upper() if h else "" for h in all_rows[5]]
        MAPA_UPPER = {k.upper(): v for k, v in MAPA_CC_ACUNA.items()}
        cc_indices = {i: MAPA_UPPER[h] for i, h in enumerate(headers) if h in MAPA_UPPER}

        if not cc_indices:
            raise ValueError(f"No se encontraron columnas CC válidas. Encabezados: {headers}")
        _log(logs, f"Columnas CC detectadas: {list(set(cc_indices.values()))}")

        # Transformar filas
        registros = []
        for row in all_rows[6:]:
            celda = row[0]
            if not celda:
                continue
            celda_str = str(celda).strip()
            if celda_str.lower() in FILAS_IGNORAR or celda_str.startswith("Total"):
                continue
            codigo_raw = celda_str.split(" ", 1)[0].strip()
            if "." not in codigo_raw:
                continue
            if codigo_raw not in homologacion:
                continue
            codigo_gn = homologacion[codigo_raw]

            for idx, codigo_cc in cc_indices.items():
                if idx >= len(row) or row[idx] is None:
                    continue
                try:
                    monto = float(row[idx])
                except (TypeError, ValueError):
                    continue
                if monto == 0:
                    continue
                registros.append({
                    "fecha":          pd.to_datetime(f"{periodo}-01"),
                    "codigo_cuenta":  codigo_gn,
                    "codigo_cc":      codigo_cc,
                    "valor":          monto,
                    "periodo":        periodo,
                    "fuente":         "OBUMA",
                    "archivo_origen": "webapp_upload",
                    "sociedad":       "ACUÑA",
                })

        df = pd.DataFrame(registros)
        _log(logs, f"Registros procesados: {len(df)}")
        if df.empty:
            raise ValueError("No se encontraron registros válidos. Verifica que las cuentas estén en la tabla de homologación.")

        # Resumen por CC
        for cc, val in df.groupby("codigo_cc")["valor"].sum().items():
            _log(logs, f"  {cc}: ${val:,.0f}")

        # Cargar a BD
        with engine.begin() as conn:
            # Excluir fuente='CV_MANUAL' para preservar el costo variable ingresado manualmente
            r = conn.execute(text("""
                DELETE FROM marts.fact_real
                WHERE periodo = :p AND sociedad = 'ACUÑA' AND fuente <> 'CV_MANUAL'
            """), {"p": periodo})
            _log(logs, f"Registros anteriores eliminados: {r.rowcount} (CV Manual preservado)")

            df.to_sql("fact_real", con=conn, schema="marts", if_exists="append", index=False)

            conn.execute(text("""
                UPDATE marts.fact_real
                SET fecha_id = TO_CHAR(fecha, 'YYYYMMDD')::INT
                WHERE fecha_id IS NULL AND periodo = :p AND sociedad = 'ACUÑA'
            """), {"p": periodo})

        _log(logs, f"✓ {len(df)} registros cargados en marts.fact_real")
        _registrar_auditoria(engine, "marts.fact_real", periodo, len(df), "ETL ACUÑA via webapp")

        return {"ok": True, "periodo": periodo, "n_registros": len(df), "logs": logs, "error": None}

    except Exception as e:
        _log(logs, f"✗ Error: {e}")
        return {"ok": False, "periodo": None, "n_registros": 0, "logs": logs, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# ETL GRAN NATURAL
# ═══════════════════════════════════════════════════════════════

def run_etl_gn(file_bytes: bytes) -> dict:
    """
    Procesa Excel Obuma Gran Natural → marts.fact_real (sociedad = 'GRAN_NATURAL').
    """
    import openpyxl
    logs = []
    engine = get_engine()

    try:
        _log(logs, "Abriendo archivo Excel Gran Natural...")
        # Extraer periodo con openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        periodo = _extraer_periodo_obuma(ws)
        _log(logs, f"Periodo detectado: {periodo}")

        # Leer con pandas para el melt
        df_raw = pd.read_excel(io.BytesIO(file_bytes), header=None)
        _log(logs, f"Filas leídas: {len(df_raw)}")

        # El archivo GN tiene 7 columnas (Cuenta + 5 CC + Total)
        n_cols = len(df_raw.columns)
        if n_cols < 6:
            raise ValueError(f"El archivo tiene solo {n_cols} columnas. Se esperan al menos 6.")

        # Asignar nombres de columna estándar
        col_names = ["Cuenta", "Ninguno", "Administracion", "Comercial", "Distribucion", "Produccion"]
        if n_cols >= 7:
            col_names.append("Total")
        df_raw.columns = col_names + list(range(n_cols - len(col_names)))

        # Filtrar solo filas con código de cuenta (contienen ".")
        df = df_raw[
            df_raw["Cuenta"].notna() &
            df_raw["Cuenta"].astype(str).str.contains(r"\.", regex=True) &
            ~df_raw["Cuenta"].astype(str).str.startswith("Desde") &
            ~df_raw["Cuenta"].astype(str).str.startswith("Centro")
        ].copy()

        if df.empty:
            raise ValueError("No se encontraron filas con código de cuenta. ¿Es el archivo GN correcto?")

        df["codigo_cuenta"] = df["Cuenta"].astype(str).str.split(" ", n=1).str[0].str.strip()

        cols_cc = ["Ninguno", "Administracion", "Comercial", "Distribucion", "Produccion"]
        df_long = df.melt(
            id_vars=["codigo_cuenta"],
            value_vars=cols_cc,
            var_name="nombre_cc_raw",
            value_name="valor"
        )
        df_long["valor"] = pd.to_numeric(df_long["valor"], errors="coerce")
        df_long = df_long[df_long["valor"].notna() & (df_long["valor"] != 0)].copy()
        df_long["codigo_cc"]      = df_long["nombre_cc_raw"].map(MAPA_CC_GN)
        df_long["periodo"]        = periodo
        df_long["fecha"]          = pd.to_datetime(f"{periodo}-01")
        df_long["fuente"]         = "OBUMA"
        df_long["archivo_origen"] = "webapp_upload"
        df_long["sociedad"]       = "GRAN_NATURAL"

        df_final = df_long[["fecha", "codigo_cuenta", "codigo_cc",
                             "valor", "periodo", "fuente", "archivo_origen", "sociedad"]]

        _log(logs, f"Registros procesados: {len(df_final)}")
        if df_final.empty:
            raise ValueError("No se encontraron registros válidos después del filtrado.")

        for cc, val in df_final.groupby("codigo_cc")["valor"].sum().items():
            _log(logs, f"  {cc}: ${val:,.0f}")

        with engine.begin() as conn:
            # Excluir fuente='CV_MANUAL' para preservar el costo variable ingresado manualmente
            r = conn.execute(text("""
                DELETE FROM marts.fact_real
                WHERE periodo = :p AND sociedad = 'GRAN_NATURAL' AND fuente <> 'CV_MANUAL'
            """), {"p": periodo})
            _log(logs, f"Registros anteriores eliminados: {r.rowcount} (CV Manual preservado)")

            df_final.to_sql("fact_real", con=conn, schema="marts", if_exists="append", index=False)

            conn.execute(text("""
                UPDATE marts.fact_real
                SET fecha_id = TO_CHAR(fecha, 'YYYYMMDD')::INT
                WHERE fecha_id IS NULL AND periodo = :p AND sociedad = 'GRAN_NATURAL'
            """), {"p": periodo})

        _log(logs, f"✓ {len(df_final)} registros cargados en marts.fact_real")
        _registrar_auditoria(engine, "marts.fact_real", periodo, len(df_final), "ETL GRAN NATURAL via webapp")

        return {"ok": True, "periodo": periodo, "n_registros": len(df_final), "logs": logs, "error": None}

    except Exception as e:
        _log(logs, f"✗ Error: {e}")
        return {"ok": False, "periodo": None, "n_registros": 0, "logs": logs, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# ETL PRESUPUESTO
# ═══════════════════════════════════════════════════════════════

def run_etl_presupuesto(file_bytes: bytes, anio: str = "2026") -> dict:
    """
    Procesa Presupuesto_Maestro.xlsx → marts.fact_presupuesto.
    Reemplaza todo el presupuesto del año indicado.
    """
    logs = []
    engine = get_engine()
    MESES = {k: f"{anio}-{v}" for k, v in MESES_PPTO.items()}

    def leer_hoja_cc(hoja, codigo_cc):
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=hoja, header=None)
        header_row = next(
            (i for i, v in enumerate(df.iloc[:, 0]) if str(v).strip() == "CÓDIGO"), None
        )
        if header_row is None:
            raise ValueError(f"No se encontró 'CÓDIGO' en hoja '{hoja}'")
        df.columns = df.iloc[header_row].astype(str).str.strip()
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        cols = list(df.columns)
        cols[0] = "codigo_cuenta"
        df.columns = cols
        df["codigo_cuenta"] = df["codigo_cuenta"].astype(str).str.strip()
        df["codigo_cuenta"] = df["codigo_cuenta"].where(
            df["codigo_cuenta"].str.match(r'^\d+\.\d+\.\d+\.\d+$')
        ).ffill()
        df = df[df["codigo_cuenta"].str.match(r'^\d+\.\d+\.\d+\.\d+$', na=False)].copy()
        cols_mes = [c for c in df.columns if c in MESES]
        if not cols_mes:
            raise ValueError(f"No se encontraron columnas de meses en hoja '{hoja}'")
        for col in cols_mes:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df_agg = df.groupby("codigo_cuenta")[cols_mes].sum().reset_index()
        df_long = df_agg.melt(id_vars=["codigo_cuenta"], value_vars=cols_mes,
                              var_name="mes", value_name="valor")
        df_long["periodo"]        = df_long["mes"].map(MESES)
        df_long["fecha"]          = pd.to_datetime(df_long["periodo"] + "-01")
        df_long["codigo_cc"]      = codigo_cc
        df_long["fuente"]         = "PRESUPUESTO"
        df_long["archivo_origen"] = "webapp_upload"
        df_long = df_long[df_long["valor"] != 0]
        return df_long[["fecha", "codigo_cuenta", "codigo_cc", "valor",
                         "periodo", "fuente", "archivo_origen"]]

    def leer_consolidado():
        df = pd.read_excel(io.BytesIO(file_bytes),
                           sheet_name="Consolidado_Automatico", header=None)
        registros = []

        # Ventas (4.1.01.001): fila 2 = meses, fila 3 = valores
        meses_v   = [str(v).strip() for v in df.iloc[2, 0:12]]
        valores_v = df.iloc[3, 0:12].tolist()
        for mes, val in zip(meses_v, valores_v):
            if mes in MESES and pd.notna(val) and float(val) != 0:
                registros.append({
                    "fecha": pd.to_datetime(MESES[mes] + "-01"),
                    "codigo_cuenta": "4.1.01.001", "codigo_cc": "CC-00",
                    "valor": float(val), "periodo": MESES[mes],
                    "fuente": "PRESUPUESTO", "archivo_origen": "webapp_upload",
                })

        # CV (3.1.01.001): filas 6+7 y 11+12 (dos líneas de CV)
        for fila_mes, fila_val in [(6, 7), (11, 12)]:
            meses_cv  = [str(v).strip() for v in df.iloc[fila_mes, 0:12]]
            valores_cv = df.iloc[fila_val, 0:12].tolist()
            for mes, val in zip(meses_cv, valores_cv):
                if mes in MESES and pd.notna(val) and float(val) != 0:
                    existing = next(
                        (r for r in registros
                         if r["periodo"] == MESES[mes] and r["codigo_cuenta"] == "3.1.01.001"),
                        None
                    )
                    if existing:
                        existing["valor"] += float(val)
                    else:
                        registros.append({
                            "fecha": pd.to_datetime(MESES[mes] + "-01"),
                            "codigo_cuenta": "3.1.01.001", "codigo_cc": "CC-00",
                            "valor": float(val), "periodo": MESES[mes],
                            "fuente": "PRESUPUESTO", "archivo_origen": "webapp_upload",
                        })
        return pd.DataFrame(registros)

    try:
        _log(logs, f"Procesando Presupuesto Maestro {anio}...")
        frames = []

        for hoja, codigo_cc in HOJAS_CC_PPTO.items():
            _log(logs, f"  Leyendo hoja {hoja} ({codigo_cc})...")
            df_cc = leer_hoja_cc(hoja, codigo_cc)
            _log(logs, f"    → {len(df_cc)} registros")
            frames.append(df_cc)

        _log(logs, "  Leyendo Consolidado_Automatico (Ventas + CV)...")
        df_consol = leer_consolidado()
        _log(logs, f"    → {len(df_consol)} registros")
        if not df_consol.empty:
            frames.append(df_consol)

        df_final = pd.concat(frames, ignore_index=True)
        _log(logs, f"Total registros a cargar: {len(df_final)}")

        # Resumen por CC (total anual)
        for cc, val in df_final.groupby("codigo_cc")["valor"].sum().items():
            _log(logs, f"  {cc}: ${val:,.0f}")

        with engine.begin() as conn:
            r = conn.execute(text(
                "DELETE FROM marts.fact_presupuesto WHERE periodo LIKE :anio"
            ), {"anio": f"{anio}-%"})
            _log(logs, f"Registros anteriores eliminados: {r.rowcount}")

            df_final.to_sql("fact_presupuesto", con=conn, schema="marts",
                            if_exists="append", index=False, method="multi")

            conn.execute(text("""
                UPDATE marts.fact_presupuesto
                SET fecha_id = TO_CHAR(fecha, 'YYYYMMDD')::INT
                WHERE fecha_id IS NULL AND periodo LIKE :anio
            """), {"anio": f"{anio}-%"})

        _log(logs, f"✓ {len(df_final)} registros cargados en marts.fact_presupuesto")
        _registrar_auditoria(engine, "marts.fact_presupuesto",
                             f"{anio}-AN", len(df_final), "ETL Presupuesto via webapp")

        return {"ok": True, "periodo": f"{anio} (anual)", "n_registros": len(df_final),
                "logs": logs, "error": None}

    except Exception as e:
        _log(logs, f"✗ Error: {e}")
        return {"ok": False, "periodo": None, "n_registros": 0, "logs": logs, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# CV REAL SYNC
# ═══════════════════════════════════════════════════════════════

CODIGO_CUENTA_CV = "3.1.01.001"
CODIGO_CC_CV     = "CC-00"

PERIODOS_2026 = {
    f"2026-{m:02d}": f"2026-{m:02d}" for m in range(1, 13)
}


def guardar_cv_staging(periodo: str, sociedad: str, monto: float) -> dict:
    """
    Inserta o actualiza un registro en staging.cv_real_manual.
    Si ya existe el periodo+sociedad, lo reemplaza (DELETE + INSERT).
    """
    logs = []
    engine = get_engine()
    try:
        fecha = pd.to_datetime(f"{periodo}-01")
        with engine.begin() as conn:
            r = conn.execute(text("""
                DELETE FROM staging.cv_real_manual
                WHERE TO_CHAR(periodo, 'YYYY-MM') = :p AND sociedad = :s
            """), {"p": periodo, "s": sociedad})
            _log(logs, f"Registros anteriores eliminados: {r.rowcount}")

            conn.execute(text("""
                INSERT INTO staging.cv_real_manual (periodo, sociedad, monto)
                VALUES (:fecha, :s, :m)
            """), {"fecha": fecha, "s": sociedad, "m": monto})
            _log(logs, f"✓ Guardado: {sociedad} {periodo} → ${monto:,.0f}")

        return {"ok": True, "logs": logs, "error": None}
    except Exception as e:
        _log(logs, f"✗ Error: {e}")
        return {"ok": False, "logs": logs, "error": str(e)}


def eliminar_cv_staging(periodo: str, sociedad: str) -> dict:
    """Elimina un registro de staging.cv_real_manual."""
    logs = []
    engine = get_engine()
    try:
        with engine.begin() as conn:
            r = conn.execute(text("""
                DELETE FROM staging.cv_real_manual
                WHERE TO_CHAR(periodo, 'YYYY-MM') = :p AND sociedad = :s
            """), {"p": periodo, "s": sociedad})
        _log(logs, f"Eliminado: {sociedad} {periodo} ({r.rowcount} fila)")
        return {"ok": True, "logs": logs, "error": None}
    except Exception as e:
        _log(logs, f"✗ Error: {e}")
        return {"ok": False, "logs": logs, "error": str(e)}


def run_etl_cv_sync() -> dict:
    """
    Sincroniza staging.cv_real_manual → marts.fact_real (COSTO_VAR).
    Para cada periodo+sociedad en staging:
      - Elimina filas con codigo_cuenta = '3.1.01.001' en fact_real
      - Inserta el nuevo monto con fuente = 'CV_MANUAL'
    """
    logs = []
    engine = get_engine()
    try:
        # Leer staging
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT
                    periodo::date                  AS fecha,
                    TO_CHAR(periodo, 'YYYY-MM')    AS periodo_str,
                    sociedad,
                    monto                          AS valor
                FROM staging.cv_real_manual
                WHERE monto > 0
                ORDER BY periodo, sociedad
            """), conn)

        if df.empty:
            _log(logs, "staging.cv_real_manual no tiene registros con monto > 0.")
            return {"ok": True, "n_registros": 0, "logs": logs, "error": None}

        _log(logs, f"Registros en staging: {len(df)}")
        for _, row in df.iterrows():
            _log(logs, f"  {row['periodo_str']} | {row['sociedad']:12s} | ${row['valor']:>15,.0f}")

        # Preparar DataFrame para fact_real
        df_insert = pd.DataFrame({
            "fecha":          df["fecha"],
            "codigo_cuenta":  CODIGO_CUENTA_CV,
            "codigo_cc":      CODIGO_CC_CV,
            "valor":          df["valor"],
            "periodo":        df["periodo_str"],
            "fuente":         "CV_MANUAL",
            "archivo_origen": "staging.cv_real_manual",
            "sociedad":       df["sociedad"],
        })
        df_insert["fecha_id"] = df["fecha"].apply(lambda d: int(d.strftime("%Y%m%d")))

        # Sincronizar período a período
        with engine.begin() as conn:
            for (periodo, sociedad), grupo in df_insert.groupby(["periodo", "sociedad"]):
                r = conn.execute(text("""
                    DELETE FROM marts.fact_real
                    WHERE periodo = :p AND sociedad = :s AND codigo_cuenta = :cc
                """), {"p": periodo, "s": sociedad, "cc": CODIGO_CUENTA_CV})
                _log(logs, f"  Eliminados {r.rowcount} registros anteriores — {sociedad} {periodo}")

                grupo.to_sql("fact_real", con=conn, schema="marts",
                             if_exists="append", index=False)
                _log(logs, f"  Insertado {len(grupo)} registro — {sociedad} {periodo}  ${grupo['valor'].sum():,.0f}")

        _log(logs, f"✓ Sincronización completa — {len(df_insert)} registros en fact_real")
        _registrar_auditoria(engine, "marts.fact_real", "MULTI", len(df_insert),
                             "ETL CV_REAL SYNC via webapp")

        return {"ok": True, "n_registros": len(df_insert), "logs": logs, "error": None}

    except Exception as e:
        _log(logs, f"✗ Error: {e}")
        return {"ok": False, "n_registros": 0, "logs": logs, "error": str(e)}
