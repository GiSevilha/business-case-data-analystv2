def limpiar_reservas(con, ruta):
    query = f"""
        SELECT * EXCLUDE (estado, personas),
            CASE WHEN LOWER(estado) = 'cancelled' THEN 'cancelada' ELSE LOWER(estado) END AS estado,
            CASE WHEN personas <= 0 THEN NULL ELSE personas END AS personas
        FROM '{ruta}'
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY user_id, tour_id, proveedor_id, fecha_reserva, fecha_actividad, estado, personas, importe_eur, campana, canal
            ORDER BY reserva_id ASC
        ) = 1
    """
    return con.sql(query)