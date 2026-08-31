"""Informe COMEX: ejecuta todas las metricas y consultas de contraste de
hipotesis sobre la base de datos limpia. Uso: python src/informe.py"""
import duckdb
from metricas import (
    resumen_estado_negocio,
    acogida_por_destino,
    acogida_ticket_por_destino,
    retencion_por_canal_entrada,
    retencion_por_campana_entrada,
    retencion_por_destino_entrada,
    retencion_por_dispositivo_habitual,
    retencion_por_free_tour_entrada,
    retencion_canal_controlado_por_free,
    retencion_por_canal_ic95,
    retencion_por_campana_ic95,
    retencion_por_destino_controlada_canal,
    repeticion_ventana_observacion,
    repeticion_trip_stacking,
    funnel_por_tipo_sesion,
    conversion_por_device,
    conocidos_vs_desconocidos,
    cancelacion_por_lead_time,
    cancelacion_por_canal,
    sensibilidad_definicion_venta,
    revenue_por_tipo_cliente,
    ltv_free_vs_pago_entrada,
    reservas_con_proveedor_de_baja,
)

con = duckdb.connect("data/processed/civitatis.duckdb", read_only=True)

BLOQUES = {
    "PREGUNTA 3 - Estado del negocio": [
        ("Resumen estado del negocio", resumen_estado_negocio),
        ("Sensibilidad de la definicion de venta", sensibilidad_definicion_venta),
        ("Cancelacion por antelacion (lead time)", cancelacion_por_lead_time),
        ("Cancelacion por canal", cancelacion_por_canal),
        ("Reservas confirmadas con proveedor de baja", reservas_con_proveedor_de_baja),
    ],
    "PREGUNTA 1 - Repeticion": [
        ("Revenue por tipo de cliente (por que importa)", revenue_por_tipo_cliente),
        ("Repeticion dentro de 180d por cohorte (censura)", repeticion_ventana_observacion),
        ("Trip-stacking vs recompra real", repeticion_trip_stacking),
        ("Retencion por free tour de entrada", retencion_por_free_tour_entrada),
        ("Retencion por canal (IC95)", retencion_por_canal_ic95),
        ("Retencion por canal controlando por free/pago", retencion_canal_controlado_por_free),
        ("Retencion por campana (IC95)", retencion_por_campana_ic95),
        ("Retencion por dispositivo habitual", retencion_por_dispositivo_habitual),
        ("LTV entrada free vs de pago", ltv_free_vs_pago_entrada),
    ],
    "PREGUNTA 2 - Destinos": [
        ("Acogida por destino", acogida_por_destino),
        ("Acogida + ticket medio por destino", acogida_ticket_por_destino),
        ("Retencion por destino de entrada", retencion_por_destino_entrada),
        ("Retencion por destino controlada por canal", retencion_por_destino_controlada_canal),
    ],
    "PREGUNTAS DE APOYO": [
        ("Conocidos vs desconocidos (sesiones)", conocidos_vs_desconocidos),
        ("Funnel por tipo de sesion", funnel_por_tipo_sesion),
        ("Conversion por dispositivo", conversion_por_device),
    ],
}

for titulo, consultas in BLOQUES.items():
    print("\n" + "=" * 78 + "\n" + titulo + "\n" + "=" * 78)
    for nombre, fn in consultas:
        print(f"\n--- {nombre} ---")
        print(fn(con).df().to_string(index=False))
