"""
Conexión a Supabase PostgreSQL.
- get_engine: reutiliza el engine (cache_resource).
- query:       consultas SELECT con caché de 5 min (cache_data).
- query_live:  consultas sin caché (para datos que deben ser siempre frescos).
- execute:     DML sin caché (INSERT/UPDATE/DELETE).
"""
import streamlit as st
from sqlalchemy import create_engine, text
import pandas as pd


@st.cache_resource
def get_engine():
    cfg = st.secrets["database"]
    url = (
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str, params: dict = None) -> pd.DataFrame:
    """Ejecuta una consulta SELECT y cachea el resultado 5 minutos."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def query_live(sql: str, params: dict = None) -> pd.DataFrame:
    """Consulta sin caché — usar solo cuando se necesitan datos al instante."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def execute(sql: str, params: dict = None) -> None:
    """Ejecuta un statement DML (INSERT, UPDATE, DELETE) con commit."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})
    # Limpiar caché tras escritura para que la próxima lectura sea fresca
    query.clear()
