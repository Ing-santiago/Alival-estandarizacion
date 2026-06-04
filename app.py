import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime, timezone
from supabase import create_client, Client
from optimizacion import (
    optimizar_mezcla,
    optimizar_descremado,
    calcular_crema,
    calcular_leche,
)
import websocket as ws_lib

st.set_page_config(page_title="Sistema de Estandarización", layout="wide")

st.title("🥛 Sistema de Estandarización de Leche")
st.markdown("Optimización de mezclas lácteas")

st.info("Aplicación lista para Streamlit Cloud ✅")

# Placeholder básico
st.write("La app está correctamente configurada.")
