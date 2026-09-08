"""
Consultas de negocio para el informe COMEX (`python src/informe.py`).

Definición de cliente recurrente / recompra
-------------------------------------------
Un cliente recurrente es quien, DESPUÉS de haber disfrutado su primera actividad
confirmada (su fecha de actividad ya pasó), hace una nueva reserva confirmada con
fecha de reserva posterior a esa primera actividad. Esto separa la recompra real
de la reserva múltiple para un mismo viaje: la mitad de las "segundas reservas"
ocurren en menos de 14 días del primer pedido y son planificación de un único
viaje, no lealtad (ver `recompra_trip_stacking`).

La tasa se mide sobre la BASE MADURA: clientes cuya primera actividad fue hace
>= 180 días. El 66 % de las recompras ocurren en < 90 días, así que con 6 meses
de exposición ya se observa casi toda la recompra y se evita el sesgo de censura
de las cohortes recientes (ver `recompra_por_cohorte`).

Resultado: ~16 % de recompra sobre la base madura.
"""

# CTE reutilizable. Una fila por cliente con primera actividad ya disfrutada:
#   recompra          1 si hizo una nueva reserva confirmada tras esa 1a actividad
#   dias_exposicion   días desde su 1a actividad hasta el final de los datos
#   canal/campana/importe_eur/personas/tour_id/fr/fa  -> de la PRIMERA reserva
_ELEGIBLES = """
WITH conf AS (
    SELECT user_id, reserva_id,
           fecha_reserva::date AS fr, fecha_actividad::date AS fa,
           tour_id, canal, campana, importe_eur, personas,
           ROW_NUMBER() OVER (PARTITION BY user_id
                              ORDER BY fecha_reserva, reserva_id) AS rn
    FROM reservas WHERE estado = 'confirmada'
),
primera   AS (SELECT * FROM conf WHERE rn = 1),
siguiente AS (SELECT user_id, MIN(fr) AS fr_sig FROM conf WHERE rn >= 2 GROUP BY user_id),
corte     AS (SELECT MAX(fecha_reserva)::date AS d FROM reservas),
elegibles AS (
    SELECT p.user_id, p.canal, p.campana, p.importe_eur, p.personas,
           p.tour_id, p.fr, p.fa,
           CASE WHEN s.fr_sig IS NOT NULL AND s.fr_sig > p.fa THEN 1 ELSE 0 END AS recompra,
           date_diff('day', p.fa, (SELECT d FROM corte)) AS dias_exposicion
    FROM primera p
    LEFT JOIN siguiente s USING (user_id)
    WHERE p.fa <= (SELECT d FROM corte)
)
"""

_MADURA = "dias_exposicion >= 180"


def _ic95(p="AVG(recompra)", n="COUNT(*)"):
    """Intervalo de confianza 95 % (Wald) para una proporción, en puntos %."""
    return (f"ROUND(100*({p} - 1.96*sqrt({p}*(1-{p})/{n})), 1) AS ic95_low, "
            f"ROUND(100*({p} + 1.96*sqrt({p}*(1-{p})/{n})), 1) AS ic95_high")


# ===========================================================================
# PREGUNTA 1 — Repetición
# ===========================================================================

def recompra_global(con):
    """Tasa de recompra sobre la base madura. ~16 %."""
    return con.sql(_ELEGIBLES + f"""
        SELECT COUNT(*) AS clientes_elegibles,
               SUM(recompra) AS recompran,
               ROUND(100.0 * SUM(recompra) / COUNT(*), 1) AS pct_recompra
        FROM elegibles WHERE {_MADURA}
    """)


def recompra_por_cohorte(con):
    """Recompra por trimestre de la primera actividad, SIN filtro de madurez.
    Demuestra que la tasa es estable (~14-19 %) en cohortes con >= 180 días de
    exposición y solo cae en las últimas (censuradas): el ~16 % no es un
    artefacto de la ventana de observación."""
    return con.sql(_ELEGIBLES + """
        SELECT date_trunc('quarter', fa) AS cohorte_1a_actividad,
               COUNT(*) AS clientes,
               MIN(dias_exposicion) AS exposicion_min,
               ROUND(100.0 * AVG(recompra), 1) AS pct_recompra
        FROM elegibles GROUP BY 1 ORDER BY 1
    """)


def recompra_trip_stacking(con):
    """Separa la 2ª reserva del 'mismo viaje' (<= 14 días del 1er pedido) de la
    recompra real (> 14 días). ~50 % de los clientes con 2ª reserva la hacen en
    menos de 14 días: por eso la definición de recompra exige haber disfrutado
    ya la primera actividad."""
    return con.sql("""
        WITH x AS (
            SELECT user_id, fecha_reserva::date AS fr,
                   ROW_NUMBER() OVER (PARTITION BY user_id
                                      ORDER BY fecha_reserva, reserva_id) AS rn
            FROM reservas WHERE estado = 'confirmada'
        ),
        gaps AS (
            SELECT a.user_id, date_diff('day', a.fr, b.fr) AS d
            FROM x a JOIN x b USING (user_id)
            WHERE a.rn = 1 AND b.rn = 2
        )
        SELECT CASE WHEN d <= 14 THEN 'mismo viaje (<=14d)'
                    ELSE 'recompra real (>14d)' END AS tipo,
               COUNT(*) AS clientes,
               ROUND(AVG(d)) AS dias_medios,
               ROUND(MEDIAN(d)) AS dias_mediana
        FROM gaps GROUP BY 1 ORDER BY 1
    """)


def valor_cliente_por_recompra(con):
    """Facturación total generada por cliente según recompró o no (base madura).
    Quien recompra vale ~219 € frente a ~107 € del que compra una sola vez."""
    return con.sql(_ELEGIBLES + f"""
        , total AS (
            SELECT user_id, SUM(importe_eur) AS rev
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        )
        SELECT CASE WHEN e.recompra = 1 THEN 'recompra' ELSE 'una sola vez' END AS tipo,
               COUNT(*) AS clientes,
               ROUND(SUM(t.rev)) AS revenue,
               ROUND(AVG(t.rev), 1) AS revenue_medio_cliente
        FROM elegibles e JOIN total t USING (user_id)
        WHERE e.{_MADURA}
        GROUP BY 1 ORDER BY revenue_medio_cliente DESC
    """)


def recompra_por_canal(con):
    """Factor 1: el canal de captación. Solo clientes con 1ª reserva DE PAGO
    (aísla el efecto del free tour) y sin Email (etiquetado contaminado: sus
    primeras reservas llevan todas campañas de retención). Directo recompra
    ~2x que Social; el IC de Directo no solapa el de Social."""
    return con.sql(_ELEGIBLES + f"""
        SELECT canal, COUNT(*) AS clientes,
               ROUND(100.0 * AVG(recompra), 1) AS pct_recompra,
               {_ic95()}
        FROM elegibles
        WHERE {_MADURA} AND importe_eur > 0 AND canal <> 'Email'
        GROUP BY 1 ORDER BY pct_recompra DESC
    """)


def recompra_canal_estratificado_por_free(con):
    """El canal no es un espejismo del free tour: el gradiente de canal aparece
    DENTRO de cada estrato (1ª de pago y 1ª free), y free < pago en cada canal."""
    return con.sql(_ELEGIBLES + f"""
        SELECT canal,
               CASE WHEN importe_eur = 0 THEN 'free' ELSE 'pago' END AS tipo_primera,
               COUNT(*) AS clientes,
               ROUND(100.0 * AVG(recompra), 1) AS pct_recompra
        FROM elegibles
        WHERE {_MADURA} AND canal <> 'Email'
        GROUP BY 1, 2 ORDER BY 2 DESC, pct_recompra DESC
    """)


def recompra_canal_estandarizada_destino(con):
    """El canal tampoco es un reflejo del destino: al recalcular la recompra de
    cada canal como si todos vendieran la misma mezcla de destinos (mix global),
    las cifras no se mueven."""
    return con.sql(_ELEGIBLES + f"""
        , cli AS (
            SELECT e.canal, t.destino, e.recompra
            FROM elegibles e JOIN tours t ON e.tour_id = t.tour_id
            WHERE e.{_MADURA} AND e.canal <> 'Email'
        ),
        celda AS (SELECT canal, destino, AVG(recompra) AS r FROM cli GROUP BY 1, 2),
        peso  AS (SELECT destino, COUNT(*) * 1.0 / (SELECT COUNT(*) FROM cli) AS w FROM cli GROUP BY 1),
        crudo AS (SELECT canal, AVG(recompra) AS rc FROM cli GROUP BY 1)
        SELECT c.canal,
               ROUND(100.0 * crudo.rc, 1) AS pct_crudo,
               ROUND(100.0 * SUM(c.r * p.w) / SUM(p.w), 1) AS pct_estandarizado_a_destino
        FROM celda c JOIN peso p USING (destino) JOIN crudo USING (canal)
        GROUP BY c.canal, crudo.rc
        ORDER BY pct_estandarizado_a_destino DESC
    """)


def recompra_por_free_tour(con):
    """Factor 2 (en negativo): quien entra por un free tour recompra MENOS
    (~11 % vs ~18 % de pago). El free tour es palanca de conversión same-trip,
    no de fidelización."""
    return con.sql(_ELEGIBLES + f"""
        SELECT CASE WHEN importe_eur = 0 THEN '1a = free tour' ELSE '1a = de pago' END AS primera_reserva,
               COUNT(*) AS clientes,
               ROUND(100.0 * AVG(recompra), 1) AS pct_recompra,
               {_ic95()}
        FROM elegibles WHERE {_MADURA}
        GROUP BY 1 ORDER BY pct_recompra DESC
    """)


def recompra_por_destino(con):
    """Factor 3 (modesto): el destino de la 1ª experiencia. Roma y Madrid
    fidelizan (~21 %); Nueva York y Marrakech, no (~11 %). Los extremos tienen
    IC separado."""
    return con.sql(_ELEGIBLES + f"""
        SELECT t.destino, COUNT(*) AS clientes,
               ROUND(100.0 * AVG(e.recompra), 1) AS pct_recompra,
               {_ic95('AVG(e.recompra)')}
        FROM elegibles e JOIN tours t ON e.tour_id = t.tour_id
        WHERE e.{_MADURA}
        GROUP BY 1 ORDER BY pct_recompra DESC
    """)


def recompra_factores_sin_efecto(con):
    """Los factores que NO explican la recompra: campaña, importe de la 1ª (más
    allá de free/pago), tamaño de grupo, antelación, dispositivo habitual.
    Todos planos o con IC solapados."""
    tramos = {
        "importe 1a (tramos)":
            "CASE WHEN importe_eur = 0 THEN '0 (free)' WHEN importe_eur < 50 THEN '<50' "
            "WHEN importe_eur < 100 THEN '50-100' WHEN importe_eur < 200 THEN '100-200' ELSE '200+' END",
        "tamano de grupo 1a":
            "CASE WHEN personas IS NULL THEN '(nulo)' WHEN personas = 1 THEN '1' WHEN personas = 2 THEN '2' "
            "WHEN personas <= 4 THEN '3-4' ELSE '5+' END",
        "antelacion 1a reserva":
            "CASE WHEN date_diff('day', fr, fa) <= 7 THEN '0-7d' WHEN date_diff('day', fr, fa) <= 30 THEN '8-30d' "
            "WHEN date_diff('day', fr, fa) <= 90 THEN '31-90d' ELSE '90+d' END",
        "campana 1a reserva": "COALESCE(campana, '(sin campana)')",
    }
    out = {}
    for nombre, expr in tramos.items():
        out[nombre] = con.sql(_ELEGIBLES + f"""
            SELECT {expr} AS grupo, COUNT(*) AS clientes,
                   ROUND(100.0 * AVG(recompra), 1) AS pct_recompra
            FROM elegibles WHERE {_MADURA}
            GROUP BY 1 HAVING COUNT(*) >= 25 ORDER BY pct_recompra DESC
        """).df()
    out["dispositivo habitual"] = con.sql(_ELEGIBLES + f"""
        , dh AS (
            SELECT user_id, device FROM ga_eventos
            WHERE user_id IS NOT NULL AND NOT es_bot
            GROUP BY user_id, device
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY COUNT(DISTINCT session_id) DESC) = 1
        )
        SELECT dh.device AS grupo, COUNT(*) AS clientes,
               ROUND(100.0 * AVG(e.recompra), 1) AS pct_recompra
        FROM elegibles e JOIN dh USING (user_id)
        WHERE e.{_MADURA}
        GROUP BY 1 ORDER BY pct_recompra DESC
    """).df()
    return out


def cancelacion_no_es_churn(con):
    """Una cancelación no rompe la relación con el cliente. Dos ángulos:
    (a) entre los clientes de la base madura, quien sufrió alguna cancelación
        recompra MÁS, no menos;
    (b) de quienes cancelan su primera reserva, ~31 % hace luego una reserva
        confirmada."""
    a = con.sql(_ELEGIBLES + f"""
        , cancel AS (
            SELECT DISTINCT user_id FROM reservas WHERE estado = 'cancelada'
        )
        SELECT CASE WHEN c.user_id IS NOT NULL THEN 'sufrio una cancelacion'
                    ELSE 'sin cancelaciones' END AS grupo,
               COUNT(*) AS clientes,
               ROUND(100.0 * AVG(e.recompra), 1) AS pct_recompra
        FROM elegibles e LEFT JOIN cancel c USING (user_id)
        WHERE e.{_MADURA}
        GROUP BY 1 ORDER BY pct_recompra DESC
    """).df()
    b = con.sql("""
        WITH prim AS (
            SELECT user_id, fecha_reserva::date AS fr, estado,
                   ROW_NUMBER() OVER (PARTITION BY user_id
                                      ORDER BY fecha_reserva, reserva_id) AS rn
            FROM reservas WHERE estado IN ('confirmada', 'cancelada')
        ),
        p1 AS (SELECT user_id, fr FROM prim WHERE rn = 1 AND estado = 'cancelada'),
        vuelve AS (
            SELECT p1.user_id,
                   MAX(CASE WHEN r.estado = 'confirmada' AND r.fecha_reserva::date > p1.fr
                            THEN 1 ELSE 0 END) AS volvio
            FROM p1 LEFT JOIN reservas r USING (user_id)
            GROUP BY 1
        )
        SELECT COUNT(*) AS clientes_cancelan_su_1a,
               ROUND(100.0 * AVG(volvio), 1) AS pct_compra_confirmada_despues
        FROM vuelve
    """).df()
    return {"(a) recompra segun sufrio cancelacion": a,
            "(b) vuelve tras cancelar su primera reserva": b}


# ===========================================================================
# PREGUNTA 2 — Destinos
# ===========================================================================

def acogida_por_destino(con):
    """Volumen e importe de reservas confirmadas por destino."""
    return con.sql("""
        SELECT t.destino,
               COUNT(*) AS reservas,
               ROUND(SUM(r.importe_eur)) AS revenue,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_reservas,
               ROUND(100.0 * SUM(r.importe_eur) / SUM(SUM(r.importe_eur)) OVER (), 1) AS pct_revenue
        FROM reservas r JOIN tours t ON r.tour_id = t.tour_id
        WHERE r.estado = 'confirmada'
        GROUP BY 1 ORDER BY reservas DESC
    """)


def acogida_demanda_vs_conversion(con):
    """"Acogida" = demanda x conversión, no solo volumen. Cruza el interés
    (sesiones con evento view_item, por destino en la URL) con las reservas.
    Atenas: 3ª en interés (casi como Roma) pero convierte la mitad -> demanda
    desaprovechada. Madrid/Roma/París/Londres: lideran interés Y conversión."""
    return con.sql("""
        WITH interes AS (
            SELECT split_part(url, '/', 5) AS destino,
                   COUNT(DISTINCT session_id) AS sesiones_interes
            FROM ga_eventos
            WHERE NOT es_bot AND event_name = 'view_item'
              AND split_part(url, '/', 5) <> ''
            GROUP BY 1
        ),
        res AS (
            SELECT t.destino, COUNT(*) AS reservas
            FROM reservas r JOIN tours t ON r.tour_id = t.tour_id
            WHERE r.estado = 'confirmada' GROUP BY 1
        )
        SELECT i.destino,
               i.sesiones_interes,
               res.reservas,
               ROUND(100.0 * i.sesiones_interes / SUM(i.sesiones_interes) OVER (), 1) AS pct_interes,
               ROUND(100.0 * res.reservas / SUM(res.reservas) OVER (), 1) AS pct_reservas,
               ROUND(100.0 * res.reservas / i.sesiones_interes, 1) AS reservas_por_100_sesiones
        FROM interes i JOIN res USING (destino)
        ORDER BY reservas_por_100_sesiones DESC
    """)


def acogida_ticket_por_destino(con):
    """Ticket medio, personas por reserva y precio por persona. Contrasta la
    hipótesis "París factura por grupos más grandes": FALSA. París tiene MENOS
    personas por reserva que Madrid (2,94 vs 3,08); factura más por PRECIO POR
    PERSONA (32 € vs 24 €): vende tours más caros."""
    return con.sql("""
        SELECT t.destino,
               COUNT(*) AS reservas,
               ROUND(SUM(r.importe_eur)) AS revenue,
               ROUND(AVG(r.importe_eur), 1) AS ticket_medio,
               ROUND(AVG(r.personas), 2) AS personas_medias,
               ROUND(AVG(t.precio_por_persona_eur), 1) AS precio_pp_medio
        FROM reservas r JOIN tours t ON r.tour_id = t.tour_id
        WHERE r.estado = 'confirmada'
        GROUP BY 1 ORDER BY reservas DESC
    """)


def retencion_por_destino_estandarizada_canal(con):
    """La retención por destino no es un reflejo del canal de entrada: al
    estandarizar cada destino al mix de canal global, el ranking no se mueve
    (Madrid/Roma arriba, Nueva York/Marrakech abajo)."""
    return con.sql(_ELEGIBLES + f"""
        , cli AS (
            SELECT t.destino, e.canal, e.recompra
            FROM elegibles e JOIN tours t ON e.tour_id = t.tour_id
            WHERE e.{_MADURA} AND e.canal <> 'Email'
        ),
        celda AS (SELECT destino, canal, AVG(recompra) AS r FROM cli GROUP BY 1, 2),
        peso  AS (SELECT canal, COUNT(*) * 1.0 / (SELECT COUNT(*) FROM cli) AS w FROM cli GROUP BY 1),
        crudo AS (SELECT destino, AVG(recompra) AS rc FROM cli GROUP BY 1)
        SELECT c.destino,
               ROUND(100.0 * crudo.rc, 1) AS pct_crudo,
               ROUND(100.0 * SUM(c.r * p.w) / SUM(p.w), 1) AS pct_estandarizado_a_canal
        FROM celda c JOIN peso p USING (canal) JOIN crudo USING (destino)
        GROUP BY c.destino, crudo.rc
        ORDER BY pct_estandarizado_a_canal DESC
    """)


# ===========================================================================
# PREGUNTA 3 — Estado del negocio
# ===========================================================================

def resumen_estado_negocio(con):
    """Venta = SUM(importe_eur) de reservas confirmada. Fuente de verdad =
    reservas.estado (no GA: 66 reservas del 10-15 marzo 2026 sin ningún evento
    por una caída del tracking)."""
    return con.sql("""
        SELECT
            ROUND(SUM(importe_eur) FILTER (WHERE estado = 'confirmada')) AS venta_confirmada,
            COUNT(*)               FILTER (WHERE estado = 'confirmada')   AS reservas_confirmadas,
            COUNT(*)               FILTER (WHERE estado = 'confirmada' AND importe_eur = 0) AS free_tours,
            ROUND(SUM(importe_eur) FILTER (WHERE estado = 'pendiente'))   AS pipeline_pendiente,
            ROUND(SUM(importe_eur) FILTER (WHERE estado = 'cancelada'))   AS ingreso_perdido_cancelacion,
            ROUND(100.0 * SUM(importe_eur) FILTER (WHERE estado = 'cancelada')
                  / SUM(importe_eur) FILTER (WHERE estado = 'confirmada'), 1) AS pct_cancelado_sobre_venta
        FROM reservas
    """)


def venta_por_semestre(con):
    """Crecimiento: +68 % de ingreso en dos años, monotónico (~+15 % por
    semestre). Se excluyen las ~9 reservas sueltas anteriores a jul-2024."""
    return con.sql("""
        SELECT year(fecha_reserva) || '-' ||
                 CASE WHEN month(fecha_reserva) <= 6 THEN 'H1' ELSE 'H2' END AS semestre,
               COUNT(*) FILTER (WHERE estado = 'confirmada') AS reservas,
               ROUND(SUM(importe_eur) FILTER (WHERE estado = 'confirmada')) AS venta
        FROM reservas
        WHERE fecha_reserva >= DATE '2024-07-01'
        GROUP BY 1 ORDER BY 1
    """)


def sensibilidad_definicion_venta(con):
    """La elección (solo confirmada) es robusta: sumar el pipeline pendiente
    solo mueve +4 %. Restar las cancelaciones NO es una definición válida (son
    reservas distintas, no un descuento)."""
    return con.sql("""
        SELECT
            ROUND(SUM(importe_eur) FILTER (WHERE estado = 'confirmada'))                       AS a_solo_confirmada,
            ROUND(SUM(importe_eur) FILTER (WHERE estado IN ('confirmada', 'pendiente')))       AS b_mas_pendiente,
            ROUND(100.0 * SUM(importe_eur) FILTER (WHERE estado = 'pendiente')
                  / SUM(importe_eur) FILTER (WHERE estado = 'confirmada'), 1)                  AS pct_extra_pendiente,
            COUNT(*) FILTER (WHERE estado = 'confirmada' AND importe_eur > 0)                  AS n_confirmada_de_pago,
            COUNT(*) FILTER (WHERE estado = 'confirmada' AND importe_eur = 0)                  AS n_free_tours
        FROM reservas
    """)


def cancelacion_por_lead_time(con):
    """El exceso de cancelación sobre la tasa base (~14 %) se concentra en las
    reservas muy anticipadas: 90+ días cancelan el 24 %."""
    return con.sql("""
        WITH r AS (
            SELECT estado, importe_eur,
                   date_diff('day', fecha_reserva::date, fecha_actividad) AS lead
            FROM reservas WHERE estado IN ('confirmada', 'cancelada')
        )
        SELECT CASE WHEN lead <= 7 THEN '0-7 d' WHEN lead <= 30 THEN '8-30 d'
                    WHEN lead <= 90 THEN '31-90 d' ELSE '90+ d' END AS antelacion,
               COUNT(*) AS reservas_resueltas,
               ROUND(100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada') / COUNT(*), 1) AS pct_cancelacion,
               ROUND(SUM(importe_eur) FILTER (WHERE estado = 'cancelada')) AS eur_cancelado
        FROM r GROUP BY 1 ORDER BY 1
    """)


def cancelacion_por_canal(con):
    """Social y Afiliados cancelan más (~17-18 %) que el resto (~13 %): tráfico
    de peor calidad también aquí (retienen peor Y cancelan más)."""
    return con.sql("""
        SELECT canal,
               COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')) AS reservas_resueltas,
               ROUND(100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada')
                     / COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')), 1) AS pct_cancelacion
        FROM reservas GROUP BY 1 ORDER BY pct_cancelacion DESC
    """)


def reservas_con_proveedor_de_baja(con):
    """Riesgo operativo (fuera de la cifra de venta): reservas confirmadas
    creadas DESPUÉS de la baja de su proveedor. El sistema no lo impide."""
    return con.sql("""
        WITH en_riesgo AS (
            SELECT r.proveedor_id, p.fecha_baja, r.importe_eur
            FROM reservas r JOIN proveedores p ON r.proveedor_id = p.proveedor_id
            WHERE p.fecha_baja IS NOT NULL
              AND r.fecha_reserva::date > p.fecha_baja
              AND r.estado = 'confirmada'
        ),
        filas AS (
            SELECT proveedor_id::VARCHAR AS proveedor_id,
                   fecha_baja::VARCHAR AS fecha_baja,
                   COUNT(*) AS reservas_confirmadas,
                   ROUND(SUM(importe_eur)) AS importe_en_riesgo,
                   1 AS orden
            FROM en_riesgo GROUP BY 1, 2
            UNION ALL
            SELECT 'TOTAL', NULL, COUNT(*), ROUND(SUM(importe_eur)), 0 FROM en_riesgo
        )
        SELECT proveedor_id, fecha_baja, reservas_confirmadas, importe_en_riesgo
        FROM filas ORDER BY orden, importe_en_riesgo DESC
    """)


# ===========================================================================
# PREGUNTAS DE APOYO — identidad y conversión
# ===========================================================================

def conocidos_vs_desconocidos(con):
    """Solo el ~10 % de las sesiones es identificable tras propagar user_id por
    cookie_id."""
    return con.sql("""
        WITH s AS (
            SELECT session_id,
                   MAX(CASE WHEN user_id_propagado IS NOT NULL THEN 1 ELSE 0 END) AS ident
            FROM ga_eventos WHERE NOT es_bot GROUP BY 1
        )
        SELECT CASE WHEN ident = 1 THEN 'identificada' ELSE 'anonima' END AS tipo_sesion,
               COUNT(*) AS sesiones,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM s GROUP BY 1 ORDER BY sesiones DESC
    """)


def funnel_por_tipo_sesion(con):
    """begin_checkout y purchase solo se disparan con sesión iniciada (~0 en
    anónimas): la conversión NO es medible para el ~90 % del tráfico."""
    return con.sql("""
        WITH s AS (
            SELECT session_id,
                MAX(CASE WHEN user_id_propagado IS NOT NULL THEN 1 ELSE 0 END) AS ident,
                MAX(CASE WHEN event_name = 'view_item'      THEN 1 ELSE 0 END) AS vi,
                MAX(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END) AS bc,
                MAX(CASE WHEN event_name = 'purchase'       THEN 1 ELSE 0 END) AS pu
            FROM ga_eventos WHERE NOT es_bot GROUP BY 1
        )
        SELECT CASE WHEN ident = 1 THEN 'identificada' ELSE 'anonima' END AS tipo_sesion,
               COUNT(*) AS sesiones,
               ROUND(100.0 * SUM(vi) / COUNT(*), 1) AS pct_view_item,
               ROUND(100.0 * SUM(bc) / COUNT(*), 1) AS pct_begin_checkout,
               ROUND(100.0 * SUM(pu) / COUNT(*), 1) AS pct_purchase
        FROM s GROUP BY 1 ORDER BY 1
    """)


def embudo_por_device(con):
    """El "móvil convierte 2,3x peor" es un ARTEFACTO del login. Entre sesiones
    identificadas, móvil y escritorio convierten casi igual (purchase 31 % vs
    34 %, checkout->compra 77 % vs 79 %). El hueco está en el paso de
    identificarse: de las sesiones con interés (view_item), móvil se identifica
    el 19 % vs 35 % en escritorio. Y comprar EXIGE cuenta (0 compras anónimas).
    Móvil es el 70 % del tráfico."""
    return con.sql("""
        WITH s AS (
            SELECT session_id, ANY_VALUE(device) AS device,
                MAX(CASE WHEN user_id_propagado IS NOT NULL THEN 1 ELSE 0 END) AS ident,
                MAX(CASE WHEN event_name = 'view_item'      THEN 1 ELSE 0 END) AS vi,
                MAX(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END) AS bc,
                MAX(CASE WHEN event_name = 'purchase'       THEN 1 ELSE 0 END) AS pu
            FROM ga_eventos WHERE NOT es_bot GROUP BY 1
        )
        SELECT device,
               COUNT(*) AS sesiones,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_trafico,
               ROUND(100.0 * AVG(ident), 1) AS pct_identificada,
               ROUND(100.0 * AVG(ident) FILTER (WHERE vi = 1), 1) AS pct_ident_si_interes,
               ROUND(100.0 * AVG(pu)    FILTER (WHERE vi = 1), 1) AS pct_compra_si_interes,
               ROUND(100.0 * AVG(pu)    FILTER (WHERE ident = 1), 1) AS pct_compra_si_identificada,
               ROUND(100.0 * SUM(pu) / NULLIF(SUM(bc), 0), 1) AS pct_checkout_a_compra
        FROM s GROUP BY 1 ORDER BY sesiones DESC
    """)
