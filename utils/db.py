"""
Conexión a Supabase PostgreSQL.
- get_engine: reutiliza el engine (cache_resource).
- query:       consultas SELECT con caché de 5 min (cache_data).
- query_live:  consultas sin caché (para datos que deben ser siempre frescos).
- execute:     DML sin caché (INSERT/UPDATE/DELETE).
"""
import time

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import pandas as pd


@st.cache_resource
def get_engine():
    cfg = st.secrets["database"]
    url = (
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )
    # El pooler de Supabase en modo sesión admite pocos clientes simultáneos:
    # pool chico, reciclado antes de que el pooler corte conexiones inactivas.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_recycle=240,
        connect_args={
            "connect_timeout": 10,
            "sslmode": "require",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )


def _read_sql_con_reintentos(sql: str, params: dict, intentos: int = 3) -> pd.DataFrame:
    """Lee de la BD reintentando ante fallas de conexión (pooler saturado
    o proyecto Supabase pausado que tarda en despertar)."""
    for intento in range(intentos):
        engine = get_engine()
        try:
            with engine.connect() as conn:
                return pd.read_sql(text(sql), conn, params=params)
        except OperationalError:
            # Descartar el engine cacheado: sus conexiones pueden estar muertas
            engine.dispose()
            get_engine.clear()
            if intento == intentos - 1:
                st.error(
                    "⚠ No se pudo conectar a la base de datos (Supabase). "
                    "Reintenta en unos segundos. Si persiste, revisa que el "
                    "proyecto Supabase no esté pausado y que los Secrets de "
                    "Streamlit Cloud usen el host del pooler."
                )
                st.stop()
            time.sleep(2 ** intento)


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str, params: dict = None) -> pd.DataFrame:
    """Ejecuta una consulta SELECT y cachea el resultado 5 minutos."""
    return _read_sql_con_reintentos(sql, params)


def query_live(sql: str, params: dict = None) -> pd.DataFrame:
    """Consulta sin caché — usar solo cuando se necesitan datos al instante."""
    return _read_sql_con_reintentos(sql, params)


def execute(sql: str, params: dict = None) -> None:
    """Ejecuta un statement DML (INSERT, UPDATE, DELETE) con commit."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})
    # Limpiar caché tras escritura para que la próxima lectura sea fresca
    query.clear()


def guardar_reporte(
    titulo: str,
    tipo: str,
    periodo_desde: str,
    periodo_hasta: str,
    sociedad: str,
    datos: dict,
    analisis: str,
    creado_por: str,
) -> None:
    """Inserta un análisis IA en reports.reportes_guardados.
    Helper único usado por EERR, Centro de Costos, Control Cuentas y Riesgos.
    tipo: 'EERR' | 'CC' | 'CUENTAS' | 'RIESGOS'
    """
    import json
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO reports.reportes_guardados
                (titulo, tipo, periodo_desde, periodo_hasta,
                 sociedad, datos_json, analisis_ia, creado_por)
            VALUES
                (:titulo, :tipo, :pdesde, :phasta,
                 :sociedad, :datos, :analisis, :usuario)
        """), {
            "titulo":   titulo,
            "tipo":     tipo,
            "pdesde":   periodo_desde,
            "phasta":   periodo_hasta,
            "sociedad": sociedad,
            "datos":    json.dumps(datos),
            "analisis": analisis,
            "usuario":  creado_por,
        })
