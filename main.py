# =============================================================================
# requirements.txt — dependencias para Streamlit Cloud:
#   pulp>=2.7.0
#   pandas>=1.5.0
#   streamlit>=1.28.0
#   supabase>=2.0.0
#   python-dotenv>=1.0.0
#   websocket-client>=1.6.0
# =============================================================================

import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime, timezone

# ── Importaciones con manejo de errores explícito para Streamlit Cloud ───────
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    st.error("❌ Dependencia faltante: `python-dotenv`. Agrega `python-dotenv>=1.0.0` a requirements.txt")
    st.stop()

try:
    from supabase import create_client, Client
except ModuleNotFoundError:
    st.error("❌ Dependencia faltante: `supabase`. Agrega `supabase>=2.0.0` a requirements.txt")
    st.stop()

try:
    from optimizacion import (
        optimizar_mezcla,
        optimizar_descremado,
        calcular_crema,
        calcular_leche,
        FAT_LECHE_MIN, FAT_LECHE_MAX,
        FAT_CREMA_MIN, FAT_CREMA_MAX,
        CLARIFIER_RATE_L_H,
        _fmt_tiempo,
    )
except ModuleNotFoundError as _e:
    st.error(f"❌ No se pudo importar el módulo de optimización: {_e}. Verifica que `pulp>=2.7.0` esté en requirements.txt")
    st.stop()

try:
    import websocket as ws_lib
except ModuleNotFoundError:
    st.error("❌ Dependencia faltante: `websocket-client`. Agrega `websocket-client>=1.6.0` a requirements.txt")
    st.stop()

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# AUTENTICACIÓN CON SUPABASE
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def init_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

sb: Client = init_supabase()

def init_session_state_auth():
    if "auth_token"    not in st.session_state: st.session_state.auth_token    = None
    if "user_email"    not in st.session_state: st.session_state.user_email    = None
    if "authenticated" not in st.session_state: st.session_state.authenticated = False

init_session_state_auth()

def login_user(email: str, password: str):
    if sb is None:
        return False, "Supabase no configurado"
    try:
        response = sb.auth.sign_in_with_password({"email": email, "password": password})
        if response.session:
            st.session_state.auth_token    = response.session.access_token
            st.session_state.user_email    = response.user.email
            st.session_state.authenticated = True
            return True, "Login exitoso"
        return False, "Sin sesión"
    except Exception as e:
        return False, str(e)

def logout_user():
    if sb:
        try:
            sb.auth.sign_out()
        except Exception:
            pass
    st.session_state.auth_token    = None
    st.session_state.user_email    = None
    st.session_state.authenticated = False
    st.rerun()

def check_auth():
    if sb is None:
        return False
    try:
        session = sb.auth.get_session()
        if session:
            st.session_state.auth_token    = session.access_token
            st.session_state.user_email    = session.user.email
            st.session_state.authenticated = True
            return True
    except Exception:
        pass
    return False

def show_login_form():
    st.markdown("---")
    st.markdown("### 🔐 Iniciar Sesión")
    with st.form("login_form", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            email    = st.text_input("📧 Email",       placeholder="tu@email.com")
        with col2:
            password = st.text_input("🔑 Contraseña", type="password")
        submitted = st.form_submit_button("Iniciar Sesión", type="primary", use_container_width=True)
        if submitted:
            if email and password:
                success, message = login_user(email, password)
                if success:
                    st.success("✅ Login exitoso")
                    st.rerun()
                else:
                    st.error(f"❌ Error: {message}")
            else:
                st.warning("⚠️ Completa email y contraseña")
    st.markdown("---")

def get_current_user_id():
    if sb and st.session_state.authenticated:
        try:
            session = sb.auth.get_session()
            if session:
                return session.user.id
        except Exception:
            pass
    return None

# Verificar auth antes de renderizar cualquier UI
if sb is not None and not st.session_state.authenticated:
    check_auth()
    if not st.session_state.authenticated:
        st.set_page_config(page_title="kLineal - Login", page_icon="🥛", layout="centered")
        st.markdown("### 🥛 Sistema de Estandarización de Leche")
        st.info("Por favor, inicia sesión para acceder a la aplicación")
        show_login_form()
        st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# GESTOR DE TEMAS
# ─────────────────────────────────────────────────────────────────────────────
THEME_FILE = os.path.expanduser("~/.klineal_theme.json")

def guardar_tema(nombre_tema):
    try:
        with open(THEME_FILE, "w", encoding="utf-8") as f:
            json.dump({"tema": nombre_tema}, f)
    except Exception:
        pass

def obtener_tema_actual():
    if os.path.exists(THEME_FILE):
        try:
            with open(THEME_FILE, "r") as f:
                return json.load(f).get("tema", "Oscuro Premium")
        except Exception:
            pass
    return "Oscuro Premium"

tema_actual = obtener_tema_actual()
if "tema_seleccionado" not in st.session_state:
    st.session_state.tema_seleccionado = tema_actual

# ─────────────────────────────────────────────────────────────────────────────
# ASISTENTE IA — WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────
def enviar_mensaje_ws(mensaje: str) -> str:
    try:
        ws_url   = f"ws://dev02.aspsols.com:{os.getenv('WS_PORT', '8080')}/ws"
        ws_token = os.getenv("WS_AUTH_TOKEN", "default_token")
        conn     = ws_lib.create_connection(ws_url, header={"x-auth-token": ws_token})
        connected = json.loads(conn.recv())
        if connected.get("type") != "connected":
            conn.close()
            return "❌ Error: no se recibió confirmación de conexión."
        conn.send(json.dumps({"type": "message", "content": mensaje}))
        respuesta = ""
        while True:
            raw  = conn.recv()
            data = json.loads(raw)
            tipo = data.get("type")
            if   tipo == "typing":  continue
            elif tipo == "message": respuesta = data.get("content", ""); break
            elif tipo == "error":   respuesta = f"❌ Error del servidor: {data.get('message', '')}"; break
        conn.close()
        return respuesta
    except ConnectionRefusedError:
        return "❌ No se pudo conectar: asegúrate de que el servidor WebSocket esté corriendo."
    except Exception as e:
        return f"❌ Error de conexión: {str(e)}"

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE BASE DE DATOS — TANQUES
# ─────────────────────────────────────────────────────────────────────────────
def cargar_tanques_db():
    if sb is None:
        return []
    try:
        res = sb.table("tanques").select("*").is_("eliminado_en", None).order("creado_en").execute()
        return [
            {
                "id"        : r["id"],
                "Tanque"    : r["nombre"],
                "Volumen"   : float(r["volumen"]),
                "Grasa"     : float(r["grasa"]),
                "Densidad"  : float(r["densidad"])   if r.get("densidad")   is not None else 1.032,
                "Crioscopia": float(r["crioscopia"]) if r.get("crioscopia") is not None else -0.520,
                "Acidez"    : float(r["acidez"])     if r.get("acidez")     is not None else 16.0,
                "Costo"     : float(r.get("costo") or 0),
            }
            for r in (res.data or [])
        ]
    except Exception as e:
        st.error(f"Error cargando tanques de Supabase: {e}")
        return []

def agregar_tanque_db(nombre, volumen, grasa, densidad, crioscopia, acidez, costo=0):
    if sb is None:
        st.warning("⚠️ Sin conexión a Supabase — revisa las variables de entorno")
        return None
    try:
        res = sb.table("tanques").insert({
            "nombre"    : nombre,
            "volumen"   : str(float(volumen)),
            "grasa"     : str(float(grasa)),
            "densidad"  : str(float(densidad)),
            "crioscopia": str(float(crioscopia)),
            "acidez"    : str(float(acidez)),
            "costo"     : str(float(costo)),
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        st.error(f"Error guardando en Supabase: {e}")
        return None

def eliminar_tanque_db(tanque_id):
    if sb is None:
        return True
    if not tanque_id:
        st.error("⚠️ ID de tanque inválido")
        return False
    try:
        ahora    = datetime.now(timezone.utc).isoformat()
        response = sb.table("tanques").update({"eliminado_en": ahora}).eq("id", tanque_id).execute()
        if response.data is not None:
            st.success("✅ Tanque eliminado de la base de datos")
            return True
        return False
    except Exception as e:
        st.error(f"❌ Error eliminando tanque: {e}")
        return False

def actualizar_tanque_db(tanque_id, nombre, volumen, grasa, densidad, crioscopia, acidez, costo=0):
    if sb is None:
        return False
    try:
        sb.table("tanques").update({
            "nombre"    : nombre,
            "volumen"   : str(float(volumen)),
            "grasa"     : str(float(grasa)),
            "densidad"  : str(float(densidad)),
            "crioscopia": str(float(crioscopia)),
            "acidez"    : str(float(acidez)),
            "costo"     : str(float(costo)),
        }).eq("id", tanque_id).execute()
        return True
    except Exception:
        return False

def actualizar_inventario_tanques(resultados):
    if sb is None:
        st.error("❌ No hay conexión a la base de datos")
        return False
    try:
        actualizaciones = []
        for r in resultados:
            litros_a_descontar = float(r.get("Litros a Bombear", 0))
            nombre_tanque      = r.get("Tanque", "")
            if litros_a_descontar <= 0:
                continue
            tanque_data = next((t for t in st.session_state.tanques if t["Tanque"] == nombre_tanque), None)
            if not tanque_data:
                st.warning(f"⚠️ Tanque '{nombre_tanque}' no encontrado en el inventario")
                continue
            tanque_id     = tanque_data.get("id")
            volumen_actual = tanque_data.get("Volumen", 0)
            if not tanque_id:
                st.warning(f"⚠️ Tanque '{nombre_tanque}' no tiene ID válido")
                continue
            nuevo_volumen = volumen_actual - litros_a_descontar
            if nuevo_volumen < 0:
                st.error(
                    f"❌ Error: No hay suficiente volumen en '{nombre_tanque}'. "
                    f"Disponible: {volumen_actual:,.2f} L, Solicitado: {litros_a_descontar:,.2f} L"
                )
                return False
            actualizaciones.append({
                "id"                : tanque_id,
                "nombre"            : nombre_tanque,
                "volumen_anterior"  : volumen_actual,
                "volumen_nuevo"     : nuevo_volumen,
                "litros_descontados": litros_a_descontar,
            })

        for act in actualizaciones:
            sb.table("tanques").update({"volumen": str(float(act["volumen_nuevo"]))}).eq("id", act["id"]).execute()
            st.success(
                f"✅ `{act['nombre']}`: {act['volumen_anterior']:,.2f} L → "
                f"{act['volumen_nuevo']:,.2f} L (-{act['litros_descontados']:,.2f} L)"
            )
        for act in actualizaciones:
            for t in st.session_state.tanques:
                if t["Tanque"] == act["nombre"]:
                    t["Volumen"] = act["volumen_nuevo"]
                    break

        total_descontado = sum(a["litros_descontados"] for a in actualizaciones)
        st.info(f"📊 Total descontado: `{total_descontado:,.2f} L` de `{len(actualizaciones)}` tanque(s)")
        return True
    except Exception as e:
        st.error(f"❌ Error actualizando inventario: {e}")
        return False

def actualizar_inventario_descremado(resultados_tanques):
    """Descuenta el volumen de leche procesada en el descremado desde el inventario."""
    if sb is None:
        st.error("❌ No hay conexión a la base de datos")
        return False
    try:
        actualizaciones = []
        for r in resultados_tanques:
            nombre_tanque      = r.get("Tanque", "")
            litros_a_descontar = float(r.get("Leche a Procesar (L)", 0))
            if litros_a_descontar <= 0:
                continue
            tanque_data = next(
                (t for t in st.session_state.tanques if t["Tanque"] == nombre_tanque), None
            )
            if not tanque_data:
                st.warning(f"⚠️ Tanque '{nombre_tanque}' no encontrado")
                continue
            tanque_id     = tanque_data.get("id")
            volumen_actual = tanque_data.get("Volumen", 0)
            if not tanque_id:
                st.warning(f"⚠️ Tanque '{nombre_tanque}' sin ID válido")
                continue
            nuevo_volumen = volumen_actual - litros_a_descontar
            if nuevo_volumen < 0:
                st.error(
                    f"❌ Volumen insuficiente en '{nombre_tanque}'. "
                    f"Disponible: {volumen_actual:,.2f} L | Requerido: {litros_a_descontar:,.2f} L"
                )
                return False
            actualizaciones.append({
                "id"                : tanque_id,
                "nombre"            : nombre_tanque,
                "volumen_anterior"  : volumen_actual,
                "volumen_nuevo"     : nuevo_volumen,
                "litros_descontados": litros_a_descontar,
            })

        for act in actualizaciones:
            sb.table("tanques").update({"volumen": str(float(act["volumen_nuevo"]))}).eq("id", act["id"]).execute()
            st.success(
                f"✅ `{act['nombre']}`: {act['volumen_anterior']:,.2f} L → "
                f"{act['volumen_nuevo']:,.2f} L (-{act['litros_descontados']:,.2f} L)"
            )
        for act in actualizaciones:
            for t in st.session_state.tanques:
                if t["Tanque"] == act["nombre"]:
                    t["Volumen"] = act["volumen_nuevo"]
                    break

        total = sum(a["litros_descontados"] for a in actualizaciones)
        st.info(f"📊 Total leche procesada descontada: `{total:,.2f} L` de `{len(actualizaciones)}` tanque(s)")
        return True
    except Exception as e:
        st.error(f"❌ Error actualizando inventario: {e}")
        return False

def cargar_historial_db():
    if sb is None:
        return []
    try:
        res = (
            sb.table("estandarizaciones")
            .select("creado_en,volumen_objetivo,grasa_objetivo,densidad_objetivo,crioscopia_objetivo,acidez_objetivo")
            .order("creado_en", desc=True)
            .execute()
        )
        return [
            {
                "Fecha"              : r["creado_en"][:16].replace("T", "  "),
                "Volumen"            : r["volumen_objetivo"],
                "Grasa objetivo"     : r["grasa_objetivo"],
                "Densidad objetivo"  : r.get("densidad_objetivo", 1.032),
                "Crioscopia objetivo": r.get("crioscopia_objetivo", -0.520),
                "Acidez objetivo"    : r.get("acidez_objetivo", 16.0),
            }
            for r in (res.data or [])
        ]
    except Exception:
        return []

def guardar_estandarizacion_db(volumen_obj, grasa_obj, densidad_obj, crioscopia_obj, acidez_obj, resultados):
    if sb is None:
        return False
    try:
        res = sb.table("estandarizaciones").insert({
            "volumen_objetivo"   : str(float(volumen_obj)),
            "grasa_objetivo"     : str(float(grasa_obj)),
            "densidad_objetivo"  : str(float(densidad_obj)),
            "crioscopia_objetivo": str(float(crioscopia_obj)),
            "acidez_objetivo"    : str(float(acidez_obj)),
            "volumen_total_usado": str(float(volumen_obj)),
            "estado"             : "completada",
        }).execute()
        if not res.data:
            return False
        est_id  = res.data[0]["id"]
        detalles = []
        for r in resultados:
            litros = r["Litros usados"]
            if litros > 0:
                tanque_row = next(
                    (t for t in st.session_state.tanques if t["id"] == r["tanque_id"]), None
                )
                if tanque_row and "id" in tanque_row:
                    detalles.append({
                        "estandarizacion_id": est_id,
                        "tanque_id"         : tanque_row["id"],
                        "litros_usados"     : str(float(litros)),
                        "grasa_tanque"      : str(float(tanque_row["Grasa"])),
                    })
        if detalles:
            sb.table("estandarizacion_tanques").insert(detalles).execute()
        return True
    except Exception:
        return False

def limpiar_todo_db():
    if sb is None:
        return
    try:
        sb.table("estandarizaciones").update({"eliminado_en": "now()"}).neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        sb.table("tanques").update({"eliminado_en": "now()"}).neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        st.success("✅ Todos los datos han sido eliminados")
    except Exception as e:
        st.error(f"❌ Error limpiando datos: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE BASE DE DATOS — RECETAS
# ─────────────────────────────────────────────────────────────────────────────
def cargar_recetas_db():
    if sb is None:
        return []
    try:
        res = (
            sb.table("recetas")
            .select("*")
            .eq("activo", True)
            .is_("eliminado_en", None)
            .order("creado_en")
            .execute()
        )
        return [
            {
                "id"            : r["id"],
                "nombre"        : r["nombre"],
                "descripcion"   : r.get("descripcion", ""),
                "grasa_min"     : float(r["grasa_min"]),
                "grasa_max"     : float(r["grasa_max"]),
                "densidad_min"  : float(r["densidad_min"]),
                "densidad_max"  : float(r["densidad_max"]),
                "crioscopia_min": float(r["crioscopia_min"]),
                "crioscopia_max": float(r["crioscopia_max"]),
                "acidez_min"    : float(r["acidez_min"]),
                "acidez_max"    : float(r["acidez_max"]),
                "volumen_default": float(r.get("volumen_default") or 10000.0),
            }
            for r in (res.data or [])
        ]
    except Exception as e:
        st.error(f"Error cargando recetas de Supabase: {e}")
        return []

def agregar_receta_db(
    nombre, descripcion, grasa_min, grasa_max,
    densidad_min, densidad_max, crioscopia_min, crioscopia_max,
    acidez_min, acidez_max, volumen_default,
):
    if sb is None:
        st.warning("⚠️ Sin conexión a Supabase — revisa las variables de entorno")
        return None
    try:
        res = sb.table("recetas").insert({
            "nombre"        : nombre,
            "descripcion"   : descripcion,
            "grasa_min"     : str(float(grasa_min)),
            "grasa_max"     : str(float(grasa_max)),
            "densidad_min"  : str(float(densidad_min)),
            "densidad_max"  : str(float(densidad_max)),
            "crioscopia_min": str(float(crioscopia_min)),
            "crioscopia_max": str(float(crioscopia_max)),
            "acidez_min"    : str(float(acidez_min)),
            "acidez_max"    : str(float(acidez_max)),
            "volumen_default": str(float(volumen_default)),
            "activo"        : True,
        }).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        st.error(f"Error guardando receta en Supabase: {e}")
        return None

def eliminar_receta_db(receta_id):
    if sb is None:
        return True
    if not receta_id:
        st.error("⚠️ ID de receta inválido")
        return False
    try:
        ahora    = datetime.now(timezone.utc).isoformat()
        response = sb.table("recetas").update({"eliminado_en": ahora}).eq("id", receta_id).execute()
        if response.data is not None:
            st.success("✅ Receta eliminada de la base de datos")
            return True
        return False
    except Exception as e:
        st.error(f"❌ Error eliminando receta: {e}")
        return False

def actualizar_receta_db(
    receta_id, nombre, descripcion, grasa_min, grasa_max,
    densidad_min, densidad_max, crioscopia_min, crioscopia_max,
    acidez_min, acidez_max, volumen_default, activo=True,
):
    if sb is None:
        return False
    try:
        sb.table("recetas").update({
            "nombre"        : nombre,
            "descripcion"   : descripcion,
            "grasa_min"     : str(float(grasa_min)),
            "grasa_max"     : str(float(grasa_max)),
            "densidad_min"  : str(float(densidad_min)),
            "densidad_max"  : str(float(densidad_max)),
            "crioscopia_min": str(float(crioscopia_min)),
            "crioscopia_max": str(float(crioscopia_max)),
            "acidez_min"    : str(float(acidez_min)),
            "acidez_max"    : str(float(acidez_max)),
            "volumen_default": str(float(volumen_default)),
            "activo"        : activo,
        }).eq("id", receta_id).execute()
        return True
    except Exception as e:
        st.error(f"Error actualizando receta: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZAR SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
DEFAULTS_TANQUE = {"Densidad": 1.032, "Crioscopia": -0.520, "Acidez": 16.0, "Costo": 0.0}

if "tanques" not in st.session_state:
    loaded = cargar_tanques_db()
    for t in loaded:
        for k, v in DEFAULTS_TANQUE.items():
            t.setdefault(k, v)
    st.session_state.tanques = loaded

if "historial"        not in st.session_state: st.session_state.historial        = cargar_historial_db()
if "recetas"          not in st.session_state: st.session_state.recetas          = cargar_recetas_db()
if "ws_chat_history"  not in st.session_state: st.session_state.ws_chat_history  = []

# ─────────────────────────────────────────────────────────────────────────────
# HEADER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-header">🥛 Sistema de Estandarización de Leche</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Optimización y cálculo de mezclas lácteas usando grasa, densidad, crioscopia y acidez</p>',
    unsafe_allow_html=True,
)
st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# BARRA LATERAL
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("Logo.jpeg", use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.header("📊 Resumen")
    if st.session_state.tanques:
        df_temp       = pd.DataFrame(st.session_state.tanques)
        total_vol     = df_temp["Volumen"].sum()
        grasa_prom    = (df_temp["Volumen"] * df_temp["Grasa"]).sum()    / total_vol if total_vol > 0 else 0
        densidad_prom = (df_temp["Volumen"] * df_temp["Densidad"]).sum() / total_vol if total_vol > 0 else 0
        crio_prom     = (df_temp["Volumen"] * df_temp["Crioscopia"]).sum() / total_vol if total_vol > 0 else 0
        acidez_prom   = (df_temp["Volumen"] * df_temp["Acidez"]).sum()  / total_vol if total_vol > 0 else 0
        costo_total   = sum(t["Volumen"] * t.get("Costo", 0) for t in st.session_state.tanques)
        costo_prom    = (df_temp["Volumen"] * df_temp["Costo"]).sum()   / total_vol if total_vol > 0 and "Costo" in df_temp.columns else 0

        st.metric("Total tanques",       len(st.session_state.tanques))
        st.metric("Volumen total",       f"{total_vol:,.0f} L")
        st.metric("Grasa promedio",      f"{grasa_prom:.2f}%")
        st.metric("Densidad promedio",   f"{densidad_prom:.3f} kg/L")
        st.metric("Crioscopia promedio", f"{crio_prom:.3f} °C")
        st.metric("Acidez promedio",     f"{acidez_prom:.2f} °D")
        st.metric("Costo total estimado",  f"${costo_total:,.2f}")
        st.metric("Costo promedio por L",  f"${costo_prom:.2f}/L")
    else:
        st.info("No hay tanques registrados")

    st.markdown("---")
    if st.button("🗑️ Limpiar todo", type="secondary", use_container_width=True):
        limpiar_todo_db()
        st.session_state.tanques   = []
        st.session_state.historial = []
        st.rerun()

    st.markdown("---")
    st.subheader("🎨 Personalización")
    tema_opciones = ["Oscuro Premium", "Claro Limpio", "Azul Profundo"]
    idx_tema  = tema_opciones.index(st.session_state.tema_seleccionado) if st.session_state.tema_seleccionado in tema_opciones else 0
    tema_sel  = st.selectbox("Tema Visual Activo", tema_opciones, index=idx_tema, key="select_tema")
    if tema_sel != st.session_state.tema_seleccionado:
        guardar_tema(tema_sel)
        st.session_state.tema_seleccionado = tema_sel
        st.rerun()

    st.markdown("---")
    st.subheader("🔐 Usuario")
    if st.session_state.authenticated:
        st.success(f"✅ Conectado: {st.session_state.user_email}")
        if st.button("Cerrar Sesión", type="secondary", use_container_width=True):
            logout_user()
    else:
        show_login_form()
        st.info("💡 Inicia sesión para guardar tus datos")

# ─────────────────────────────────────────────────────────────────────────────
# PESTAÑAS PRINCIPALES  (se agrega tab6 = Descremado)
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📝 Registro de Tanques",
    "🔢 Calculadora Simple",
    "⚡ Optimización",
    "📜 Historial",
    "📋 Recetas",
    "🥛 Descremado",
])

# ═════════════════════════════════════════════════════════════════════════════
# MÓDULO 1 — REGISTRO DE TANQUES
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("📝 Registro de Tanques")
    st.markdown("Ingrese los datos del tanque para agregarlo al inventario")

    with st.form("form_agregar_tanque", clear_on_submit=True):
        st.markdown("### 📦 Nuevo Tanque")
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1: tanque  = st.text_input("🏷️ Nombre del tanque", placeholder="Ej: Tanque A-01")
        with col2: volumen = st.number_input("📊 Volumen disponible (L)", min_value=0.0, value=0.0, step=0.000001, format="%.6f")
        with col3: grasa   = st.number_input("🥛 Grasa (%)", min_value=0.0, max_value=100.0, value=3.5, step=0.000001, format="%.6f")
        st.markdown("---")
        col4, col5, col6 = st.columns([2, 2, 2])
        with col4: densidad   = st.number_input("⚖️ Densidad (kg/L)",   min_value=0.0, value=1.032,  step=0.000001, format="%.6f")
        with col5: crioscopia = st.number_input("❄️ Crioscopia (°C)",   value=-0.520, step=0.000001, format="%.6f")
        with col6: acidez     = st.number_input("🧪 Acidez (°D)",       min_value=0.0, value=16.0,  step=0.000001, format="%.6f")
        st.markdown(" ")
        col7, _ = st.columns([2, 4])
        with col7: costo = st.number_input("💰 Costo por litro ($/L)", min_value=0.0, value=0.0, step=0.000001, format="%.6f")
        st.markdown(" ")
        submitted = st.form_submit_button("➕ Agregar tanque", type="primary", use_container_width=True)
        if submitted:
            if not tanque.strip():
                st.error("⚠️ El nombre del tanque es obligatorio")
            elif volumen <= 0:
                st.error("⚠️ El volumen debe ser mayor a 0")
            else:
                tanque_id = agregar_tanque_db(tanque, volumen, grasa, densidad, crioscopia, acidez, costo)
                st.session_state.tanques.append({
                    "id": tanque_id, "Tanque": tanque, "Volumen": volumen,
                    "Grasa": grasa, "Densidad": densidad, "Crioscopia": crioscopia,
                    "Acidez": acidez, "Costo": costo,
                })
                st.success(f"✅ Tanque '{tanque}' agregado exitosamente")
                st.rerun()

    if st.session_state.tanques:
        st.markdown("---")
        st.subheader("📋 Inventario de Tanques")
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        with col_f1: filtro_nombre = st.text_input("🔍 Filtrar por nombre", placeholder="Buscar tanque...")
        with col_f2:
            tanques_opciones = ["Todos"] + list(set(t["Tanque"] for t in st.session_state.tanques))
            filtro_tanque    = st.selectbox("🏷️ Tanque específico", tanques_opciones)
        with col_f3:
            filtro_grasa = st.selectbox("🥛 Grasa", ["Todos", "> 3.5%", "< 3.5%", ">= 4.0%"])

        df_disp = pd.DataFrame(st.session_state.tanques)
        if filtro_nombre:            df_disp = df_disp[df_disp["Tanque"].str.contains(filtro_nombre, case=False, na=False)]
        if filtro_tanque != "Todos": df_disp = df_disp[df_disp["Tanque"] == filtro_tanque]
        if   filtro_grasa == "> 3.5%":  df_disp = df_disp[df_disp["Grasa"] > 3.5]
        elif filtro_grasa == "< 3.5%":  df_disp = df_disp[df_disp["Grasa"] < 3.5]
        elif filtro_grasa == ">= 4.0%": df_disp = df_disp[df_disp["Grasa"] >= 4.0]

        st.markdown("### ✏️ Editar directamente en la tabla")
        st.info("💡 Haz clic en cualquier celda para editar y luego presiona 'Guardar cambios'.")
        df_edit       = df_disp[["Tanque", "Volumen", "Grasa", "Densidad", "Crioscopia", "Acidez", "Costo"]].copy()
        column_config = {
            "Tanque"    : st.column_config.TextColumn("Tanque"),
            "Volumen"   : st.column_config.NumberColumn("Volumen (L)",    min_value=0,   step=0.000001, format="%.6f"),
            "Grasa"     : st.column_config.NumberColumn("Grasa (%)",      min_value=0,   max_value=100, step=0.000001, format="%.6f"),
            "Densidad"  : st.column_config.NumberColumn("Densidad (kg/L)", min_value=0,  step=0.000001, format="%.6f"),
            "Crioscopia": st.column_config.NumberColumn("Crioscopia (°C)",              step=0.000001, format="%.6f"),
            "Acidez"    : st.column_config.NumberColumn("Acidez (°D)",    min_value=0,   step=0.000001, format="%.6f"),
            "Costo"     : st.column_config.NumberColumn("Costo ($/L)",    min_value=0,   step=0.000001, format="%.6f"),
        }
        edited_df = st.data_editor(
            df_edit, column_config=column_config, hide_index=True,
            use_container_width=True, num_rows="fixed",
            key="editor_tanques", disabled=["Tanque"],
        )
        if st.button("💾 Guardar cambios de la tabla", type="primary"):
            cambios_guardados = 0; errores = 0
            for idx, row in edited_df.iterrows():
                for i, t in enumerate(st.session_state.tanques):
                    if t["Tanque"] == row["Tanque"]:
                        if (
                            abs(t["Volumen"]    - row["Volumen"])        > 0.01  or
                            abs(t["Grasa"]      - row["Grasa"])          > 0.01  or
                            abs(t["Densidad"]   - row["Densidad"])       > 0.001 or
                            abs(t["Crioscopia"] - row["Crioscopia"])     > 0.001 or
                            abs(t["Acidez"]     - row["Acidez"])         > 0.01  or
                            abs(t.get("Costo",0)- row.get("Costo", 0))  > 0.01
                        ):
                            if actualizar_tanque_db(
                                t["id"], t["Tanque"], row["Volumen"], row["Grasa"],
                                row["Densidad"], row["Crioscopia"], row["Acidez"],
                                row.get("Costo", 0),
                            ):
                                st.session_state.tanques[i].update({
                                    "Volumen": row["Volumen"], "Grasa": row["Grasa"],
                                    "Densidad": row["Densidad"], "Crioscopia": row["Crioscopia"],
                                    "Acidez": row["Acidez"], "Costo": row.get("Costo", 0),
                                })
                                cambios_guardados += 1
                            else:
                                errores += 1
                        break
            if   cambios_guardados > 0: st.success(f"✅ {cambios_guardados} tanque(s) actualizado(s)"); st.rerun()
            elif errores           > 0: st.error(f"❌ Error al actualizar {errores} tanque(s)")
            else:                       st.info("ℹ️ No se detectaron cambios")

        st.markdown("---")
        st.subheader("🗑️ Eliminar Tanque")
        tanques_nombres   = [t["Tanque"] for t in st.session_state.tanques]
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1: tanque_a_eliminar = st.selectbox("Seleccionar tanque a eliminar", tanques_nombres)
        with col_del2:
            st.markdown(" "); st.markdown(" ")
            if st.button("🗑️ Eliminar", type="primary", use_container_width=True):
                tanque_data = next((t for t in st.session_state.tanques if t["Tanque"] == tanque_a_eliminar), None)
                if tanque_data:
                    if eliminar_tanque_db(tanque_data["id"]):
                        st.session_state.tanques = [t for t in st.session_state.tanques if t["id"] != tanque_data["id"]]
                        st.success("✅ Tanque eliminado exitosamente")
                        st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# MÓDULO 2 — CALCULADORA SIMPLE
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("🔢 Calculadora de Promedios")
    if st.session_state.tanques:
        df        = pd.DataFrame(st.session_state.tanques)
        total_vol = df["Volumen"].sum()
        st.metric("Grasa promedio",      f"{(df['Volumen']*df['Grasa']).sum()/total_vol:.2f}%"      if total_vol > 0 else "—")
        st.metric("Densidad promedio",   f"{(df['Volumen']*df['Densidad']).sum()/total_vol:.3f} kg/L" if total_vol > 0 else "—")
        st.metric("Crioscopia promedio", f"{(df['Volumen']*df['Crioscopia']).sum()/total_vol:.3f} °C" if total_vol > 0 else "—")
        st.metric("Acidez promedio",     f"{(df['Volumen']*df['Acidez']).sum()/total_vol:.2f} °D"    if total_vol > 0 else "—")
    else:
        st.info("No hay tanques registrados")

# ═════════════════════════════════════════════════════════════════════════════
# MÓDULO 3 — OPTIMIZACIÓN INDUSTRIAL
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("⚡ Optimización Inteligente de Mezcla (Balance de Masas)")
    st.info("💡 Este motor utiliza balance de masas (kg) para garantizar precisión <0.01% en grasa y sólidos.")

    # Asistente IA
    with st.expander("🤖 Consultar Asistente IA", expanded=False):
        st.caption("Conecta con el agente de IA para consultas sobre formulación de mezclas y control industrial.")
        chat_container = st.container(height=450)
        with chat_container:
            if not st.session_state.ws_chat_history:
                st.info("👋 **¡Hola! Soy tu asistente IA experto en formulación de mezclas y control industrial.**\n\nEscribe tu consulta abajo para empezar.")
            else:
                for msg in st.session_state.ws_chat_history:
                    avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
                    with st.chat_message(msg["role"], avatar=avatar):
                        st.markdown(msg["content"])
        col_inp, col_send = st.columns([6, 1])
        with col_inp:
            user_input = st.text_area(
                "Tu mensaje", key="ws_input", label_visibility="collapsed",
                placeholder="Escribe aquí tu duda...", height=50,
            )
        with col_send:
            send_clicked = st.button("📤 Enviar", key="ws_send", type="primary", use_container_width=True)
        col_clear, _ = st.columns([2, 5])
        with col_clear:
            if st.session_state.ws_chat_history:
                if st.button("🗑️ Limpiar historial", key="ws_clear", type="secondary", use_container_width=True):
                    st.session_state.ws_chat_history = []
                    st.rerun()
        if send_clicked and user_input.strip():
            st.session_state.ws_chat_history.append({"role": "user", "content": user_input})
            with st.spinner("🤔 Pensando..."):
                respuesta = enviar_mensaje_ws(user_input)
            st.session_state.ws_chat_history.append({"role": "assistant", "content": respuesta})
            st.rerun()

    st.markdown("---")

    if not st.session_state.tanques:
        st.warning("⚠️ No hay tanques disponibles. Registre inventario primero en '📝 Registro de Tanques'.")
        st.stop()

    tanques_frescos = cargar_tanques_db()
    st.session_state.tanques = tanques_frescos
    df = pd.DataFrame(st.session_state.tanques)
    if df.empty:
        st.info("No hay datos para procesar.")
        st.stop()

    df["Masa_Disponible_Kg"] = df["Volumen"] * df["Densidad"]
    df["Masa_Grasa_Kg"]      = df["Masa_Disponible_Kg"] * (df["Grasa"] / 100.0)
    df["Masa_Crio_Ref"]      = df["Masa_Disponible_Kg"] * df["Crioscopia"]
    df["Masa_Acidez_Ref"]    = df["Masa_Disponible_Kg"] * df["Acidez"]
    df["Costo_Por_Kg"]       = df["Costo"] / df["Densidad"]
    df["Score"]              = df["Grasa"] * 2 + df["Costo_Por_Kg"] * 0.5 - df["Densidad"] * 1

    st.subheader("⚙️ Configuración de Producción")
    col_conf1, col_conf2 = st.columns(2)
    with col_conf2:
        modo = st.radio("🤖 Estrategia de Optimización", ["Manual (Fijo)", "Automático con Recetas"], horizontal=True, key="modo_radio")
        receta_seleccionada = None
        if modo == "Automático con Recetas":
            if st.session_state.get("recetas"):
                recetas_opciones = ["Sin receta (rangos industriales)"] + [r["nombre"] for r in st.session_state.recetas]
                receta_seleccionada = st.selectbox("📋 Seleccionar Receta Predefinida", recetas_opciones, key="selector_receta_opt")
            else:
                st.warning("⚠️ No hay recetas disponibles. Crea recetas en la pestaña '📋 Recetas'")
    with col_conf1:
        volumen_obj_L = st.number_input("🎯 Volumen a Producir (Litros)", min_value=100.0, value=10000.0, step=0.000001, format="%.6f")
        if modo == "Automático con Recetas" and receta_seleccionada and receta_seleccionada != "Sin receta (rangos industriales)":
            grasa_obj = 0.0; densidad_obj_est = 1.032; crio_obj = -0.520; acidez_obj = 16.0
        else:
            col_obj1, col_obj2 = st.columns(2)
            with col_obj1:
                grasa_obj       = st.number_input("🥛 Grasa Objetivo (%)",          min_value=0.1, max_value=10.0, value=3.2,    step=0.000001, format="%.6f")
                densidad_obj_est = st.number_input("⚖️ Densidad Estimada (kg/L)",   min_value=1.020, max_value=1.040, value=1.032, step=0.000001, format="%.6f")
            with col_obj2:
                crio_obj   = st.number_input("❄️ Crioscopia Objetivo (°C)", value=-0.520, step=0.000001, format="%.6f")
                acidez_obj = st.number_input("🧪 Acidez Objetivo (°D)",     value=16.0,  step=0.000001, format="%.6f")

    # Rangos
    if modo == "Manual (Fijo)":
        col_tol1, col_tol2 = st.columns(2)
        with col_tol1:
            tol_grasa   = st.number_input("Tolerancia Grasa (±%)",          value=0.05,  step=0.000001, min_value=0.000001, format="%.6f")
            tol_densidad = st.number_input("Tolerancia Densidad (±kg/L)",   value=0.001, step=0.000001, min_value=0.000001, format="%.6f")
        with col_tol2:
            tol_crio   = st.number_input("Tolerancia Crioscopia (±°C)",     value=0.005, step=0.000001, min_value=0.000001, format="%.6f")
            tol_acidez = st.number_input("Tolerancia Acidez (±°D)",         value=0.5,   step=0.000001, min_value=0.000001, format="%.6f")
        g_min, g_max = grasa_obj - tol_grasa,      grasa_obj + tol_grasa
        d_min, d_max = densidad_obj_est - tol_densidad, densidad_obj_est + tol_densidad
        c_min, c_max = crio_obj - tol_crio,        crio_obj + tol_crio
        a_min, a_max = acidez_obj - tol_acidez,    acidez_obj + tol_acidez
    else:
        receta_seleccionada_widget = st.session_state.get("selector_receta_opt", None)
        receta_usada = None
        if st.session_state.get("recetas") and receta_seleccionada_widget and receta_seleccionada_widget != "Sin receta (rangos industriales)":
            receta_usada = next((r for r in st.session_state.recetas if r["nombre"] == receta_seleccionada_widget), None)
        if receta_usada:
            g_min, g_max = float(receta_usada["grasa_min"]),      float(receta_usada["grasa_max"])
            d_min, d_max = float(receta_usada["densidad_min"]),   float(receta_usada["densidad_max"])
            c_min, c_max = float(receta_usada["crioscopia_min"]), float(receta_usada["crioscopia_max"])
            a_min, a_max = float(receta_usada["acidez_min"]),     float(receta_usada["acidez_max"])
            st.success(f"📋 **Receta '{receta_usada['nombre']}' aplicada**")
            with st.expander("📊 Ver parámetros de receta cargados", expanded=True):
                st.write(f"• Grasa: `{g_min}-{g_max}%`")
                st.write(f"• Densidad: `{d_min}-{d_max} kg/L`")
                st.write(f"• Crioscopia: `{c_min}-{c_max} °C`")
                st.write(f"• Acidez: `{a_min}-{a_max} °D`")
        else:
            g_min, g_max = 3.0, 3.4; d_min, d_max = 1.030, 1.034; c_min, c_max = -0.530, -0.510; a_min, a_max = 15.0, 18.0
            st.info("🤖 **Modo Flexible:** Usando rangos industriales estándar")
            with st.expander("📊 Ver rangos automáticos aplicados"):
                st.write(f"• Grasa: `{g_min}-{g_max}%` | Densidad: `{d_min}-{d_max} kg/L`")
                st.write(f"• Crioscopia: `{c_min}-{c_max} °C` | Acidez: `{a_min}-{a_max} °D`")

    masa_total_disponible = df["Masa_Disponible_Kg"].sum()
    masa_objetivo_Kg      = volumen_obj_L * densidad_obj_est if modo == "Manual (Fijo)" else volumen_obj_L * 1.032
    if masa_objetivo_Kg > masa_total_disponible * 0.99:
        st.error(f"❌ **Insuficiente materia prima** | Requerido: `{masa_objetivo_Kg:,.2f} kg` | Disponible: `{masa_total_disponible:,.2f} kg`")
        st.stop()

    st.markdown("---")

    # Aditivos
    df_aditivos = None
    with st.expander("🧂 Adición de Sólidos y Aditivos (Opcional)", expanded=False):
        st.caption("Define los insumos a incorporar.")
        usar_aditivos = st.checkbox("✅ Activar adición de sólidos y aditivos", value=False, key="chk_aditivos")
    
        if usar_aditivos:
            default_aditivos = [
                {"nombre": "Leche en Polvo Entera",    "costo_kg": 3.50, "limite_max_kg": 50.0, "grasa_kg": 0.10, "densidad_kg": 1.314,"crio_kg": -4.84, "acidez_kg": 11.4},
                {"nombre": "Leche en Polvo Descremada","costo_kg": 3.20, "limite_max_kg": 50.0, "grasa_kg": 0.01, "densidad_kg": 1.314,"crio_kg": -0.515, "acidez_kg": 17.0},
                {"nombre": "Fosfatos / Sales",         "costo_kg": 8.00, "limite_max_kg":  5.0, "grasa_kg": 0.00, "densidad_kg": 0.000,"crio_kg": -0.530, "acidez_kg": 14.0},
                {"nombre": "Estabilizantes",           "costo_kg":12.00, "limite_max_kg":  2.0, "grasa_kg": 0.00, "densidad_kg": 0.000,"crio_kg": -0.500, "acidez_kg": 15.0},
            ]
            _df_aditivos = st.data_editor(
                pd.DataFrame(default_aditivos), num_rows="dynamic", use_container_width=True,
                column_config={
                    "nombre"        : "Nombre",
                    "costo_kg"      : st.column_config.NumberColumn("Costo $/kg"),
                    "limite_max_kg" : st.column_config.NumberColumn("Máx kg"),
                    "grasa_kg"      : st.column_config.NumberColumn("Fracción grasa/kg"),
                    "densidad_kg"   : st.column_config.NumberColumn("Densidad kg/L"),
                    "crio_kg"       : st.column_config.NumberColumn("Contribución Crio/kg"),
                    "acidez_kg"     : st.column_config.NumberColumn("Contribución Acidez/kg"),
                },
                key="editor_aditivos",
            )
            if _df_aditivos is not None and not _df_aditivos.empty:
                df_aditivos = _df_aditivos[_df_aditivos["nombre"].notna() & (_df_aditivos["nombre"] != "")]
        else:
            st.info("☝️ Activa la opción de arriba para incluir sólidos o aditivos en la mezcla.")

    if st.button("🚀 Calcular Mezcla Óptima", type="primary", use_container_width=True):
        with st.spinner("🔍 Resolviendo modelo de programación lineal..."):
            resultado_opt = optimizar_mezcla(
                df, volumen_obj_L,
                g_min, g_max, d_min, d_max, c_min, c_max, a_min, a_max,
                aditivos=df_aditivos,
            )

        if resultado_opt["status"] != "Optimal":
            if "error" in resultado_opt and "Insuficiente" in resultado_opt.get("error", ""):
                st.error(f"❌ **{resultado_opt['error']}**")
                st.write(f"- Masa requerida: `{resultado_opt['masa_requerida']:,.2f} kg`")
                st.write(f"- Masa disponible: `{resultado_opt['masa_disponible']:,.2f} kg`")
            else:
                st.error(f"❌ **No se encontró solución factible**\n\nEstado: `{resultado_opt['status']}`")
            st.stop()

        resultados = resultado_opt["resultados"]
        metricas   = resultado_opt["metricas"]

        grasa_final_pct    = float(metricas["grasa_final"])
        crio_final         = float(metricas["crioscopia_final"])
        acidez_final       = float(metricas["acidez_final"])
        densidad_final_est = float(metricas["densidad_final"])
        costo_grand_total  = float(metricas["costo_total"])
        tanques_activos    = int(metricas["tanques_activos"])
        slack_min_v        = float(metricas["slack_min_acidez"])
        slack_max_v        = float(metricas["slack_max_acidez"])

        st.success(f"✅ **Solución Óptima** | Tanques/Insumos: `{tanques_activos}`")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("📊 Volumen Final",   f"{volumen_obj_L:,.1f} L")
            st.metric("⚖️ Masa Total",      f"{metricas['masa_total']:,.1f} kg")
        with c2:
            st.metric("🥛 Grasa Resultante", f"{grasa_final_pct:.3f}%")
            st.metric("⚖️ Densidad Est.",    f"{densidad_final_est:.4f} kg/L")
        with c3:
            st.metric("❄️ Crioscopia",       f"{crio_final:.4f} °C")
            st.metric("🧪 Acidez",           f"{acidez_final:.2f} °D")

        st.markdown("### 📋 Orden de Bombeo / Dosificación")
        if resultados:
            st.dataframe(
                pd.DataFrame(resultados).style.format({
                    "Litros a Bombear": "{:,.2f}",
                    "Masa (kg)"       : "{:,.2f}",
                    "Costo Parcial"   : "${:,.2f}",
                }),
                use_container_width=True, hide_index=True,
            )

        st.markdown("### 💰 Análisis de Costos")
        ec1, ec2 = st.columns(2)
        with ec1:
            st.write(f"**🥛 Costo Materia Prima:** `${metricas['costo_materia_prima']:,.2f}`")
            st.write(f"**🧼 Costo Limpiezas (CIP):** `${metricas['costo_limpiezas']:,.2f}` ({tanques_activos} tanque(s))")
        with ec2:
            st.metric("💵 Costo Total",    f"${costo_grand_total:,.2f}")
            st.metric("📈 Costo Unitario", f"${metricas['costo_unitario']:.4f}/L")

        alertas = []
        if not (g_min <= grasa_final_pct <= g_max):  alertas.append(f"⚠️ Grasa ({grasa_final_pct:.2f}%) fuera de rango [{g_min}-{g_max}%]")
        if not (c_min <= crio_final      <= c_max):  alertas.append(f"⚠️ Crioscopia ({crio_final:.3f}°C) fuera de rango")
        if not (a_min <= acidez_final    <= a_max):  alertas.append(f"⚠️ Acidez ({acidez_final:.1f}°D) fuera de rango")
        if crio_final > -0.510:                       alertas.append("🚨 **ALERTA CRÍTICA**: Crioscopia > -0.510°C — Riesgo de adulteración con agua")
        if densidad_final_est < 1.028 or densidad_final_est > 1.036:
            alertas.append(f"⚠️ Densidad ({densidad_final_est:.4f}) fuera de rango industrial [1.028-1.036]")

        if alertas:
            with st.expander("🚨 Alertas de Calidad", expanded=True):
                for a in alertas: st.warning(a)
        else:
            st.success("✅ Todos los parámetros dentro de rangos aceptables")

        st.markdown("---")
        st.info("⚠️ La optimización es un cálculo teórico. Confirma si afectará el inventario.")
        afectacion = st.radio(
            "📦 ¿Esta optimización afectará el inventario?",
            ["No, solo es un cálculo teórico", "Sí, se procederá a bombear los tanques"],
            index=0, key="afectacion_inventario",
        )
        if afectacion == "Sí, se procederá a bombear los tanques":
            st.warning("🚨 Se descontarán los litros calculados. Esta acción no se puede deshacer.")
            total_desc = sum(r["Litros a Bombear"] for r in resultados)
            st.write(f"**Total a descontar:** `{total_desc:,.2f} L`")
            confirmar = st.checkbox("✓ Confirmo que se bombearán los tanques", key="confirmar_bombeo")
            if confirmar:
                if st.button("🔴 ACTUALIZAR INVENTARIO AHORA", type="primary", key="btn_actualizar_inventario"):
                    with st.spinner("⏳ Actualizando inventario..."):
                        if actualizar_inventario_tanques(resultados):
                            st.balloons()
                            st.success("✅ Inventario actualizado correctamente")
                            st.session_state.tanques = cargar_tanques_db()
                            st.rerun()
                        else:
                            st.error("❌ Error al actualizar inventario")

        st.markdown("---")
        if st.button("💾 Guardar en Historial", type="secondary"):
            resultados_db = []
            for r in resultados:
                td = next((t for t in st.session_state.tanques if t["Tanque"] == r["Tanque"]), None)
                resultados_db.append({
                    "tanque_id"  : td["id"] if td and "id" in td else None,
                    "Litros usados": r["Litros a Bombear"],
                    "tanque"     : r["Tanque"],
                })
            if guardar_estandarizacion_db(volumen_obj_L, grasa_final_pct, densidad_final_est, crio_final, acidez_final, resultados_db):
                st.success("✅ Estandarización guardada en el historial")
                st.session_state.historial = cargar_historial_db()
            else:
                st.error("❌ Error al guardar en la base de datos")

# ═════════════════════════════════════════════════════════════════════════════
# MÓDULO 4 — HISTORIAL
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("📜 Historial de Estandarizaciones")
    if st.session_state.historial:
        st.dataframe(pd.DataFrame(st.session_state.historial), use_container_width=True)
    else:
        st.info("No hay operaciones en el historial")

# ═════════════════════════════════════════════════════════════════════════════
# MÓDULO 5 — RECETAS
# ═════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("📋 Recetas de Estandarización")
    st.markdown("Administra las recetas o parámetros predefinidos para la optimización")

    with st.expander("➕ Agregar Nueva Receta", expanded=False):
        with st.form("form_agregar_receta", clear_on_submit=True):
            col1, col2 = st.columns([3, 3])
            with col1:
                nombre_receta      = st.text_input("🏷️ Nombre de la receta", placeholder="Ej: Leche Entera Estándar")
                descripcion_receta = st.text_area("📝 Descripción", placeholder="Descripción opcional")
                volumen_receta     = st.number_input("📊 Volumen por defecto (L)", value=10000.0, step=0.0001, format="%.4f")
            with col2:
                st.markdown("**🥛 Grasa (%)** &emsp;|&emsp; **⚖️ Densidad (kg/L)**")
                cg1, cg2, cd1, cd2 = st.columns(4)
                grasa_min_rec    = cg1.number_input("Min", value=3.0,   step=0.000001, format="%.6f", key="g_min_new")
                grasa_max_rec    = cg2.number_input("Max", value=3.5,   step=0.000001, format="%.6f", key="g_max_new")
                densidad_min_rec = cd1.number_input("Min", value=1.030, step=0.000001, format="%.6f", key="d_min_new")
                densidad_max_rec = cd2.number_input("Max", value=1.033, step=0.000001, format="%.6f", key="d_max_new")
                st.markdown("**❄️ Crioscopia (°C)** &emsp;|&emsp; **🧪 Acidez (°D)**")
                cc1, cc2, ca1, ca2 = st.columns(4)
                crioscopia_min_rec = cc1.number_input("Min", value=-0.530, step=0.000001, format="%.6f", key="c_min_new")
                crioscopia_max_rec = cc2.number_input("Max", value=-0.510, step=0.000001, format="%.6f", key="c_max_new")
                acidez_min_rec     = ca1.number_input("Min", value=14.0,   step=0.000001, format="%.6f", key="a_min_new")
                acidez_max_rec     = ca2.number_input("Max", value=18.0,   step=0.000001, format="%.6f", key="a_max_new")
            submitted_receta = st.form_submit_button("💾 Guardar Receta", type="primary", use_container_width=True)
            if submitted_receta:
                if not nombre_receta.strip():
                    st.error("⚠️ El nombre de la receta es obligatorio")
                else:
                    rid = agregar_receta_db(
                        nombre_receta, descripcion_receta,
                        grasa_min_rec, grasa_max_rec, densidad_min_rec, densidad_max_rec,
                        crioscopia_min_rec, crioscopia_max_rec, acidez_min_rec, acidez_max_rec,
                        volumen_receta,
                    )
                    if rid:
                        st.session_state.recetas.append({
                            "id": rid, "nombre": nombre_receta, "descripcion": descripcion_receta,
                            "grasa_min": grasa_min_rec, "grasa_max": grasa_max_rec,
                            "densidad_min": densidad_min_rec, "densidad_max": densidad_max_rec,
                            "crioscopia_min": crioscopia_min_rec, "crioscopia_max": crioscopia_max_rec,
                            "acidez_min": acidez_min_rec, "acidez_max": acidez_max_rec,
                            "volumen_default": volumen_receta,
                        })
                        st.success(f"✅ Receta '{nombre_receta}' guardada exitosamente")
                        st.rerun()

    if st.session_state.recetas:
        st.markdown("---")
        st.subheader("📋 Recetas Guardadas")
        for receta in st.session_state.recetas:
            with st.expander(f"📌 {receta['nombre']}"):
                tab_ver, tab_editar = st.tabs(["👁️ Ver Detalles", "✏️ Editar Receta"])
                with tab_ver:
                    col_r1, col_r2 = st.columns([3, 1])
                    with col_r1:
                        if receta.get("descripcion"): st.write(f"📝 {receta['descripcion']}")
                        st.markdown(f"**Volumen por defecto:** {receta['volumen_default']} L")
                        st.markdown("**Parámetros:**")
                        st.write(f"- Grasa: {receta['grasa_min']}% – {receta['grasa_max']}%")
                        st.write(f"- Densidad: {receta['densidad_min']} – {receta['densidad_max']} kg/L")
                        st.write(f"- Crioscopia: {receta['crioscopia_min']} a {receta['crioscopia_max']} °C")
                        st.write(f"- Acidez: {receta['acidez_min']} – {receta['acidez_max']} °D")
                    with col_r2:
                        st.markdown(" ")
                        if st.button("🗑️ Eliminar", key=f"elim_receta_{receta['id']}", type="secondary"):
                            if eliminar_receta_db(receta["id"]):
                                st.session_state.recetas = [r for r in st.session_state.recetas if r["id"] != receta["id"]]
                                st.success("✅ Receta eliminada")
                                st.rerun()
                with tab_editar:
                    with st.form(f"form_editar_{receta['id']}", clear_on_submit=False):
                        ce1, ce2 = st.columns([3, 3])
                        with ce1:
                            e_nombre = st.text_input("🏷️ Nombre", value=receta["nombre"],              key=f"e_nom_{receta['id']}")
                            e_desc   = st.text_area("📝 Descripción", value=receta.get("descripcion",""), key=f"e_desc_{receta['id']}")
                            e_vol    = st.number_input("📊 Volumen (L)", value=float(receta.get("volumen_default",10000.0)), step=0.000001, format="%.6f", key=f"e_vol_{receta['id']}")
                        with ce2:
                            st.markdown("**🥛 Grasa (%)** &emsp;|&emsp; **⚖️ Densidad (kg/L)**")
                            eg1, eg2, ed1, ed2 = st.columns(4)
                            e_gmin = eg1.number_input("Min", value=float(receta["grasa_min"]),     step=0.000001, format="%.6f", key=f"e_gmin_{receta['id']}")
                            e_gmax = eg2.number_input("Max", value=float(receta["grasa_max"]),     step=0.000001, format="%.6f", key=f"e_gmax_{receta['id']}")
                            e_dmin = ed1.number_input("Min", value=float(receta["densidad_min"]), step=0.000001, format="%.6f", key=f"e_dmin_{receta['id']}")
                            e_dmax = ed2.number_input("Max", value=float(receta["densidad_max"]), step=0.000001, format="%.6f", key=f"e_dmax_{receta['id']}")
                            st.markdown("**❄️ Crioscopia (°C)** &emsp;|&emsp; **🧪 Acidez (°D)**")
                            ec1, ec2, ea1, ea2 = st.columns(4)
                            e_cmin = ec1.number_input("Min", value=float(receta["crioscopia_min"]), step=0.000001, format="%.6f", key=f"e_cmin_{receta['id']}")
                            e_cmax = ec2.number_input("Max", value=float(receta["crioscopia_max"]), step=0.000001, format="%.6f", key=f"e_cmax_{receta['id']}")
                            e_amin = ea1.number_input("Min", value=float(receta["acidez_min"]),    step=0.000001, format="%.6f", key=f"e_amin_{receta['id']}")
                            e_amax = ea2.number_input("Max", value=float(receta["acidez_max"]),    step=0.000001, format="%.6f", key=f"e_amax_{receta['id']}")
                        btn_guardar = st.form_submit_button("✅ Guardar Cambios", type="primary", use_container_width=True)
                        if btn_guardar:
                            if not e_nombre.strip():
                                st.error("⚠️ El nombre es obligatorio")
                            else:
                                if actualizar_receta_db(
                                    receta["id"], e_nombre, e_desc,
                                    e_gmin, e_gmax, e_dmin, e_dmax,
                                    e_cmin, e_cmax, e_amin, e_amax, e_vol,
                                ):
                                    st.success("✅ Cambios guardados.")
                                    st.session_state.recetas = cargar_recetas_db()
                                    st.rerun()
                                else:
                                    st.error("❌ Error guardando. Revisa conexión a la base de datos.")
    else:
        st.info("No hay recetas guardadas. Crea una nueva receta arriba.")

# ═════════════════════════════════════════════════════════════════════════════
# MÓDULO 6 — DESCREMADO  🥛
# ═════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("🥛 Proceso de Descremado — Clarificador Centrífugo")
    st.info(
        f"💡 Capacidad del clarificador: **{CLARIFIER_RATE_L_H} L crema/hora** | "
        f"Grasa residual leche descremada: **0.05%** | "
        f"Rango grasa leche: **{FAT_LECHE_MIN}%–{FAT_LECHE_MAX}%** | "
        f"Rango grasa crema: **{FAT_CREMA_MIN}%–{FAT_CREMA_MAX}%**"
    )

    if not st.session_state.tanques:
        st.warning("⚠️ No hay tanques disponibles. Registre inventario en '📝 Registro de Tanques'.")
        st.stop()

    # ── Pestañas internas ────────────────────────────────────────────────────
    desc_tab1, desc_tab2, desc_tab3 = st.tabs([
        "🔢 Calculadora Rápida",
        "⚡ Optimización de Descremado",
        "📐 Fórmula y Referencia",
    ])

    # ════════════════════════════════════════════════════════
    # SUB-TAB 1 — Calculadora Rápida (sin inventario)
    # ════════════════════════════════════════════════════════
    with desc_tab1:
        st.subheader("🔢 Calculadora Rápida de Balance de Materia Grasa")
        st.markdown("Calcula directamente sin afectar el inventario de tanques.")

        modo_calc = st.radio(
            "Dirección del cálculo",
            ["🔜 Leche disponible → Crema obtenida", "🔛 Crema deseada → Leche necesaria"],
            horizontal=True, key="modo_calc_desc",
        )
        st.markdown("---")

        if modo_calc == "🔜 Leche disponible → Crema obtenida":
            col_a, col_b = st.columns(2)
            with col_a:
                vol_leche_calc = st.number_input(
                    "📊 Volumen de leche disponible (L)",
                    min_value=1.0, value=10000.0, step=100.0, format="%.1f",
                    key="calc_vol_leche",
                )
                fat_leche_calc = st.slider(
                    f"🥛 % Grasa de la leche [{FAT_LECHE_MIN}–{FAT_LECHE_MAX}%]",
                    min_value=FAT_LECHE_MIN, max_value=FAT_LECHE_MAX,
                    value=3.7, step=0.1, key="calc_fat_leche",
                )
            with col_b:
                fat_crema_calc = st.slider(
                    f"🧈 % Grasa objetivo en crema [{FAT_CREMA_MIN}–{FAT_CREMA_MAX}%]",
                    min_value=FAT_CREMA_MIN, max_value=FAT_CREMA_MAX,
                    value=45.0, step=1.0, key="calc_fat_crema_f",
                )

            if st.button("▶️ Calcular", type="primary", key="btn_calc_forward"):
                try:
                    r = calcular_crema(vol_leche_calc, fat_leche_calc, fat_crema_calc)
                    st.success("✅ Cálculo completado")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🧈 Crema obtenida",        f"{r['vol_crema_L']:,.1f} L")
                    m2.metric("🥛 Leche descremada",      f"{r['vol_descremada_L']:,.1f} L")
                    m3.metric("⏱️ Tiempo clarificación",  _fmt_tiempo(r["tiempo_h"]))
                    m4.metric("📈 Rendimiento",           f"{r['rendimiento_pct']:.2f}%")
                    st.markdown("**Resumen del balance:**")
                    st.write(
                        f"De **{r['vol_leche_L']:,.1f} L** de leche cruda al **{r['fat_leche_pct']}% grasa** → "
                        f"**{r['vol_crema_L']:,.1f} L** crema ({r['fat_crema_pct']}% grasa) + "
                        f"**{r['vol_descremada_L']:,.1f} L** leche descremada ({r['fat_descremada_pct']}% grasa)"
                    )
                except ValueError as e:
                    st.error(f"❌ {e}")

        else:  # Crema → Leche
            col_a, col_b = st.columns(2)
            with col_a:
                vol_crema_calc = st.number_input(
                    "🧈 Volumen de crema requerido (L)",
                    min_value=1.0, value=800.0, step=50.0, format="%.1f",
                    key="calc_vol_crema",
                )
                fat_crema_calc2 = st.slider(
                    f"🧈 % Grasa objetivo en crema [{FAT_CREMA_MIN}–{FAT_CREMA_MAX}%]",
                    min_value=FAT_CREMA_MIN, max_value=FAT_CREMA_MAX,
                    value=45.0, step=1.0, key="calc_fat_crema_b",
                )
            with col_b:
                fat_leche_calc2 = st.slider(
                    f"🥛 % Grasa de la leche disponible [{FAT_LECHE_MIN}–{FAT_LECHE_MAX}%]",
                    min_value=FAT_LECHE_MIN, max_value=FAT_LECHE_MAX,
                    value=3.7, step=0.1, key="calc_fat_leche_b",
                )

            if st.button("▶️ Calcular", type="primary", key="btn_calc_backward"):
                try:
                    r = calcular_leche(vol_crema_calc, fat_crema_calc2, fat_leche_calc2)
                    st.success("✅ Cálculo completado")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("🥛 Leche necesaria",      f"{r['vol_leche_L']:,.1f} L")
                    m2.metric("🥛 Leche descremada",     f"{r['vol_descremada_L']:,.1f} L")
                    m3.metric("⏱️ Tiempo clarificación", _fmt_tiempo(r["tiempo_h"]))
                    m4.metric("📈 Rendimiento",          f"{r['rendimiento_pct']:.2f}%")
                    st.markdown("**Resumen del balance:**")
                    st.write(
                        f"Para obtener **{r['vol_crema_L']:,.1f} L** de crema al **{r['fat_crema_pct']}% grasa** "
                        f"se necesitan **{r['vol_leche_L']:,.1f} L** de leche cruda al **{r['fat_leche_pct']}% grasa**. "
                        f"Leche descremada resultante: **{r['vol_descremada_L']:,.1f} L** ({r['fat_descremada_pct']}% grasa)."
                    )
                except ValueError as e:
                    st.error(f"❌ {e}")

    # ════════════════════════════════════════════════════════
    # SUB-TAB 2 — Optimización de Descremado con inventario
    # ════════════════════════════════════════════════════════
    with desc_tab2:
        st.subheader("⚡ Optimización de Descremado con Inventario")
        st.markdown(
            "Selecciona automáticamente la **combinación óptima de tanques** "
            "para producir el volumen de crema deseado al menor costo."
        )

        # Refrescar inventario
        tanques_desc = cargar_tanques_db()
        st.session_state.tanques = tanques_desc
        df_desc = pd.DataFrame(st.session_state.tanques)

        if df_desc.empty:
            st.warning("⚠️ No hay tanques en el inventario.")
            st.stop()

        df_desc["Masa_Disponible_Kg"] = df_desc["Volumen"] * df_desc["Densidad"]
        df_desc["Costo_Por_Kg"]       = df_desc["Costo"] / df_desc["Densidad"].replace(0, 1.032)

        # Mostrar inventario disponible
        with st.expander("📋 Ver inventario de tanques disponibles", expanded=False):
            cols_show = ["Tanque", "Volumen", "Grasa", "Densidad", "Costo"]
            st.dataframe(
                df_desc[cols_show].style.format({
                    "Volumen" : "{:,.1f} L",
                    "Grasa"   : "{:.2f}%",
                    "Densidad": "{:.3f} kg/L",
                    "Costo"   : "${:.2f}/L",
                }),
                use_container_width=True, hide_index=True,
            )
            grasa_prom_inv = (
                (df_desc["Volumen"] * df_desc["Grasa"]).sum() / df_desc["Volumen"].sum()
                if df_desc["Volumen"].sum() > 0 else 0
            )
            st.info(
                f"📊 **Inventario total:** `{df_desc['Volumen'].sum():,.1f} L` | "
                f"**Grasa promedio ponderada:** `{grasa_prom_inv:.2f}%`"
            )

        st.markdown("---")
        st.markdown("### ⚙️ Parámetros del Proceso de Descremado")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            vol_crema_opt = st.number_input(
                "🧈 Volumen de crema a producir (L)",
                min_value=1.0, value=800.0, step=50.0, format="%.1f",
                key="opt_vol_crema",
            )
        with col_d2:
            fat_crema_opt = st.slider(
                f"🧈 % Grasa objetivo en crema [{FAT_CREMA_MIN}–{FAT_CREMA_MAX}%]",
                min_value=FAT_CREMA_MIN, max_value=FAT_CREMA_MAX,
                value=40.0, step=1.0, key="opt_fat_crema",
            )

        # Estimación previa
        Gc_est = fat_crema_opt / 100
        Gs_est = 0.05          / 100
        df_validos = df_desc[df_desc["Grasa"] / 100 > Gs_est].copy()
        if not df_validos.empty:
            crema_max_est = (df_validos["Volumen"] * (df_validos["Grasa"] / 100 - Gs_est) / (Gc_est - Gs_est)).sum()
            leche_total_est = df_desc["Volumen"].sum()
            col_e1, col_e2, col_e3 = st.columns(3)
            col_e1.metric("🧈 Crema máx. posible",  f"{crema_max_est:,.1f} L")
            col_e2.metric("🥛 Leche total disponible", f"{leche_total_est:,.1f} L")
            col_e3.metric("⏱️ Tiempo estimado",
                         _fmt_tiempo(vol_crema_opt / CLARIFIER_RATE_L_H)
                         if vol_crema_opt <= crema_max_est else "N/D")
            if vol_crema_opt > crema_max_est * 0.99:
                st.error(
                    f"❌ La crema requerida ({vol_crema_opt:,.1f} L) supera la capacidad "
                    f"máxima ({crema_max_est:,.1f} L). Reduzca el volumen o agregue más materia prima."
                )
        else:
            st.error("❌ Ningún tanque tiene grasa suficiente para este proceso de descremado.")

        st.markdown("---")
        if st.button("🚀 Optimizar Descremado", type="primary", use_container_width=True, key="btn_opt_desc"):
            with st.spinner("🔍 Resolviendo optimización de descremado..."):
                res_desc = optimizar_descremado(df_desc, vol_crema_opt, fat_crema_opt)

            if res_desc["status"] != "Optimal":
                st.error(f"❌ **{res_desc.get('error', 'No se encontró solución')}**")
                if "crema_posible_L" in res_desc:
                    st.write(f"- Crema posible: `{res_desc['crema_posible_L']:,.2f} L`")
                    st.write(f"- Crema requerida: `{res_desc['crema_requerida_L']:,.2f} L`")
            else:
                met = res_desc["metricas_descremado"]
                st.success(
                    f"✅ **Solución Óptima de Descremado** | "
                    f"Tanques seleccionados: `{met['tanques_usados']}`"
                )

                # Métricas principales
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("🥛 Leche a procesar",   f"{met['vol_leche_total_L']:,.1f} L")
                m2.metric("🧈 Crema producida",     f"{met['vol_crema_total_L']:,.1f} L",  f"{met['fat_crema_pct']}% grasa")
                m3.metric("🥛 Leche descremada",    f"{met['vol_descremada_total_L']:,.1f} L", f"{met['fat_descremada_pct']}% grasa")
                m4.metric("⏱️ Tiempo total",        _fmt_tiempo(met["tiempo_total_h"]))

                st.markdown("---")
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    st.metric("📈 Rendimiento crema",   f"{met['rendimiento_pct']:.2f}%")
                    st.metric("💵 Costo materia prima", f"${met['costo_materia_prima']:,.2f}")
                with col_r2:
                    st.metric("🧼 Costo CIP",           f"${met['costo_limpiezas']:,.2f}")
                    st.metric("💰 Costo total",         f"${met['costo_total']:,.2f}")
                st.metric("📊 Costo unitario crema",   f"${met['costo_unitario_crema']:.4f}/L")

                # Balance de masas
                st.markdown("### ⚖️ Balance de Masas")
                st.info(res_desc["balance_masas"]["descripcion"])

                # Tabla de resultados por tanque
                st.markdown("### 📋 Asignación por Tanque")
                df_res_desc = pd.DataFrame(res_desc["resultados_tanques"])
                st.dataframe(
                    df_res_desc.style.format({
                        "Leche a Procesar (L)": "{:,.2f}",
                        "Crema Obtenida (L)"  : "{:,.2f}",
                        "Leche Descremada (L)": "{:,.2f}",
                        "Grasa Entrada (%)"   : "{:.2f}",
                        "Grasa Crema (%)"     : "{:.2f}",
                        "Grasa Descremada (%)": "{:.2f}",
                        "Tiempo Proceso (h)"  : "{:.2f}",
                        "Costo Parcial ($)"   : "${:,.2f}",
                    }),
                    use_container_width=True, hide_index=True,
                )

                # Alertas de calidad
                alertas_desc = []
                if met["vol_crema_total_L"] < vol_crema_opt * 0.99:
                    alertas_desc.append(
                        f"⚠️ Crema producida ({met['vol_crema_total_L']:,.1f} L) "
                        f"< objetivo ({vol_crema_opt:,.1f} L)"
                    )
                if met["tiempo_total_h"] > 8:
                    alertas_desc.append(
                        f"⚠️ Tiempo de proceso ({_fmt_tiempo(met['tiempo_total_h'])}) "
                        f"supera 8 horas. Considere dividir en lotes."
                    )
                if alertas_desc:
                    with st.expander("⚠️ Alertas del proceso", expanded=True):
                        for a in alertas_desc: st.warning(a)
                else:
                    st.success("✅ Proceso dentro de parámetros operativos normales")

                # Actualización de inventario
                st.markdown("---")
                st.info("⚠️ El descremado consume leche cruda del inventario.")
                afect_desc = st.radio(
                    "📦 ¿Descontar leche procesada del inventario?",
                    ["No, solo es un cálculo teórico",
                     "Sí, descontar leche procesada del inventario"],
                    index=0, key="afectacion_desc",
                )
                if afect_desc == "Sí, descontar leche procesada del inventario":
                    st.warning(
                        f"🚨 Se descontarán **{met['vol_leche_total_L']:,.1f} L** "
                        f"de leche cruda de los tanques seleccionados."
                    )
                    confirmar_desc = st.checkbox(
                        "✓ Confirmo el inicio del proceso de descremado",
                        key="confirmar_desc",
                    )
                    if confirmar_desc:
                        if st.button("🔴 CONFIRMAR DESCREMADO Y ACTUALIZAR INVENTARIO",
                                     type="primary", key="btn_actualizar_desc"):
                            with st.spinner("⏳ Actualizando inventario..."):
                                if actualizar_inventario_descremado(res_desc["resultados_tanques"]):
                                    st.balloons()
                                    st.success(
                                        f"✅ Descremado confirmado. "
                                        f"Se han descontado {met['vol_leche_total_L']:,.1f} L del inventario."
                                    )
                                    st.session_state.tanques = cargar_tanques_db()
                                    st.rerun()
                                else:
                                    st.error("❌ Error al actualizar inventario. Verifica la conexión.")

    # ════════════════════════════════════════════════════════
    # SUB-TAB 3 — Fórmula y Referencia
    # ════════════════════════════════════════════════════════
    with desc_tab3:
        st.subheader("📐 Fórmula Base — Balance de Materia Grasa")
        st.markdown("""
        El proceso de descremado por clarificación centrífuga se rige por la **conservación de grasa total**:

        ```
        V_leche × G_leche = V_crema × G_crema + V_descremada × G_descremada
        ```

        Despejando el volumen de crema:

        ```
        V_crema = V_leche × (G_leche − G_descremada)
                            ─────────────────────────
                             (G_crema − G_descremada)
        ```

        Y para calcular la leche necesaria dado un objetivo de crema:

        ```
        V_leche = V_crema × (G_crema − G_descremada)
                            ─────────────────────────
                             (G_leche − G_descremada)
        ```

        **Donde:**
        - `V_leche`      = Volumen de leche cruda a procesar (L)
        - `G_leche`      = % grasa de la leche cruda / 100  → rango: 0.1%–6.5%
        - `V_crema`      = Volumen de crema obtenida (L)
        - `G_crema`      = % grasa de la crema / 100         → rango: 20%–55%
        - `V_descremada` = Volumen de leche descremada resultante (L)
        - `G_descremada` = % grasa residual en leche descremada / 100 = **0.05%** (constante del clarificador)

        **Tiempo de procesamiento:**
        ```
        T (h) = V_crema / 800  [L/h]
        ```

        ---
        ### 📊 Ejemplo de referencia calibrado
        """)
        try:
            r_ej = calcular_crema(10_000, 3.7, 45.0)
            st.table(pd.DataFrame([{
                "Leche entrada (L)"    : f"{r_ej['vol_leche_L']:,.0f}",
                "Grasa leche (%)"      : f"{r_ej['fat_leche_pct']}",
                "Crema obtenida (L)"   : f"{r_ej['vol_crema_L']:,.1f}",
                "Grasa crema (%)"      : f"{r_ej['fat_crema_pct']}",
                "Leche descremada (L)" : f"{r_ej['vol_descremada_L']:,.1f}",
                "Rendimiento (%)"      : f"{r_ej['rendimiento_pct']:.2f}",
                "Tiempo proceso"       : _fmt_tiempo(r_ej['tiempo_h']),
            }]))
        except Exception:
            st.info("Ejemplo: 10.000 L de leche al 3.7% → 812 L de crema al 45% + 9.188 L de leche descremada en 1 h 1 min")

        st.markdown("""
        ---
        ### 🏭 Parámetros operativos del clarificador
        | Parámetro | Valor |
        |-----------|-------|
        | Velocidad de proceso | 800 L crema / hora |
        | Grasa residual leche descremada | 0.05% |
        | Rango grasa leche entrada | 0.1% – 6.5% |
        | Rango grasa crema objetivo | 20% – 55% |
        | Costo CIP por tanque | $5.00 |
        """)
