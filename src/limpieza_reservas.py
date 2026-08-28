def limpiar_reservas(con, ruta):
    query = f"""
        SELECT * EXCLUDE (estado),
            CASE WHEN LOWER(estado) = 'cancelled' THEN 'cancelada' ELSE LOWER(estado) END AS estado
        FROM '{ruta}'
    """
    return con.sql(query)