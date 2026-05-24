"""
CRUD para reports.riesgos_oportunidades
"""
from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from utils.db import query, get_engine


def obtener_riesgos(periodo_ref: str, sociedad: str = "Todas") -> pd.DataFrame:
    """Retorna todos los registros del período (y sociedad si aplica)."""
    filtro = "AND sociedad = :soc" if sociedad != "Todas" else ""
    return query(f"""
        SELECT *
        FROM reports.riesgos_oportunidades
        WHERE periodo_ref = :periodo {filtro}
        ORDER BY tipo, probabilidad DESC, impacto_nivel DESC
    """, {"periodo": periodo_ref, "soc": sociedad})


def guardar_riesgo(data: dict) -> int:
    """Inserta un nuevo riesgo/oportunidad. Retorna el id generado."""
    with get_engine().begin() as conn:
        result = conn.execute(text("""
            INSERT INTO reports.riesgos_oportunidades
                (periodo_ref, sociedad, tipo, categoria, nombre, descripcion,
                 probabilidad, impacto_nivel, impacto_monto, estado,
                 responsable, plan_accion, fecha_vcto, creado_por)
            VALUES
                (:periodo_ref, :sociedad, :tipo, :categoria, :nombre, :descripcion,
                 :probabilidad, :impacto_nivel, :impacto_monto, :estado,
                 :responsable, :plan_accion, :fecha_vcto, :creado_por)
            RETURNING id
        """), data)
        return result.fetchone()[0]


def actualizar_riesgo(riesgo_id: int, data: dict):
    """Actualiza un registro existente."""
    data["id"] = riesgo_id
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE reports.riesgos_oportunidades
            SET tipo           = :tipo,
                categoria      = :categoria,
                nombre         = :nombre,
                descripcion    = :descripcion,
                probabilidad   = :probabilidad,
                impacto_nivel  = :impacto_nivel,
                impacto_monto  = :impacto_monto,
                estado         = :estado,
                responsable    = :responsable,
                plan_accion    = :plan_accion,
                fecha_vcto     = :fecha_vcto
            WHERE id = :id
        """), data)


def eliminar_riesgo(riesgo_id: int):
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM reports.riesgos_oportunidades WHERE id = :id"),
            {"id": riesgo_id},
        )


# ── helpers de codificación ────────────────────────────────────
PROB_NUM   = {"ALTA": 3, "MEDIA": 2, "BAJA": 1}
IMPACT_NUM = {"ALTO": 3, "MEDIO": 2, "BAJO": 1}

CATEGORIAS  = ["COMERCIAL", "OPERACIONAL", "FINANCIERO", "REGULATORIO", "OTRO"]
PROBABILIDADES = ["ALTA", "MEDIA", "BAJA"]
IMPACTOS    = ["ALTO", "MEDIO", "BAJO"]
ESTADOS     = ["ABIERTO", "EN_GESTION", "CERRADO", "MATERIALIZADO"]
ESTADOS_LABEL = {
    "ABIERTO":       "Abierto",
    "EN_GESTION":    "En gestión",
    "CERRADO":       "Cerrado",
    "MATERIALIZADO": "Materializado",
}
