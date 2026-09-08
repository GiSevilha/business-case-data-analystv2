"""Informe COMEX: ejecuta todas las consultas de negocio sobre la base de datos
limpia, agrupadas por las tres preguntas del comité. Uso: python src/informe.py

Las cifras aquí son las que sostienen el memo (memo/memo_comex.html).
"""
import duckdb

from metricas import (
    # Pregunta 1 — Repetición
    recompra_global,
    recompra_por_cohorte,
    recompra_trip_stacking,
    valor_cliente_por_recompra,
    recompra_por_canal,
    recompra_canal_estratificado_por_free,
    recompra_canal_estandarizada_destino,
    recompra_por_free_tour,
    recompra_por_destino,
    recompra_factores_sin_efecto,
    cancelacion_no_es_churn,
    # Pregunta 2 — Destinos
    acogida_por_destino,
    acogida_demanda_vs_conversion,
    acogida_ticket_por_destino,
    retencion_por_destino_estandarizada_canal,
    # Pregunta 3 — Estado del negocio
    resumen_estado_negocio,
    venta_por_semestre,
    sensibilidad_definicion_venta,
    cancelacion_por_lead_time,
    cancelacion_por_canal,
    reservas_con_proveedor_de_baja,
    # Apoyo — identidad y conversión
    conocidos_vs_desconocidos,
    funnel_por_tipo_sesion,
    embudo_por_device,
)

con = duckdb.connect("data/processed/civitatis.duckdb", read_only=True)

BLOQUES = {
    "PREGUNTA 1 - Repeticion: que factores explican que un cliente vuelva a comprar": [
        ("Recompra global (base madura >=180d)", recompra_global),
        ("Recompra por cohorte trimestral (control de censura)", recompra_por_cohorte),
        ("Trip-stacking vs recompra real (por que la definicion exige disfrutar la 1a)", recompra_trip_stacking),
        ("Valor del cliente segun recompra o no", valor_cliente_por_recompra),
        ("Factor 1 - Canal (1a de pago, sin Email)", recompra_por_canal),
        ("  Canal estratificado por free/pago (no es espejismo del free tour)", recompra_canal_estratificado_por_free),
        ("  Canal estandarizado al mix de destino (no es espejismo del destino)", recompra_canal_estandarizada_destino),
        ("Factor 2 - Free tour de entrada (en negativo)", recompra_por_free_tour),
        ("Factor 3 - Destino de la 1a experiencia", recompra_por_destino),
        ("Cancelacion NO es churn", cancelacion_no_es_churn),
    ],
    "PREGUNTA 2 - Destinos: acogida y retencion": [
        ("Acogida por destino (volumen e importe)", acogida_por_destino),
        ("Acogida = demanda x conversion (interes view_item vs reservas)", acogida_demanda_vs_conversion),
        ("Ticket medio por destino (Paris: precio/persona, no grupos)", acogida_ticket_por_destino),
        ("Retencion por destino estandarizada al mix de canal", retencion_por_destino_estandarizada_canal),
    ],
    "PREGUNTA 3 - Estado del negocio: cuanto hemos vendido realmente": [
        ("Resumen del estado del negocio", resumen_estado_negocio),
        ("Venta por semestre (crecimiento +68%)", venta_por_semestre),
        ("Sensibilidad de la definicion de venta", sensibilidad_definicion_venta),
        ("Cancelacion por antelacion (lead time)", cancelacion_por_lead_time),
        ("Cancelacion por canal", cancelacion_por_canal),
        ("Reservas confirmadas con proveedor de baja (riesgo operativo)", reservas_con_proveedor_de_baja),
    ],
    "PREGUNTAS DE APOYO - identidad y conversion": [
        ("Conocidos vs desconocidos (sesiones)", conocidos_vs_desconocidos),
        ("Funnel por tipo de sesion (conversion no medible en anonimas)", funnel_por_tipo_sesion),
        ("Embudo por dispositivo (el 2,3x de movil es artefacto del login)", embudo_por_device),
    ],
}

for titulo, consultas in BLOQUES.items():
    print("\n" + "=" * 90 + "\n" + titulo + "\n" + "=" * 90)
    for nombre, fn in consultas:
        print(f"\n--- {nombre} ---")
        resultado = fn(con)
        if isinstance(resultado, dict):  # recompra_factores_sin_efecto devuelve varios DataFrames
            for sub, df in resultado.items():
                print(f"  [{sub}]")
                print(df.to_string(index=False))
        else:
            print(resultado.df().to_string(index=False))

# El bloque de "factores sin efecto" se imprime aparte por devolver varios DataFrames
print("\n" + "=" * 90 + "\nPREGUNTA 1 (cont.) - Factores que NO explican la recompra\n" + "=" * 90)
for sub, df in recompra_factores_sin_efecto(con).items():
    print(f"\n--- {sub} ---")
    print(df.to_string(index=False))
