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