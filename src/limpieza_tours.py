def limpiar_tours(con, ruta):
    query = f"""
        select * exclude (proveedor_id),
            case when proveedor_id = 1099 then null else proveedor_id end as proveedor_id
        from '{ruta}'
"""
    return con.sql(query)