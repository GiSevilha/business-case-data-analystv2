"""
Genera una base de datos reducida para la app (`data/processed/civitatis_app.duckdb`)
a partir de la base completa (`data/processed/civitatis.duckdb`).

La app solo necesita `reservas`, `tours` y un subconjunto de columnas de
`ga_eventos`. Quitar las columnas de texto pesadas (url, ip, cookie_id,
temp_client_id...) reduce el fichero de ~79 MB a un tamaño que cabe en el
repositorio y en el plan gratuito de Streamlit Community Cloud.

Uso (después de `python src/main.py`):
    python src/build_app_db.py
"""
from pathlib import Path

import duckdb

FULL = Path("data/processed/civitatis.duckdb")
SLIM = Path("data/processed/civitatis_app.duckdb")

if not FULL.exists():
    raise SystemExit(f"Falta {FULL}. Ejecuta antes: python src/main.py")

SLIM.unlink(missing_ok=True)

con = duckdb.connect(str(SLIM))
con.execute(f"ATTACH '{FULL.as_posix()}' AS src (READ_ONLY)")

con.execute("CREATE TABLE reservas AS SELECT * FROM src.reservas")
con.execute("CREATE TABLE tours    AS SELECT * FROM src.tours")
con.execute(
    """
    CREATE TABLE ga_eventos AS
    SELECT session_id, event_name, event_date, device,
           user_id, user_id_propagado, es_bot, reserva_id
    FROM src.ga_eventos
    """
)

con.execute("DETACH src")
con.execute("VACUUM")
con.execute("CHECKPOINT")
con.close()

mb = SLIM.stat().st_size / 1_000_000
print(f"OK -> {SLIM} ({mb:.1f} MB)")
