-- ================================================================
-- 08_notas_gestion.sql
-- Tabla para notas de gestión por varianza (controller)
-- ================================================================

CREATE TABLE IF NOT EXISTS reports.notas_gestion (
    id              SERIAL PRIMARY KEY,
    periodo_desde   TEXT        NOT NULL,           -- 'YYYY-MM'
    periodo_hasta   TEXT        NOT NULL,           -- 'YYYY-MM'
    sociedad        TEXT        NOT NULL DEFAULT 'Todas',
    tipo            TEXT        NOT NULL,           -- 'CC' | 'CUENTA' | 'EERR'
    referencia      TEXT        NOT NULL,           -- código CC o nombre cuenta
    nota            TEXT        NOT NULL,
    creado_por      TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Una nota por combinación período + sociedad + tipo + referencia
    CONSTRAINT uq_nota UNIQUE (periodo_desde, periodo_hasta, sociedad, tipo, referencia)
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_notas_periodo
    ON reports.notas_gestion (periodo_desde, periodo_hasta);

CREATE INDEX IF NOT EXISTS idx_notas_sociedad
    ON reports.notas_gestion (sociedad);

CREATE INDEX IF NOT EXISTS idx_notas_tipo_ref
    ON reports.notas_gestion (tipo, referencia);

-- Trigger para actualizar actualizado_en automáticamente
CREATE OR REPLACE FUNCTION reports.fn_update_notas_ts()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.actualizado_en = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notas_update ON reports.notas_gestion;
CREATE TRIGGER trg_notas_update
    BEFORE UPDATE ON reports.notas_gestion
    FOR EACH ROW EXECUTE FUNCTION reports.fn_update_notas_ts();
