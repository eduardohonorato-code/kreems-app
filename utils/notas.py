"""
Helpers para Notas de Gestión (reports.notas_gestion).
"""
from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from utils.db import get_engine


def guardar_nota(
    periodo_desde: str,
    periodo_hasta: str,
    sociedad: str,
    tipo: str,
    referencia: str,
    nota: str,
    creado_por: str = "",
) -> None:
    """
    Inserta o actualiza una nota (upsert por constraint UNIQUE).
    tipo: 'CC' | 'CUENTA' | 'EERR'
    """
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO reports.notas_gestion
                (periodo_desde, periodo_hasta, sociedad, tipo, referencia, nota, creado_por)
            VALUES
                (:pdesde, :phasta, :sociedad, :tipo, :ref, :nota, :usuario)
            ON CONFLICT ON CONSTRAINT uq_nota
            DO UPDATE SET
                nota           = EXCLUDED.nota,
                creado_por     = EXCLUDED.creado_por,
                actualizado_en = NOW()
        """), {
            "pdesde":  periodo_desde,
            "phasta":  periodo_hasta,
            "sociedad": sociedad,
            "tipo":    tipo,
            "ref":     referencia,
            "nota":    nota,
            "usuario": creado_por,
        })


def obtener_notas(
    periodo_desde: str,
    periodo_hasta: str,
    sociedad: str,
    tipo: str | None = None,
) -> pd.DataFrame:
    """
    Retorna notas del período/sociedad como DataFrame.
    Columnas: id, tipo, referencia, nota, creado_por, creado_en, actualizado_en
    """
    filtro_tipo = "AND tipo = :tipo" if tipo else ""
    params: dict = {
        "pdesde":   periodo_desde,
        "phasta":   periodo_hasta,
        "sociedad": sociedad,
    }
    if tipo:
        params["tipo"] = tipo

    with get_engine().connect() as conn:
        return pd.read_sql(text(f"""
            SELECT id, tipo, referencia, nota, creado_por,
                   creado_en AT TIME ZONE 'America/Santiago' AS creado_en,
                   actualizado_en AT TIME ZONE 'America/Santiago' AS actualizado_en
            FROM reports.notas_gestion
            WHERE periodo_desde = :pdesde
              AND periodo_hasta  = :phasta
              AND sociedad        = :sociedad
              {filtro_tipo}
            ORDER BY actualizado_en DESC
        """), conn, params=params)


def eliminar_nota(nota_id: int) -> None:
    """Elimina una nota por su id."""
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM reports.notas_gestion WHERE id = :id"),
            {"id": nota_id},
        )


# ── Comentarios del plan de acción (Reporte de Gerencia) ──────
# tipo 'DESVIO', referencia '<codigo_cuenta>|<codigo_cc>', vigente todo el año.
TIPO_DESVIO = "DESVIO"


def obtener_notas_desvio(ano: int) -> dict:
    """{(codigo_cuenta, codigo_cc): {explicacion, accion, responsable, fecha, actualizado}}"""
    with get_engine().connect() as conn:
        df = pd.read_sql(text("""
            SELECT referencia, nota, accion, responsable, fecha_compromiso,
                   actualizado_en AT TIME ZONE 'America/Santiago' AS actualizado_en
            FROM reports.notas_gestion
            WHERE tipo = :tipo AND periodo_desde = :d AND periodo_hasta = :h
        """), conn, params={"tipo": TIPO_DESVIO, "d": f"{ano}-01", "h": f"{ano}-12"})
    out = {}
    for r in df.itertuples():
        cuenta, _, cc = str(r.referencia).partition("|")
        out[(cuenta, cc)] = {
            "explicacion": r.nota or "",
            "accion": r.accion or "",
            "responsable": r.responsable or "",
            "fecha": r.fecha_compromiso if pd.notna(r.fecha_compromiso) else None,
            "actualizado": r.actualizado_en,
        }
    return out


def guardar_notas_desvio(ano: int, filas: list, creado_por: str = "") -> int:
    """
    Guarda los comentarios del plan de acción. Cada fila: codigo_cuenta, codigo_cc,
    explicacion, accion, responsable, fecha. Una fila sin ningún texto borra la nota.
    Retorna cuántas notas quedaron guardadas.
    """
    n = 0
    with get_engine().begin() as conn:
        for f in filas:
            ref = f"{f['codigo_cuenta']}|{f['codigo_cc']}"
            clave = {"tipo": TIPO_DESVIO, "d": f"{ano}-01", "h": f"{ano}-12", "ref": ref}
            textos = [str(f.get(k) or "").strip() for k in ("explicacion", "accion", "responsable")]
            fecha = f.get("fecha") or None
            if not any(textos) and not fecha:
                conn.execute(text("""
                    DELETE FROM reports.notas_gestion
                    WHERE tipo = :tipo AND periodo_desde = :d AND periodo_hasta = :h
                      AND sociedad = 'Todas' AND referencia = :ref
                """), clave)
                continue
            conn.execute(text("""
                INSERT INTO reports.notas_gestion
                    (periodo_desde, periodo_hasta, sociedad, tipo, referencia, nota,
                     accion, responsable, fecha_compromiso, creado_por)
                VALUES (:d, :h, 'Todas', :tipo, :ref, :nota, :accion, :resp, :fecha, :usuario)
                ON CONFLICT ON CONSTRAINT uq_nota
                DO UPDATE SET nota = EXCLUDED.nota, accion = EXCLUDED.accion,
                              responsable = EXCLUDED.responsable,
                              fecha_compromiso = EXCLUDED.fecha_compromiso,
                              creado_por = EXCLUDED.creado_por, actualizado_en = NOW()
            """), {**clave, "nota": textos[0], "accion": textos[1], "resp": textos[2],
                   "fecha": fecha, "usuario": creado_por})
            n += 1
    return n
