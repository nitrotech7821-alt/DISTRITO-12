import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, date
from io import BytesIO

import pandas as pd
import streamlit as st
import psycopg2
import pydeck as pdk
import streamlit.components.v1 as components

try:
    import folium
    from streamlit_folium import st_folium
    TIENE_FOLIUM = True
except Exception:
    folium = None
    st_folium = None
    TIENE_FOLIUM = False

@st.cache_data(show_spinner=False)
def cargar_poligono_kml(ruta_kml):
    """Lee un archivo KML y regresa lista de puntos [longitud, latitud] para pintar el polígono."""
    try:
        ruta = Path(ruta_kml)
        if not ruta.exists():
            return []
        root = ET.parse(ruta).getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        puntos = []
        for elem in root.findall(".//kml:coordinates", ns):
            texto = (elem.text or "").strip()
            if not texto:
                continue
            for item in texto.replace("\n", " ").replace("\t", " ").split():
                partes = item.split(",")
                if len(partes) >= 2:
                    lon = float(partes[0])
                    lat = float(partes[1])
                    puntos.append([lon, lat])
        if len(puntos) > 1 and puntos[0] == puntos[-1]:
            puntos = puntos[:-1]
        return puntos
    except Exception:
        return []

def centro_poligono(puntos):
    if not puntos:
        return 29.072967, -110.955919
    lons = [p[0] for p in puntos]
    lats = [p[1] for p in puntos]
    return sum(lats) / len(lats), sum(lons) / len(lons)

def mapa_para_seleccionar_ubicacion(lat_actual=None, lon_actual=None, key="mapa_captura"):
    """Mapa clickeable para seleccionar latitud/longitud manualmente."""
    if not TIENE_FOLIUM:
        st.warning("Para usar selección manual en mapa instala: pip install folium streamlit-folium")
        return None, None

    puntos_distrito = cargar_poligono_kml(str(KML_DISTRITO12))
    centro_lat, centro_lon = centro_poligono(puntos_distrito)

    if lat_actual not in (None, 0, 0.0) and lon_actual not in (None, 0, 0.0):
        centro_lat, centro_lon = float(lat_actual), float(lon_actual)

    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=13, tiles="CartoDB positron")

    if puntos_distrito:
        # folium usa [lat, lon]; el KML viene como [lon, lat]
        poligono_latlon = [[lat, lon] for lon, lat in puntos_distrito]
        folium.Polygon(
            poligono_latlon,
            color="#E94E1B",
            weight=4,
            fill=True,
            fill_color="#087B75",
            fill_opacity=0.18,
            tooltip="Distrito Local 12",
        ).add_to(m)

    if lat_actual not in (None, 0, 0.0) and lon_actual not in (None, 0, 0.0):
        folium.Marker(
            [float(lat_actual), float(lon_actual)],
            tooltip="Ubicación seleccionada",
            icon=folium.Icon(color="red", icon="home"),
        ).add_to(m)

    st.caption("Haz clic sobre la vivienda o punto correcto. El sistema tomará esa latitud y longitud para pintarlo en el mapa.")
    data = st_folium(m, height=430, width=None, key=key)
    click = data.get("last_clicked") if isinstance(data, dict) else None
    if click:
        return float(click["lat"]), float(click["lng"])
    return None, None


def aplicar_gps_desde_url():
    """Lee coordenadas enviadas por el botón GPS del celular y las pone en session_state."""
    try:
        qp = st.query_params
        gps_lat = qp.get("gps_lat")
        gps_lon = qp.get("gps_lon")
        if isinstance(gps_lat, list):
            gps_lat = gps_lat[0]
        if isinstance(gps_lon, list):
            gps_lon = gps_lon[0]
        if gps_lat and gps_lon:
            st.session_state.lat_manual_d12 = float(gps_lat)
            st.session_state.lon_manual_d12 = float(gps_lon)
            st.session_state.msg_geo_d12 = "Ubicación GPS tomada desde el celular"
            # Limpia parámetros para que no se vuelvan a aplicar en cada recarga.
            try:
                st.query_params.clear()
            except Exception:
                pass
    except Exception:
        pass


def boton_gps_celular():
    """Muestra botón HTML para pedir GPS del navegador/celular y regresar coordenadas a Streamlit."""
    components.html(
        """
        <div style="font-family:Arial, sans-serif; width:100%;">
          <button id="gpsBtn" style="
              width:100%; padding:12px 14px; border:0; border-radius:14px;
              background:linear-gradient(90deg,#087B75,#14A39A); color:white;
              font-weight:900; font-size:15px; cursor:pointer;">
              📍 Usar mi ubicación actual
          </button>
          <div id="gpsMsg" style="margin-top:8px; font-size:13px; color:#475569; font-weight:700;"></div>
        </div>
        <script>
        const btn = document.getElementById('gpsBtn');
        const msg = document.getElementById('gpsMsg');
        btn.onclick = function(){
            if (!navigator.geolocation) {
                msg.innerHTML = 'Tu navegador no permite geolocalización.';
                return;
            }
            msg.innerHTML = 'Solicitando permiso de ubicación...';
            navigator.geolocation.getCurrentPosition(function(pos){
                const lat = pos.coords.latitude.toFixed(8);
                const lon = pos.coords.longitude.toFixed(8);
                msg.innerHTML = 'Ubicación tomada: ' + lat + ', ' + lon;
                const url = new URL(window.parent.location.href);
                url.searchParams.set('gps_lat', lat);
                url.searchParams.set('gps_lon', lon);
                window.parent.location.href = url.toString();
            }, function(err){
                let texto = 'No se pudo obtener la ubicación.';
                if (err.code === 1) texto = 'Permiso denegado. Activa ubicación en el navegador.';
                if (err.code === 2) texto = 'Ubicación no disponible. Revisa GPS o señal.';
                if (err.code === 3) texto = 'La solicitud tardó demasiado. Intenta de nuevo.';
                msg.innerHTML = texto;
            }, {enableHighAccuracy:true, timeout:15000, maximumAge:0});
        };
        </script>
        """,
        height=95,
    )

try:
    from streamlit_option_menu import option_menu
    TIENE_MENU = True
except Exception:
    TIENE_MENU = False

st.set_page_config(page_title="Sistema Distrito 12", page_icon="📍", layout="wide")

# ============================================================
# CONFIGURACIÓN POSTGRESQL
# ============================================================
PG_HOST = "localhost"
PG_PORT = "5432"
PG_DATABASE = "DISTRITO 12"
PG_USER = "postgres"
PG_PASSWORD = "Nitrotech1611"  # Cambia si tu PostgreSQL usa otra contraseña

CARPETA_EVIDENCIAS = str(Path(__file__).parent / "EVIDENCIAS")
Path(CARPETA_EVIDENCIAS).mkdir(parents=True, exist_ok=True)

# Archivo del contorno del Distrito 12. Déjalo en la misma carpeta del app.py
KML_DISTRITO12 = Path(__file__).with_name("DISTRITO_LOCAL_12.kml")

USUARIOS_INICIALES = {
    "admin": {"password": "1234", "rol": "Administrador"},
    "captura": {"password": "1234", "rol": "Captura"},
    "consulta": {"password": "1234", "rol": "Consulta"},
}

CATEGORIAS = ["Verde", "Amarillo", "Rojo"]
COLORES = {
    "Verde": [0, 160, 80],
    "Amarillo": [245, 190, 0],
    "Rojo": [220, 40, 40],
}

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #EEF8F5 0%, #FFF7E7 60%, #FDE0CF 100%);
}
.block-container { padding-top: 18px; }
.header-card {
    background: linear-gradient(135deg, rgba(219,246,241,0.98), rgba(255,242,216,0.98));
    padding: 24px;
    border-radius: 24px;
    box-shadow: 0px 8px 24px rgba(0,0,0,0.10);
    text-align: center;
    margin-bottom: 18px;
}
.header-card h1 { color: #087B75; font-weight: 900; }
.card {
    background: rgba(255,255,255,0.94);
    padding: 20px;
    border-radius: 18px;
    box-shadow: 0px 5px 15px rgba(0,0,0,0.08);
    border-left: 7px solid #087B75;
    margin-bottom: 18px;
}
.stButton > button {
    background: linear-gradient(90deg, #E94E1B, #F2B233);
    color: white;
    border: none;
    border-radius: 14px;
    padding: 10px;
    font-weight: 900;
    width: 100%;
}
.stDownloadButton > button {
    background: linear-gradient(90deg, #087B75, #14A39A);
    color: white;
    border: none;
    border-radius: 14px;
    padding: 10px;
    font-weight: 900;
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

@st.cache_resource(show_spinner=False)
def conectar():
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
        )
        conn.autocommit = False
        return conn, None
    except Exception as e:
        return None, str(e)

conn, error_pg = conectar()

def pg_ok():
    return conn is not None

def ejecutar(sql, params=None, commit=True):
    if params is None:
        params = []
    cur = conn.cursor()
    cur.execute(sql, params)
    if commit:
        conn.commit()
    return cur

def consulta_df(sql, params=None):
    if params is None:
        params = []
    return pd.read_sql(sql, conn, params=params)

def crear_excel(df):
    salida = BytesIO()
    df.to_excel(salida, index=False)
    salida.seek(0)
    return salida

def limpiar(txt):
    return str(txt or "").strip().upper()

def quitar_acentos(texto):
    texto = str(texto or "")
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).upper().strip()

def normalizar_archivo(texto):
    texto = quitar_acentos(texto)
    texto = re.sub(r"[^A-Z0-9_\- ]", "", texto)
    return texto.replace(" ", "_")[:90] or "ARCHIVO"

@st.cache_data(ttl=86400, show_spinner=False)
def geocodificar_direccion(direccion, colonia="", ciudad="Hermosillo", estado="Sonora", pais="México"):
    """Convierte una dirección en latitud/longitud usando OpenStreetMap Nominatim."""
    partes = [str(direccion or "").strip(), str(colonia or "").strip(), ciudad, estado, pais]
    consulta = ", ".join([p for p in partes if p])
    if not consulta.strip():
        return None, None, "Sin dirección"
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": consulta,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        })
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SistemaDistrito12DIF/1.0 difhermosillomunicipal@gmail.com"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            return None, None, f"No localizado: {consulta}"
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon, f"Localizado: {consulta}"
    except Exception as e:
        return None, None, f"Error geocodificando: {e}"

def actualizar_coordenadas_ciudadano(ciudadano_id, latitud, longitud):
    ejecutar("UPDATE ciudadanos SET latitud=%s, longitud=%s WHERE id=%s", [latitud, longitud, ciudadano_id])
    registrar_historial(ciudadano_id, "Coordenadas actualizadas automáticamente por dirección")

def geocodificar_registros_pendientes(limite=25):
    """Busca registros sin coordenadas y trata de ponerles pin automáticamente."""
    df = consulta_df("""
        SELECT id, direccion, colonia
        FROM ciudadanos
        WHERE (latitud IS NULL OR longitud IS NULL OR latitud=0 OR longitud=0)
          AND COALESCE(direccion,'') <> ''
        ORDER BY id DESC
        LIMIT %s
    """, [int(limite)])
    ok, fallidos, mensajes = 0, 0, []
    for _, r in df.iterrows():
        lat, lon, msg = geocodificar_direccion(r.get("direccion", ""), r.get("colonia", ""))
        if lat is not None and lon is not None:
            actualizar_coordenadas_ciudadano(int(r["id"]), lat, lon)
            ok += 1
        else:
            fallidos += 1
        mensajes.append(f"ID {r['id']}: {msg}")
        time.sleep(1.1)  # Nominatim recomienda no mandar muchas consultas por segundo
    return ok, fallidos, mensajes

# ============================================================
# BASE DE DATOS
# ============================================================
def crear_tablas():
    ejecutar("""
    CREATE TABLE IF NOT EXISTS ciudadanos (
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        telefono TEXT,
        direccion TEXT,
        colonia TEXT,
        seccion TEXT,
        distrito TEXT DEFAULT '12',
        categoria TEXT,
        latitud DOUBLE PRECISION,
        longitud DOUBLE PRECISION,
        observaciones TEXT,
        feedback TEXT,
        usuario TEXT,
        fecha DATE DEFAULT CURRENT_DATE,
        hora TIME DEFAULT CURRENT_TIME,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    ejecutar("""
    CREATE TABLE IF NOT EXISTS evidencias_d12 (
        id SERIAL PRIMARY KEY,
        ciudadano_id INTEGER REFERENCES ciudadanos(id) ON DELETE CASCADE,
        nombre_archivo TEXT,
        ruta_archivo TEXT,
        tipo TEXT,
        observacion TEXT,
        fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        usuario TEXT
    );
    """)
    ejecutar("""
    CREATE TABLE IF NOT EXISTS historial_d12 (
        id SERIAL PRIMARY KEY,
        ciudadano_id INTEGER REFERENCES ciudadanos(id) ON DELETE CASCADE,
        accion TEXT,
        usuario TEXT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

if pg_ok():
    try:
        crear_tablas()
    except Exception:
        conn.rollback()

# ============================================================
# LOGIN
# ============================================================
def validar_usuario(usuario, password):
    if usuario in USUARIOS_INICIALES and USUARIOS_INICIALES[usuario]["password"] == password:
        return USUARIOS_INICIALES[usuario]["rol"]
    return ""

def login():
    if "logueado_d12" not in st.session_state:
        st.session_state.logueado_d12 = False
    if "usuario_d12" not in st.session_state:
        st.session_state.usuario_d12 = ""
    if "rol_d12" not in st.session_state:
        st.session_state.rol_d12 = ""

    if st.session_state.logueado_d12:
        return True

    st.markdown("""
    <div class="header-card">
        <h1>📍 Sistema Distrito 12</h1>
        <p>Mapeador · Captura · Reportes · Evidencias · IA</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    if pg_ok():
        st.success(f"PostgreSQL conectado | {PG_HOST}:{PG_PORT}")
    else:
        st.error("No se pudo conectar a PostgreSQL.")
        st.code(f"Base: {PG_DATABASE}\nUsuario: {PG_USER}\nError: {error_pg}")
        st.info("Primero crea la base de datos en PostgreSQL con nombre: DISTRITO 12")
        st.stop()

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("🔐 Entrar"):
        rol = validar_usuario(usuario, password)
        if rol:
            st.session_state.logueado_d12 = True
            st.session_state.usuario_d12 = usuario
            st.session_state.rol_d12 = rol
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")
    st.info("Usuarios iniciales: admin / captura / consulta. Contraseña: 1234")
    st.markdown('</div>', unsafe_allow_html=True)
    return False

if not login():
    st.stop()

# ============================================================
# FUNCIONES DEL SISTEMA
# ============================================================
def insertar_ciudadano(data):
    cur = ejecutar("""
        INSERT INTO ciudadanos
        (nombre, telefono, direccion, colonia, seccion, distrito, categoria, latitud, longitud, observaciones, feedback, usuario, fecha, hora)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, [
        data["nombre"], data["telefono"], data["direccion"], data["colonia"], data["seccion"],
        data["distrito"], data["categoria"], data["latitud"], data["longitud"], data["observaciones"],
        data["feedback"], st.session_state.usuario_d12, data["fecha"], data["hora"],
    ])
    cid = cur.fetchone()[0]
    conn.commit()
    registrar_historial(cid, "Registro capturado")
    return cid

def actualizar_ciudadano(ciudadano_id, data):
    ejecutar("""
        UPDATE ciudadanos SET
            nombre=%s,
            telefono=%s,
            direccion=%s,
            colonia=%s,
            seccion=%s,
            distrito=%s,
            categoria=%s,
            latitud=%s,
            longitud=%s,
            observaciones=%s,
            feedback=%s,
            fecha=%s,
            hora=%s
        WHERE id=%s
    """, [
        data["nombre"], data["telefono"], data["direccion"], data["colonia"], data["seccion"],
        data["distrito"], data["categoria"], data["latitud"], data["longitud"], data["observaciones"],
        data["feedback"], data["fecha"], data["hora"], int(ciudadano_id)
    ])
    registrar_historial(int(ciudadano_id), "Registro modificado")
    conn.commit()

def eliminar_ciudadano(ciudadano_id):
    # Las evidencias e historial relacionadas se eliminan por ON DELETE CASCADE en PostgreSQL.
    registrar_historial(int(ciudadano_id), "Registro eliminado")
    ejecutar("DELETE FROM ciudadanos WHERE id=%s", [int(ciudadano_id)])
    conn.commit()

def registrar_historial(ciudadano_id, accion):
    try:
        ejecutar("INSERT INTO historial_d12(ciudadano_id, accion, usuario) VALUES (%s,%s,%s)",
                 [ciudadano_id, accion, st.session_state.usuario_d12])
    except Exception:
        conn.rollback()

def buscar_ciudadanos(texto="", categoria="Todas", colonia="Todas", seccion="", limite=2000):
    filtros, params = [], []
    if texto:
        filtros.append("(nombre ILIKE %s OR telefono ILIKE %s OR direccion ILIKE %s OR colonia ILIKE %s OR observaciones ILIKE %s OR feedback ILIKE %s)")
        params.extend([f"%{texto}%"] * 6)
    if categoria != "Todas":
        filtros.append("categoria=%s")
        params.append(categoria)
    if colonia != "Todas":
        filtros.append("colonia=%s")
        params.append(colonia)
    if seccion:
        filtros.append("seccion ILIKE %s")
        params.append(f"%{seccion}%")
    where = "WHERE " + " AND ".join(filtros) if filtros else ""
    return consulta_df(f"""
        SELECT id, nombre, telefono, direccion, colonia, seccion, distrito, categoria,
               latitud, longitud, observaciones, feedback, usuario, fecha, hora, fecha_creacion
        FROM ciudadanos
        {where}
        ORDER BY id DESC
        LIMIT {int(limite)}
    """, params)

def leer_colonias():
    try:
        df = consulta_df("SELECT DISTINCT colonia FROM ciudadanos WHERE colonia IS NOT NULL AND colonia<>'' ORDER BY colonia")
        return df["colonia"].astype(str).tolist()
    except Exception:
        return []

def guardar_evidencia(ciudadano_id, archivo, tipo, obs):
    if archivo is None:
        st.error("Selecciona un archivo.")
        return False
    carpeta = Path(CARPETA_EVIDENCIAS) / f"REGISTRO_{ciudadano_id}"
    carpeta.mkdir(parents=True, exist_ok=True)
    ext = Path(archivo.name).suffix.lower()
    nombre = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{normalizar_archivo(tipo)}_{normalizar_archivo(Path(archivo.name).stem)}{ext}"
    ruta = carpeta / nombre
    with open(ruta, "wb") as f:
        f.write(archivo.getbuffer())
    ejecutar("""
        INSERT INTO evidencias_d12(ciudadano_id, nombre_archivo, ruta_archivo, tipo, observacion, usuario)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, [ciudadano_id, archivo.name, str(ruta), tipo, obs, st.session_state.usuario_d12])
    registrar_historial(ciudadano_id, f"Evidencia subida: {tipo}")
    return True

def leer_evidencias(ciudadano_id):
    return consulta_df("SELECT * FROM evidencias_d12 WHERE ciudadano_id=%s ORDER BY id DESC", [ciudadano_id])

def interpretar_ia(comando):
    t = quitar_acentos(comando)
    filtros, params = [], []
    titulo = "Reporte inteligente Distrito 12"
    agrupacion = "detalle"

    if "VERDE" in t:
        filtros.append("categoria=%s"); params.append("Verde"); titulo += " | Verde"
    if "AMARILLO" in t:
        filtros.append("categoria=%s"); params.append("Amarillo"); titulo += " | Amarillo"
    if "ROJO" in t or "ROJOS" in t:
        filtros.append("categoria=%s"); params.append("Rojo"); titulo += " | Rojo"

    if "HOY" in t:
        filtros.append("fecha=CURRENT_DATE"); titulo += " | Hoy"
    if "COLONIA" in t or "COLONIAS" in t:
        agrupacion = "colonia"; titulo = "Registros por colonia"
    if "SECCION" in t or "SECCIONES" in t:
        agrupacion = "seccion"; titulo = "Registros por sección"
    if "CATEGORIA" in t or "COLORES" in t:
        agrupacion = "categoria"; titulo = "Registros por categoría"
    if "USUARIO" in t or "CAPTURISTA" in t:
        agrupacion = "usuario"; titulo = "Registros por usuario"

    # Búsqueda libre si no es sólo agrupación
    palabras_ignorar = {"DAME","LOS","LAS","DEL","DE","EL","LA","EN","POR","REPORTE","REGISTROS","CUANTOS","CUANTAS","DISTRITO","12","VERDE","AMARILLO","ROJO","HOY"}
    palabras = [p for p in re.findall(r"[A-Z0-9]+", t) if p not in palabras_ignorar and len(p) >= 3]
    if palabras and agrupacion == "detalle":
        condiciones = []
        for p in palabras:
            condiciones.append("(nombre ILIKE %s OR direccion ILIKE %s OR colonia ILIKE %s OR seccion ILIKE %s OR observaciones ILIKE %s OR feedback ILIKE %s)")
            params.extend([f"%{p}%"] * 6)
        filtros.append(" AND ".join(condiciones))
        titulo += " | Búsqueda libre"

    where = "WHERE " + " AND ".join(filtros) if filtros else ""
    df = consulta_df(f"""
        SELECT * FROM ciudadanos
        {where}
        ORDER BY id DESC
        LIMIT 10000
    """, params)

    agrupado = pd.DataFrame()
    if not df.empty and agrupacion != "detalle":
        agrupado = df.groupby(agrupacion, dropna=False).agg(registros=("id", "count")).reset_index().sort_values("registros", ascending=False)
    return titulo, df, agrupado

# ============================================================
# ENCABEZADO Y MENÚ SUPERIOR
# ============================================================
st.markdown("""
<div class="header-card">
    <h1>📍 Sistema Integral Distrito 12 v8</h1>
    <p>Mapeador territorial · Categorías verde/amarillo/rojo · Reportes inteligentes</p>
</div>
""", unsafe_allow_html=True)

cuser, clogout = st.columns([4, 1])
cuser.success(f"Usuario: {st.session_state.usuario_d12} | Rol: {st.session_state.rol_d12} | PostgreSQL conectado")
if clogout.button("Cerrar sesión"):
    st.session_state.logueado_d12 = False
    st.session_state.usuario_d12 = ""
    st.session_state.rol_d12 = ""
    st.rerun()

if TIENE_MENU:
    menu = option_menu(
        None,
        ["Inicio", "Captura", "Modificar/Eliminar", "Mapeador", "Reportes", "Excel", "Evidencias", "IA", "Configuración"],
        icons=["house", "person-plus", "pencil-square", "map", "bar-chart", "file-earmark-excel", "camera", "robot", "gear"],
        default_index=0,
        orientation="horizontal",
    )
else:
    menu = st.radio(
        "Módulos",
        ["Inicio", "Captura", "Modificar/Eliminar", "Mapeador", "Reportes", "Excel", "Evidencias", "IA", "Configuración"],
        horizontal=True,
    )

# ============================================================
# MÓDULOS
# ============================================================
if menu == "Inicio":
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🏠 Dashboard Distrito 12")
    try:
        total = int(consulta_df("SELECT COUNT(*) total FROM ciudadanos").iloc[0]["total"])
        verdes = int(consulta_df("SELECT COUNT(*) total FROM ciudadanos WHERE categoria='Verde'").iloc[0]["total"])
        amarillos = int(consulta_df("SELECT COUNT(*) total FROM ciudadanos WHERE categoria='Amarillo'").iloc[0]["total"])
        rojos = int(consulta_df("SELECT COUNT(*) total FROM ciudadanos WHERE categoria='Rojo'").iloc[0]["total"])
        hoy = int(consulta_df("SELECT COUNT(*) total FROM ciudadanos WHERE fecha=CURRENT_DATE").iloc[0]["total"])
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total", f"{total:,}")
        c2.metric("🟢 Verde", f"{verdes:,}")
        c3.metric("🟡 Amarillo", f"{amarillos:,}")
        c4.metric("🔴 Rojo", f"{rojos:,}")
        c5.metric("Hoy", f"{hoy:,}")
        st.markdown("### Últimos registros")
        st.dataframe(buscar_ciudadanos(limite=50), use_container_width=True)
    except Exception as e:
        st.error(f"No se pudo cargar el dashboard: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Captura":
    if st.session_state.rol_d12 == "Consulta":
        st.warning("Tu usuario sólo tiene permiso de consulta.")
        st.stop()

    # Diseño tipo ficha + mapa grande, parecido al flujo de Google Maps.
    st.markdown("""
    <style>
    .capture-shell{background:#ffffff;border-radius:18px;padding:18px;box-shadow:0 8px 28px rgba(15,23,42,.08);border:1px solid rgba(15,23,42,.08);margin-bottom:16px;}
    .capture-title{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;}
    .capture-title h2{margin:0;color:#0f172a;font-weight:900;}
    .help-box{background:#eaf4ff;border:1px solid #bfdbfe;color:#075985;padding:12px 14px;border-radius:12px;font-weight:700;margin-bottom:12px;}
    .coord-box{display:flex;gap:18px;align-items:center;justify-content:space-between;background:#ecfdf5;border:1px solid #bbf7d0;border-radius:12px;padding:12px 14px;margin-top:10px;color:#065f46;font-weight:800;}
    .mini-card{background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;padding:14px;box-shadow:0 4px 14px rgba(15,23,42,.05);}
    .mini-card h4{margin:0 0 8px 0;color:#172554;font-weight:900;}
    .required-note{color:#dc2626;font-size:13px;margin-top:8px;}
    </style>
    """, unsafe_allow_html=True)

    if "lat_manual_d12" not in st.session_state:
        st.session_state.lat_manual_d12 = None
    if "lon_manual_d12" not in st.session_state:
        st.session_state.lon_manual_d12 = None
    if "msg_geo_d12" not in st.session_state:
        st.session_state.msg_geo_d12 = ""
    if "direccion_busqueda_d12" not in st.session_state:
        st.session_state.direccion_busqueda_d12 = ""

    aplicar_gps_desde_url()

    st.markdown('<div class="capture-shell">', unsafe_allow_html=True)
    st.markdown("""
    <div class="capture-title">
        <div>
            <h2>📍 Captura Ciudadana</h2>
            <div style="color:#64748b;font-weight:600;">Captura los datos, busca la dirección y confirma la ubicación exacta en el mapa.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    panel_datos, panel_mapa = st.columns([0.35, 0.65], gap="large")

    with panel_datos:
        st.markdown('<div class="mini-card"><h4>Datos generales</h4>', unsafe_allow_html=True)
        nombre = st.text_input("Nombre completo *", key="cap_nombre").upper()
        ctel, csec = st.columns(2)
        with ctel:
            telefono = st.text_input("Teléfono / Celular", key="cap_tel")
        with csec:
            seccion = st.text_input("Sección electoral", key="cap_sec").upper()

        colonia = st.text_input("Colonia", key="cap_col", placeholder="Ejemplo: LEY 57").upper()
        direccion = st.text_input("Dirección", key="cap_dir", placeholder="Ejemplo: AV. PLAN DE IGUALA").upper()
        cnum1, cnum2 = st.columns(2)
        with cnum1:
            numero_ext = st.text_input("Número exterior", key="cap_num_ext", placeholder="266")
        with cnum2:
            numero_int = st.text_input("Número interior", key="cap_num_int", placeholder="Opcional")

        categoria = st.selectbox("Categoría", CATEGORIAS, key="cap_cat")
        distrito = st.text_input("Distrito", value="12", key="cap_dist")
        fecha_cap = st.date_input("Fecha", value=date.today(), key="cap_fecha")
        hora_cap = st.time_input("Hora", value=datetime.now().time().replace(microsecond=0), key="cap_hora")
        observaciones = st.text_area("Observaciones", key="cap_obs", height=90).upper()
        feedback = st.text_area("Retroalimentación / seguimiento", key="cap_feed", height=70).upper()

        direccion_linea = " ".join([p for p in [direccion, numero_ext] if str(p or "").strip()]).strip()
        direccion_completa = ", ".join([p for p in [direccion_linea, colonia, "Hermosillo", "Sonora", "México"] if str(p or "").strip()])

        st.caption("Ejemplo recomendado: AV. PLAN DE IGUALA 266, LEY 57, HERMOSILLO, SONORA")

        # --- Google Maps auxiliar ---
        # OpenStreetMap no siempre encuentra números de casa en Hermosillo.
        # Este botón abre la dirección directamente en Google Maps para verificarla
        # y permite copiar la latitud/longitud y pegarlas en Captura manual.
        google_query = direccion_completa if direccion_linea else "Hermosillo, Sonora, México"
        google_q = urllib.parse.quote_plus(google_query)
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={google_q}"
        st.link_button("🗺️ Abrir dirección en Google Maps", google_maps_url, use_container_width=True)
        boton_gps_celular()
        st.caption("En celular: presiona el botón GPS y acepta el permiso del navegador. Debe estar en HTTPS si lo usas por Internet.")

        with st.expander("👀 Vista previa Google Maps de la dirección", expanded=False):
            st.caption("Si Google sí encuentra la ubicación, copia las coordenadas de la URL o haz clic derecho en el mapa y pégalas en Captura manual de coordenadas.")
            components.iframe(f"https://www.google.com/maps?q={google_q}&z=17&output=embed", height=360)

        if st.button("🔎 Buscar dirección", use_container_width=True):
            if not direccion_linea:
                st.warning("Captura calle y número para buscar.")
            else:
                with st.spinner("Buscando dirección en el mapa..."):
                    lat_auto, lon_auto, msg_geo = geocodificar_direccion(direccion_linea, colonia)
                st.session_state.msg_geo_d12 = msg_geo
                st.session_state.direccion_busqueda_d12 = direccion_completa
                if lat_auto is not None and lon_auto is not None:
                    st.session_state.lat_manual_d12 = lat_auto
                    st.session_state.lon_manual_d12 = lon_auto
                    st.rerun()
                else:
                    st.warning(msg_geo)
                    st.info("OpenStreetMap no la encontró. Usa el botón 🗺️ Abrir dirección en Google Maps, copia las coordenadas y pégalas abajo en Captura manual de coordenadas.")

        if st.button("🧹 Limpiar ubicación", use_container_width=True):
            st.session_state.lat_manual_d12 = None
            st.session_state.lon_manual_d12 = None
            st.session_state.msg_geo_d12 = ""
            st.rerun()

        with st.expander("Captura manual de coordenadas", expanded=False):
            st.caption("Pega aquí las coordenadas de Google Maps. Ejemplo: 29.1206827 y -110.9719226")
            latitud = st.number_input("Latitud", value=0.0, format="%.8f", key="cap_lat")
            longitud = st.number_input("Longitud", value=0.0, format="%.8f", key="cap_lon")
            if st.button("📌 Usar coordenadas manuales", use_container_width=True):
                if latitud != 0 and longitud != 0:
                    st.session_state.lat_manual_d12 = float(latitud)
                    st.session_state.lon_manual_d12 = float(longitud)
                    st.session_state.msg_geo_d12 = "Ubicación cargada manualmente con coordenadas"
                    st.rerun()
                else:
                    st.warning("Captura latitud y longitud válidas.")
        st.markdown('<div class="required-note">* Campos obligatorios: nombre o dirección.</div></div>', unsafe_allow_html=True)

    with panel_mapa:
        st.markdown('<div class="help-box">ℹ️ Busca la dirección o haz clic sobre el mapa para seleccionar la vivienda exacta. Después puedes abrir Google Maps para verificar la ubicación.</div>', unsafe_allow_html=True)

        lat_base = st.session_state.lat_manual_d12 or (st.session_state.get("cap_lat") if st.session_state.get("cap_lat", 0) != 0 else None)
        lon_base = st.session_state.lon_manual_d12 or (st.session_state.get("cap_lon") if st.session_state.get("cap_lon", 0) != 0 else None)

        if TIENE_FOLIUM:
            puntos_distrito = cargar_poligono_kml(str(KML_DISTRITO12))
            centro_lat, centro_lon = centro_poligono(puntos_distrito)
            zoom = 13
            if lat_base and lon_base:
                centro_lat, centro_lon = float(lat_base), float(lon_base)
                zoom = 17

            mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
            folium.TileLayer("CartoDB positron", name="Mapa claro", control=True).add_to(mapa)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Satélite",
                overlay=False,
                control=True,
            ).add_to(mapa)

            if puntos_distrito:
                poligono_latlon = [[lat, lon] for lon, lat in puntos_distrito]
                folium.Polygon(
                    poligono_latlon,
                    color="#E94E1B",
                    weight=4,
                    fill=True,
                    fill_color="#087B75",
                    fill_opacity=0.14,
                    tooltip="Distrito Local 12",
                ).add_to(mapa)

            if lat_base and lon_base:
                popup_html = f"""
                <div style='width:230px;font-family:Arial'>
                    <b>{direccion_linea or 'Ubicación seleccionada'}</b><br>
                    {colonia or ''}, Hermosillo, Sonora<br>
                    <small>Lat: {float(lat_base):.6f}<br>Lon: {float(lon_base):.6f}</small>
                </div>
                """
                folium.Marker(
                    [float(lat_base), float(lon_base)],
                    tooltip=direccion_linea or "Ubicación seleccionada",
                    popup=folium.Popup(popup_html, max_width=260),
                    icon=folium.Icon(color="red", icon="home"),
                ).add_to(mapa)

            folium.LayerControl(position="topright").add_to(mapa)
            datos_mapa = st_folium(mapa, height=540, width=None, key="mapa_captura_v6_google_style")
            click = datos_mapa.get("last_clicked") if isinstance(datos_mapa, dict) else None
            if click:
                st.session_state.lat_manual_d12 = float(click["lat"])
                st.session_state.lon_manual_d12 = float(click["lng"])
                st.session_state.msg_geo_d12 = "Ubicación seleccionada manualmente en el mapa"
                st.rerun()
        else:
            st.warning("Instala folium y streamlit-folium para usar el mapa interactivo.")

        lat_sel = st.session_state.get("lat_manual_d12")
        lon_sel = st.session_state.get("lon_manual_d12")
        if lat_sel and lon_sel:
            st.markdown(f"""
            <div class="coord-box">
                <div>✅ Dirección localizada / ubicación seleccionada</div>
                <div>Latitud: {lat_sel:.8f}</div>
                <div>Longitud: {lon_sel:.8f}</div>
            </div>
            """, unsafe_allow_html=True)
            b1, b2 = st.columns([1,1])
            b1.link_button("🧭 Abrir en Google Maps", f"https://www.google.com/maps/search/?api=1&query={lat_sel},{lon_sel}", use_container_width=True)
            with b2:
                with st.expander("👀 Vista Google Maps", expanded=False):
                    url_google = f"https://www.google.com/maps?q={lat_sel},{lon_sel}&z=18&output=embed"
                    components.iframe(url_google, height=260)
        else:
            if st.session_state.msg_geo_d12:
                st.warning(st.session_state.msg_geo_d12)
            else:
                st.info("Sin ubicación seleccionada. Busca una dirección o haz clic en el mapa.")

    st.markdown('</div>', unsafe_allow_html=True)

    # ==============================
    # DOCUMENTACIÓN FOTOGRÁFICA
    # ==============================
    st.markdown('<div class="capture-shell">', unsafe_allow_html=True)
    st.markdown("### 📷 Documentación fotográfica")
    fd1, fd2, fd3, fd4 = st.columns(4)
    with fd1:
        st.markdown("#### 👤 Rostro")
        cap_rostro = st.camera_input("Tomar foto", key="cap_rostro_nuevo")
        up_rostro = st.file_uploader("Subir", type=["jpg", "jpeg", "png"], key="up_rostro_nuevo")
    with fd2:
        st.markdown("#### 🪪 INE frente")
        cap_ine_frente = st.camera_input("Tomar foto", key="cap_ine_frente_nuevo")
        up_ine_frente = st.file_uploader("Subir", type=["jpg", "jpeg", "png", "pdf"], key="up_ine_frente_nuevo")
    with fd3:
        st.markdown("#### 🪪 INE reverso")
        cap_ine_reverso = st.camera_input("Tomar foto", key="cap_ine_reverso_nuevo")
        up_ine_reverso = st.file_uploader("Subir", type=["jpg", "jpeg", "png", "pdf"], key="up_ine_reverso_nuevo")
    with fd4:
        st.markdown("#### 🏠 Comprobante")
        up_comprobante = st.file_uploader("Subir comprobante", type=["jpg", "jpeg", "png", "pdf"], key="up_comprobante_nuevo")

    st.divider()
    if st.button("💾 GUARDAR REGISTRO", use_container_width=True):
        if not nombre and not direccion:
            st.error("Captura al menos nombre o dirección.")
        else:
            lat_final = st.session_state.get("lat_manual_d12") or (latitud if latitud != 0 else None)
            lon_final = st.session_state.get("lon_manual_d12") or (longitud if longitud != 0 else None)

            if (lat_final is None or lon_final is None) and direccion_linea:
                with st.spinner("Buscando coordenadas de la dirección..."):
                    lat_auto, lon_auto, msg_geo = geocodificar_direccion(direccion_linea, colonia)
                if lat_auto is not None and lon_auto is not None:
                    lat_final, lon_final = lat_auto, lon_auto
                    st.success(f"Pin generado automáticamente: {lat_final:.6f}, {lon_final:.6f}")
                else:
                    st.warning("No se encontró la dirección. Puedes guardar sin coordenadas o seleccionar la ubicación en el mapa.")

            direccion_guardar = " ".join([p for p in [direccion, numero_ext] if str(p or "").strip()]).strip() or direccion
            if numero_int:
                direccion_guardar = f"{direccion_guardar} INT. {numero_int}"

            cid = insertar_ciudadano({
                "nombre": nombre, "telefono": telefono, "direccion": direccion_guardar, "colonia": colonia,
                "seccion": seccion, "distrito": distrito, "categoria": categoria,
                "latitud": lat_final,
                "longitud": lon_final,
                "observaciones": observaciones, "feedback": feedback,
                "fecha": fecha_cap, "hora": hora_cap,
            })
            documentos = [
                (cap_rostro, "Foto Persona"),
                (up_rostro, "Foto Persona"),
                (cap_ine_frente, "INE Frente"),
                (up_ine_frente, "INE Frente"),
                (cap_ine_reverso, "INE Reverso"),
                (up_ine_reverso, "INE Reverso"),
                (up_comprobante, "Comprobante Domicilio"),
            ]
            docs_guardados = 0
            for archivo_doc, tipo_doc in documentos:
                if archivo_doc is not None:
                    if guardar_evidencia(int(cid), archivo_doc, tipo_doc, "DOCUMENTO CAPTURADO EN ALTA DE REGISTRO"):
                        docs_guardados += 1

            st.session_state.lat_manual_d12 = None
            st.session_state.lon_manual_d12 = None
            st.session_state.msg_geo_d12 = ""
            st.success(f"Registro guardado correctamente. ID: {cid} | Documentos guardados: {docs_guardados}")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Modificar/Eliminar":
    if st.session_state.rol_d12 == "Consulta":
        st.warning("Tu usuario sólo tiene permiso de consulta.")
        st.stop()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("✏️ Modificar o eliminar captura del ciudadano")
    st.info("Busca el registro por nombre, teléfono, colonia, dirección o sección. Después selecciona el ID para editarlo.")

    b1, b2, b3 = st.columns([2, 1, 1])
    with b1:
        texto_busqueda = st.text_input("Buscar ciudadano", key="buscar_modificar_d12")
    with b2:
        categoria_busqueda = st.selectbox("Categoría", ["Todas"] + CATEGORIAS, key="cat_modificar_d12")
    with b3:
        limite_busqueda = st.number_input("Límite", min_value=10, max_value=5000, value=100, step=10, key="lim_modificar_d12")

    if st.button("🔎 Buscar para modificar"):
        st.session_state["df_modificar_d12"] = buscar_ciudadanos(texto_busqueda, categoria_busqueda, "Todas", "", int(limite_busqueda))

    df_mod = st.session_state.get("df_modificar_d12", pd.DataFrame())
    if df_mod.empty:
        st.info("Realiza una búsqueda para cargar registros.")
    else:
        st.dataframe(df_mod, use_container_width=True)
        seleccionado = st.selectbox(
            "Selecciona el registro",
            df_mod["id"].tolist(),
            format_func=lambda x: f"ID {x} | {df_mod[df_mod['id']==x].iloc[0]['nombre']} | {df_mod[df_mod['id']==x].iloc[0]['colonia']} | Sección {df_mod[df_mod['id']==x].iloc[0]['seccion']}",
            key="select_modificar_d12"
        )
        row = df_mod[df_mod["id"] == seleccionado].iloc[0]

        st.markdown("### Datos del ciudadano")
        c1, c2 = st.columns(2)
        with c1:
            nombre_m = st.text_input("Nombre completo", value=str(row.get("nombre") or ""), key="mod_nombre").upper()
            telefono_m = st.text_input("Teléfono", value=str(row.get("telefono") or ""), key="mod_telefono")
            direccion_m = st.text_input("Dirección", value=str(row.get("direccion") or ""), key="mod_direccion").upper()
            colonia_m = st.text_input("Colonia", value=str(row.get("colonia") or ""), key="mod_colonia").upper()
            seccion_m = st.text_input("Sección electoral", value=str(row.get("seccion") or ""), key="mod_seccion").upper()
        with c2:
            distrito_m = st.text_input("Distrito", value=str(row.get("distrito") or "12"), key="mod_distrito")
            cat_actual = str(row.get("categoria") or "Verde")
            idx_cat = CATEGORIAS.index(cat_actual) if cat_actual in CATEGORIAS else 0
            categoria_m = st.selectbox("Categoría", CATEGORIAS, index=idx_cat, key="mod_categoria")
            fecha_val = row.get("fecha")
            if pd.isna(fecha_val):
                fecha_val = date.today()
            elif not isinstance(fecha_val, date):
                fecha_val = pd.to_datetime(fecha_val).date()
            fecha_m = st.date_input("Fecha", value=fecha_val, key="mod_fecha")
            hora_val = row.get("hora")
            if pd.isna(hora_val):
                hora_val = datetime.now().time().replace(microsecond=0)
            hora_m = st.time_input("Hora", value=hora_val, key="mod_hora")
            lat_m = st.number_input("Latitud", value=float(row.get("latitud") or 0.0), format="%.8f", key="mod_lat")
            lon_m = st.number_input("Longitud", value=float(row.get("longitud") or 0.0), format="%.8f", key="mod_lon")

        observaciones_m = st.text_area("Observaciones", value=str(row.get("observaciones") or ""), key="mod_obs").upper()
        feedback_m = st.text_area("Feedback / seguimiento", value=str(row.get("feedback") or ""), key="mod_feedback").upper()

        col_geo, col_guardar = st.columns(2)
        with col_geo:
            recalcular_pin = st.checkbox("📍 Recalcular ubicación con dirección y colonia", value=False)
        with col_guardar:
            st.caption("Al guardar, el mapa se actualizará con los nuevos datos.")

        if st.button("💾 Guardar modificaciones"):
            lat_final = lat_m if lat_m != 0 else None
            lon_final = lon_m if lon_m != 0 else None
            if recalcular_pin and direccion_m:
                with st.spinner("Buscando coordenadas actualizadas..."):
                    lat_auto, lon_auto, msg_geo = geocodificar_direccion(direccion_m, colonia_m)
                if lat_auto is not None and lon_auto is not None:
                    lat_final, lon_final = lat_auto, lon_auto
                    st.success(f"Pin actualizado: {lat_final:.6f}, {lon_final:.6f}")
                else:
                    st.warning(msg_geo)

            actualizar_ciudadano(int(seleccionado), {
                "nombre": nombre_m,
                "telefono": telefono_m,
                "direccion": direccion_m,
                "colonia": colonia_m,
                "seccion": seccion_m,
                "distrito": distrito_m,
                "categoria": categoria_m,
                "latitud": lat_final,
                "longitud": lon_final,
                "observaciones": observaciones_m,
                "feedback": feedback_m,
                "fecha": fecha_m,
                "hora": hora_m,
            })
            st.success(f"Registro ID {seleccionado} modificado correctamente.")
            st.session_state.pop("df_modificar_d12", None)
            st.rerun()

        st.markdown("---")
        st.markdown("### 🗑️ Eliminar registro")
        if st.session_state.rol_d12 != "Administrador":
            st.warning("Sólo el usuario Administrador puede eliminar registros.")
        else:
            confirmar = st.checkbox(f"Confirmo que deseo eliminar el registro ID {seleccionado}", key="confirm_delete_d12")
            if st.button("🗑️ Eliminar definitivamente"):
                if not confirmar:
                    st.error("Primero marca la casilla de confirmación.")
                else:
                    eliminar_ciudadano(int(seleccionado))
                    st.success(f"Registro ID {seleccionado} eliminado correctamente.")
                    st.session_state.pop("df_modificar_d12", None)
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Mapeador":
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🗺️ Mapeador Distrito 12")

    puntos_distrito = cargar_poligono_kml(str(KML_DISTRITO12))
    centro_lat, centro_lon = centro_poligono(puntos_distrito)

    df = buscar_ciudadanos(limite=10000)
    df_map = df.dropna(subset=["latitud", "longitud"]).copy()
    df_map = df_map[(df_map["latitud"] != 0) & (df_map["longitud"] != 0)]

    capas = []

    if puntos_distrito:
        capas.append(
            pdk.Layer(
                "PolygonLayer",
                data=[{"distrito": "Distrito Local 12", "polygon": puntos_distrito}],
                get_polygon="polygon",
                get_fill_color=[8, 123, 117, 35],
                get_line_color=[8, 123, 117, 255],
                line_width_min_pixels=3,
                pickable=True,
                stroked=True,
                filled=True,
            )
        )
        capas.append(
            pdk.Layer(
                "PathLayer",
                data=[{"name": "Límite Distrito 12", "path": puntos_distrito + [puntos_distrito[0]]}],
                get_path="path",
                get_color=[233, 78, 27],
                width_min_pixels=4,
                pickable=True,
            )
        )
    else:
        st.warning("No encontré el archivo DISTRITO_LOCAL_12.kml. Déjalo en la misma carpeta que app_distrito12.py para ver el contorno del distrito.")

    if not df_map.empty:
        df_map["color"] = df_map["categoria"].apply(lambda x: COLORES.get(str(x), [80, 80, 80]))
        capas.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_map,
                get_position="[longitud, latitud]",
                get_fill_color="color",
                get_radius=70,
                pickable=True,
            )
        )

    st.pydeck_chart(pdk.Deck(
        initial_view_state=pdk.ViewState(
            latitude=float(df_map["latitud"].mean()) if not df_map.empty else float(centro_lat),
            longitude=float(df_map["longitud"].mean()) if not df_map.empty else float(centro_lon),
            zoom=11,
            pitch=0,
        ),
        layers=capas,
        tooltip={"text": "{nombre}\n{colonia}\nCategoría: {categoria}\nSección: {seccion}\n{distrito}"},
    ))

    c1, c2, c3 = st.columns(3)
    c1.metric("Puntos del contorno", f"{len(puntos_distrito):,}")
    c2.metric("Registros con coordenadas", f"{len(df_map):,}")
    c3.metric("Total registros", f"{len(df):,}")

    st.markdown("### 📍 Generar pines por dirección")
    st.caption("Si tus registros tienen dirección pero no latitud/longitud, este botón intentará localizarlos automáticamente con OpenStreetMap.")
    limite_geo = st.number_input("Máximo de registros a geocodificar por intento", min_value=1, max_value=100, value=25, step=5)
    if st.button("📌 Generar pines faltantes"):
        with st.spinner("Buscando coordenadas, puede tardar unos segundos..."):
            ok, fallidos, mensajes = geocodificar_registros_pendientes(limite_geo)
        st.success(f"Coordenadas generadas: {ok}")
        if fallidos:
            st.warning(f"No localizados: {fallidos}")
        with st.expander("Ver detalle de geocodificación"):
            for m in mensajes:
                st.write(m)
        st.info("Presiona Actualizar o vuelve a entrar al Mapeador para ver los nuevos pines.")

    if df_map.empty:
        st.info("Ya se muestra el contorno del Distrito 12. Cuando captures ciudadanos con latitud y longitud, aparecerán como pines verde/amarillo/rojo.")
    else:
        st.markdown("### Registros en mapa")
        st.dataframe(df_map, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Reportes":
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📊 Reportes")
    colonias = leer_colonias()
    c1, c2, c3 = st.columns(3)
    with c1:
        categoria = st.selectbox("Categoría", ["Todas"] + CATEGORIAS)
    with c2:
        colonia = st.selectbox("Colonia", ["Todas"] + colonias)
    with c3:
        seccion = st.text_input("Sección")
    texto = st.text_input("Buscar texto")
    if st.button("📊 Generar reporte"):
        st.session_state["reporte_d12"] = buscar_ciudadanos(texto, categoria, colonia, seccion, 10000)
    rep = st.session_state.get("reporte_d12", pd.DataFrame())
    if rep.empty:
        st.info("Selecciona filtros y genera el reporte.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Registros", len(rep))
        c2.metric("Colonias", rep["colonia"].nunique())
        c3.metric("Secciones", rep["seccion"].nunique())
        st.dataframe(rep, use_container_width=True)
        st.download_button("📥 Descargar Excel", data=crear_excel(rep), file_name="reporte_distrito12.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.markdown("### Por categoría")
        st.dataframe(rep.groupby("categoria", dropna=False).size().reset_index(name="registros"), use_container_width=True)
        st.markdown("### Por colonia")
        st.dataframe(rep.groupby("colonia", dropna=False).size().reset_index(name="registros").sort_values("registros", ascending=False), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Excel":
    if st.session_state.rol_d12 == "Consulta":
        st.warning("Tu usuario sólo tiene permiso de consulta.")
        st.stop()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📥 Importar Excel y cruzar información")
    st.info("Columnas recomendadas: nombre, telefono, direccion, colonia, seccion, categoria, latitud, longitud, observaciones")
    archivo = st.file_uploader("Sube Excel", type=["xlsx", "xls"])
    if archivo:
        df = pd.read_excel(archivo)
        st.dataframe(df.head(100), use_container_width=True)
        if st.button("🚀 Importar registros"):
            insertados = 0
            for _, r in df.iterrows():
                try:
                    data = {
                        "nombre": limpiar(r.get("nombre", r.get("NOMBRE", ""))),
                        "telefono": str(r.get("telefono", r.get("TELEFONO", ""))),
                        "direccion": limpiar(r.get("direccion", r.get("DIRECCION", ""))),
                        "colonia": limpiar(r.get("colonia", r.get("COLONIA", ""))),
                        "seccion": str(r.get("seccion", r.get("SECCION", ""))).replace(".0", ""),
                        "distrito": "12",
                        "categoria": str(r.get("categoria", r.get("CATEGORIA", "Verde"))).title(),
                        "latitud": float(r.get("latitud", r.get("LATITUD", 0)) or 0) or None,
                        "longitud": float(r.get("longitud", r.get("LONGITUD", 0)) or 0) or None,
                        "observaciones": limpiar(r.get("observaciones", r.get("OBSERVACIONES", ""))),
                        "feedback": "",
                        "fecha": date.today(),
                        "hora": datetime.now().time().replace(microsecond=0),
                    }
                    insertar_ciudadano(data)
                    insertados += 1
                except Exception as e:
                    conn.rollback()
                    st.warning(f"Registro no importado: {e}")
            st.success(f"Importación terminada. Registros insertados: {insertados}")
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Evidencias":
    if st.session_state.rol_d12 == "Consulta":
        st.warning("Tu usuario sólo tiene permiso de consulta.")
        st.stop()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📷 Evidencias / Expediente digital")
    st.info("Aquí puedes tomar foto desde celular o subir archivo de la INE, comprobante y otras evidencias.")

    texto = st.text_input("Buscar persona, colonia, teléfono o dirección")
    if st.button("🔎 Buscar registro"):
        st.session_state["busqueda_evid_d12"] = buscar_ciudadanos(texto=texto, limite=50)

    df = st.session_state.get("busqueda_evid_d12", pd.DataFrame())
    if df.empty:
        st.info("Busca un registro para subir evidencias.")
    else:
        cid = st.selectbox(
            "Selecciona registro",
            df["id"].tolist(),
            format_func=lambda x: f"ID {x} | {df[df['id']==x].iloc[0]['nombre']} | {df[df['id']==x].iloc[0]['colonia']}"
        )
        st.dataframe(df[df["id"] == cid], use_container_width=True)

        st.markdown("### 🪪 INE")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**INE frente**")
            ine_frente_foto = st.camera_input("📷 Tomar foto INE frente", key=f"cam_ine_frente_{cid}")
            ine_frente_archivo = st.file_uploader("📄 Subir INE frente", type=["jpg", "jpeg", "png", "pdf"], key=f"up_ine_frente_{cid}")
        with c2:
            st.markdown("**INE reverso**")
            ine_reverso_foto = st.camera_input("📷 Tomar foto INE reverso", key=f"cam_ine_reverso_{cid}")
            ine_reverso_archivo = st.file_uploader("📄 Subir INE reverso", type=["jpg", "jpeg", "png", "pdf"], key=f"up_ine_reverso_{cid}")

        st.markdown("### 👤 Foto de persona y comprobante")
        c3, c4 = st.columns(2)
        with c3:
            foto_persona = st.camera_input("📷 Tomar foto de la persona", key=f"cam_persona_{cid}")
            foto_persona_archivo = st.file_uploader("📄 Subir foto de la persona", type=["jpg", "jpeg", "png"], key=f"up_persona_{cid}")
        with c4:
            comprobante = st.file_uploader("📄 Subir comprobante de domicilio", type=["jpg", "jpeg", "png", "pdf"], key=f"up_comprobante_{cid}")

        obs_ine = st.text_input("Observación para documentos principales", key=f"obs_principal_{cid}").upper()

        if st.button("💾 Guardar INE / documentos principales"):
            guardados = 0
            documentos = [
                (ine_frente_foto, "INE Frente", "foto"),
                (ine_frente_archivo, "INE Frente", "archivo"),
                (ine_reverso_foto, "INE Reverso", "foto"),
                (ine_reverso_archivo, "INE Reverso", "archivo"),
                (foto_persona, "Foto Persona", "foto"),
                (foto_persona_archivo, "Foto Persona", "archivo"),
                (comprobante, "Comprobante Domicilio", "archivo"),
            ]
            for archivo_doc, tipo_doc, origen in documentos:
                if archivo_doc is not None:
                    # st.camera_input genera nombre genérico; lo cambiamos para que quede claro en carpeta.
                    if origen == "foto" and hasattr(archivo_doc, "name"):
                        archivo_doc.name = f"{normalizar_archivo(tipo_doc)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    if guardar_evidencia(int(cid), archivo_doc, tipo_doc, obs_ine):
                        guardados += 1
            if guardados > 0:
                st.success(f"Documentos guardados correctamente: {guardados}")
                st.rerun()
            else:
                st.warning("No seleccionaste ni tomaste ninguna foto para guardar.")

        st.markdown("### 📎 Otra evidencia")
        tipo = st.selectbox("Tipo", ["Foto de visita", "Postal", "INE", "Comprobante", "Otro"])
        obs = st.text_input("Observación", key=f"obs_otro_{cid}")
        archivo = st.file_uploader("Archivo adicional", type=["jpg", "jpeg", "png", "pdf", "xlsx", "docx"], key=f"archivo_otro_{cid}")
        if st.button("📎 Guardar evidencia adicional"):
            if guardar_evidencia(int(cid), archivo, tipo, obs.upper()):
                st.success("Evidencia guardada.")
                st.rerun()

        st.markdown("### Evidencias guardadas")
        evid = leer_evidencias(int(cid))
        st.dataframe(evid, use_container_width=True)
        for _, r in evid.iterrows():
            ruta = str(r["ruta_archivo"])
            if os.path.exists(ruta):
                with open(ruta, "rb") as f:
                    st.download_button(
                        f"📥 Descargar {r['tipo']} - {r['nombre_archivo']}",
                        data=f.read(),
                        file_name=str(r["nombre_archivo"]),
                        key=f"evid_{r['id']}"
                    )
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "IA":
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🤖 Asistente Inteligente Distrito 12")
    ejemplos = [
        "Dame los rojos",
        "Registros de hoy",
        "Cuántos hay por colonia",
        "Cuántos hay por sección",
        "Registros por categoría",
        "Buscar Palo Verde",
    ]
    ejemplo = st.selectbox("Preguntas rápidas", ["-- Escribir --"] + ejemplos)
    consulta = st.text_area("¿Qué información necesitas?", value="" if ejemplo == "-- Escribir --" else ejemplo, height=100)
    if st.button("🤖 Generar respuesta"):
        if not consulta.strip():
            st.warning("Escribe una consulta.")
        else:
            try:
                titulo, df, agrupado = interpretar_ia(consulta)
                st.session_state["ia_titulo"] = titulo
                st.session_state["ia_df"] = df
                st.session_state["ia_agrupado"] = agrupado
            except Exception as e:
                conn.rollback()
                st.error(f"No se pudo generar: {e}")
    titulo = st.session_state.get("ia_titulo")
    df = st.session_state.get("ia_df", pd.DataFrame())
    agrupado = st.session_state.get("ia_agrupado", pd.DataFrame())
    if titulo:
        st.success(titulo)
        st.metric("Registros encontrados", len(df))
        if not agrupado.empty:
            st.dataframe(agrupado, use_container_width=True)
            st.bar_chart(agrupado.set_index(agrupado.columns[0])["registros"])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Descargar Excel IA", data=crear_excel(df), file_name="reporte_ia_distrito12.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Pregunta algo al asistente para generar información.")
    st.markdown('</div>', unsafe_allow_html=True)

elif menu == "Configuración":
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("⚙️ Configuración")
    st.write("Base de datos:", PG_DATABASE)
    st.write("Carpeta evidencias:", CARPETA_EVIDENCIAS)
    st.write("Usuarios iniciales:")
    st.code("admin / 1234\ncaptura / 1234\nconsulta / 1234")
    st.markdown("### Comando para correr")
    st.code("streamlit run app_distrito12.py --server.address 0.0.0.0 --server.port 8502")
    st.markdown("### Requisitos")
    st.code("streamlit\npandas\npsycopg2-binary\npydeck\nopenpyxl\nstreamlit-option-menu")
    st.markdown('</div>', unsafe_allow_html=True)
