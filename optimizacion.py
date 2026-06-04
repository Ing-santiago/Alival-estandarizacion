"""
Módulo de Optimización para Sistema de Estandarización de Leche
Contiene la lógica de programación lineal para optimización de mezclas lácteas.

Cambios v2:
  - "leche desnatada" → "leche descremada" en toda la nomenclatura
  - Nueva función: optimizar_descremado() para proceso de separación centrífuga
"""

import pulp
import pandas as pd

# ─── Constantes del clarificador ────────────────────────────────────────────
CLARIFIER_RATE_L_H = 800   # L de crema por hora
FAT_SKIM_PCT       = 0.05  # % grasa residual en leche descremada

FAT_LECHE_MIN = 0.1
FAT_LECHE_MAX = 6.5
FAT_CREMA_MIN = 20.0
FAT_CREMA_MAX = 55.0


# ─── Helpers de descremado ───────────────────────────────────────────────────

def calcular_crema(
    vol_leche_L: float,
    fat_leche_pct: float,
    fat_crema_pct: float,
    fat_descremada_pct: float = FAT_SKIM_PCT,
) -> dict:
    """
    Cálculo hacia adelante: Leche cruda → Crema obtenida
    (Balance de materia grasa)

    Parámetros
    ----------
    vol_leche_L       : Volumen de leche cruda disponible (L)
    fat_leche_pct     : % grasa de la leche cruda  (0.1 – 6.5)
    fat_crema_pct     : % grasa objetivo en la crema (20 – 55)
    fat_descremada_pct: % grasa residual en leche descremada (default 0.05)

    Retorna dict con: vol_crema_L, vol_descremada_L, tiempo_h, rendimiento_pct
    """
    if not (FAT_LECHE_MIN <= fat_leche_pct <= FAT_LECHE_MAX):
        raise ValueError(
            f"% grasa leche debe estar entre {FAT_LECHE_MIN}% y {FAT_LECHE_MAX}%. "
            f"Valor recibido: {fat_leche_pct}%"
        )
    if not (FAT_CREMA_MIN <= fat_crema_pct <= FAT_CREMA_MAX):
        raise ValueError(
            f"% grasa crema debe estar entre {FAT_CREMA_MIN}% y {FAT_CREMA_MAX}%. "
            f"Valor recibido: {fat_crema_pct}%"
        )
    if fat_crema_pct <= fat_leche_pct:
        raise ValueError(
            f"El % grasa de la crema ({fat_crema_pct}%) debe ser mayor "
            f"que el de la leche ({fat_leche_pct}%)."
        )

    Gm = fat_leche_pct      / 100
    Gc = fat_crema_pct      / 100
    Gs = fat_descremada_pct / 100

    vol_crema_L      = vol_leche_L * (Gm - Gs) / (Gc - Gs)
    vol_descremada_L = vol_leche_L - vol_crema_L
    tiempo_h         = vol_crema_L / CLARIFIER_RATE_L_H
    rendimiento_pct  = (vol_crema_L / vol_leche_L) * 100

    return {
        "modo"               : "Leche → Crema",
        "vol_leche_L"        : round(vol_leche_L,       2),
        "fat_leche_pct"      : round(fat_leche_pct,     2),
        "vol_crema_L"        : round(vol_crema_L,        2),
        "fat_crema_pct"      : round(fat_crema_pct,      2),
        "vol_descremada_L"   : round(vol_descremada_L,   2),
        "fat_descremada_pct" : round(fat_descremada_pct, 2),
        "tiempo_h"           : round(tiempo_h,            4),
        "rendimiento_pct"    : round(rendimiento_pct,     4),
    }


def calcular_leche(
    vol_crema_L: float,
    fat_crema_pct: float,
    fat_leche_pct: float,
    fat_descremada_pct: float = FAT_SKIM_PCT,
) -> dict:
    """
    Cálculo hacia atrás: Crema deseada → Leche cruda necesaria

    Parámetros
    ----------
    vol_crema_L       : Volumen de crema requerido (L)
    fat_crema_pct     : % grasa objetivo en la crema (20 – 55)
    fat_leche_pct     : % grasa de la leche cruda disponible (0.1 – 6.5)
    fat_descremada_pct: % grasa residual en leche descremada (default 0.05)

    Retorna dict con: vol_leche_L, vol_descremada_L, tiempo_h, rendimiento_pct
    """
    if not (FAT_LECHE_MIN <= fat_leche_pct <= FAT_LECHE_MAX):
        raise ValueError(
            f"% grasa leche debe estar entre {FAT_LECHE_MIN}% y {FAT_LECHE_MAX}%. "
            f"Valor recibido: {fat_leche_pct}%"
        )
    if not (FAT_CREMA_MIN <= fat_crema_pct <= FAT_CREMA_MAX):
        raise ValueError(
            f"% grasa crema debe estar entre {FAT_CREMA_MIN}% y {FAT_CREMA_MAX}%. "
            f"Valor recibido: {fat_crema_pct}%"
        )
    if fat_crema_pct <= fat_leche_pct:
        raise ValueError(
            f"El % grasa de la crema ({fat_crema_pct}%) debe ser mayor "
            f"que el de la leche ({fat_leche_pct}%)."
        )

    Gc = fat_crema_pct      / 100
    Gm = fat_leche_pct      / 100
    Gs = fat_descremada_pct / 100

    vol_leche_L      = vol_crema_L * (Gc - Gs) / (Gm - Gs)
    vol_descremada_L = vol_leche_L - vol_crema_L
    tiempo_h         = vol_crema_L / CLARIFIER_RATE_L_H
    rendimiento_pct  = (vol_crema_L / vol_leche_L) * 100

    return {
        "modo"               : "Crema → Leche",
        "vol_leche_L"        : round(vol_leche_L,        2),
        "fat_leche_pct"      : round(fat_leche_pct,      2),
        "vol_crema_L"        : round(vol_crema_L,         2),
        "fat_crema_pct"      : round(fat_crema_pct,       2),
        "vol_descremada_L"   : round(vol_descremada_L,    2),
        "fat_descremada_pct" : round(fat_descremada_pct,  2),
        "tiempo_h"           : round(tiempo_h,             4),
        "rendimiento_pct"    : round(rendimiento_pct,      4),
    }


def _fmt_tiempo(horas: float) -> str:
    h = int(horas)
    m = round((horas - h) * 60)
    if m == 0:
        return f"{h} h"
    if h == 0:
        return f"{m} min"
    return f"{h} h {m} min"


# ─── Motor de optimización de mezclas ────────────────────────────────────────

def optimizar_mezcla(
    df,
    volumen_obj_L,
    g_min, g_max,
    d_min, d_max,
    c_min, c_max,
    a_min, a_max,
    aditivos=None,
):
    """
    Optimiza la mezcla de tanques para cumplir con los rangos objetivo.

    Args:
        df            : DataFrame con datos de tanques
        volumen_obj_L : Volumen objetivo en litros
        g_min, g_max  : Rangos de grasa (%)
        d_min, d_max  : Rangos de densidad (kg/L)
        c_min, c_max  : Rangos de crioscopia (°C)
        a_min, a_max  : Rangos de acidez (°D)
        aditivos      : DataFrame opcional con columnas:
                        nombre, costo_kg, limite_max_kg,
                        grasa_kg,densidad_kg,crio_kg, acidez_kg

    Returns:
        dict con estado, solución y métricas
    """
    densidad_estimada    = (d_min + d_max) / 2
    masa_objetivo_Kg     = volumen_obj_L * densidad_estimada
    masa_total_disponible = df["Masa_Disponible_Kg"].sum()

    if masa_objetivo_Kg > masa_total_disponible * 0.99:
        return {
            "status"           : "Infeasible",
            "error"            : "Insuficiente materia prima",
            "masa_requerida"   : masa_objetivo_Kg,
            "masa_disponible"  : masa_total_disponible,
        }

    # ── Modelo ──────────────────────────────────────────────────────────────
    model = pulp.LpProblem("Estandarizacion_Leche_Masa", pulp.LpMinimize)

    x_kg = {
        i: pulp.LpVariable(
            f"Kg_Tanque_{i}", lowBound=0,
            upBound=df.loc[i, "Masa_Disponible_Kg"]
        )
        for i in df.index
    }
    y_bin = {
        i: pulp.LpVariable(f"Usa_Tanque_{i}", cat="Binary")
        for i in df.index
    }
    slack_min_acidez = pulp.LpVariable("slack_min_acidez", lowBound=0)
    slack_max_acidez = pulp.LpVariable("slack_max_acidez", lowBound=0)

    z_kg = {}
    if aditivos is not None and len(aditivos) > 0:
        for j in aditivos.index:
            z_kg[j] = pulp.LpVariable(
                f"Kg_Ad_{aditivos.loc[j, 'nombre']}",
                lowBound=0,
                upBound=float(aditivos.loc[j, "limite_max_kg"]),
            )

    # ── Función objetivo ─────────────────────────────────────────────────────
    COSTO_CIP_POR_TANQUE = 5.0
    PENALTY_ACIDEZ       = 50.0

    costo_leche    = pulp.lpSum([x_kg[i] * df.loc[i, "Costo_Por_Kg"] for i in df.index])
    costo_limpiezas = pulp.lpSum([y_bin[i] * COSTO_CIP_POR_TANQUE for i in df.index])
    uso_grasa      = pulp.lpSum([
        x_kg[i] * (df.loc[i, "Grasa"] / 100.0) * df.loc[i, "Costo_Por_Kg"] * 0.1
        for i in df.index
    ])
    penalizacion_acidez = PENALTY_ACIDEZ * (slack_min_acidez + slack_max_acidez)

    costo_total_obj = costo_leche + costo_limpiezas + uso_grasa + penalizacion_acidez
    if z_kg:
        costo_aditivos = pulp.lpSum([
            z_kg[j] * float(aditivos.loc[j, "costo_kg"]) for j in z_kg
        ])
        model += costo_total_obj + costo_aditivos, "Costo_Total_Operacion"
    else:
        model += costo_total_obj, "Costo_Total_Operacion"

    # ── Restricciones ────────────────────────────────────────────────────────
    masa_tanques = pulp.lpSum([x_kg[i] for i in df.index])
    masa_ads     = pulp.lpSum([z_kg[j] for j in z_kg]) if z_kg else 0
    model += masa_tanques + masa_ads == masa_objetivo_Kg, "Meta_Masa_Total"

    # Grasa — suma(x_i * G_i) en [g_min%, g_max%] de masa total
    grasa_tanques = pulp.lpSum([x_kg[i] * (df.loc[i, "Grasa"] / 100.0) for i in df.index])
    grasa_ads     = pulp.lpSum([z_kg[j] * float(aditivos.loc[j, "grasa_kg"]) for j in z_kg]) if z_kg else 0
    model += grasa_tanques + grasa_ads >= masa_objetivo_Kg * (g_min / 100.0), "Min_Grasa"
    model += grasa_tanques + grasa_ads <= masa_objetivo_Kg * (g_max / 100.0), "Max_Grasa"

    # Densidad — promedio ponderado solo sobre componentes con densidad > 0
    # Aditivos con densidad_kg == 0 (ej: fosfatos) no aportan al balance de densidad
    densidad_tanques = pulp.lpSum([x_kg[i] * float(df.loc[i, "Densidad"]) for i in df.index])
    if z_kg:
        ads_con_densidad = [j for j in z_kg if float(aditivos.loc[j, "densidad_kg"]) > 0]
        densidad_ads   = pulp.lpSum([z_kg[j] * float(aditivos.loc[j, "densidad_kg"]) for j in ads_con_densidad])
        masa_densidad  = masa_tanques + pulp.lpSum([z_kg[j] for j in ads_con_densidad])
    else:
        densidad_ads  = 0
        masa_densidad = masa_tanques
    model += densidad_tanques + densidad_ads >= masa_densidad * d_min, "Min_Densidad"
    model += densidad_tanques + densidad_ads <= masa_densidad * d_max, "Max_Densidad"

    # Crioscopia — suma(x_i * C_i) en [c_min, c_max] * masa total
    # crio_kg de aditivos es la contribución de crioscopia por kg (mismo esquema que leche)
    crio_tanques = pulp.lpSum([x_kg[i] * float(df.loc[i, "Crioscopia"]) for i in df.index])
    crio_ads     = pulp.lpSum([z_kg[j] * float(aditivos.loc[j, "crio_kg"]) for j in z_kg]) if z_kg else 0
    model += crio_tanques + crio_ads >= masa_objetivo_Kg * c_min, "Min_Crioscopia"
    model += crio_tanques + crio_ads <= masa_objetivo_Kg * c_max, "Max_Crioscopia"

    # Acidez (con slack para estabilidad numérica)
    acidez_tanques = pulp.lpSum([x_kg[i] * float(df.loc[i, "Acidez"]) for i in df.index])
    acidez_ads     = pulp.lpSum([z_kg[j] * float(aditivos.loc[j, "acidez_kg"]) for j in z_kg]) if z_kg else 0
    model += acidez_tanques + acidez_ads >= masa_objetivo_Kg * a_min - slack_min_acidez, "Min_Acidez"
    model += acidez_tanques + acidez_ads <= masa_objetivo_Kg * a_max + slack_max_acidez, "Max_Acidez"

    # Big-M
    M = 10_000_000
    for i in df.index:
        model += x_kg[i] <= M * y_bin[i], f"Link_Activacion_{i}"

    # ── Resolver ─────────────────────────────────────────────────────────────
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=45, threads=4)
    model.solve(solver)
    status = pulp.LpStatus[model.status]

    if status != "Optimal":
        return {"status": status, "error": "No se encontró solución factible"}

    # ── Procesar resultados ──────────────────────────────────────────────────
    resultados            = []
    masa_usada_total      = 0.0
    grasa_usada_total     = 0.0
    crio_usada_total      = 0.0
    acidez_usada_total    = 0.0
    costo_materia_prima   = 0.0
    tanques_activos       = 0

    for i in df.index:
        kg_usados = x_kg[i].value()
        if kg_usados is None or kg_usados < 0.05:
            continue
        tanques_activos += 1
        litros_usados    = kg_usados / df.loc[i, "Densidad"]
        costo_tanque     = kg_usados * df.loc[i, "Costo_Por_Kg"]

        resultados.append({
            "Tanque"          : df.loc[i, "Tanque"],
            "Litros a Bombear": round(litros_usados, 2),
            "Masa (kg)"       : round(kg_usados, 2),
            "Grasa Origen"    : f"{df.loc[i, 'Grasa']}%",
            "Costo Parcial"   : round(costo_tanque, 2),
        })
        masa_usada_total   += kg_usados
        grasa_usada_total  += kg_usados * (df.loc[i, "Grasa"] / 100.0)
        crio_usada_total   += kg_usados * df.loc[i, "Crioscopia"]
        acidez_usada_total += kg_usados * df.loc[i, "Acidez"]
        costo_materia_prima += costo_tanque

    if z_kg:
        for j in aditivos.index:
            kg_usado = z_kg[j].value()
            if kg_usado and kg_usado > 0.001:
                densidad_ad = float(aditivos.loc[j, "densidad_kg"]) if float(aditivos.loc[j, "densidad_kg"]) > 0 else 1.0

                resultados.append({
                    "Tanque"          : f"Aditivo: {aditivos.loc[j, 'nombre']}",
                    "Litros a Bombear": round(kg_usado / densidad_ad, 2),
                    "Masa (kg)"       : round(kg_usado, 2),
                    "Grasa Origen"    : f"{aditivos.loc[j, 'grasa_kg'] * 100:.2f}%",
                    "Costo Parcial"   : round(kg_usado * aditivos.loc[j, "costo_kg"], 2),
                })
                masa_usada_total    += kg_usado
                grasa_usada_total   += kg_usado * aditivos.loc[j, "grasa_kg"]
                crio_usada_total    += kg_usado * aditivos.loc[j, "crio_kg"]
                acidez_usada_total  += kg_usado * aditivos.loc[j, "acidez_kg"]
                costo_materia_prima += kg_usado * aditivos.loc[j, "costo_kg"]

    grasa_final_pct    = (grasa_usada_total / masa_usada_total) * 100 if masa_usada_total > 0 else 0.0
    crio_final         = crio_usada_total   / masa_usada_total        if masa_usada_total > 0 else 0.0
    acidez_final       = acidez_usada_total / masa_usada_total        if masa_usada_total > 0 else 0.0
    densidad_final_est = masa_usada_total   / volumen_obj_L           if volumen_obj_L    > 0 else 0.0

    slack_min_v = float(slack_min_acidez.value()) if slack_min_acidez.value() is not None else 0.0
    slack_max_v = float(slack_max_acidez.value()) if slack_max_acidez.value() is not None else 0.0

    costo_limpiezas_total = tanques_activos * COSTO_CIP_POR_TANQUE
    costo_grand_total     = costo_materia_prima + costo_limpiezas_total

    return {
        "status"    : "Optimal",
        "resultados": resultados,
        "metricas"  : {
            "volumen_final"   : float(volumen_obj_L),
            "masa_total"      : float(masa_usada_total),
            "grasa_final"     : float(grasa_final_pct),
            "grasa_total_kg"  : float(grasa_usada_total),
            "densidad_final"  : float(densidad_final_est),
            "crioscopia_final": float(crio_final),
            "acidez_final"    : float(acidez_final),
            "costo_materia_prima": float(costo_materia_prima),
            "costo_limpiezas" : float(costo_limpiezas_total),
            "costo_total"     : float(costo_grand_total),
            "tanques_activos" : int(tanques_activos),
            "slack_min_acidez": float(slack_min_v),
            "slack_max_acidez": float(slack_max_v),
            "costo_unitario"  : float(costo_grand_total / volumen_obj_L) if volumen_obj_L > 0 else 0.0,
        },
        "rangos_objetivo": {
            "grasa"     : (float(g_min), float(g_max)),
            "densidad"  : (float(d_min), float(d_max)),
            "crioscopia": (float(c_min), float(c_max)),
            "acidez"    : (float(a_min), float(a_max)),
        },
    }


# ─── Optimización específica de descremado ───────────────────────────────────

def optimizar_descremado(
    df,
    volumen_crema_obj_L: float,
    fat_crema_obj_pct: float  = 40.0,
    fat_descremada_pct: float = FAT_SKIM_PCT,
) -> dict:
    """
    Optimiza la selección de tanques para el proceso de descremado centrífugo.

    Selecciona la combinación de tanques que minimiza el costo de materia prima
    para producir el volumen de crema objetivo, aplicando balance de materia grasa.

    Args:
        df                : DataFrame con columnas: Tanque, Volumen, Grasa, Densidad,
                            Crioscopia, Acidez, Costo, Masa_Disponible_Kg, Costo_Por_Kg
        volumen_crema_obj_L: Litros de crema a producir
        fat_crema_obj_pct : % grasa objetivo en la crema (20 – 55, default 40)
        fat_descremada_pct : % grasa residual en leche descremada (default 0.05)

    Returns:
        dict con:
          status, resultados_tanques, metricas_descremado, balance_masas
    """
    if not (FAT_CREMA_MIN <= fat_crema_obj_pct <= FAT_CREMA_MAX):
        return {
            "status": "Error",
            "error" : f"% grasa crema debe estar entre {FAT_CREMA_MIN}% y {FAT_CREMA_MAX}%.",
        }
    if volumen_crema_obj_L <= 0:
        return {"status": "Error", "error": "El volumen de crema debe ser mayor a 0."}

    Gc = fat_crema_obj_pct  / 100
    Gs = fat_descremada_pct / 100

    # Para cada tanque calculamos cuánta crema puede aportar y cuánta leche necesitamos
    tanques_validos = df[df["Grasa"] / 100 > Gs].copy()
    if tanques_validos.empty:
        return {
            "status": "Infeasible",
            "error" : "Ningún tanque tiene suficiente grasa para el proceso de descremado.",
        }

    tanques_validos = tanques_validos.copy()
    tanques_validos["Fat_Frac"]         = tanques_validos["Grasa"] / 100
    tanques_validos["Crema_Max_L"]      = (
        tanques_validos["Volumen"]
        * (tanques_validos["Fat_Frac"] - Gs)
        / (Gc - Gs)
    )
    tanques_validos["Descremada_Max_L"] = tanques_validos["Volumen"] - tanques_validos["Crema_Max_L"]

    crema_total_posible = tanques_validos["Crema_Max_L"].sum()
    if volumen_crema_obj_L > crema_total_posible * 0.99:
        return {
            "status"              : "Infeasible",
            "error"               : "Volumen de crema requerido supera la capacidad disponible.",
            "crema_posible_L"     : round(crema_total_posible, 2),
            "crema_requerida_L"   : round(volumen_crema_obj_L, 2),
        }

    # ── Modelo de optimización ───────────────────────────────────────────────
    model = pulp.LpProblem("Descremado_Optimo", pulp.LpMinimize)

    # x[i] = litros de leche a procesar del tanque i
    x_vol = {
        i: pulp.LpVariable(
            f"Litros_Tanque_{i}",
            lowBound=0,
            upBound=float(tanques_validos.loc[i, "Volumen"]),
        )
        for i in tanques_validos.index
    }
    y_bin = {
        i: pulp.LpVariable(f"Usa_Tanque_{i}", cat="Binary")
        for i in tanques_validos.index
    }

    COSTO_CIP = 5.0

    costo_leche     = pulp.lpSum([
        x_vol[i] * float(tanques_validos.loc[i, "Costo"])
        for i in tanques_validos.index
    ])
    costo_limpiezas = pulp.lpSum([y_bin[i] * COSTO_CIP for i in tanques_validos.index])
    model += costo_leche + costo_limpiezas, "Costo_Total"

    # crema producida por tanque i = x_vol[i] * (Fat_i - Gs) / (Gc - Gs)
    crema_por_tanque = {
        i: x_vol[i] * float((tanques_validos.loc[i, "Fat_Frac"] - Gs) / (Gc - Gs))
        for i in tanques_validos.index
    }
    model += (
        pulp.lpSum(crema_por_tanque[i] for i in tanques_validos.index)
        == volumen_crema_obj_L,
        "Meta_Crema",
    )

    M = 10_000_000
    for i in tanques_validos.index:
        model += x_vol[i] <= M * y_bin[i], f"Link_{i}"

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=30, threads=4)
    model.solve(solver)
    status = pulp.LpStatus[model.status]

    if status != "Optimal":
        return {"status": status, "error": "No se encontró solución factible para el descremado."}

    # ── Resultados ───────────────────────────────────────────────────────────
    resultados_tanques   = []
    vol_leche_total      = 0.0
    vol_crema_total      = 0.0
    vol_descremada_total = 0.0
    grasa_crema_total    = 0.0
    costo_mp             = 0.0
    tanques_usados       = 0

    for i in tanques_validos.index:
        litros_leche = x_vol[i].value()
        if litros_leche is None or litros_leche < 0.1:
            continue
        tanques_usados   += 1
        fat_i             = float(tanques_validos.loc[i, "Fat_Frac"])
        litros_crema      = litros_leche * (fat_i - Gs) / (Gc - Gs)
        litros_descremada = litros_leche - litros_crema
        costo_tanque      = litros_leche * float(tanques_validos.loc[i, "Costo"])
        tiempo_h          = litros_crema / CLARIFIER_RATE_L_H

        resultados_tanques.append({
            "Tanque"              : tanques_validos.loc[i, "Tanque"],
            "Leche a Procesar (L)": round(litros_leche,      2),
            "Crema Obtenida (L)"  : round(litros_crema,       2),
            "Leche Descremada (L)": round(litros_descremada,  2),
            "Grasa Entrada (%)"   : round(fat_i * 100,        2),
            "Grasa Crema (%)"     : round(fat_crema_obj_pct,  2),
            "Grasa Descremada (%)": round(fat_descremada_pct, 2),
            "Tiempo Proceso (h)"  : round(tiempo_h,            2),
            "Costo Parcial ($)"   : round(costo_tanque,        2),
        })

        vol_leche_total      += litros_leche
        vol_crema_total      += litros_crema
        vol_descremada_total += litros_descremada
        grasa_crema_total    += litros_crema * Gc
        costo_mp             += costo_tanque

    tiempo_total_h        = vol_crema_total / CLARIFIER_RATE_L_H
    costo_limpiezas_total = tanques_usados * COSTO_CIP
    costo_grand_total     = costo_mp + costo_limpiezas_total
    rendimiento_pct       = (vol_crema_total / vol_leche_total * 100) if vol_leche_total > 0 else 0.0

    return {
        "status"           : "Optimal",
        "resultados_tanques": resultados_tanques,
        "metricas_descremado": {
            "vol_leche_total_L"     : round(vol_leche_total,        2),
            "vol_crema_total_L"     : round(vol_crema_total,         2),
            "vol_descremada_total_L": round(vol_descremada_total,    2),
            "fat_crema_pct"         : round(fat_crema_obj_pct,       2),
            "fat_descremada_pct"    : round(fat_descremada_pct,      2),
            "tiempo_total_h"        : round(tiempo_total_h,           4),
            "rendimiento_pct"       : round(rendimiento_pct,          4),
            "tanques_usados"        : tanques_usados,
            "costo_materia_prima"   : round(costo_mp,                 2),
            "costo_limpiezas"       : round(costo_limpiezas_total,    2),
            "costo_total"           : round(costo_grand_total,        2),
            "costo_unitario_crema"  : round(
                costo_grand_total / vol_crema_total, 4
            ) if vol_crema_total > 0 else 0.0,
        },
        "balance_masas": {
            "descripcion": (
                f"De {round(vol_leche_total, 1)} L de leche cruda "
                f"se obtienen {round(vol_crema_total, 1)} L de crema ({fat_crema_obj_pct}% grasa) "
                f"y {round(vol_descremada_total, 1)} L de leche descremada ({fat_descremada_pct}% grasa). "
                f"Tiempo estimado de clarificación: {_fmt_tiempo(tiempo_total_h)}."
            )
        },
    }
