-- ============================================================
-- 11_ppto_ventas_cv.sql
-- Presupuesto de VENTAS y COSTO VARIABLE por categoría/producto.
--
-- Tabla fuente editable (formato ancho: una fila por categoría con 12 meses).
-- Es ADITIVA. El ETL reagrega:
--   tipo = 'VENTA'           -> cuenta 4.1.01.001, CC-00
--   tipo = 'COSTO_VARIABLE'  -> cuenta 3.1.01.001, CC-00
-- preservando el resto de fact_presupuesto (gastos por CC).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.ppto_ventas_cv (
    id              BIGSERIAL PRIMARY KEY,
    ano             INT          NOT NULL,
    tipo            TEXT         NOT NULL,   -- 'VENTA' | 'COSTO_VARIABLE'
    categoria       TEXT         DEFAULT '', -- ej: Potes, Paletas, Galletas...
    notas           TEXT,
    ene  NUMERIC(18,2) NOT NULL DEFAULT 0,
    feb  NUMERIC(18,2) NOT NULL DEFAULT 0,
    mar  NUMERIC(18,2) NOT NULL DEFAULT 0,
    abr  NUMERIC(18,2) NOT NULL DEFAULT 0,
    may  NUMERIC(18,2) NOT NULL DEFAULT 0,
    jun  NUMERIC(18,2) NOT NULL DEFAULT 0,
    jul  NUMERIC(18,2) NOT NULL DEFAULT 0,
    ago  NUMERIC(18,2) NOT NULL DEFAULT 0,
    sep  NUMERIC(18,2) NOT NULL DEFAULT 0,
    oct  NUMERIC(18,2) NOT NULL DEFAULT 0,
    nov  NUMERIC(18,2) NOT NULL DEFAULT 0,
    dic  NUMERIC(18,2) NOT NULL DEFAULT 0,
    creado_en       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ppto_ventascv_ano_tipo
    ON staging.ppto_ventas_cv (ano, tipo);

COMMENT ON TABLE staging.ppto_ventas_cv IS
    'Presupuesto editable de Ventas y Costo Variable por categoría. Se reagrega a marts.fact_presupuesto (4.1.01.001 / 3.1.01.001, CC-00).';
