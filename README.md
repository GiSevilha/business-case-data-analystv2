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

### 1. Repetición — ¿qué factores explican que un cliente repita?

Tasa base: **28,9 %** de los compradores repiten (≈ 32 % en cohortes con
suficiente antigüedad). Los repetidores generan el **46 % de la facturación**.

1. **Free tour de entrada — el factor con mayor efecto.** Los clientes cuya
   primera reserva fue un free tour repiten el **52,2 %**, frente al **22,8 %**
   de los que empezaron con una reserva de pago. El efecto se mantiene *dentro*
   de cada canal, así que no es un artefacto del canal de captación. Además, el
   100 % de las segundas reservas de esos clientes son de pago.
2. **Canal — el factor más sólido de forma accionable.** El canal de adquisición
   predice la retención con claridad (Email ≈ 43 % vs. Social ≈ 21 %) y es algo
   sobre lo que el negocio puede actuar directamente (dónde invertir el
   presupuesto de marketing). Social y Afiliados son el tráfico de peor calidad:
   retienen peor *y* cancelan más.
3. **Destino — efecto real pero menos accionable.** Rango del 17,9 % (Marrakech)
   al 36,8 % (Roma), con muestras robustas (300–710 clientes por destino). El
   efecto es real, pero Civitatis no puede "fabricar" más demanda de Roma a
   voluntad: es más útil como información (dónde reforzar oferta o marketing
   local) que como palanca directa.
4. **Campaña — dato interesante, con una advertencia.** `newsletter_semanal`
   (49,6 %) y `post_compra_crossell` (40,3 %) destacan, pero un boletín semanal
   y una venta cruzada post-compra se dirigen a quien *ya* es cliente: no tiene
   sentido que consten como la campaña de una *primera* reserva. Probable fallo
   de atribución de origen — no sirve para decidir inversión en captación
   (además, muestras pequeñas: 125 y 144 clientes, IC ±9 pp). Como herramienta
   de *retención* el newsletter sí tiene un papel, pero modesto: ~5 % de las
   segundas reservas.
5. **Dispositivo — sin efecto real.** 29,3 % / 28,9 % / 26,1 % (mobile /
   desktop / tablet). Diferencias mínimas: se descarta como factor de
   repetición. (Sí afecta a la *primera compra*: escritorio convierte ~2,3×
   mejor que móvil.)

> Matiz para la defensa: ~la mitad de las segundas reservas ocurren en menos de
> 14 días del primer pedido — son del mismo viaje, no recompra real. La recompra
> a más de 14 días (mediana ~80 días) es del **14 %**.

### 2. Destinos — ¿qué localizaciones tienen mayor acogida y cuáles retienen mejor?

- **Madrid y Roma** concentran el mayor volumen de reservas y, además, la
  retención más alta: son los **destinos ancla** del negocio.
- **Marrakech**, en el extremo opuesto, combina el menor volumen con la menor
  retención (17,9 %) → conviene revisar la propuesta de valor o el
  posicionamiento de ese destino.
- **París** genera más facturación con menos reservas que Madrid, señal de un
  **ticket medio superior** que merece investigarse (¿tours más caros?, ¿más
  personas por reserva?).

### 3. Estado del negocio — ¿cuánto hemos vendido realmente?

- **624.789 € confirmados** sobre **6.928 reservas**.
- Las **cancelaciones** representan una pérdida de **108.157 €** — un 17,3 %
  adicional sobre la venta confirmada —, lo que convierte la **reducción de
  cancelaciones** en la palanca de mayor impacto económico inmediato, por encima
  incluso de la cifra pendiente de confirmar (26.290 €).

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
| **Conversión (bruta)** | Sesiones con ≥ 1 evento con `reserva_id` no nulo / total de sesiones | Mide si la sesión terminó en un intento de compra, sin importar el desenlace posterior. **Solo es medible en sesiones identificadas**: el evento no se dispara sin sesión iniciada. |
| **Conversión neta / efectiva** | De esas sesiones que convirtieron, cuántas terminaron con su reserva en estado `confirmada` | Cuánta de la conversión "se mantiene". |
| **Cohorte (pestaña Repetición)** | Clientes cuya *primera* reserva confirmada cae en el rango de fechas | Las 2 últimas cohortes trimestrales están censuradas (poco tiempo para repetir). |

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
