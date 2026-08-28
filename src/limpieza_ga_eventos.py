def limpiar_ga_eventos(con, ruta):
    query = f"""SELECT * EXCLUDE (event_date, device),
                    COALESCE(
                        try_strptime(event_date, '%Y-%m-%d %H:%M:%S'),
                        try_strptime(event_date, '%d/%m/%Y %H:%M')
                    ) AS event_date,
                    CASE WHEN LOWER(device) = 'desktp' THEN 'desktop' ELSE LOWER(device) END AS device
                FROM '{ruta}'"""
    return con.sql(query)