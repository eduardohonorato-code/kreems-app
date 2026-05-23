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
