"""
Módulo de Optimización para Sistema de Estandarización de Leche
Lógica:
  - Insumos: SOLO tanques del inventario
  - Si la densidad resultante no alcanza el rango objetivo, se añade
    automáticamente Leche Descremada en Polvo (LDP) como corrector.
  - Crioscopia y acidez se gestionan con holgura penalizada (no son causas
    de rechazo duro; el sistema reporta desviaciones en las alertas de calidad).
"""
import pulp
import pandas as pd
import math

# ── Constantes del clarificador ────────────────────────────────────────────
CLARIFIER_RATE_L_H = 800   # L de crema por hora
FAT_SKIM_PCT       = 0.05  # % grasa residual en leche descremada
FAT_LECHE_MIN = 0.1
FAT_LECHE_MAX = 6.5
FAT_CREMA_MIN = 20.0
FAT_CREMA_MAX = 55.0

# ── Propiedades de la Leche Descremada en Polvo (LDP) ─────────────────────
# Valores típicos por kg de LDP añadido a la mezcla líquida
LDP_GRASA_KG    = 0.01      # fracción grasa por kg
LDP_DENSIDAD_KG = 1.324     # densidad kg/L
LDP_CRIO_KG     = -0.594    # contribución crioscopia por kg (°C·kg)
LDP_ACIDEZ_KG   = 0.135     # contribución acidez por kg (% acidez·kg)
LDP_COSTO_KG    = 17500.0   # $/kg (configurable en main)
LDP_MAX_KG_DEFAULT = 200.0  # kg máximo permitido por lote

# ── Helpers de descremado ───────────────────────────────────────────────────

def calcular_crema(
    vol_leche_L: float,
    fat_leche_pct: float,
    fat_crema_pct: float,
    fat_descremada_pct: float = FAT_SKIM_PCT,
) -> dict:
    """Cálculo hacia adelante: Leche cruda → Crema obtenida"""
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
    Gm = fat_leche_pct / 100
    Gc = fat_crema_pct / 100
    Gs = fat_descremada_pct / 100
    vol_crema_L      = vol_leche_L * (Gm - Gs) / (Gc - Gs)
    vol_descremada_L = vol_leche_L - vol_crema_L
    tiempo_h         = vol_crema_L / CLARIFIER_RATE_L_H
    rendimiento_pct  = (vol_crema_L / vol_leche_L) * 100
    return {
        "modo": "Leche → Crema",
        "vol_leche_L": round(vol_leche_L, 2),
        "fat_leche_pct": round(fat_leche_pct, 2),
        "vol_crema_L": round(vol_crema_L, 2),
        "fat_crema_pct": round(fat_crema_pct, 2),
        "vol_descremada_L": round(vol_descremada_L, 2),
        "fat_descremada_pct": round(fat_descremada_pct, 2),
        "tiempo_h": round(tiempo_h, 4),
        "rendimiento_pct": round(rendimiento_pct, 4),
    }

def calcular_leche(
    vol_crema_L: float,
    fat_crema_pct: float,
    fat_leche_pct: float,
    fat_descremada_pct: float = FAT_SKIM_PCT,
) -> dict:
    """Cálculo hacia atrás: Crema deseada → Leche cruda necesaria"""
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
    Gc = fat_crema_pct / 100
    Gm = fat_leche_pct / 100
    Gs = fat_descremada_pct / 100
    vol_leche_L      = vol_crema_L * (Gc - Gs) / (Gm - Gs)
    vol_descremada_L = vol_leche_L - vol_crema_L
    tiempo_h         = vol_crema_L / CLARIFIER_RATE_L_H
    rendimiento_pct  = (vol_crema_L / vol_leche_L) * 100
    return {
        "modo": "Crema → Leche",
        "vol_leche_L": round(vol_leche_L, 2),
        "fat_leche_pct": round(fat_leche_pct, 2),
        "vol_crema_L": round(vol_crema_L, 2),
        "fat_crema_pct": round(fat_crema_pct, 2),
        "vol_descremada_L": round(vol_descremada_L, 2),
        "fat_descremada_pct": round(fat_descremada_pct, 2),
        "tiempo_h": round(tiempo_h, 4),
        "rendimiento_pct": round(rendimiento_pct, 4),
    }

def _fmt_tiempo(horas: float) -> str:
    h = int(horas)
    m = round((horas - h) * 60)
    if m == 0:
        return f"{h} h"
    if h == 0:
        return f"{m} min"
    return f"{h} h {m} min"


# ── Diagnóstico de infactibilidad ───────────────────────────────────────────

def diagnosticar_infactibilidad_real(
    df,
    volumen_obj_L: float,
    g_min: float, g_max: float,
    d_min: float, d_max: float,
    c_min: float, c_max: float,
    a_min: float, a_max: float,
) -> dict:
    """
    Analiza por qué la optimización no encontró solución,
    incluyendo la nota de que LDP se añade automáticamente si la densidad
    de los tanques no alcanza el rango objetivo.
    """
    resultados = {
        "es_posible": True,
        "problemas": [],
        "recomendaciones": [],
        "combinaciones_posibles": [],
    }

    densidad_est  = (d_min + d_max) / 2
    masa_total    = df["Masa_Disponible_Kg"].sum()
    volumen_total = df["Volumen"].sum()

    # ── Volumen suficiente ──────────────────────────────────────────────────
    masa_objetivo = volumen_obj_L * densidad_est
    if masa_objetivo > masa_total:
        resultados["es_posible"] = False
        resultados["problemas"].append(
            f"Volumen insuficiente: requiere {masa_objetivo:.0f} kg, "
            f"disponible {masa_total:.0f} kg"
        )
        resultados["recomendaciones"].append(
            f"Reducir volumen objetivo a máximo {masa_total / densidad_est:.0f} L"
        )

    if volumen_obj_L > volumen_total:
        resultados["es_posible"] = False
        resultados["problemas"].append(
            f"Volumen objetivo ({volumen_obj_L:.0f} L) supera el inventario "
            f"({volumen_total:.0f} L)"
        )
        resultados["recomendaciones"].append(
            f"Reducir volumen objetivo a máximo {volumen_total:.0f} L"
        )

    # ── Grasa ───────────────────────────────────────────────────────────────
    grasa_min_t = df["Grasa"].min()
    grasa_max_t = df["Grasa"].max()

    if g_max < grasa_min_t:
        resultados["es_posible"] = False
        resultados["problemas"].append(
            f"Grasa objetivo máxima ({g_max}%) < grasa mínima disponible ({grasa_min_t}%)"
        )
        resultados["recomendaciones"].append(
            f"Ampliar grasa máxima objetivo a ≥ {grasa_min_t}%"
        )
    if g_min > grasa_max_t:
        resultados["es_posible"] = False
        resultados["problemas"].append(
            f"Grasa objetivo mínima ({g_min}%) > grasa máxima disponible ({grasa_max_t}%)"
        )
        resultados["recomendaciones"].append(
            f"Reducir grasa mínima objetivo a ≤ {grasa_max_t}%"
        )

    # ── Densidad — informativa (LDP la corrige automáticamente) ────────────
    dens_prom = (df["Masa_Disponible_Kg"] * df["Densidad"]).sum() / masa_total if masa_total > 0 else 0
    if dens_prom < d_min:
        resultados["recomendaciones"].append(
            f"Densidad promedio de tanques ({dens_prom:.4f} kg/L) por debajo del objetivo "
            f"({d_min} kg/L). Se añadirá LDP automáticamente para corregirla."
        )

    # ── Crioscopia — informativa ────────────────────────────────────────────
    crio_prom = (df["Masa_Disponible_Kg"] * df["Crioscopia"]).sum() / masa_total if masa_total > 0 else 0
    c_lo = min(c_min, c_max)
    c_hi = max(c_min, c_max)
    if crio_prom < c_lo or crio_prom > c_hi:
        resultados["recomendaciones"].append(
            f"Crioscopia promedio ({crio_prom:.4f}°C) fuera del rango objetivo "
            f"[{c_lo}, {c_hi}]°C. Esto se reportará como alerta de calidad pero no "
            f"impide la optimización."
        )

    # ── Combinaciones posibles ──────────────────────────────────────────────
    tanques_g = df[df["Grasa"] >= g_min]
    if not tanques_g.empty and tanques_g["Volumen"].sum() >= volumen_obj_L:
        resultados["combinaciones_posibles"].append({
            "descripcion": f"Usar solo tanques con grasa ≥ {g_min}%",
            "tanques": tanques_g["Tanque"].tolist(),
            "volumen_total": tanques_g["Volumen"].sum(),
            "volumen_necesario": volumen_obj_L,
        })

    df_ord = df.sort_values("Grasa", ascending=False)
    vol_ac, selec = 0.0, []
    for _, row in df_ord.iterrows():
        if vol_ac < volumen_obj_L:
            selec.append(row["Tanque"])
            vol_ac += row["Volumen"]
    if selec:
        resultados["combinaciones_posibles"].append({
            "descripcion": "Posible combinación (priorizando grasa alta)",
            "tanques": selec,
            "volumen_total": vol_ac,
        })

    return resultados


def diagnosticar_infactibilidad(
    df, volumen_obj_L,
    g_min, g_max, d_min, d_max, c_min, c_max, a_min, a_max,
    aditivos=None,
) -> dict:
    """Versión simplificada (compatibilidad)."""
    masa_total = df["Masa_Disponible_Kg"].sum()
    grasa_prom = (df["Masa_Disponible_Kg"] * df["Grasa"]).sum() / masa_total if masa_total > 0 else 0
    return {
        "parametros": [],
        "bloqueos": [],
        "resumen": f"Grasa promedio disponible: {grasa_prom:.2f}%",
        "grasa_prom_disponible": grasa_prom,
    }


# ── Motor de optimización ────────────────────────────────────────────────────

def optimizar_mezcla(
    df,
    volumen_obj_L: float,
    g_min: float, g_max: float,
    d_min: float, d_max: float,
    c_min: float, c_max: float,
    a_min: float, a_max: float,
    ldp_costo_kg: float = LDP_COSTO_KG,
    ldp_max_kg: float = LDP_MAX_KG_DEFAULT,
    aditivos=None,          # ignorado; mantenido por compatibilidad de firma
) -> dict:
    """
    Optimiza la mezcla usando SOLO los tanques del inventario.

    Corrector automático de densidad:
      Si la densidad promedio de los tanques no alcanza d_min, el modelo
      puede añadir Leche Descremada en Polvo (LDP) hasta ldp_max_kg.
      La cantidad de LDP se determina por el optimizador, no manualmente.

    Crioscopia y acidez:
      Se manejan con holgura penalizada — si los tanques no pueden cumplir
      el rango, el modelo elige la mezcla que más se acerque y el resultado
      se reporta como alerta de calidad en la interfaz.
    """
    densidad_estimada     = (d_min + d_max) / 2
    masa_objetivo_Kg      = volumen_obj_L * densidad_estimada
    masa_total_disponible = df["Masa_Disponible_Kg"].sum()

    if masa_objetivo_Kg > masa_total_disponible * 1.01:
        return {
            "status": "Infeasible",
            "error": "Insuficiente materia prima",
            "masa_requerida": masa_objetivo_Kg,
            "masa_disponible": masa_total_disponible,
        }

    # ── Modelo LP ──────────────────────────────────────────────────────────
    model = pulp.LpProblem("Estandarizacion_Leche", pulp.LpMinimize)

    # Variables de tanques (kg por tanque)
    x_kg = {
        i: pulp.LpVariable(
            f"Kg_T{i}", lowBound=0,
            upBound=df.loc[i, "Masa_Disponible_Kg"]
        )
        for i in df.index
    }
    # Variables binarias de activación de tanque (para costo CIP)
    y_bin = {
        i: pulp.LpVariable(f"Usa_T{i}", cat="Binary")
        for i in df.index
    }
    # Variable LDP (kg de leche descremada en polvo)
    ldp_kg = pulp.LpVariable("LDP_kg", lowBound=0, upBound=ldp_max_kg)

    # Holguras para crioscopia y acidez (permiten solución aunque estén fuera de rango)
    slack_crio_menos = pulp.LpVariable("slack_crio_menos", lowBound=0)
    slack_crio_mas   = pulp.LpVariable("slack_crio_mas",   lowBound=0)
    slack_acid_menos = pulp.LpVariable("slack_acid_menos", lowBound=0)
    slack_acid_mas   = pulp.LpVariable("slack_acid_mas",   lowBound=0)

    # ── Función objetivo ────────────────────────────────────────────────────
    COSTO_CIP   = 5.0
    PEN_CRIO    = 200.0    # alta penalización para minimizar desviación de crioscopia
    PEN_ACIDEZ  = 100.0
    PEN_LDP     = ldp_costo_kg  # costo real del LDP en la función objetivo

    costo_leche    = pulp.lpSum(x_kg[i] * df.loc[i, "Costo_Por_Kg"] for i in df.index)
    costo_cip      = pulp.lpSum(y_bin[i] * COSTO_CIP               for i in df.index)
    costo_ldp      = ldp_kg * PEN_LDP
    pen_crio_total = PEN_CRIO   * (slack_crio_menos + slack_crio_mas)
    pen_acid_total = PEN_ACIDEZ * (slack_acid_menos + slack_acid_mas)

    model += costo_leche + costo_cip + costo_ldp + pen_crio_total + pen_acid_total, "Objetivo"

    # ── Restricciones ───────────────────────────────────────────────────────
    masa_tanques = pulp.lpSum(x_kg[i] for i in df.index)

    # Masa total = tanques + LDP = masa objetivo (igualdad)
    model += masa_tanques + ldp_kg == masa_objetivo_Kg, "Meta_Masa"

    # Grasa (dura) — usa escalar fijo para linealidad
    grasa_t = pulp.lpSum(x_kg[i] * (df.loc[i, "Grasa"] / 100.0) for i in df.index)
    grasa_ldp = ldp_kg * LDP_GRASA_KG
    model += grasa_t + grasa_ldp >= masa_objetivo_Kg * (g_min / 100.0), "Min_Grasa"
    model += grasa_t + grasa_ldp <= masa_objetivo_Kg * (g_max / 100.0), "Max_Grasa"

    # Densidad (dura) — el LDP la corrige hacia arriba
    # densidad promedio ponderada ≥ d_min:  sum(x_i * D_i) + ldp * D_ldp >= masa_total * d_min
    dens_t   = pulp.lpSum(x_kg[i] * float(df.loc[i, "Densidad"]) for i in df.index)
    dens_ldp = ldp_kg * LDP_DENSIDAD_KG
    model += dens_t + dens_ldp >= masa_objetivo_Kg * d_min, "Min_Densidad"
    model += dens_t + dens_ldp <= masa_objetivo_Kg * d_max, "Max_Densidad"

    # Crioscopia (blanda — holgura penalizada)
    c_lo = min(c_min, c_max)
    c_hi = max(c_min, c_max)
    crio_t   = pulp.lpSum(x_kg[i] * float(df.loc[i, "Crioscopia"]) for i in df.index)
    crio_ldp = ldp_kg * LDP_CRIO_KG
    model += crio_t + crio_ldp >= masa_objetivo_Kg * c_lo - slack_crio_menos, "Min_Crio"
    model += crio_t + crio_ldp <= masa_objetivo_Kg * c_hi + slack_crio_mas,   "Max_Crio"

    # Acidez (blanda — holgura penalizada)
    acid_t   = pulp.lpSum(x_kg[i] * float(df.loc[i, "Acidez"]) for i in df.index)
    acid_ldp = ldp_kg * LDP_ACIDEZ_KG
    model += acid_t + acid_ldp >= masa_objetivo_Kg * a_min - slack_acid_menos, "Min_Acidez"
    model += acid_t + acid_ldp <= masa_objetivo_Kg * a_max + slack_acid_mas,   "Max_Acidez"

    # Big-M para activación de tanques
    M = 1_000_000_000
    for i in df.index:
        model += x_kg[i] <= M * y_bin[i], f"Link_T{i}"

    # ── Resolver ───────────────────────────────────────────────────────────
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60, threads=4)
    model.solve(solver)
    status = pulp.LpStatus[model.status]

    if status != "Optimal":
        return {"status": status, "error": "No se encontró solución factible"}

    # ── Procesar resultados ────────────────────────────────────────────────
    resultados          = []
    masa_usada_total    = 0.0
    grasa_usada_total   = 0.0
    crio_usada_total    = 0.0
    acidez_usada_total  = 0.0
    costo_mp            = 0.0
    tanques_activos     = 0

    for i in df.index:
        kg = x_kg[i].value()
        if kg is None or kg < 0.05:
            continue
        tanques_activos    += 1
        litros              = kg / df.loc[i, "Densidad"]
        costo_t             = kg * df.loc[i, "Costo_Por_Kg"]
        resultados.append({
            "Tanque"          : df.loc[i, "Tanque"],
            "Litros a Bombear": round(litros, 2),
            "Masa (kg)"       : round(kg, 2),
            "Grasa Origen"    : f"{df.loc[i, 'Grasa']}%",
            "Tipo"            : "Tanque",
            "Costo Parcial"   : round(costo_t, 2),
        })
        masa_usada_total   += kg
        grasa_usada_total  += kg * (df.loc[i, "Grasa"] / 100.0)
        crio_usada_total   += kg * df.loc[i, "Crioscopia"]
        acidez_usada_total += kg * df.loc[i, "Acidez"]
        costo_mp           += costo_t

    # LDP si el optimizador decidió usarla
    ldp_usado = ldp_kg.value() if ldp_kg.value() is not None else 0.0
    if ldp_usado > 0.01:
        ldp_litros = ldp_usado / LDP_DENSIDAD_KG
        ldp_costo  = ldp_usado * ldp_costo_kg
        resultados.append({
            "Tanque"          : "⚗️ LDP — Leche Descremada en Polvo",
            "Litros a Bombear": round(ldp_litros, 3),
            "Masa (kg)"       : round(ldp_usado, 3),
            "Grasa Origen"    : f"{LDP_GRASA_KG * 100:.1f}%",
            "Tipo"            : "Corrector densidad",
            "Costo Parcial"   : round(ldp_costo, 2),
        })
        masa_usada_total   += ldp_usado
        grasa_usada_total  += ldp_usado * LDP_GRASA_KG
        crio_usada_total   += ldp_usado * LDP_CRIO_KG
        acidez_usada_total += ldp_usado * LDP_ACIDEZ_KG
        costo_mp           += ldp_costo

    grasa_final_pct    = (grasa_usada_total / masa_usada_total) * 100 if masa_usada_total > 0 else 0.0
    crio_final         = crio_usada_total   / masa_usada_total        if masa_usada_total > 0 else 0.0
    acidez_final       = acidez_usada_total / masa_usada_total        if masa_usada_total > 0 else 0.0
    densidad_final_est = masa_usada_total   / volumen_obj_L           if volumen_obj_L     > 0 else 0.0

    costo_cip_total  = tanques_activos * COSTO_CIP
    costo_total      = costo_mp + costo_cip_total

    return {
        "status"    : "Optimal",
        "resultados": resultados,
        "ldp_usado_kg": round(ldp_usado, 3),
        "metricas"  : {
            "volumen_final"      : float(volumen_obj_L),
            "masa_total"         : float(masa_usada_total),
            "grasa_final"        : float(grasa_final_pct),
            "grasa_total_kg"     : float(grasa_usada_total),
            "densidad_final"     : float(densidad_final_est),
            "crioscopia_final"   : float(crio_final),
            "acidez_final"       : float(acidez_final),
            "costo_materia_prima": float(costo_mp),
            "costo_limpiezas"    : float(costo_cip_total),
            "costo_total"        : float(costo_total),
            "tanques_activos"    : int(tanques_activos),
            "ldp_usado_kg"       : round(ldp_usado, 3),
            "slack_min_acidez"   : float(slack_acid_menos.value() or 0),
            "slack_max_acidez"   : float(slack_acid_mas.value()   or 0),
            "costo_unitario"     : float(costo_total / volumen_obj_L) if volumen_obj_L > 0 else 0.0,
        },
        "rangos_objetivo": {
            "grasa"     : (float(g_min), float(g_max)),
            "densidad"  : (float(d_min), float(d_max)),
            "crioscopia": (float(c_lo),  float(c_hi)),
            "acidez"    : (float(a_min), float(a_max)),
        },
    }


# ── Optimización de descremado ───────────────────────────────────────────────

def optimizar_descremado(
    df,
    volumen_crema_obj_L: float,
    fat_crema_obj_pct: float = 40.0,
    fat_descremada_pct: float = FAT_SKIM_PCT,
) -> dict:
    """Optimiza la selección de tanques para el proceso de descremado centrífugo."""
    if not (FAT_CREMA_MIN <= fat_crema_obj_pct <= FAT_CREMA_MAX):
        return {"status": "Error",
                "error": f"% grasa crema debe estar entre {FAT_CREMA_MIN}% y {FAT_CREMA_MAX}%."}
    if volumen_crema_obj_L <= 0:
        return {"status": "Error", "error": "El volumen de crema debe ser mayor a 0."}

    Gc = fat_crema_obj_pct / 100
    Gs = fat_descremada_pct / 100

    tanques_validos = df[df["Grasa"] / 100 > Gs].copy()
    if tanques_validos.empty:
        return {"status": "Infeasible",
                "error": "Ningún tanque tiene suficiente grasa para el descremado."}

    tanques_validos["Fat_Frac"]      = tanques_validos["Grasa"] / 100
    tanques_validos["Crema_Max_L"]   = (
        tanques_validos["Volumen"]
        * (tanques_validos["Fat_Frac"] - Gs)
        / (Gc - Gs)
    )
    tanques_validos["Descremada_Max_L"] = tanques_validos["Volumen"] - tanques_validos["Crema_Max_L"]

    crema_posible = tanques_validos["Crema_Max_L"].sum()
    if volumen_crema_obj_L > crema_posible * 0.99:
        return {
            "status": "Infeasible",
            "error": "Volumen de crema requerido supera la capacidad disponible.",
            "crema_posible_L"  : round(crema_posible, 2),
            "crema_requerida_L": round(volumen_crema_obj_L, 2),
        }

    model  = pulp.LpProblem("Descremado_Optimo", pulp.LpMinimize)
    x_vol  = {i: pulp.LpVariable(f"L_T{i}", lowBound=0,
                                  upBound=float(tanques_validos.loc[i, "Volumen"]))
               for i in tanques_validos.index}
    y_bin  = {i: pulp.LpVariable(f"Usa_T{i}", cat="Binary")
               for i in tanques_validos.index}

    COSTO_CIP = 5.0
    model += (pulp.lpSum(x_vol[i] * float(tanques_validos.loc[i, "Costo"]) for i in tanques_validos.index)
              + pulp.lpSum(y_bin[i] * COSTO_CIP for i in tanques_validos.index)), "Costo"

    crema_p = {i: x_vol[i] * float((tanques_validos.loc[i, "Fat_Frac"] - Gs) / (Gc - Gs))
               for i in tanques_validos.index}
    model += pulp.lpSum(crema_p[i] for i in tanques_validos.index) == volumen_crema_obj_L, "Meta_Crema"

    M = 1_000_000_000
    for i in tanques_validos.index:
        model += x_vol[i] <= M * y_bin[i], f"Link_{i}"

    pulp.PULP_CBC_CMD(msg=False, timeLimit=30, threads=4).solve(model)
    status = pulp.LpStatus[model.status]
    if status != "Optimal":
        return {"status": status, "error": "No se encontró solución factible para el descremado."}

    resultados_tanques = []
    vol_leche_t = vol_crema_t = vol_desc_t = costo_t = 0.0
    tanques_usados = 0

    for i in tanques_validos.index:
        ll = x_vol[i].value()
        if ll is None or ll < 0.1:
            continue
        tanques_usados += 1
        fat_i  = float(tanques_validos.loc[i, "Fat_Frac"])
        lc     = ll * (fat_i - Gs) / (Gc - Gs)
        ld     = ll - lc
        ct     = ll * float(tanques_validos.loc[i, "Costo"])
        th     = lc / CLARIFIER_RATE_L_H
        resultados_tanques.append({
            "Tanque"              : tanques_validos.loc[i, "Tanque"],
            "Leche a Procesar (L)": round(ll, 2),
            "Crema Obtenida (L)"  : round(lc, 2),
            "Leche Descremada (L)": round(ld, 2),
            "Grasa Entrada (%)"   : round(fat_i * 100, 2),
            "Grasa Crema (%)"     : round(fat_crema_obj_pct, 2),
            "Grasa Descremada (%)": round(fat_descremada_pct, 2),
            "Tiempo Proceso (h)"  : round(th, 2),
            "Costo Parcial ($)"   : round(ct, 2),
        })
        vol_leche_t += ll; vol_crema_t += lc; vol_desc_t += ld; costo_t += ct

    tt_h   = vol_crema_t / CLARIFIER_RATE_L_H
    cip_t  = tanques_usados * COSTO_CIP
    gran_t = costo_t + cip_t
    rend   = (vol_crema_t / vol_leche_t * 100) if vol_leche_t > 0 else 0.0

    return {
        "status": "Optimal",
        "resultados_tanques": resultados_tanques,
        "metricas_descremado": {
            "vol_leche_total_L"     : round(vol_leche_t, 2),
            "vol_crema_total_L"     : round(vol_crema_t, 2),
            "vol_descremada_total_L": round(vol_desc_t, 2),
            "fat_crema_pct"         : round(fat_crema_obj_pct, 2),
            "fat_descremada_pct"    : round(fat_descremada_pct, 2),
            "tiempo_total_h"        : round(tt_h, 4),
            "rendimiento_pct"       : round(rend, 4),
            "tanques_usados"        : tanques_usados,
            "costo_materia_prima"   : round(costo_t, 2),
            "costo_limpiezas"       : round(cip_t, 2),
            "costo_total"           : round(gran_t, 2),
            "costo_unitario_crema"  : round(gran_t / vol_crema_t, 4) if vol_crema_t > 0 else 0.0,
        },
        "balance_masas": {
            "descripcion": (
                f"De {round(vol_leche_t, 1)} L de leche cruda "
                f"se obtienen {round(vol_crema_t, 1)} L de crema ({fat_crema_obj_pct}% grasa) "
                f"y {round(vol_desc_t, 1)} L de leche descremada ({fat_descremada_pct}% grasa). "
                f"Tiempo estimado: {_fmt_tiempo(tt_h)}."
            )
        },
    }
