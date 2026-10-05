-- ============================================================
-- 12_eliminaciones_ic.sql
-- Eliminaciones intercompany ACUÑA → Gran Natural (servicios de personal).
--
-- ACUÑA (que paga los sueldos) factura a GN: en ACUÑA queda como venta
-- (4.1.01.001, CC-00) y en GN como gasto (3.1.01.018 SERVICIOS DE PERSONAL,
-- CC-04). No son ventas: en consolidado se eliminan ambos lados.
--
-- Una fila por mes con el monto total a eliminar. utils/etl.py escribe en
-- marts.fact_real dos filas negativas con fuente = 'ELIM_IC', que la recarga
-- mensual desde Obuma preserva.
-- ============================================================

CREATE TABLE IF NOT EXISTS staging.eliminaciones_ic (
    id             BIGSERIAL PRIMARY KEY,
    periodo        VARCHAR(7)    NOT NULL UNIQUE,   -- 'YYYY-MM'
    monto          NUMERIC(18,2) NOT NULL CHECK (monto > 0),
    glosa          TEXT,
    ingresado_por  TEXT,
    fecha_ingreso  TIMESTAMP     NOT NULL DEFAULT now()
);

-- Carga inicial: facturas de servicios de personal jun y ago 2026
INSERT INTO staging.eliminaciones_ic (periodo, monto, glosa)
VALUES
    ('2026-06', 24000000, 'Factura ACUÑA → GN servicios de personal (ajuste, no es venta)'),
    ('2026-08', 24000000, 'Factura ACUÑA → GN servicios de personal (ajuste, no es venta)')
ON CONFLICT (periodo) DO NOTHING;
