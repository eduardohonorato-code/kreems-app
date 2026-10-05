-- ============================================================
-- 13_notas_desvio.sql
-- Comentarios del plan de acción del Reporte de Gerencia.
--
-- Reutiliza reports.notas_gestion con tipo = 'DESVIO':
--   referencia    = '<codigo_cuenta>|<codigo_cc>'
--   periodo_desde = 'YYYY-01', periodo_hasta = 'YYYY-12' (vale para todo el año:
--                   el comentario sigue a la cuenta mes a mes hasta que se edite)
--   nota          = explicación (qué pasó)
-- Se agregan las columnas del compromiso.
-- ============================================================

ALTER TABLE reports.notas_gestion ADD COLUMN IF NOT EXISTS accion           TEXT;
ALTER TABLE reports.notas_gestion ADD COLUMN IF NOT EXISTS responsable      TEXT;
ALTER TABLE reports.notas_gestion ADD COLUMN IF NOT EXISTS fecha_compromiso DATE;
