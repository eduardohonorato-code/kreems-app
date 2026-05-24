-- ═══════════════════════════════════════════════════════════════
-- Tabla: reports.riesgos_oportunidades
-- Registro de riesgos y oportunidades presupuestarias
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS reports.riesgos_oportunidades (
    id              SERIAL PRIMARY KEY,
    periodo_ref     VARCHAR(7)   NOT NULL,          -- '2026-04'
    sociedad        VARCHAR(50)  NOT NULL DEFAULT 'Todas',
    tipo            VARCHAR(15)  NOT NULL CHECK (tipo IN ('RIESGO','OPORTUNIDAD')),
    categoria       VARCHAR(30)  NOT NULL CHECK (categoria IN
                        ('COMERCIAL','OPERACIONAL','FINANCIERO','REGULATORIO','OTRO')),
    nombre          VARCHAR(200) NOT NULL,
    descripcion     TEXT,
    probabilidad    VARCHAR(10)  NOT NULL CHECK (probabilidad IN ('ALTA','MEDIA','BAJA')),
    impacto_nivel   VARCHAR(10)  NOT NULL CHECK (impacto_nivel IN ('ALTO','MEDIO','BAJO')),
    impacto_monto   NUMERIC(18,2),                  -- impacto estimado en $
    estado          VARCHAR(20)  NOT NULL DEFAULT 'ABIERTO'
                        CHECK (estado IN ('ABIERTO','EN_GESTION','CERRADO','MATERIALIZADO')),
    responsable     VARCHAR(100),
    plan_accion     TEXT,
    fecha_vcto      DATE,
    creado_por      VARCHAR(100),
    creado_en       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_riesgos_periodo
    ON reports.riesgos_oportunidades(periodo_ref, sociedad);

-- Trigger auto-actualizar actualizado_en
CREATE OR REPLACE FUNCTION reports.fn_riesgos_ts()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.actualizado_en = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_riesgos_ts ON reports.riesgos_oportunidades;
CREATE TRIGGER trg_riesgos_ts
    BEFORE UPDATE ON reports.riesgos_oportunidades
    FOR EACH ROW EXECUTE FUNCTION reports.fn_riesgos_ts();
