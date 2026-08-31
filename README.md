# Business Case — Data Analyst · Civitatis

Análisis del tráfico web y las reservas de Civitatis para responder a las tres
preguntas del Comité Ejecutivo: **repetición de clientes**, **destinos** y
**estado del negocio**.

## Cómo ejecutar

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows ; en Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

1. **Datos.** Descarga los 5 CSV y colócalos en `data/raw/`:
   `clientes.csv`, `proveedores.csv`, `ga_eventos.csv`, `reservas.csv`, `tours.csv`.
   Los CSV **no** están versionados (ver `.gitignore`). El fichero de eventos supera
   los 100 MB.

2. **Construye la base de datos limpia** (DuckDB):

   ```bash
   python src/main.py
   ```

   Genera `data/processed/civitatis.duckdb` con las tablas limpias y las
   correspondencias de identidad.

3. **App interactiva:**

   ```bash
   streamlit run src/app.py
   ```

   Filtros por rango de fechas personalizado, semana o mes; por canal y por
   destino. Cuatro pestañas: estado del negocio, repetición, destinos, tráfico y
   conversión.

4. **Informe estático** (todas las métricas por consola, sin la app):

   ```bash
   python src/informe.py
   ```

## Estructura

| Ruta | Contenido |
|------|-----------|
| `src/main.py` | Orquesta la limpieza y persiste las tablas en DuckDB |
| `src/limpieza_*.py` | Limpieza por fichero (reservas, clientes, tours, ga_eventos) |
| `src/identidad.py` | Resolución de identidad: crosswalk por DNI y propagación por cookie_id |
| `src/calidad_trafico.py` | Marcado de tráfico de bot (`es_bot`) |
| `src/metricas.py` | Todas las consultas de negocio y de contraste de hipótesis |
| `src/informe.py` | Runner que ejecuta `metricas.py` agrupado por pregunta del comité |
| `src/app.py` | Aplicación Streamlit |
| `memo/memo_comex.html` | Memo ejecutivo de una página para el COMEX |

## Decisiones y uso de IA

### Definición exacta de las métricas clave

| Métrica | Definición | Por qué |
|---------|-----------|---------|
| **Venta** | `SUM(importe_eur)` de reservas en estado `confirmada` | Dinero comprometido, no intención ni proyección. Se usa `reservas.estado` como fuente de verdad y **no** `ga_eventos`, porque 68 reservas reales no tienen ningún evento asociado (fallo de tracking del 10–15 de marzo de 2026). |
| **Volumen de ventas** | `COUNT(*)` de reservas `confirmada`, incluidos los free tours (0 €) | Mide actividad comercial gestionada, no solo ingreso (separación habitual *bookings* vs. *revenue*). |
| **Ingreso perdido por cancelación** | `SUM(importe_eur)` de reservas `cancelada` | Pérdida ya materializada, útil para priorizar. No es una venta ni una proyección. |
| **Pipeline pendiente** | `SUM(importe_eur)` de reservas `pendiente` | Contexto: lo que aún podría confirmarse. |
| **Cliente recurrente** | `user_id` con ≥ 2 reservas `confirmada`, siempre en días distintos | Cada reserva es una decisión de compra independiente. Se reporta también la **recompra real** (2.ª reserva a > 14 días) porque ~la mitad de las segundas reservas ocurren en < 14 días (mismo viaje). |
| **Sesión** | Cada `session_id` distinto en `ga_eventos`, excluyendo `es_bot = TRUE` | Cada `session_id` está asociado a un único `cookie_id` y `device`. |
| **Conversión (bruta)** | Sesiones con ≥ 1 evento `purchase` (`reserva_id` no nulo) / total de sesiones | Mide si la sesión terminó en intento de compra. **Solo es medible en sesiones identificadas**: el evento `purchase` no se dispara sin sesión iniciada. |
| **Conversión neta** | De las sesiones que convirtieron, cuántas quedan en estado `confirmada` | Cuánta de la conversión "se mantiene". |
| **Cohorte (pestaña Repetición)** | Clientes cuya *primera* reserva confirmada cae en el rango de fechas | Las 2 últimas cohortes trimestrales están censuradas (poco tiempo para repetir). |

### Supuestos y decisiones de limpieza

- **`ga_eventos.event_date`** combinaba dos formatos (`%Y-%m-%d %H:%M:%S` y `%d/%m/%Y %H:%M`);
  se normalizan ambos a `TIMESTAMP` con `COALESCE` (32.589 vs. 670.232 filas; 100 % de cobertura).
- **`device`** con mayúsculas/minúsculas y erratas (`desktp`) → normalizado a minúsculas.
- **Estados de reserva** `CANCELLED` / `cancelada` se asumen equivalentes; todos los estados a minúsculas.
- **`personas` ≤ 0** → `NULL` (error de guardado; no se pierde el resto de la fila).
- **45 reservas duplicadas** con `reserva_id` distinto (patrón anómalo ~1.400.000, sin `session_id`) → eliminadas.
- **Identidad de clientes:** 59 clientes duplicados por DNI con `user_id` y email distintos (email sintético derivado del `user_id`). Se toma `MIN(user_id)` por DNI como canónico y se traduce en `reservas`, `clientes` y `ga_eventos` vía `crosswalk_clientes`.
- **1 fila con `fecha_alta` a futuro** (del duplicado ya corregido) → eliminada.
- **40 clientes con `fecha_baja` futura** → se mantiene (consistente con bajas programadas).
- **18 clientes con `fecha_nacimiento = 1900-01-01`** → `NULL` (placeholder de sistema).
- **Tour 5008** apunta a `proveedor_id = 1099` inexistente → `NULL` en `tours.proveedor_id` (187 reservas quedan sin proveedor atribuible).
- **Identidad en `ga_eventos`:** ningún `cookie_id` se asocia a más de un `user_id`; se propaga el `user_id` conocido con `MAX(user_id) OVER (PARTITION BY cookie_id)` (recupera 48.239 eventos). `temp_client_id` se descarta por ser subconjunto de `cookie_id`.
- **Tráfico de bot:** 6 `cookie_id` con volúmenes anómalos (~47.449 eventos, mismo `temp_client_id` `Tbot0000000`, sin `user_id` ni reservas) → marcados con `es_bot`, no eliminados; excluidos de todas las métricas de negocio.
- **`destino`** se extrae de `tours.url` con `SPLIT_PART(url, '/', 5)` (patrón verificado constante en las 65 filas), no del texto libre de `descripcion`.

### Limitaciones conocidas

- Conversión no medible para el ~90 % del tráfico (sesiones anónimas).
- Posible re-registro no capturado (`user_id` 24563/28015, mismo nombre/teléfono, DNI distinto).
- 304 reservas de SEM sin campaña asociada (17,6 %): posible pérdida de trazabilidad.
- 282 reservas confirmadas creadas tras la baja de su proveedor (1004 / 1017): revisar con Operaciones.

### Uso de herramientas de IA

_(Completar: qué tareas se delegaron en asistentes de IA, qué propusieron, qué se
descartó y por qué. El código y las decisiones se revisaron y verificaron manualmente.)_
