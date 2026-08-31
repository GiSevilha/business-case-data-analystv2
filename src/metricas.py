def retencion_por_destino_entrada(con):
    query = """
        WITH primera_reserva AS (
        SELECT user_id, tour_id
        FROM reservas
        WHERE estado = 'confirmada'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY fecha_reserva ASC
        ) = 1
    ),
    recurrencia AS (
        SELECT user_id, COUNT(*) AS num_reservas
        FROM reservas
        WHERE estado = 'confirmada'
        GROUP BY user_id
    )
    SELECT
        t.destino,
        COUNT(*) AS clientes_totales,
        SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) AS clientes_recurrentes,
        ROUND(100.0 * SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_retencion
    FROM primera_reserva p
    JOIN tours t ON p.tour_id = t.tour_id
    JOIN recurrencia r ON p.user_id = r.user_id
    GROUP BY t.destino
    ORDER BY pct_retencion DESC
"""
    return con.sql(query)

def resumen_estado_negocio(con):
    query = """
        SELECT
            SUM(CASE WHEN estado = 'confirmada' THEN importe_eur ELSE 0 END) AS venta_total,
            SUM(CASE WHEN estado = 'confirmada' THEN 1 ELSE 0 END) AS volumen_ventas,
            SUM(CASE WHEN estado = 'pendiente' THEN importe_eur ELSE 0 END) AS pipeline_pendiente,
            SUM(CASE WHEN estado = 'cancelada' THEN importe_eur ELSE 0 END) AS ingreso_perdido_cancelacion
        FROM reservas
    """
    return con.sql(query)


def retencion_por_canal_entrada(con):
    query = """
            WITH primera_reserva AS (
            SELECT user_id, canal
            FROM reservas
            WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY user_id
                ORDER BY fecha_reserva ASC
            ) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas
            WHERE estado = 'confirmada'
            GROUP BY user_id
        )
        SELECT
            p.canal,
            COUNT(*) AS clientes_totales,
            SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) AS clientes_recurrentes,
            ROUND(100.0 * SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_retencion
        FROM primera_reserva p
        JOIN recurrencia r ON p.user_id = r.user_id
        GROUP BY p.canal
        ORDER BY pct_retencion DESC
    """

    return con.sql(query)


def retencion_por_campana_entrada(con):
    query = """
            WITH primera_reserva AS (
            SELECT user_id, campana
            FROM reservas
            WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY user_id
                ORDER BY fecha_reserva ASC
            ) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas
            WHERE estado = 'confirmada'
            GROUP BY user_id
        )
        SELECT
            p.campana,
            COUNT(*) AS clientes_totales,
            SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) AS clientes_recurrentes,
            ROUND(100.0 * SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_retencion
        FROM primera_reserva p
        JOIN recurrencia r ON p.user_id = r.user_id
        GROUP BY p.campana
        ORDER BY pct_retencion DESC
    """

    return con.sql(query)


def retencion_por_dispositivo_habitual(con):
    query = """
        WITH dispositivo_habitual AS (
            SELECT user_id, device, COUNT(DISTINCT session_id) AS num_sesiones
            FROM ga_eventos
            WHERE user_id IS NOT NULL AND NOT es_bot
            GROUP BY user_id, device
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY user_id
                ORDER BY num_sesiones DESC
            ) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas
            WHERE estado = 'confirmada'
            GROUP BY user_id
        )
        SELECT
            d.device AS dispositivo_habitual,
            COUNT(*) AS clientes_totales,
            SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) AS clientes_recurrentes,
            ROUND(100.0 * SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_retencion
        FROM dispositivo_habitual d
        JOIN recurrencia r ON d.user_id = r.user_id
        GROUP BY d.device
        ORDER BY pct_retencion DESC
    """
    return con.sql(query)


def acogida_por_destino(con):
    query = """
        SELECT
            t.destino,
            COUNT(*) AS volumen_reservas,
            SUM(r.importe_eur) AS importe_total
        FROM reservas r
        JOIN tours t ON r.tour_id = t.tour_id
        WHERE r.estado = 'confirmada'
        GROUP BY t.destino
        ORDER BY volumen_reservas DESC
    """
    return con.sql(query)


# ---------------------------------------------------------------------------
# Consultas de contraste de hipotesis (COMEX)
# ---------------------------------------------------------------------------

def acogida_ticket_por_destino(con):
    """Acogida + ticket medio, personas por reserva y precio por persona.
    Contrasta la hipotesis 'Paris factura mas por grupos mas grandes'
    (falso: es mayor precio por persona, no mas personas)."""
    query = """
        SELECT
            t.destino,
            COUNT(*) AS reservas,
            ROUND(SUM(r.importe_eur)) AS revenue,
            ROUND(AVG(r.importe_eur), 1) AS ticket_medio,
            ROUND(AVG(r.personas), 2) AS personas_medias,
            ROUND(AVG(t.precio_por_persona_eur), 1) AS precio_pp_medio,
            COUNT(DISTINCT r.user_id) AS clientes
        FROM reservas r
        JOIN tours t ON r.tour_id = t.tour_id
        WHERE r.estado = 'confirmada'
        GROUP BY t.destino
        ORDER BY reservas DESC
    """
    return con.sql(query)


def repeticion_ventana_observacion(con):
    """Repeticion DENTRO de 180 dias por cohorte trimestral de primera
    reserva confirmada. Sirve para descartar que las diferencias de
    retencion sean sesgo de censura temporal: el % es estable (~29-33%)
    en todas las cohortes con exposicion completa; solo las 2 ultimas
    cohortes estan censuradas y deben excluirse del titular."""
    query = """
        WITH x AS (
            SELECT user_id, fecha_reserva::date AS fr,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) AS rn
            FROM reservas WHERE estado = 'confirmada'
        ),
        base AS (SELECT user_id, fr AS f1 FROM x WHERE rn = 1),
        seg AS (
            SELECT b.user_id, b.f1, MIN(x.fr) AS f2
            FROM base b JOIN x ON x.user_id = b.user_id AND x.rn >= 2
            GROUP BY 1, 2
        )
        SELECT
            date_trunc('quarter', b.f1) AS cohorte,
            COUNT(*) AS clientes,
            ROUND(100.0 * COUNT(s.user_id) FILTER (WHERE date_diff('day', s.f1, s.f2) <= 180) / COUNT(*), 1) AS pct_repeat_180d,
            date_diff('day', MAX(b.f1), (SELECT MAX(fecha_reserva)::date FROM reservas)) AS dias_exposicion_min
        FROM base b LEFT JOIN seg s USING (user_id)
        GROUP BY 1 ORDER BY 1
    """
    return con.sql(query)


def repeticion_trip_stacking(con):
    """Separa la 2a reserva del 'mismo viaje' (<=14 dias) de la recompra
    real (>14 dias). ~50% de los 'recurrentes' reservan su 2a actividad
    en menos de 14 dias: es planificacion de un unico viaje, no lealtad."""
    query = """
        WITH x AS (
            SELECT user_id, fecha_reserva::date AS fr,
                   ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) AS rn
            FROM reservas WHERE estado = 'confirmada'
        ),
        gaps AS (
            SELECT a.user_id, date_diff('day', a.fr, b.fr) AS d
            FROM x a JOIN x b USING (user_id)
            WHERE a.rn = 1 AND b.rn = 2
        )
        SELECT
            CASE WHEN d <= 14 THEN 'mismo viaje (<=14d)' ELSE 'recompra real (>14d)' END AS tipo,
            COUNT(*) AS clientes,
            ROUND(AVG(d), 0) AS dias_medios,
            ROUND(MEDIAN(d), 0) AS dias_mediana
        FROM gaps GROUP BY 1 ORDER BY 1
    """
    return con.sql(query)


def retencion_por_free_tour_entrada(con):
    """Factor mas fuerte de repeticion: haber entrado por un free tour
    (importe 0) casi triplica la retencion (52% vs 23%)."""
    query = """
        WITH primera AS (
            SELECT user_id, importe_eur
            FROM reservas WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        )
        SELECT
            CASE WHEN p.importe_eur = 0 THEN 'free tour' ELSE 'de pago' END AS primera_reserva,
            COUNT(*) AS clientes,
            SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) AS clientes_recurrentes,
            ROUND(100.0 * SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_retencion
        FROM primera p JOIN recurrencia r USING (user_id)
        GROUP BY 1 ORDER BY pct_retencion DESC
    """
    return con.sql(query)


def retencion_canal_controlado_por_free(con):
    """Retencion por canal separando primera reserva free vs de pago.
    Demuestra que canal y free-tour son dos efectos reales e
    independientes: el canal sobrevive dentro de cada segmento."""
    query = """
        WITH primera AS (
            SELECT user_id, canal, importe_eur
            FROM reservas WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        )
        SELECT
            p.canal,
            CASE WHEN p.importe_eur = 0 THEN 'free' ELSE 'pago' END AS tipo_primera,
            COUNT(*) AS clientes,
            ROUND(100.0 * SUM(CASE WHEN r.num_reservas >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_retencion
        FROM primera p JOIN recurrencia r USING (user_id)
        GROUP BY 1, 2 ORDER BY 2, pct_retencion DESC
    """
    return con.sql(query)


def retencion_por_canal_ic95(con):
    """Retencion por canal con intervalo de confianza 95% (Wald).
    Distingue senal real (Email vs Social no solapan) de ruido muestral
    (campanas pequenas)."""
    query = """
        WITH primera AS (
            SELECT user_id, canal
            FROM reservas WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        ),
        base AS (
            SELECT p.canal, COUNT(*) AS c,
                   AVG(CASE WHEN r.num_reservas >= 2 THEN 1.0 ELSE 0 END) AS p
            FROM primera p JOIN recurrencia r USING (user_id) GROUP BY 1
        )
        SELECT canal, c AS clientes,
               ROUND(100 * p, 1) AS pct_retencion,
               ROUND(100 * (p - 1.96 * sqrt(p * (1 - p) / c)), 1) AS ic95_low,
               ROUND(100 * (p + 1.96 * sqrt(p * (1 - p) / c)), 1) AS ic95_high
        FROM base ORDER BY p DESC
    """
    return con.sql(query)


def retencion_por_campana_ic95(con):
    """Retencion por campana de la primera reserva con IC95. newsletter_semanal
    y post_compra_crossell destacan pero con IC muy anchos y nombres de
    campanas de retencion: probable error de etiquetado de origen."""
    query = """
        WITH primera AS (
            SELECT user_id, COALESCE(campana, 'Sin campana') AS campana
            FROM reservas WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        ),
        base AS (
            SELECT p.campana, COUNT(*) AS c,
                   AVG(CASE WHEN r.num_reservas >= 2 THEN 1.0 ELSE 0 END) AS p
            FROM primera p JOIN recurrencia r USING (user_id) GROUP BY 1
        )
        SELECT campana, c AS clientes,
               ROUND(100 * p, 1) AS pct_retencion,
               ROUND(100 * (p - 1.96 * sqrt(p * (1 - p) / c)), 1) AS ic95_low,
               ROUND(100 * (p + 1.96 * sqrt(p * (1 - p) / c)), 1) AS ic95_high
        FROM base ORDER BY p DESC
    """
    return con.sql(query)


def retencion_por_destino_controlada_canal(con):
    """Retencion por destino estandarizada al mix de canal GLOBAL
    (standardizacion directa): que retencion tendria cada destino si su
    reparto de canales fuese el del total de clientes. El ranking apenas
    cambia respecto al crudo => el efecto destino es real y no un
    artefacto del canal de entrada."""
    query = """
        WITH primera AS (
            SELECT user_id, canal, tour_id
            FROM reservas WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS num_reservas
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        ),
        cliente AS (
            SELECT t.destino, p.canal,
                   CASE WHEN r.num_reservas >= 2 THEN 1.0 ELSE 0 END AS repite
            FROM primera p JOIN recurrencia r USING (user_id)
            JOIN tours t ON p.tour_id = t.tour_id
        ),
        celda AS (
            SELECT destino, canal, AVG(repite) AS ret, COUNT(*) AS n
            FROM cliente GROUP BY 1, 2
        ),
        peso_global AS (
            SELECT canal, COUNT(*) * 1.0 / (SELECT COUNT(*) FROM cliente) AS w
            FROM cliente GROUP BY 1
        ),
        crudo AS (
            SELECT destino, AVG(repite) AS ret_cruda FROM cliente GROUP BY 1
        )
        SELECT
            c.destino,
            ROUND(100.0 * cr.ret_cruda, 1) AS pct_retencion_cruda,
            ROUND(100.0 * SUM(c.ret * g.w) / SUM(g.w), 1) AS pct_retencion_estandarizada
        FROM celda c
        JOIN peso_global g USING (canal)
        JOIN crudo cr USING (destino)
        GROUP BY c.destino, cr.ret_cruda
        ORDER BY pct_retencion_estandarizada DESC
    """
    return con.sql(query)


def funnel_por_tipo_sesion(con):
    """Funnel por sesion identificada vs anonima. Revela que los eventos
    begin_checkout y purchase solo se disparan con sesion logueada
    (~0 en anonimas) => la tasa de conversion NO es medible para el 90%
    del trafico; solo para sesiones identificadas (32%)."""
    query = """
        WITH s AS (
            SELECT session_id,
                MAX(CASE WHEN user_id_propagado IS NOT NULL THEN 1 ELSE 0 END) AS ident,
                MAX(CASE WHEN event_name = 'view_item' THEN 1 ELSE 0 END) AS vi,
                MAX(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END) AS bc,
                MAX(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END) AS pu
            FROM ga_eventos WHERE NOT es_bot GROUP BY 1
        )
        SELECT
            CASE WHEN ident = 1 THEN 'identificada' ELSE 'anonima' END AS tipo_sesion,
            COUNT(*) AS sesiones,
            ROUND(100.0 * SUM(vi) / COUNT(*), 1) AS pct_view_item,
            ROUND(100.0 * SUM(bc) / COUNT(*), 1) AS pct_begin_checkout,
            ROUND(100.0 * SUM(pu) / COUNT(*), 1) AS pct_purchase
        FROM s GROUP BY 1 ORDER BY 1
    """
    return con.sql(query)


def conversion_por_device(con):
    """Efecto del dispositivo en la probabilidad de compra (no en la
    repeticion). Desktop convierte ~2.3x mejor que mobile, que es el 70%
    del trafico: friccion de checkout movil."""
    query = """
        WITH s AS (
            SELECT session_id, ANY_VALUE(device) AS device,
                MAX(CASE WHEN user_id_propagado IS NOT NULL THEN 1 ELSE 0 END) AS ident,
                MAX(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END) AS bc,
                MAX(CASE WHEN event_name = 'purchase' THEN 1 ELSE 0 END) AS pu
            FROM ga_eventos WHERE NOT es_bot GROUP BY 1
        )
        SELECT device,
               COUNT(*) AS sesiones,
               ROUND(100.0 * AVG(ident), 1) AS pct_identificada,
               ROUND(100.0 * AVG(bc), 2) AS pct_begin_checkout,
               ROUND(100.0 * AVG(pu), 2) AS pct_purchase
        FROM s GROUP BY 1 ORDER BY sesiones DESC
    """
    return con.sql(query)


def conocidos_vs_desconocidos(con):
    """Proporcion de sesiones identificables tras la propagacion por
    cookie_id."""
    query = """
        WITH s AS (
            SELECT session_id,
                MAX(CASE WHEN user_id_propagado IS NOT NULL THEN 1 ELSE 0 END) AS ident
            FROM ga_eventos WHERE NOT es_bot GROUP BY 1
        )
        SELECT
            CASE WHEN ident = 1 THEN 'identificada' ELSE 'anonima' END AS tipo_sesion,
            COUNT(*) AS sesiones,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM s GROUP BY 1 ORDER BY sesiones DESC
    """
    return con.sql(query)


def cancelacion_por_lead_time(con):
    """Tasa de cancelacion por antelacion (dias entre reserva y actividad).
    Driver claro: 90+ dias cancela 24% vs 10% a 0-7 dias."""
    query = """
        WITH r AS (
            SELECT estado, date_diff('day', fecha_reserva::date, fecha_actividad) AS lead_dias
            FROM reservas
        )
        SELECT
            CASE WHEN lead_dias < 0 THEN 'negativo'
                 WHEN lead_dias <= 7 THEN '0-7 dias'
                 WHEN lead_dias <= 30 THEN '8-30 dias'
                 WHEN lead_dias <= 90 THEN '31-90 dias'
                 ELSE '90+ dias' END AS antelacion,
            COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')) AS reservas_resueltas,
            ROUND(100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada')
                  / COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')), 1) AS pct_cancelacion
        FROM r GROUP BY 1 ORDER BY 1
    """
    return con.sql(query)


def cancelacion_por_canal(con):
    """Tasa de cancelacion por canal. Social y Afiliados (los que peor
    retienen) tambien cancelan mas: trafico de baja calidad en las dos
    metricas."""
    query = """
        SELECT
            canal,
            COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')) AS reservas_resueltas,
            ROUND(100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada')
                  / COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')), 1) AS pct_cancelacion
        FROM reservas GROUP BY 1 ORDER BY pct_cancelacion DESC
    """
    return con.sql(query)


def sensibilidad_definicion_venta(con):
    """Venta bajo definiciones alternativas. La eleccion (solo confirmada)
    es robusta: anadir pendiente solo mueve +4%."""
    query = """
        SELECT
            ROUND(SUM(importe_eur) FILTER (WHERE estado = 'confirmada')) AS solo_confirmada,
            ROUND(SUM(importe_eur) FILTER (WHERE estado IN ('confirmada', 'pendiente'))) AS confirmada_mas_pendiente,
            COUNT(*) FILTER (WHERE estado = 'confirmada') AS n_confirmada,
            COUNT(*) FILTER (WHERE estado = 'confirmada' AND importe_eur > 0) AS n_confirmada_de_pago,
            COUNT(*) FILTER (WHERE estado = 'confirmada' AND importe_eur = 0) AS n_free_tours,
            ROUND(SUM(importe_eur) FILTER (WHERE estado = 'cancelada')) AS ingreso_perdido_cancelacion,
            ROUND(100.0 * SUM(importe_eur) FILTER (WHERE estado = 'cancelada')
                  / SUM(importe_eur) FILTER (WHERE estado = 'confirmada'), 1) AS pct_perdida_sobre_venta
        FROM reservas
    """
    return con.sql(query)


def revenue_por_tipo_cliente(con):
    """Reparto de facturacion entre clientes de una sola compra y
    repetidores. Los repetidores son ~46% del revenue: por eso importa
    la pregunta de repeticion."""
    query = """
        WITH r AS (
            SELECT user_id, COUNT(*) AS n, SUM(importe_eur) AS rev
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        )
        SELECT
            CASE WHEN n >= 2 THEN 'repetidor' ELSE 'una sola compra' END AS tipo_cliente,
            COUNT(*) AS clientes,
            ROUND(SUM(rev)) AS revenue,
            ROUND(100.0 * SUM(rev) / SUM(SUM(rev)) OVER (), 1) AS pct_revenue,
            ROUND(AVG(rev), 1) AS revenue_medio_cliente
        FROM r GROUP BY 1 ORDER BY revenue DESC
    """
    return con.sql(query)


def ltv_free_vs_pago_entrada(con):
    """Valor total generado segun la primera reserva fue free o de pago.
    Matiz para la defensa: los free-first repiten mas pero valen menos
    por cabeza (71 EUR vs 136 EUR)."""
    query = """
        WITH primera AS (
            SELECT user_id, importe_eur AS i1
            FROM reservas WHERE estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY fecha_reserva) = 1
        ),
        total AS (
            SELECT user_id, SUM(importe_eur) AS rev, COUNT(*) AS n
            FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        )
        SELECT
            CASE WHEN p.i1 = 0 THEN 'entrada free' ELSE 'entrada de pago' END AS segmento,
            COUNT(*) AS clientes,
            ROUND(SUM(t.rev)) AS revenue_total,
            ROUND(100.0 * SUM(t.rev) / SUM(SUM(t.rev)) OVER (), 1) AS pct_revenue,
            ROUND(AVG(t.rev), 1) AS revenue_medio,
            ROUND(AVG(t.n), 2) AS reservas_medias
        FROM primera p JOIN total t USING (user_id)
        GROUP BY 1 ORDER BY revenue_total DESC
    """
    return con.sql(query)


def reservas_con_proveedor_de_baja(con):
    """Riesgo operativo: reservas confirmadas creadas despues de la baja
    de su proveedor."""
    query = """
        SELECT
            COUNT(*) AS reservas_confirmadas,
            ROUND(SUM(r.importe_eur)) AS importe_en_riesgo
        FROM reservas r
        JOIN proveedores p ON r.proveedor_id = p.proveedor_id
        WHERE p.fecha_baja IS NOT NULL
          AND r.fecha_reserva::date > p.fecha_baja
          AND r.estado = 'confirmada'
    """
    return con.sql(query)