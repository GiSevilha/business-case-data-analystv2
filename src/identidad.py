def crosswalk_clientes(con, ruta):
    """
    Tabla de correspondencia user_id_original -> user_id_canonico.
    Agrupa por DNI (normalizado): el canónico es el user_id más bajo
    de cada grupo, asumido como el registro original (el otro es un
    re-registro con email generado automáticamente).
    """
    query = f"""
        SELECT
            user_id AS user_id_original,
            MIN(user_id) OVER (PARTITION BY LOWER(dni)) AS user_id_canonico
        FROM '{ruta}'
    """
    return con.sql(query)


def identidad_ga_eventos(relacion):
    query = """
        SELECT *, MAX(user_id) OVER (PARTITION BY cookie_id) AS user_id_propagado
        FROM ga_virtual
    """
    return relacion.query("ga_virtual", query)