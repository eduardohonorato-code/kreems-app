# Kreems FP&A — Control Presupuestario

Aplicación web interna para el control presupuestario **Real vs Presupuesto**, construida con Streamlit y PostgreSQL (Supabase). Permite analizar ventas, costos, márgenes y ejecución presupuestaria por sociedad y centro de costos, con análisis de IA integrado.

---

## Tecnologías

| Capa | Tecnología |
|---|---|
| Frontend / App | [Streamlit](https://streamlit.io) |
| Base de datos | PostgreSQL via [Supabase](https://supabase.com) |
| ORM / Conexión | SQLAlchemy + psycopg2 |
| Gráficos | Plotly |
| Export Excel | openpyxl |
| Análisis IA | [Groq API](https://groq.com) (llama-3.3-70b-versatile) |
| Deploy | Streamlit Community Cloud |

---

## Estructura del proyecto

```
kreems_app/
├── app.py                      # Página de inicio con tarjetas de navegación
├── requirements.txt
├── runtime.txt
├── assets/
│   └── logo.png
├── pages/
│   ├── 1_dashboard.py          # Resumen Ejecutivo — Ventas Real vs Presupuesto
│   ├── 2_eerr.py               # Estado de Resultados (P&L completo)
│   ├── 3_centro_costos.py      # Análisis por Centro de Costo
│   ├── 4_control_cuentas.py    # Control por Cuenta Contable
│   ├── 5_cargar_datos.py       # Carga de archivos Excel (solo admin)
│   ├── 6_reportes.py           # Reportes IA guardados
│   └── 7_admin_usuarios.py     # Administración de usuarios (solo admin)
├── utils/
│   ├── auth.py                 # Autenticación (PostgreSQL + fallback secrets)
│   ├── components.py           # Componentes reutilizables (sidebar, KPIs, selector meses)
│   ├── db.py                   # Conexión y queries (con caché 5 min)
│   ├── etl.py                  # Procesamiento de archivos Excel → BD
│   └── ai.py                   # Análisis con IA (Groq)
├── .streamlit/
│   ├── config.toml             # Tema y configuración de la app
│   └── secrets.toml            # Credenciales (NO se sube al repo)
└── sql/
    ├── 01_cargar_dim_cc.sql
    ├── 02_cargar_dim_cuentas.sql
    ├── 03_cargar_fact_real.sql
    ├── 04_crear_fact_presupuesto.sql
    ├── 05_vista_real_vs_ppto.sql
    ├── 06_reportes_guardados.sql
    └── 07_usuarios.sql
```

---

## Funcionalidades

### 📊 Resumen Ejecutivo
- Gauge de cumplimiento ventas Real vs Presupuesto
- KPIs: ventas reales, presupuesto, variación absoluta y % cumplimiento
- Gráfico de barras mensual con línea de presupuesto
- Gráfico horizontal de % ejecución por Centro de Costo
- Tabla resumen con export a Excel

### 📋 Estado de Resultados
- P&L completo: Ventas → Costo Variable → Utilidad Bruta → Costo Fijo → OPEX → EBIT → Gastos Financieros → Utilidad Neta
- Ratios financieros: Margen Bruto, EBIT, Neto (Real vs Presupuesto)
- Gráfico de composición del resultado
- Análisis IA con posibilidad de guardar el reporte
- Export a Excel

### 🏢 Centro de Costos
- Tarjetas por CC (Administración, Comercial, Distribución, Producción)
- Gráfico Real vs Presupuesto por CC
- Tabla resumen con varianza y % ejecución
- Análisis IA guardable
- Export a Excel

### 📑 Control por Cuenta Contable
- Filtros por búsqueda, Centro de Costo y Clasificación
- KPIs: cuentas totales, ejecución promedio, cuentas sobre presupuesto, alertas ≥85%
- Tabla con alertas de color por nivel de ejecución
- **Gráfico de tendencia mensual** por cuenta seleccionada (Real vs Presupuesto)
- Análisis IA guardable
- Export a Excel

### 🤖 Reportes Guardados
- Historial de análisis IA generados desde todas las páginas
- Filtros por sociedad, tipo y búsqueda en título
- KPI cards resumidas por reporte
- Toggle para ver/ocultar el análisis completo
- Eliminación de reportes

### ⬆️ Cargar Datos _(solo admin)_
- Carga de Excel de ventas reales (ACUÑA, Gran Natural)
- Carga del presupuesto anual desde archivo Excel consolidado
- Registro manual de Costos Variables
- ETL automático hacia las tablas en PostgreSQL

### 👤 Admin Usuarios _(solo admin)_
- CRUD completo de usuarios desde la propia app
- Crear, editar, cambiar contraseña y eliminar usuarios
- Control de rol (`admin` / `viewer`) y CC permitidos por usuario

---

## Configuración inicial

### 1. Clonar el repositorio
```bash
git clone https://github.com/eduardohonorato-code/kreems-app.git
cd kreems-app
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar credenciales
Crea el archivo `.streamlit/secrets.toml` con el siguiente contenido:

```toml
[database]
host     = "tu-host.supabase.co"
port     = 5432
dbname   = "postgres"
user     = "postgres"
password = "tu-password"

[groq]
api_key = "gsk_..."

# Fallback de usuarios (opcional, si no usas la tabla de BD)
[users.admin]
password = "tu-password"
nombre   = "Administrador"
rol      = "admin"
```

### 4. Ejecutar los scripts SQL en Supabase
En el SQL Editor de Supabase, ejecuta en orden:
```
sql/01_cargar_dim_cc.sql
sql/02_cargar_dim_cuentas.sql
sql/03_cargar_fact_real.sql
sql/04_crear_fact_presupuesto.sql
sql/05_vista_real_vs_ppto.sql
sql/06_reportes_guardados.sql
sql/07_usuarios.sql          ← tabla de usuarios de la app
```

### 5. Correr la app localmente
```bash
streamlit run app.py
```

---

## Roles de usuario

| Rol | Acceso |
|---|---|
| `admin` | Todo: análisis, carga de datos, administración de usuarios |
| `viewer` | Solo lectura: dashboard, EERR, CC, cuentas, reportes guardados |

Los usuarios se gestionan desde la página **Admin Usuarios** dentro de la app, o directamente en la tabla `admin.usuarios` en Supabase.

---

## Deploy en Streamlit Cloud

1. Conectar el repositorio en [share.streamlit.io](https://share.streamlit.io)
2. Configurar los **Secrets** (equivalente al `secrets.toml`) desde la interfaz de Streamlit Cloud
3. La app se despliega automáticamente en cada push a `main`

---

## Modelo de datos (simplificado)

```
marts.vw_real_vs_ppto       ← vista principal (Real vs Presupuesto)
    periodo, sociedad, codigo_cc, nombre_cc
    clasificacion, nombre_cuenta
    valor_real, valor_ppto

reports.reportes_guardados  ← análisis IA guardados
    titulo, tipo, periodo_desde, periodo_hasta
    sociedad, datos_json, analisis_ia, creado_por, creado_en

admin.usuarios              ← usuarios de la app
    usuario, password, nombre, rol, cc_permitidos, activo
```
