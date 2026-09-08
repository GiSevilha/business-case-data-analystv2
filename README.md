# Business Case — Data Analyst · Civitatis

Análisis del tráfico web y las reservas de Civitatis para responder a las tres
preguntas del Comité Ejecutivo: **repetición de clientes**, **destinos** y
**estado del negocio**.

## App desplegada

**[▶ Abrir la app en Streamlit Community Cloud](https://TU-USUARIO-civitatis.streamlit.app)**
_(sustituye por la URL real tras el despliegue — ver sección "Despliegue")_

La app funciona en la nube con una base de datos reducida
(`data/processed/civitatis_app.duckdb`, ~9 MB) que **sí** está versionada y
contiene solo lo que la app necesita (`reservas`, `tours` y un subconjunto de
columnas de `ga_eventos`). Las cifras son idénticas a las de la base completa.

## Cómo ejecutar en local

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
   python src/main.py            # -> data/processed/civitatis.duckdb (completa)
   python src/build_app_db.py    # -> data/processed/civitatis_app.duckdb (reducida)
   ```

3. **App interactiva:**

   ```bash
   streamlit run src/app.py
   ```

   Usa la DB reducida si existe, y si no la completa. Filtros por rango de fechas
   personalizado, semana o mes; por canal y por destino. Cuatro pestañas: estado
   del negocio, repetición, destinos, tráfico y conversión.

4. **Informe estático** (todas las métricas por consola, sin la app):

   ```bash
   python src/informe.py
   ```

## Despliegue (Streamlit Community Cloud)

1. Repositorio en GitHub con `src/app.py`, `requirements.txt` y
   `data/processed/civitatis_app.duckdb` versionados (ya lo están).
2. Entra en <https://share.streamlit.io> con la cuenta de GitHub.
3. **New app** → elige el repo y la rama, *Main file path* = `src/app.py`.
4. **Deploy**. En ~1 min queda una URL pública tipo
   `https://<algo>.streamlit.app` que abre la app con un clic.

Para actualizarla basta con hacer `push`: Streamlit Cloud redepliega solo. Si
cambian los datos, regenera la DB reducida (`python src/build_app_db.py`) y
súbela.

## Estructura

| Ruta | Contenido |
|------|-----------|
| `src/main.py` | Orquesta la limpieza y persiste las tablas en DuckDB |
| `src/limpieza_*.py` | Limpieza por fichero (reservas, clientes, tours, ga_eventos) |
| `src/identidad.py` | Resolución de identidad: crosswalk por DNI y propagación por cookie_id |
| `src/calidad_trafico.py` | Marcado de tráfico de bot (`es_bot`) |
| `src/metricas.py` | Todas las consultas de negocio y de contraste de hipótesis |
| `src/informe.py` | Runner que ejecuta `metricas.py` agrupado por pregunta del comité |
| `src/build_app_db.py` | Genera la DB reducida que usa la app desplegada |
| `src/app.py` | Aplicación Streamlit |
| `data/processed/civitatis_app.duckdb` | DB reducida versionada (~9 MB) para el despliegue |
| `memo/memo_comex.html` | Memo ejecutivo de una página para el COMEX |

## Hallazgos principales

> `src/informe.py` y `src/metricas.py` contienen las consultas de contraste de
> hipótesis (intervalos de confianza, control del sesgo de censura temporal,
> retención controlada por canal…). El memo (`memo/memo_comex.html`) es el
> resumen ejecutivo.

### 1. Repetición — ¿qué factores explican que un cliente vuelva a comprar?

Tasa de recompra: **≈16 %** (definición arriba; base madura, estable 14–19 % en
seis cohortes trimestrales). Quien recompra vale **222 €** frente a **109 €** del
que compra una sola vez. Son **tres factores independientes** — verificado por
estratificación y estandarización, ninguno es reflejo de otro:

1. **Canal de captación — el factor, y el más accionable.** Entre clientes con
   primera reserva de pago (aislando el free tour) y sin Email (etiquetado
   contaminado): Directo **22,5 %** · SEO 17,8 % · SEM 14,6 % · Afiliados 13,1 %
   · Social **10,2 %**. El IC de Directo no solapa el de Social. El gradiente
   aguanta *dentro* de cada estrato free/pago y al estandarizar por mix de
   destino. Social y Afiliados, además, cancelan más (17–18 % vs. 13 %).
2. **Free tour de entrada — en negativo.** Quien entra por un free tour recompra
   **menos**: 11,4 % vs. 18,0 % de pago, dentro de cada canal. El free tour
   engancha y genera una segunda reserva de pago *en el mismo viaje*, pero no
   crea lealtad: es palanca de **conversión**, no de fidelización.
3. **Destino de la primera experiencia — efecto modesto.** Madrid 21,7 % y Roma
   21,2 % arriba; Nueva York 11,9 % y Marrakech 10,6 % abajo (extremos con IC
   separado). Sobrevive a estandarizar por canal. Es información sobre dónde el
   producto cumple la expectativa, no una palanca directa.

**No explican nada:** campaña (ninguna de captación destaca; las que suben son
campañas de retención mal etiquetadas como origen), importe de la 1.ª más allá
de free/pago, tamaño de grupo, antelación, dispositivo habitual, edad.
**La cancelación no es churn:** quien sufre una cancelación recompra *más*
(23,4 % vs. 15,7 %); el 31 % de quienes cancelan su primera reserva vuelve a
comprar.

### 2. Destinos — ¿qué localizaciones tienen mayor acogida y cuáles retienen mejor?

- **Acogida = demanda × conversión**, no solo volumen. **Madrid, Roma, París y
  Londres** lideran el interés de búsqueda *y* las reservas *y* la conversión
  interés→reserva (~10 por 100 sesiones): son ~48 % del negocio y los **destinos
  ancla**.
- **París factura más que Madrid con menos reservas.** No es por grupos más
  grandes (2,94 personas/reserva vs. 3,08 en Madrid) — es **precio por persona**
  (32 € vs. 24 €): vende tours más caros.
- **Nueva York** capta bien (5.ª en reservas) pero retiene mal (11,9 %): cubo
  con fugas.
- **Atenas** es la 3.ª en interés de búsqueda (casi como Roma) pero convierte la
  mitad (5,3 por 100 sesiones) — demanda desaprovechada. No es el precio (ticket
  63 €, el más barato).
- **Marrakech** flojea en interés, conversión y retención (10,6 %). Su ticket es
  medio-alto (109 €) como Lisboa o Londres, que retienen mejor: es
  encaje/expectativa, no precio → revisar la propuesta de valor.

### 3. Estado del negocio — ¿cuánto hemos vendido realmente?

- **624.789 € confirmados** sobre **6.928 reservas** (1.072 free tours, 0 €).
- **Crecimiento +68 % en 24 meses**, monotónico (~+15 % por semestre): de 115 k€
  (H2 2024) a 193 k€ (H1 2026).
- **Cancelaciones: 108.157 €** (17,3 % sobre la venta), **estables y difusas**.
  La tasa lleva 24 meses plana (16–18 %). El *exceso* sobre esa tasa base se
  concentra en las reservas muy anticipadas (+90 días cancelan el 24 %) y en
  Social/Afiliados. Estimación realista de lo recuperable: **15–25 k€/año**.
- **Riesgo operativo aparte:** 282 reservas confirmadas (27.703 €) creadas
  *después* de la baja de su proveedor (1017 y 1004, baja 30-jun-2025).

## Decisiones y uso de IA

### Definición exacta de las métricas clave

| Métrica | Definición | Por qué |
|---------|-----------|---------|
| **Venta** | `SUM(importe_eur)` de reservas en estado `confirmada` | Dinero comprometido, no intención ni proyección. Se usa `reservas.estado` como fuente de verdad y **no** `ga_eventos`, porque 68 reservas reales no tienen ningún evento asociado (fallo de tracking del 10–15 de marzo de 2026). |
| **Volumen de ventas** | `COUNT(*)` de reservas `confirmada`, incluidos los free tours (0 €) | Mide actividad comercial gestionada, no solo ingreso (separación habitual *bookings* vs. *revenue*). |
| **Ingreso perdido por cancelación** | `SUM(importe_eur)` de reservas `cancelada` | Pérdida ya materializada, útil para priorizar. No es una venta ni una proyección. |
| **Pipeline pendiente** | `SUM(importe_eur)` de reservas `pendiente` | Contexto: lo que aún podría confirmarse. |
| **Cliente recurrente (recompra)** | Cliente cuya primera reserva `confirmada` **ya fue disfrutada** (su `fecha_actividad` está en el pasado) y que hace una **nueva reserva `confirmada` con `fecha_reserva` posterior a esa primera actividad**. Se mide sobre la **base madura**: clientes con ≥ 180 días desde su primera actividad. | Separa la recompra real de la reserva múltiple para un mismo viaje: **la mitad de las "segundas reservas" ocurren en < 14 días** del primer pedido (mediana 3 días) — es planificación de un único viaje, no lealtad. El corte de 180 días evita el sesgo de censura: el 66 % de las recompras ocurren en < 90 días. **Resultado: ≈16 %** (estable 14–19 % en seis cohortes trimestrales). |
| **Sesión** | Cada `session_id` distinto en `ga_eventos`, excluyendo `es_bot = TRUE` | Cada `session_id` está asociado a un único `cookie_id` y `device`. |
| **Conversión (bruta)** | Sesiones con ≥ 1 evento con `reserva_id` no nulo / total de sesiones | Mide si la sesión terminó en un intento de compra, sin importar el desenlace posterior. **Solo es medible en sesiones identificadas**: el evento no se dispara sin sesión iniciada. |
| **Conversión neta / efectiva** | De esas sesiones que convirtieron, cuántas terminaron con su reserva en estado `confirmada` | Cuánta de la conversión "se mantiene". |
| **Cohorte (pestaña Repetición)** | Clientes cuya *primera actividad* confirmada cae en el rango de fechas | Las cohortes con < 180 días de exposición están censuradas (poco tiempo para recomprar) y se marcan como tal. |

### Decisiones de limpieza y su impacto

**`ga_eventos.csv`**

- **`event_date`** combinaba dos formatos de fecha-hora distintos, lo que hacía
  que DuckDB la dejara como texto (`VARCHAR`) en vez de un tipo temporal.
  Verificada la proporción de cada formato (**32.589 vs. 670.232 filas**), se
  normalizan ambos a `TIMESTAMP` con `COALESCE` sobre dos patrones de parseo
  (`'%Y-%m-%d %H:%M:%S'` y `'%d/%m/%Y %H:%M'`). Cobertura del 100 % sin nulos
  resultantes.
- **`device`** aparecía con mayúsculas, minúsculas y erratas (p. ej. `desktp`
  sin la `o`) → normalizado a minúsculas y corregidas las erratas conocidas.

**`reservas.csv`**

- Se asume que el estado `CANCELLED` y `cancelada` significan lo mismo. Todos
  los estados se normalizan a minúsculas.
- Ningún `reserva_id` se repite y `importe_eur = 0` solo se da en free tours.
- **`personas` negativa o 0** (verificado que no corresponde a ningún proveedor
  ni tour concreto): se asume error al guardar el dato — todo lo demás de la
  fila es válido — y se trata como `NULL` para no perder la reserva.
- **45 reservas duplicadas con `reserva_id` distinto.** Cruzando con
  `ga_eventos` se ve que la copia no tiene `session_id` y que sus 4 últimos
  dígitos coinciden siempre con el `reserva_id` real. Además el `reserva_id`
  legítimo sigue un patrón que empieza en `900001`, mientras que las duplicadas
  están por el `1.400.000`, lo que no tiene sentido → se eliminan de `reservas`.
- **304 de 1.731 reservas del canal SEM (17,6 %) sin campaña asociada**,
  inesperado porque SEM es tráfico de pago que normalmente se etiqueta por
  campaña. Se mantiene el valor `NULL` en los datos limpios para no introducir
  información no verificada; en visualizaciones y agregaciones se muestra bajo
  la etiqueta *"Sin campaña"* como categoría propia. Recomendación: investigar
  con Marketing si es una pérdida real de trazabilidad o una configuración de
  tracking específica.

**`clientes.csv`**

- El `user_id` no está duplicado, pero al filtrar por DNI aparecen **59 filas
  de clientes duplicados** con `user_id` y email distintos. El email contiene
  parte del `user_id` (es sintético, generado a partir de él), por lo que se
  considera válido solo el `MIN(user_id)` de cada DNI (el primer registro).
  `identidad.py → crosswalk_clientes()` genera la tabla
  `user_id_original → user_id_canonico` con
  `MIN(user_id) OVER (PARTITION BY LOWER(dni))`, y se aplica a `reservas`,
  `clientes` y `ga_eventos`.
- **1 registro con `fecha_alta` a futuro** → es del `user_id` duplicado ya
  corregido, así que la fila se elimina.
- **40 clientes con `fecha_baja` posterior a la fecha actual.** La diferencia
  entre `fecha_alta` y `fecha_baja` oscila entre 238 y 1.077 días (media
  ~601), sin solapamientos ni valores atípicos. Consistente con bajas
  programadas con antelación → no se considera error, se mantiene tal cual.
- **18 clientes (0,22 %) con `fecha_nacimiento = 1900-01-01`**, un valor
  idéntico, exacto y redondo (impensable como coincidencia real entre 18
  personas). Se interpreta como un placeholder de sistema y se sustituye por
  `NULL` — sin eliminar la fila — para preservar el resto de la información del
  cliente y no distorsionar cálculos de edad.

**`tours.csv` y `proveedores.csv`**

- **Tour 5008** (187 reservas asociadas) referenciaba un `proveedor_id` (1099)
  inexistente en `proveedores.csv`. Se sustituye por `NULL` en
  `tours.proveedor_id`, preservando el resto de datos del tour. Impacto: esas
  187 reservas no pueden atribuirse a un proveedor concreto en análisis que
  crucen las tres tablas — limitación del dataset origen, no de la limpieza.
- Se añade a `tours` la columna **`destino`**, extraída de `url` con
  `SPLIT_PART(url, '/', 5)`. Se eligió `url` frente a `descripcion` por seguir
  un patrón estructurado y verificado como constante en las 65 filas
  (`civitatis.com/es/CIUDAD/nombre-tour/`), frente al texto libre de la
  descripción.
- **Proveedores 1004 y 1017** (ambos con `fecha_baja = 2025-06-30`): (1) **336
  reservas** se crearon después de que su proveedor causara baja — el sistema
  no bloquea nuevas reservas para proveedores inactivos; (2) **352 reservas**
  tienen `fecha_actividad` posterior a la baja del proveedor. El 84 % de ambos
  grupos permanece en estado `confirmada`. Recomendación: Operaciones debería
  revisar si el servicio se prestó igualmente (p. ej. con un proveedor
  sustituto) o si requieren gestión de cancelación/reembolso.

### Comprobaciones de identidad

- Ningún `cookie_id` está asociado a más de un `user_id` distinto: el
  `cookie_id` identifica de forma fiable y única a una sola persona. Eso
  permite propagar el `user_id` conocido a los eventos anónimos del mismo
  navegador con `MAX(user_id) OVER (PARTITION BY cookie_id)`. La técnica
  **recuperó identidad para 48.239 eventos** (7,6 % del total; 7,7 % de los
  previamente anónimos), reduciendo los eventos sin `user_id` de 630.546 a
  582.307.
- **`temp_client_id`** también identifica de forma unívoca a un único cliente
  (0 casos de valores compartidos entre `user_id` distintos), pero está siempre
  contenido dentro de un único `cookie_id`, y `cookie_id` está presente en el
  100 % de los eventos. Cualquier identidad recuperable vía `temp_client_id` ya
  la cubre la propagación por `cookie_id` → `temp_client_id` se descarta para
  este propósito.
- **Tráfico de bot:** 6 `cookie_id` con volúmenes anómalos (7.856–7.975 eventos
  cada uno, ~47.449 en total, 6,75 % del dataset), todos con el mismo
  `temp_client_id` (`Tbot0000000`), sin `user_id` ni ninguna reserva generada.
  Se marca con la columna `es_bot` en vez de eliminarlo — preservando el dato
  para análisis de calidad de tráfico —, pero se excluye de todas las métricas
  de negocio (sesiones, conversión, recurrencia).
- **Gap de tracking:** 68 reservas confirmadas o canceladas entre el 10 y el 15
  de marzo de 2026 no tienen ningún evento asociado en `ga_eventos`, pese a
  existir con normalidad en `reservas`. La concentración temporal sugiere un
  fallo puntual del sistema de tracking. Por eso **`reservas.estado` es la
  fuente de verdad** para definir venta y conversión, y `ga_eventos.reserva_id`
  se reserva para análisis de comportamiento de navegación.

### Limitaciones conocidas

- **Conversión no medible para el ~90 % del tráfico** (sesiones anónimas): el
  evento con `reserva_id` no se dispara sin sesión iniciada.
- **Re-registro no capturado por la deduplicación:** `user_id` 24563 / 28015,
  mismo nombre, dirección, teléfono y fecha de nacimiento, pero DNI distinto
  (posible error de tecleo). No se fusionó automáticamente por falta de una
  regla generalizable fiable para detectar coincidencias por teléfono sin
  riesgo de falsos positivos entre convivientes o familiares.
- **304 reservas de SEM sin campaña** (17,6 %): posible pérdida de trazabilidad.
- **336 / 352 reservas con proveedor de baja** (1004 / 1017): pendiente de
  revisión por Operaciones.
- **187 reservas sin proveedor atribuible** (tour 5008).

### Uso de herramientas de IA

Utilicé asistentes de IA (Claude) a lo largo de todo el proceso, con distinta
intensidad según la fase.

**Limpieza del dataset y definiciones — la IA como revisora.** La detección de
inconsistencias, las decisiones de limpieza y las definiciones de métrica
(venta, cliente recurrente, sesión, conversión) son mías y están documentadas
más arriba. Usé la IA para contrastarlas: revisar el razonamiento de cada
decisión, buscar casos que se me hubieran podido escapar y comprobar que las
cifras cuadraban.

**Análisis de hipótesis — trabajo conjunto.** Las consultas del bloque de
contraste de hipótesis de `src/metricas.py` y el runner `src/informe.py` se
escribieron con ayuda de IA a partir de preguntas que yo planteé (¿el efecto del
canal se sostiene al controlar por destino?, ¿hay sesgo de censura temporal en
la tasa de repetición?, ¿de qué depende la cancelación?…). Revisé cada consulta
y su resultado antes de darlos por buenos.

**App y memo — donde más me apoyé en la IA.** La implementación de `src/app.py`
(estructura Streamlit, consultas parametrizadas por fecha, gráficos con Altair)
y el diseño y la maquetación de `memo/memo_comex.html` se hicieron principalmente
con IA. Yo definí qué debía mostrar cada vista, con qué filtros y qué mensaje
tenía que transmitir el memo; la IA generó el código y el HTML, que ejecuté y
revisé.

Todo el código entregado se ejecuta y se ha verificado contra la base de datos;
entiendo y puedo explicar cada parte.
