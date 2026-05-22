"""
Conexión a Supabase PostgreSQL.
Usa st.cache_resource para reutilizar el engine entre requests.
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


def query(sql: str, params: dict = None) -> pd.DataFrame:
    """Ejecuta una consulta y retorna un DataFrame."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def execute(sql: str, params: dict = None) -> None:
    """Ejecuta un statement DML (INSERT, UPDATE, DELETE) con commit."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})
