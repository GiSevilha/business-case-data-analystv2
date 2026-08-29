def limpieza_clientes(con, ruta):
    query = f"""
        select * EXCLUDE (fecha_nacimiento),
            case when fecha_nacimiento = '1900-01-01' then null else fecha_nacimiento end as fecha_nacimiento
        from '{ruta}'
        qualify user_id = min(user_id) over(partition by lower(dni))
    """
    return con.sql(query)