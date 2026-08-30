def marcar_trafico_bot(relacion):
    query = """
        SELECT *, 
        CASE WHEN temp_client_id = 'Tbot0000000' THEN TRUE ELSE FALSE END AS es_bot
        FROM ga_bot_virtual
    """
    return relacion.query("ga_bot_virtual", query)