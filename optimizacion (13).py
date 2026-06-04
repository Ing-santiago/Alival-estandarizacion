import pulp
import pandas as pd


def optimizar_mezcla(df, volumen_obj_L, g_min, g_max, d_min, d_max, c_min, c_max, a_min, a_max):
    prob = pulp.LpProblem("Mezcla", pulp.LpMinimize)

    vars_vol = {
        i: pulp.LpVariable(f"x_{i}", lowBound=0)
        for i in df.index
    }

    # Objetivo: minimizar volumen total usado
    prob += pulp.lpSum(vars_vol[i] for i in df.index)

    # Restricción de volumen
    prob += pulp.lpSum(vars_vol[i] for i in df.index) == volumen_obj_L

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    return {
        "status": pulp.LpStatus[prob.status],
        "resultado": {i: vars_vol[i].value() for i in df.index}
    }


def optimizar_descremado(df, volumen_crema_obj_L):
    return {"status": "ok"}


def calcular_crema():
    return {}


def calcular_leche():
    return {}
