-- ============================================================
-- 10_ppto_detalle.sql
-- Presupuesto por DETALLE de item/persona, cuenta y centro de costo.
--
-- Tabla fuente editable (formato ancho: una fila por item con 12 meses).
-- Es ADITIVA: no modifica marts.fact_presupuesto ni la vista existente.
-- El ETL reagrega esta tabla hacia marts.fact_presupuesto (solo CC <> 'CC-00',
-- preservando Ventas y Costo Variable que viven en CC-00).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.ppto_detalle (
    id              BIGSERIAL PRIMARY KEY,
    ano             INT          NOT NULL,
    sociedad        TEXT         NOT NULL DEFAULT 'Consolidado',
    codigo_cc       TEXT         NOT NULL,
    codigo_cuenta   TEXT         NOT NULL,
    item            TEXT         NOT NULL DEFAULT '',
    tipo            TEXT,
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

CREATE INDEX IF NOT EXISTS ix_ppto_detalle_ano_cc
    ON staging.ppto_detalle (ano, codigo_cc);
CREATE INDEX IF NOT EXISTS ix_ppto_detalle_sociedad
    ON staging.ppto_detalle (ano, sociedad);
CREATE INDEX IF NOT EXISTS ix_ppto_detalle_cuenta
    ON staging.ppto_detalle (codigo_cuenta);

COMMENT ON TABLE staging.ppto_detalle IS
    'Presupuesto editable a nivel de item/persona, cuenta y CC. Se reagrega a marts.fact_presupuesto via ETL.';
