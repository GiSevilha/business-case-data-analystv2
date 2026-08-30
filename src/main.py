import duckdb
from pathlib import Path
from limpieza_ga_eventos import limpiar_ga_eventos
from limpieza_reservas import limpiar_reservas
from identidad import crosswalk_clientes, identidad_ga_eventos
from limpieza_clientes import limpieza_clientes
from limpieza_tours import limpiar_tours
from calidad_trafico import marcar_trafico_bot

con = duckdb.connect("data/processed/civitatis.duckdb")

RAW_DIR = Path("data/raw")
archivos = {
    "clientes": RAW_DIR / "clientes.csv",
    "proveedores": RAW_DIR / "proveedores.csv",
    "ga_eventos": RAW_DIR / "ga_eventos.csv",
    "reservas": RAW_DIR / "reservas.csv",
    "tours": RAW_DIR / "tours.csv",
}

def guardar_tabla(nombre_tabla, relacion):
    con.sql(f"DROP TABLE IF EXISTS {nombre_tabla}")
    relacion.create(nombre_tabla)

# limpiezas independientes, que no dependen de otras
clientes_limpio = limpieza_clientes(con, archivos["clientes"])
crosswalk = crosswalk_clientes(con, archivos["clientes"])
reservas_limpio = limpiar_reservas(con, archivos["reservas"])
ga_limpios = limpiar_ga_eventos(con, archivos["ga_eventos"])
tours_limpio = limpiar_tours(con, archivos["tours"])

# traducción de user_id duplicados vía crosswalk
reservas_final = con.sql("""
    SELECT r.* EXCLUDE (user_id), c.user_id_canonico AS user_id
    FROM reservas_limpio r
    LEFT JOIN crosswalk c ON r.user_id = c.user_id_original
""")

ga_final = con.sql(f"""select ga.* exclude (user_id), c.user_id_canonico AS user_id
                        FROM ga_limpios ga
                        left join crosswalk c on ga.user_id = c.user_id_original""")

ga_con_identidad = identidad_ga_eventos(ga_final)
ga_final_completo = marcar_trafico_bot(ga_con_identidad)

# persistir en la bbdd
guardar_tabla("clientes", clientes_limpio)
guardar_tabla("reservas", reservas_final)
guardar_tabla("ga_eventos", ga_final_completo)
guardar_tabla("tours", tours_limpio)
guardar_tabla("crosswalk_clientes", crosswalk)
# proveedores no necesitó limpieza propia, se copia tal cual
guardar_tabla("proveedores", con.sql(f"SELECT * FROM '{archivos['proveedores']}'"))
