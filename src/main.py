import duckdb
from pathlib import Path
from limpieza_ga_eventos import limpiar_ga_eventos
from limpieza_reservas import limpiar_reservas
from identidad import crosswalk_clientes
from limpieza_clientes import limpieza_clientes

con = duckdb.connect()

RAW_DIR = Path("data/raw")
archivos = {
    "clientes": RAW_DIR / "clientes.csv",
    "proveedores": RAW_DIR / "proveedores.csv",
    "ga_eventos": RAW_DIR / "ga_eventos.csv",
    "reservas": RAW_DIR / "reservas.csv",
    "tours": RAW_DIR / "tours.csv",
}

reservas_limpio = limpiar_reservas(con, archivos["reservas"])
crosswalk = crosswalk_clientes(con, archivos["clientes"])
clientes_limpio = limpieza_clientes(con, archivos["clientes"])
ga_limpios = limpiar_ga_eventos(con, archivos["ga_eventos"])

reservas_final = con.sql("""
    SELECT r.* EXCLUDE (user_id), c.user_id_canonico AS user_id
    FROM reservas_limpio r
    LEFT JOIN crosswalk c ON r.user_id = c.user_id_original
""")

ga_final = con.sql(f"""select ga.* exclude (user_id), c.user_id_canonico AS user_id
                        FROM ga_limpios ga
                        left join crosswalk c on ga.user_id = c.user_id_original""")
