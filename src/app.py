"""
App de análisis interactivo — Business Case Civitatis.

Ejecutar desde la raíz del repo:
    streamlit run src/app.py

Todas las cifras respetan las mismas definiciones que src/metricas.py:
- Venta            = importe de reservas en estado 'confirmada'
- Cliente recurrente = user_id con >= 2 reservas confirmadas en días distintos
- Sesión          = session_id distinto, excluyendo tráfico de bot (es_bot)
- Conversión      = sesión con al menos un evento 'purchase' (reserva_id no nulo)

El filtro de fechas actúa sobre reservas.fecha_reserva (y sobre ga_eventos.event_date
en la pestaña de tráfico). En la pestaña de Repetición el filtro define la COHORTE:
clientes cuya primera reserva confirmada cae dentro del rango.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

# DB reducida para la app (se versiona y se despliega); si no está, se usa la completa.
_SLIM = Path("data/processed/civitatis_app.duckdb")
_FULL = Path("data/processed/civitatis.duckdb")
DB_PATH = _SLIM if _SLIM.exists() else _FULL

st.set_page_config(
    page_title="Civitatis · Análisis",
    page_icon="📊",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# Conexión y utilidades
# --------------------------------------------------------------------------- #

@st.cache_resource
def get_con() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        st.error(
            f"No encuentro la base de datos en `{DB_PATH}`.\n\n"
            "Genérala primero con:\n\n```\npython src/main.py\npython src/build_app_db.py\n```"
        )
        st.stop()
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(show_spinner=False)
def q(sql: str, params: tuple | None = None) -> pd.DataFrame:
    con = get_con()
    return con.execute(sql, list(params) if params else None).df()


@st.cache_data(show_spinner=False)
def rango_fechas() -> tuple[dt.date, dt.date]:
    df = q("SELECT MIN(fecha_reserva)::date a, MAX(fecha_reserva)::date b FROM reservas")
    return pd.Timestamp(df.a.iloc[0]).date(), pd.Timestamp(df.b.iloc[0]).date()


@st.cache_data(show_spinner=False)
def inicio_datos_reales() -> dt.date:
    """Primer mes con volumen relevante (>= 20 reservas). Antes de mediados de 2024
    solo hay unas pocas reservas sueltas que ensucian las series temporales."""
    df = q(
        """
        SELECT MIN(m)::date AS d FROM (
            SELECT date_trunc('month', fecha_reserva) AS m, COUNT(*) AS n
            FROM reservas GROUP BY 1 HAVING COUNT(*) >= 20
        )
        """
    )
    return pd.Timestamp(df.d.iloc[0]).date()


def trunc(col: str, granularidad: str) -> str:
    unidad = {"Semana": "week", "Mes": "month", "Día": "day"}[granularidad]
    return f"date_trunc('{unidad}', {col})"


def kpi_delta(valor: float, comparado: float) -> str | None:
    if comparado in (0, None) or pd.isna(comparado):
        return None
    return f"{(valor - comparado) / comparado * 100:+.1f}% vs. periodo anterior"


EUR = lambda x: f"{x:,.0f} €".replace(",", ".")

# --------------------------------------------------------------------------- #
# Sidebar — filtros
# --------------------------------------------------------------------------- #

fmin, fmax = rango_fechas()
finicio = inicio_datos_reales()

st.sidebar.title("Filtros")

preset = st.sidebar.radio(
    "Rango rápido",
    ["Histórico con volumen", "Todo (incl. 2023)", "Últimos 12 meses", "Últimos 6 meses", "Últimos 90 días", "Personalizado"],
    index=0,
)

if preset == "Histórico con volumen":
    desde, hasta = finicio, fmax
elif preset == "Todo (incl. 2023)":
    desde, hasta = fmin, fmax
elif preset == "Últimos 12 meses":
    desde, hasta = max(fmin, fmax - dt.timedelta(days=365)), fmax
elif preset == "Últimos 6 meses":
    desde, hasta = max(fmin, fmax - dt.timedelta(days=182)), fmax
elif preset == "Últimos 90 días":
    desde, hasta = max(fmin, fmax - dt.timedelta(days=90)), fmax
else:
    desde, hasta = finicio, fmax

rango = st.sidebar.date_input(
    "Rango de fechas (fecha de reserva)",
    value=(desde, hasta),
    min_value=fmin,
    max_value=fmax,
    disabled=(preset != "Personalizado"),
)
if isinstance(rango, tuple) and len(rango) == 2:
    desde, hasta = rango

granularidad = st.sidebar.radio("Agrupar series temporales por", ["Semana", "Mes", "Día"], index=1)

canales_todos = q("SELECT DISTINCT canal FROM reservas ORDER BY 1").canal.tolist()
canales = st.sidebar.multiselect("Canal", canales_todos, default=canales_todos)

destinos_todos = q("SELECT DISTINCT destino FROM tours ORDER BY 1").destino.tolist()
destinos = st.sidebar.multiselect("Destino", destinos_todos, default=destinos_todos)

st.sidebar.caption(
    f"Datos disponibles: {fmin:%d/%m/%Y} – {fmax:%d/%m/%Y}. "
    "Tráfico de bot excluido de todas las métricas de negocio."
)

# Filtros como fragmentos SQL reutilizables (los canales/destinos van embebidos: lista blanca)
canal_sql = "(" + ",".join(f"'{c}'" for c in canales) + ")" if canales else "('__none__')"
destino_sql = "(" + ",".join(f"'{d}'" for d in destinos) + ")" if destinos else "('__none__')"

P = (desde, hasta)  # parámetros de fecha reutilizados

RESERVAS_FILTRADAS = f"""
    SELECT r.*, t.destino, t.precio_por_persona_eur
    FROM reservas r
    JOIN tours t ON r.tour_id = t.tour_id
    WHERE r.fecha_reserva::date BETWEEN ? AND ?
      AND r.canal IN {canal_sql}
      AND t.destino IN {destino_sql}
"""

# periodo anterior de igual longitud, para deltas
dur = (hasta - desde).days + 1
prev_desde, prev_hasta = desde - dt.timedelta(days=dur), desde - dt.timedelta(days=1)
Pprev = (prev_desde, prev_hasta)
# solo comparamos si el periodo anterior cae dentro del tramo con volumen real
comparar = prev_desde >= finicio

st.title("Business Case Civitatis — análisis interactivo")
st.caption(
    f"Periodo seleccionado: **{desde:%d/%m/%Y} – {hasta:%d/%m/%Y}**  ·  "
    f"{len(canales)}/{len(canales_todos)} canales  ·  {len(destinos)}/{len(destinos_todos)} destinos"
)

tab_negocio, tab_repeticion, tab_destinos, tab_trafico = st.tabs(
    ["💶 Estado del negocio", "🔁 Repetición", "📍 Destinos", "🌐 Tráfico y conversión"]
)

# --------------------------------------------------------------------------- #
# 1. Estado del negocio
# --------------------------------------------------------------------------- #
with tab_negocio:
    resumen = q(
        f"""
        WITH f AS ({RESERVAS_FILTRADAS})
        SELECT
            SUM(importe_eur) FILTER (WHERE estado = 'confirmada')                 AS venta,
            COUNT(*)         FILTER (WHERE estado = 'confirmada')                 AS n_confirmada,
            SUM(importe_eur) FILTER (WHERE estado = 'cancelada')                  AS cancelado,
            COUNT(*)         FILTER (WHERE estado = 'cancelada')                  AS n_cancelada,
            SUM(importe_eur) FILTER (WHERE estado = 'pendiente')                  AS pendiente,
            AVG(importe_eur) FILTER (WHERE estado = 'confirmada' AND importe_eur > 0) AS ticket_medio
        FROM f
        """,
        P,
    ).iloc[0]

    resumen_prev = q(
        f"""
        WITH f AS ({RESERVAS_FILTRADAS})
        SELECT
            SUM(importe_eur) FILTER (WHERE estado = 'confirmada') AS venta,
            COUNT(*)         FILTER (WHERE estado = 'confirmada') AS n_confirmada
        FROM f
        """,
        Pprev,
    ).iloc[0]

    tasa_canc = (
        100 * resumen.n_cancelada / (resumen.n_confirmada + resumen.n_cancelada)
        if (resumen.n_confirmada or resumen.n_cancelada)
        else 0
    )

    d_venta = kpi_delta(resumen.venta or 0, resumen_prev.venta) if comparar else None
    d_n = kpi_delta(resumen.n_confirmada or 0, resumen_prev.n_confirmada) if comparar else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Venta confirmada", EUR(resumen.venta or 0), d_venta)
    c2.metric("Reservas confirmadas", f"{int(resumen.n_confirmada or 0):,}".replace(",", "."), d_n)
    c3.metric("Ingreso perdido (cancelación)", EUR(resumen.cancelado or 0))
    c4.metric("Tasa de cancelación", f"{tasa_canc:.1f} %")
    c5.metric("Ticket medio (de pago)", EUR(resumen.ticket_medio or 0))

    st.divider()
    col_a, col_b = st.columns([3, 2])

    serie = q(
        f"""
        WITH f AS ({RESERVAS_FILTRADAS})
        SELECT {trunc('fecha_reserva', granularidad)}::date AS periodo,
               estado,
               SUM(importe_eur) AS importe,
               COUNT(*)         AS reservas
        FROM f
        GROUP BY 1, 2 ORDER BY 1
        """,
        P,
    )
    with col_a:
        st.subheader("Importe por estado")
        if serie.empty:
            st.info("Sin reservas en el periodo seleccionado.")
        else:
            chart = (
                alt.Chart(serie)
                .mark_bar()
                .encode(
                    x=alt.X("periodo:T", title=None),
                    y=alt.Y("importe:Q", title="€", stack=True),
                    color=alt.Color(
                        "estado:N",
                        scale=alt.Scale(
                            domain=["confirmada", "pendiente", "cancelada"],
                            range=["#0c6a5b", "#c9a227", "#b0451f"],
                        ),
                        title="Estado",
                    ),
                    tooltip=["periodo:T", "estado:N", alt.Tooltip("importe:Q", format=",.0f"), "reservas:Q"],
                )
                .properties(height=320)
            )
            st.altair_chart(chart, width="stretch")

    with col_b:
        st.subheader("Tasa de cancelación")
        serie_canc = q(
            f"""
            WITH f AS ({RESERVAS_FILTRADAS})
            SELECT {trunc('fecha_reserva', granularidad)}::date AS periodo,
                   100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada')
                       / NULLIF(COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')), 0) AS pct_cancelacion
            FROM f
            GROUP BY 1
            HAVING COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')) >= 15
            ORDER BY 1
            """,
            P,
        )
        if serie_canc.empty:
            st.info("Sin datos.")
        else:
            linea = (
                alt.Chart(serie_canc)
                .mark_line(point=True, color="#b0451f")
                .encode(
                    x=alt.X("periodo:T", title=None),
                    y=alt.Y("pct_cancelacion:Q", title="%"),
                    tooltip=["periodo:T", alt.Tooltip("pct_cancelacion:Q", format=".1f")],
                )
                .properties(height=320)
            )
            st.altair_chart(linea, width="stretch")

    st.subheader("Cancelación por antelación y por canal")
    col_c, col_d = st.columns(2)
    with col_c:
        lead = q(
            f"""
            WITH f AS ({RESERVAS_FILTRADAS})
            SELECT CASE WHEN date_diff('day', fecha_reserva::date, fecha_actividad) < 0 THEN 'negativo'
                        WHEN date_diff('day', fecha_reserva::date, fecha_actividad) <= 7  THEN '0-7 días'
                        WHEN date_diff('day', fecha_reserva::date, fecha_actividad) <= 30 THEN '8-30 días'
                        WHEN date_diff('day', fecha_reserva::date, fecha_actividad) <= 90 THEN '31-90 días'
                        ELSE '90+ días' END AS antelacion,
                   100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada')
                       / NULLIF(COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')), 0) AS pct_cancelacion,
                   COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')) AS reservas
            FROM f GROUP BY 1
            """,
            P,
        )
        orden = ["negativo", "0-7 días", "8-30 días", "31-90 días", "90+ días"]
        st.altair_chart(
            alt.Chart(lead).mark_bar(color="#b0451f").encode(
                x=alt.X("antelacion:N", sort=orden, title=None),
                y=alt.Y("pct_cancelacion:Q", title="% cancelación"),
                tooltip=["antelacion:N", alt.Tooltip("pct_cancelacion:Q", format=".1f"), "reservas:Q"],
            ).properties(height=260),
            width="stretch",
        )
    with col_d:
        canc_canal = q(
            f"""
            WITH f AS ({RESERVAS_FILTRADAS})
            SELECT canal,
                   100.0 * COUNT(*) FILTER (WHERE estado = 'cancelada')
                       / NULLIF(COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')), 0) AS pct_cancelacion,
                   COUNT(*) FILTER (WHERE estado IN ('confirmada', 'cancelada')) AS reservas
            FROM f GROUP BY 1 ORDER BY pct_cancelacion DESC
            """,
            P,
        )
        st.altair_chart(
            alt.Chart(canc_canal).mark_bar(color="#b0451f").encode(
                x=alt.X("pct_cancelacion:Q", title="% cancelación"),
                y=alt.Y("canal:N", sort="-x", title=None),
                tooltip=["canal:N", alt.Tooltip("pct_cancelacion:Q", format=".1f"), "reservas:Q"],
            ).properties(height=260),
            width="stretch",
        )

    st.caption(
        "**Venta** = importe de reservas en estado *confirmada* (dinero comprometido, "
        "fuente de verdad = `reservas.estado`). Free tours (0 €) cuentan en volumen, no en importe."
    )

# --------------------------------------------------------------------------- #
# 2. Repetición  (cohorte = primera reserva confirmada en el periodo)
# --------------------------------------------------------------------------- #
with tab_repeticion:
    st.info(
        "El rango de fechas define la **cohorte**: clientes cuya *primera* reserva confirmada "
        "cae dentro del periodo. Las 2 últimas cohortes trimestrales están censuradas "
        "(poco tiempo para repetir) — interpreta con cautela los meses más recientes."
    )

    # CTEs (sin la palabra WITH, para poder anteponer otros CTE)
    COHORTE_CTES = f"""
        primera AS (
            SELECT r.user_id, r.canal, r.campana, r.importe_eur, r.tour_id, t.destino,
                   MIN(r.fecha_reserva) OVER (PARTITION BY r.user_id) AS f1
            FROM reservas r JOIN tours t ON r.tour_id = t.tour_id
            WHERE r.estado = 'confirmada'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY r.user_id ORDER BY r.fecha_reserva) = 1
        ),
        recurrencia AS (
            SELECT user_id, COUNT(*) AS n FROM reservas WHERE estado = 'confirmada' GROUP BY 1
        ),
        base AS (
            SELECT p.*, rec.n AS num_reservas, (rec.n >= 2) AS recurrente
            FROM primera p JOIN recurrencia rec USING (user_id)
            WHERE p.f1::date BETWEEN ? AND ?
              AND p.canal IN {canal_sql}
              AND p.destino IN {destino_sql}
        )
    """
    COHORTE = f"WITH {COHORTE_CTES} "

    glob = q(COHORTE + "SELECT COUNT(*) clientes, AVG(recurrente::int) pct, AVG(num_reservas) media FROM base", P).iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Clientes en la cohorte", f"{int(glob.clientes or 0):,}".replace(",", "."))
    c2.metric("Tasa de repetición", f"{100 * (glob.pct or 0):.1f} %")
    c3.metric("Reservas por cliente", f"{glob.media or 0:.2f}")

    st.divider()

    def barras_factor(campo: str, etiqueta: str, expr: str | None = None):
        col = expr or campo
        df = q(
            COHORTE
            + f"""
            SELECT {col} AS factor, COUNT(*) AS clientes, AVG(recurrente::int) AS pct_retencion
            FROM base GROUP BY 1 HAVING COUNT(*) >= 20 ORDER BY pct_retencion DESC
            """,
            P,
        )
        if df.empty:
            st.info(f"Sin datos suficientes para «{etiqueta}» en este filtro.")
            return
        df["pct_retencion"] *= 100
        st.altair_chart(
            alt.Chart(df).mark_bar(color="#0c6a5b").encode(
                x=alt.X("pct_retencion:Q", title="% que repite"),
                y=alt.Y("factor:N", sort="-x", title=etiqueta),
                tooltip=[alt.Tooltip("factor:N", title=etiqueta),
                         alt.Tooltip("pct_retencion:Q", format=".1f"), "clientes:Q"],
            ).properties(height=max(140, 34 * len(df))),
            width="stretch",
        )
        st.caption(f"Solo grupos con ≥ 20 clientes. n total = {int(df.clientes.sum()):,}".replace(",", "."))

    colL, colR = st.columns(2)
    with colL:
        st.subheader("Según la primera reserva fue free o de pago")
        barras_factor("tipo", "Primera reserva",
                      expr="CASE WHEN importe_eur = 0 THEN 'free tour' ELSE 'de pago' END")
        st.subheader("Por canal de entrada")
        barras_factor("canal", "Canal")
    with colR:
        st.subheader("Por campaña de entrada")
        barras_factor("campana", "Campaña",
                      expr="COALESCE(campana, 'Sin campaña')")
        st.subheader("Por destino de entrada")
        barras_factor("destino", "Destino")

    st.subheader("Por dispositivo habitual del cliente")
    disp = q(
        f"""
        WITH dh AS (
            SELECT user_id, device
            FROM ga_eventos
            WHERE user_id IS NOT NULL AND NOT es_bot
            GROUP BY user_id, device
            QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY COUNT(DISTINCT session_id) DESC) = 1
        ),
        {COHORTE_CTES}
        SELECT dh.device AS factor, COUNT(*) AS clientes, 100.0 * AVG(base.recurrente::int) AS pct_retencion
        FROM base JOIN dh USING (user_id)
        GROUP BY 1 ORDER BY pct_retencion DESC
        """,
        P,
    )
    if not disp.empty:
        st.altair_chart(
            alt.Chart(disp).mark_bar(color="#5a6472").encode(
                x=alt.X("pct_retencion:Q", title="% que repite"),
                y=alt.Y("factor:N", sort="-x", title="Dispositivo"),
                tooltip=["factor:N", alt.Tooltip("pct_retencion:Q", format=".1f"), "clientes:Q"],
            ).properties(height=160),
            width="stretch",
        )
    st.caption(
        "**Cliente recurrente** = ≥ 2 reservas confirmadas. Ojo: ~la mitad de las segundas "
        "reservas ocurren en < 14 días (mismo viaje), no son recompra real."
    )

# --------------------------------------------------------------------------- #
# 3. Destinos
# --------------------------------------------------------------------------- #
with tab_destinos:
    acogida = q(
        f"""
        WITH f AS ({RESERVAS_FILTRADAS})
        SELECT destino,
               COUNT(*) FILTER (WHERE estado = 'confirmada')            AS reservas,
               SUM(importe_eur) FILTER (WHERE estado = 'confirmada')    AS revenue,
               AVG(importe_eur) FILTER (WHERE estado = 'confirmada' AND importe_eur > 0) AS ticket_medio,
               AVG(personas)    FILTER (WHERE estado = 'confirmada')    AS personas_medias
        FROM f GROUP BY 1 ORDER BY reservas DESC
        """,
        P,
    )
    retencion = q(
        COHORTE + "SELECT destino, COUNT(*) AS clientes, 100.0 * AVG(recurrente::int) AS pct_retencion FROM base GROUP BY 1",
        P,
    )
    tabla = acogida.merge(retencion, on="destino", how="left")

    colL, colR = st.columns(2)
    with colL:
        st.subheader("Acogida — volumen de reservas confirmadas")
        st.altair_chart(
            alt.Chart(acogida).mark_bar(color="#0c6a5b").encode(
                x=alt.X("reservas:Q", title="Reservas"),
                y=alt.Y("destino:N", sort="-x", title=None),
                tooltip=["destino:N", "reservas:Q", alt.Tooltip("revenue:Q", format=",.0f")],
            ).properties(height=380),
            width="stretch",
        )
    with colR:
        st.subheader("Retención por destino de entrada (cohorte)")
        if retencion.empty:
            st.info("Sin cohorte en el periodo.")
        else:
            st.altair_chart(
                alt.Chart(retencion).mark_bar(color="#0c6a5b").encode(
                    x=alt.X("pct_retencion:Q", title="% que repite"),
                    y=alt.Y("destino:N", sort="-x", title=None),
                    tooltip=["destino:N", alt.Tooltip("pct_retencion:Q", format=".1f"), "clientes:Q"],
                ).properties(height=380),
                width="stretch",
            )

    st.subheader("Detalle por destino")
    st.dataframe(
        tabla.rename(columns={
            "destino": "Destino", "reservas": "Reservas", "revenue": "Revenue €",
            "ticket_medio": "Ticket medio €", "personas_medias": "Personas/reserva",
            "clientes": "Clientes cohorte", "pct_retencion": "% retención",
        }).style.format({
            "Revenue €": "{:,.0f}", "Ticket medio €": "{:,.1f}",
            "Personas/reserva": "{:.2f}", "% retención": "{:.1f}",
        }),
        width="stretch",
        hide_index=True,
    )
    st.caption("La retención usa la cohorte del periodo; la acogida usa todas las reservas del periodo.")

# --------------------------------------------------------------------------- #
# 4. Tráfico y conversión
# --------------------------------------------------------------------------- #
with tab_trafico:
    st.caption(
        "Filtro por `event_date`. Tráfico de bot excluido. La conversión solo es medible "
        "en sesiones identificadas (el evento *purchase* no se dispara sin sesión iniciada)."
    )

    ses = q(
        f"""
        WITH s AS (
            SELECT session_id,
                   {trunc('MIN(event_date)', granularidad)}::date AS periodo,
                   MAX((user_id_propagado IS NOT NULL)::int) AS ident,
                   MAX((event_name = 'view_item')::int)      AS vi,
                   MAX((event_name = 'begin_checkout')::int) AS bc,
                   MAX((event_name = 'purchase')::int)       AS pu,
                   ANY_VALUE(device) AS device
            FROM ga_eventos
            WHERE NOT es_bot AND event_date::date BETWEEN ? AND ?
            GROUP BY session_id
        )
        SELECT * FROM s
        """,
        P,
    )

    if ses.empty:
        st.info("Sin sesiones en el periodo seleccionado.")
    else:
        total_ses = len(ses)
        ident = int(ses.ident.sum())
        conv = int(ses.pu.sum())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sesiones", f"{total_ses:,}".replace(",", "."))
        c2.metric("Identificadas", f"{100 * ident / total_ses:.1f} %")
        c3.metric("Conversión (sesiones ident.)", f"{100 * conv / ident:.1f} %" if ident else "—")
        c4.metric("Compras (evento purchase)", f"{conv:,}".replace(",", "."))

        st.divider()
        colL, colR = st.columns(2)
        with colL:
            st.subheader("Sesiones por periodo")
            serie_ses = (
                ses.assign(tipo=lambda d: d.ident.map({1: "identificada", 0: "anónima"}))
                .groupby(["periodo", "tipo"], as_index=False)
                .size()
                .rename(columns={"size": "sesiones"})
            )
            st.altair_chart(
                alt.Chart(serie_ses).mark_bar().encode(
                    x=alt.X("periodo:T", title=None),
                    y=alt.Y("sesiones:Q", stack=True),
                    color=alt.Color("tipo:N", scale=alt.Scale(
                        domain=["identificada", "anónima"], range=["#0c6a5b", "#c9c3b4"])),
                    tooltip=["periodo:T", "tipo:N", "sesiones:Q"],
                ).properties(height=300),
                width="stretch",
            )
        with colR:
            st.subheader("Conversión por dispositivo")
            dev = (
                ses.groupby("device", as_index=False)
                .agg(sesiones=("session_id", "count"), compras=("pu", "sum"))
                .assign(pct_conv=lambda d: 100 * d.compras / d.sesiones)
            )
            st.altair_chart(
                alt.Chart(dev).mark_bar(color="#0c6a5b").encode(
                    x=alt.X("pct_conv:Q", title="% sesiones con compra"),
                    y=alt.Y("device:N", sort="-x", title=None),
                    tooltip=["device:N", alt.Tooltip("pct_conv:Q", format=".2f"), "sesiones:Q"],
                ).properties(height=300),
                width="stretch",
            )

        st.subheader("Embudo por tipo de sesión")
        emb = pd.DataFrame({
            "etapa": ["view_item", "begin_checkout", "purchase"] * 2,
            "tipo": ["identificada"] * 3 + ["anónima"] * 3,
            "pct": [
                100 * ses.loc[ses.ident == 1, c].mean() for c in ["vi", "bc", "pu"]
            ] + [
                100 * ses.loc[ses.ident == 0, c].mean() for c in ["vi", "bc", "pu"]
            ],
        })
        st.altair_chart(
            alt.Chart(emb).mark_bar().encode(
                x=alt.X("etapa:N", sort=["view_item", "begin_checkout", "purchase"], title=None),
                y=alt.Y("pct:Q", title="% de sesiones"),
                color=alt.Color("tipo:N", scale=alt.Scale(
                    domain=["identificada", "anónima"], range=["#0c6a5b", "#c9c3b4"])),
                xOffset="tipo:N",
                tooltip=["etapa:N", "tipo:N", alt.Tooltip("pct:Q", format=".1f")],
            ).properties(height=280),
            width="stretch",
        )
