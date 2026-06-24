import os
import re
import unic@st.cache_data(show_spinner=False)
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
        # Evita duplicar el último punto si el KML ya cerró el polígono
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

odedata
from pathlib import Path
from datetime import datetime, date
from io import BytesIO

import pandas as pd
import streamlit as st
import psycopg2
import pydeck as pdk

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
PG_DATABASE = "distrito12"
PG_USER = "postgres"
PG_PASSWORD = "Nitrotech1611"  # Cambia si tu PostgreSQL usa otra contraseña

CARPETA_EVIDENCIAS = r"D:\DISTRITO12\EVIDENCIAS"
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
        st.info("Primero crea la base de datos en PostgreSQL con nombre: distrito12")
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
    <h1>📍 Sistema Integral Distrito 12</h1>
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
        ["Inicio", "Captura", "Mapeador", "Reportes", "Excel", "Evidencias", "IA", "Configuración"],
        icons=["house", "person-plus", "map", "bar-chart", "file-earmark-excel", "camera", "robot", "gear"],
        default_index=0,
        orientation="horizontal",
    )
else:
    menu = st.radio(
        "Módulos",
        ["Inicio", "Captura", "Mapeador", "Reportes", "Excel", "Evidencias", "IA", "Configuración"],
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
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("👥 Captura homologada Distrito 12")
    c1, c2 = st.columns(2)
    with c1:
        nombre = st.text_input("Nombre completo").upper()
        telefono = st.text_input("Teléfono")
        direccion = st.text_input("Dirección").upper()
        colonia = st.text_input("Colonia").upper()
        seccion = st.text_input("Sección electoral").upper()
    with c2:
        distrito = st.text_input("Distrito", value="12")
        categoria = st.selectbox("Categoría", CATEGORIAS)
        fecha_cap = st.date_input("Fecha", value=date.today())
        hora_cap = st.time_input("Hora", value=datetime.now().time().replace(microsecond=0))
        latitud = st.number_input("Latitud", value=0.0, format="%.8f")
        longitud = st.number_input("Longitud", value=0.0, format="%.8f")
    observaciones = st.text_area("Observaciones").upper()
    feedback = st.text_area("Feedback / seguimiento").upper()

    if st.button("💾 Guardar registro"):
        if not nombre and not direccion:
            st.error("Captura al menos nombre o dirección.")
        else:
            cid = insertar_ciudadano({
                "nombre": nombre, "telefono": telefono, "direccion": direccion, "colonia": colonia,
                "seccion": seccion, "distrito": distrito, "categoria": categoria,
                "latitud": latitud if latitud != 0 else None,
                "longitud": longitud if longitud != 0 else None,
                "observaciones": observaciones, "feedback": feedback,
                "fecha": fecha_cap, "hora": hora_cap,
            })
            st.success(f"Registro guardado correctamente. ID: {cid}")
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
    st.subheader("📷 Evidencias / Postales")
    texto = st.text_input("Buscar persona, colonia, teléfono o dirección")
    if st.button("🔎 Buscar registro"):
        st.session_state["busqueda_evid_d12"] = buscar_ciudadanos(texto=texto, limite=50)
    df = st.session_state.get("busqueda_evid_d12", pd.DataFrame())
    if df.empty:
        st.info("Busca un registro para subir evidencias.")
    else:
        cid = st.selectbox("Selecciona registro", df["id"].tolist(), format_func=lambda x: f"ID {x} | {df[df['id']==x].iloc[0]['nombre']} | {df[df['id']==x].iloc[0]['colonia']}")
        st.dataframe(df[df["id"] == cid], use_container_width=True)
        tipo = st.selectbox("Tipo", ["Foto de visita", "Postal", "INE", "Comprobante", "Otro"])
        obs = st.text_input("Observación")
        archivo = st.file_uploader("Archivo", type=["jpg", "jpeg", "png", "pdf", "xlsx", "docx"])
        if st.button("📎 Guardar evidencia"):
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
                    st.download_button(f"📥 Descargar {r['nombre_archivo']}", data=f.read(), file_name=str(r["nombre_archivo"]), key=f"evid_{r['id']}")
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
    st.code("streamlit run app_distrito12.py --server.address 0.0.0.0")
    st.markdown("### Requisitos")
    st.code("streamlit\npandas\npsycopg2-binary\npydeck\nopenpyxl\nstreamlit-option-menu")
    st.markdown('</div>', unsafe_allow_html=True)
