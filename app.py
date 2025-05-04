import streamlit as st
import folium
from streamlit.components.v1 import html
from fpdf import FPDF
from pyproj import Transformer
import requests
import xml.etree.ElementTree as ET
import geopandas as gpd
import tempfile
import os
from shapely.geometry import Point
import uuid
from datetime import datetime
from docx import Document
from branca.element import Template, MacroElement
from io import BytesIO
from html2image import Html2Image
from staticmap import StaticMap, CircleMarker

# Diccionario con los nombres de municipios y sus nombres base de archivo
shp_urls = {
"ABANILLA": "ABANILLA",
"ABARAN": "ABARAN",
"AGUILAS": "AGUILAS",
"ALBUDEITE": "ALBUDEITE",
"ALCANTARILLA": "ALCANTARILLA",
"ALEDO": "ALEDO",
"ALGUAZAS": "ALGUAZAS",
"ALHAMA_DE_MURCIA": "ALHAMA_DE_MURCIA",
"ARCHENA": "ARCHENA",
"BENIEL": "BENIEL",
"BLANCA": "BLANCA",
"BULLAS": "BULLAS",
"CALASPARRA": "CALASPARRA",
"CAMPOS_DEL_RIO": "CAMPOS_DEL_RIO",
"CARAVACA_DE_LA_CRUZ": "CARAVACA_DE_LA_CRUZ",
"CARTAGENA": "CARTAGENA",
"CEHEGIN": "CEHEGIN",
"CEUTI": "CEUTI",
"CIEZA": "CIEZA",
"FORTUNA": "FORTUNA",
"FUENTE_ALAMO_DE_MURCIA": "FUENTE_ALAMO_DE_MURCIA",
"JUMILLA": "JUMILLA",
"LAS_TORRES_DE_COTILLAS": "LAS_TORRES_DE_COTILLAS",
"LA_UNION": "LA_UNION",
"LIBRILLA": "LIBRILLA",
"LORCA": "LORCA",
"LORQUI": "LORQUI",
"LOS_ALCAZARES": "LOS_ALCAZARES",
"MAZARRON": "MAZARRON",
"MOLINA_DE_SEGURA": "MOLINA_DE_SEGURA",
"MORATALLA": "MORATALLA",
"MULA": "MULA",
"MURCIA": "MURCIA",
"OJOS": "OJOS",
"PLIEGO": "PLIEGO",
"PUERTO_LUMBRERAS": "PUERTO_LUMBRERAS",
"RICOTE": "RICOTE",
"SANTOMERA": "SANTOMERA",
"SAN_JAVIER": "SAN_JAVIER",
"SAN_PEDRO_DEL_PINATAR": "SAN_PEDRO_DEL_PINATAR",
"TORRE_PACHECO": "TORRE_PACHECO",
"TOTANA": "TOTANA",
"ULEA": "ULEA",
"VILLANUEVA_DEL_RIO_SEGURA": "VILLANUEVA_DEL_RIO_SEGURA",
"YECLA": "YECLA",

}

# Función para cargar shapefiles desde GitHub
@st.cache_data
def cargar_shapefile_desde_github(base_name):
    base_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/CATASTRO/"
    exts = [".shp", ".shx", ".dbf", ".prj", ".cpg"]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        local_paths = {}
        for ext in exts:
            filename = base_name + ext
            url = base_url + filename
            local_path = os.path.join(tmpdir, filename)
            
            response = requests.get(url)
            if response.status_code != 200:
                st.error(f"Error al descargar {url}")
                return None  # Si falta algún archivo esencial, falla todo
            
            with open(local_path, "wb") as f:
                f.write(response.content)
            local_paths[ext] = local_path
        
        shp_path = local_paths[".shp"]
        gdf = gpd.read_file(shp_path)
        return gdf
            
# Función para transformar coordenadas de ETRS89 a WGS84 (Long, Lat)
def transformar_coordenadas(x, y):
    transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lon, lat

# Función para consultar si el punto está dentro de algún polígono del GeoJSON
def consultar_geojson(x, y, geojson_url, nombre_afeccion="Afección", campo_nombre="nombre"):
    try:
        gdf = gpd.read_file(geojson_url)
        punto = Point(x, y)
        seleccion = gdf[gdf.contains(punto)]
        if not seleccion.empty:
            props = seleccion.iloc[0]
            nombre = props.get(campo_nombre, f"{nombre_afeccion} encontrado")
            return f"Dentro de {nombre_afeccion}: {nombre}"
        else:
            return f"No se encuentra en ninguna {nombre_afeccion}"
    except Exception as e:
        st.error(f"Error al leer GeoJSON de {nombre_afeccion}: {e}")
        return f"Error al consultar {nombre_afeccion}"

# Función para consultar si el punto está dentro de algún MUP del GeoJSON
def consultar_mup(x, y, geojson_url):
    try:
        gdf = gpd.read_file(geojson_url)
        punto = Point(x, y)
        seleccion = gdf[gdf.contains(punto)]
        if not seleccion.empty:
            props = seleccion.iloc[0]
            id_monte = props.get("ID_MONTE", "Desconocido")
            nombre_monte = props.get("NOMBREMONT", "Desconocido")
            municipio = props.get("MUNICIPIO", "Desconocido")
            propiedad = props.get("PROPIEDAD", "Desconocido")
            return (f"Dentro de MUP:\nID: {id_monte}\nNombre: {nombre_monte}\nMunicipio: {municipio}\nPropiedad: {propiedad}")
        else:
            return "No se encuentra en ningún MUP"
    except Exception as e:
        st.error(f"Error al consultar MUP: {e}")
        return "Error al consultar MUP"

# Función para crear el mapa con afecciones específicas
def crear_mapa(x, y, afecciones=[]):
    m = folium.Map(location=[y, x], zoom_start=16)
    folium.Marker([y, x], popup=f"Coordenadas transformadas: {x}, {y}").add_to(m)

    # Agregar capas WMS
    folium.raster_layers.WmsTileLayer(
        url="https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
        layers="Catastro",
        fmt='image/png',
        transparent=True,
        name="Catastro",
        control=True
    ).add_to(m)

    folium.raster_layers.WmsTileLayer(
        url="https://wms.mapama.gob.es/sig/Biodiversidad/RedNatura/wms.aspx?",
        name="Red Natura 2000",
        fmt="image/png",
        layers="Red Natura 2000",
        transparent=True,
        opacity=0.25,
        control=True
    ).add_to(m)

    folium.raster_layers.WmsTileLayer(
        url="https://wms.mapama.gob.es/sig/Biodiversidad/PropiedadMontes_UP/wms.aspx?",
        name="Catálogo de Montes de Utilidad Pública",
        fmt="image/png",
        layers="Catálogo de Montes de Utilidad Pública",
        transparent=True,
        opacity=0.25,
        control=True
    ).add_to(m)

    folium.LayerControl().add_to(m)

    # Añadir leyenda personalizada
    legend_html = """
    {% macro html(this, kwargs) %}
<div style="
    position: fixed;
    bottom: 20px;
    left: 20px;
    background-color: white;
    border: 1px solid grey;
    z-index: 9999;
    font-size: 10px;
    padding: 5px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
    line-height: 1.1em;
    width: auto;
    transform: scale(0.75); /* Escala todo el contenedor */
    transform-origin: top left;
">
    <b>Leyenda</b><br>
    <div>
        <img src="https://wms.mapama.gob.es/sig/Biodiversidad/RedNatura/wms.aspx?REQUEST=GetLegendGraphic&VERSION=1.1.1&FORMAT=image/png&LAYER=Red Natura 2000" alt="Red Natura"><br>
        <img src="https://wms.mapama.gob.es/sig/Biodiversidad/PropiedadMontes_UP/wms.aspx?REQUEST=GetLegendGraphic&VERSION=1.1.1&FORMAT=image/png&LAYER=Catálogo de Montes de Utilidad Pública" alt="MUP"><br>
    </div>
</div>
{% endmacro %}
"""

    legend = MacroElement()
    legend._template = Template(legend_html)
    m.get_root().add_child(legend)

    # Agregar afecciones como marcadores en el mapa
    for afeccion in afecciones:
        folium.Marker([y, x], popup=afeccion).add_to(m)

    uid = uuid.uuid4().hex[:8]
    mapa_html = f"mapa_{uid}.html"
    m.save(mapa_html)

    return mapa_html, afecciones

# Función auxiliar para convertir el mapa HTML en imagen PNG
def generar_imagen_estatica_mapa(x, y, zoom=16, size=(800, 600)):
    mapa = StaticMap(size[0], size[1])
    marcador = CircleMarker((x, y), 'red', 12)
    mapa.add_marker(marcador)
    image = mapa.render(zoom=zoom)

    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "mapa.png")
    image.save(output_path)
    return output_path

# Función para generar el PDF con los datos de la solicitud

def generar_pdf(datos, x, y, filename):
    pdf = FPDF()
    pdf.add_page()

    # Descargar e insertar el logo
    logo_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/logos.jpg"
    response = requests.get(logo_url)
    if response.status_code == 200:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_img:
            tmp_img.write(response.content)
            tmp_img_path = tmp_img.name

        page_width = pdf.w - 2 * pdf.l_margin
        logo_width = page_width
        pdf.image(tmp_img_path, x=pdf.l_margin, y=10, w=logo_width)

        logo_height = logo_width * 0.2
        pdf.set_y(10 + logo_height + 5)

    # Título principal
    pdf.set_font("Arial", "B", size=16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "Informe de Afecciones Ambientales", ln=True, align="C")
    pdf.ln(10)

    azul_rgb = (141, 179, 226)

    # Lista de campos que deben aparecer en orden y en negrita
    campos_orden = [
        "Fecha solicitud", "Fecha informe", "Nombre", "Apellidos", "Dni", "Dirección",
        "Teléfono", "Email", "Objeto de la solicitud"
    ]

    # Campos de localización
    campos_localizacion = ["Municipio", "Polígono", "Parcela"]
    
    def seccion_titulo(texto):
        pdf.set_fill_color(*azul_rgb)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, texto, ln=True, fill=True)
        pdf.ln(2)

    def campo_orden(titulo, valor):
        pdf.set_font("Arial", "B", 12)
        pdf.cell(50, 8, f"{titulo}:", ln=0)
        pdf.set_font("Arial", "", 12)
        pdf.multi_cell(0, 8, valor if valor else "No especificado")
 
    # 1. Datos del solicitante
    seccion_titulo("1. Datos del solicitante")
    campos_orden = [
        ("Fecha solicitud", datos.get("fecha_solicitud", "").strip()),
        ("Fecha informe", datos.get("fecha_informe", "").strip()),
        ("Nombre", datos.get("nombre", "").strip()),
        ("Apellidos", datos.get("apellidos", "").strip()),
        ("DNI", datos.get("dni", "").strip()),
        ("Dirección", datos.get("dirección", "").strip()),
        ("Teléfono", datos.get("teléfono", "").strip()),
        ("Email", datos.get("email", "").strip()),
    ]
    for titulo, valor in campos_orden:
        campo_orden(titulo, valor)

    # Objeto de la solicitud
    objeto = datos.get("objeto de la solicitud", "").strip()
    pdf.ln(2)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Objeto de la solicitud:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, objeto if objeto else "No especificado")

    # 2. Afecciones detectadas
    seccion_titulo("2. Afecciones detectadas")
    afecciones_keys = [k for k in datos if k.lower().startswith("afección")]

    if afecciones_keys:
        for key in afecciones_keys:
            valor = datos[key].strip()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, f"{key.capitalize()}:", ln=True)
            pdf.set_font("Arial", "", 12)

            if key.lower() == "afección mup" and valor.lower().startswith("dentro de mup"):
                lines = valor.split("\n")
                resumen = lines[0]
                pdf.multi_cell(0, 8, resumen)
                if len(lines) > 4:
                    # Cabecera tabla
                    pdf.set_fill_color(200, 200, 200)
                    pdf.set_font("Arial", "B", 11)
                    pdf.cell(30, 8, "ID", border=1, fill=True)
                    pdf.cell(80, 8, "Nombre", border=1, fill=True)
                    pdf.cell(40, 8, "Municipio", border=1, fill=True)
                    pdf.cell(40, 8, "Propiedad", border=1, ln=True, fill=True)

                    # Obtener los campos por líneas (se asume estructura tipo 'ID: valor')
                    datos_mup = {}
                    for line in lines[1:]:
                        if ":" in line:
                            clave, valor_linea = line.split(":", 1)
                            datos_mup[clave.strip().lower()] = valor_linea.strip()

                    pdf.set_font("Arial", "", 11)
                    pdf.cell(30, 8, datos_mup.get("id", ""), border=1)
                    pdf.cell(80, 8, datos_mup.get("nombre", ""), border=1)
                    pdf.cell(40, 8, datos_mup.get("municipio", ""), border=1)
                    pdf.cell(40, 8, datos_mup.get("propiedad", ""), border=1, ln=True)
                else:
                    pdf.multi_cell(0, 8, "\n".join(lines[1:]))
            else:
                pdf.multi_cell(0, 8, valor)
    else:
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 8, "No se han detectado afecciones.", ln=True)

    # Afecciones adicionales que no se han mostrado
    for key in ["afección vp", "afección enp", "afección zepa", "afección lic", "afección tm"]:
        valor = datos.get(key, "").strip()
        if valor:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, f"{key.capitalize()}:", ln=True)
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 8, valor)

    # 3. Localización
    seccion_titulo("3. Localización")
    for campo in ["municipio", "polígono", "parcela"]:
        valor = datos.get(campo, "").strip()
        campo_orden(campo.capitalize(), valor if valor else "No disponible")

    # Coordenadas
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Coordenadas ETRS89: X = {x}, Y = {y}", ln=True)

    # Insertar imagen del mapa si existe
    imagen_mapa_path = generar_imagen_estatica_mapa(x, y)

    if os.path.exists(imagen_mapa_path):
        epw = pdf.w - 2 * pdf.l_margin  # Calcular el ancho útil de la página

        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Mapa de localización:", ln=True)
        pdf.image(imagen_mapa_path, x=pdf.l_margin, w=epw)

    pdf.output(filename)
    return filename
    
# Interfaz de Streamlit  
st.image("https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/logos.jpg", use_container_width=True)
st.title("\U0001F5FA️ Informe de Afecciones Ambientales")

modo = st.radio("Selecciona el modo de búsqueda", ["Por coordenadas", "Por parcela"])

# Variables iniciales de coordenadas y de selección (para el modo parcela)
x = 0.0
y = 0.0
municipio_sel = ""
masa_sel = ""
parcela_sel = ""

if modo == "Por parcela":
    municipio_sel = st.selectbox("Municipio", sorted(shp_urls.keys()))
    archivo_base = shp_urls[municipio_sel]
    
    # Cargar el shapefile del municipio seleccionado
    gdf = cargar_shapefile_desde_github(archivo_base)
    
    if gdf is not None:
        masa_sel = st.selectbox("Polígono", sorted(gdf["MASA"].unique()))
        parcela_sel = st.selectbox("Parcela", sorted(gdf[gdf["MASA"] == masa_sel]["PARCELA"].unique()))
        parcela = gdf[(gdf["MASA"] == masa_sel) & (gdf["PARCELA"] == parcela_sel)]
        
        if parcela.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all():
            # Calcular el centroide y asignar coordenadas
            puntos = parcela.copy()
            puntos["geometry"] = puntos.geometry.centroid
            puntos["longitude"] = puntos.geometry.x
            puntos["latitude"] = puntos.geometry.y
            parcela = puntos  
          
            punto_centro = parcela.geometry.iloc[0]
            x = punto_centro.x
            y = punto_centro.y         
                    
            st.success("Parcela cargada correctamente.")
            st.write(f"Municipio: {municipio_sel}")
            st.write(f"Polígono: {masa_sel}")
            st.write(f"Parcela: {parcela_sel}")
        else:
            st.error("La geometría seleccionada no es un polígono válido.")
    else:
        st.error(f"No se pudo cargar el shapefile para el municipio: {municipio_sel}")

# Si el modo es "Por coordenadas" NO se solicita la entrada previa
# Se incluirán los inputs de coordenadas en el formulario

with st.form("formulario"):
    # Si el modo es "Por coordenadas", incluir campos para las coordenadas en el formulario
    if modo == "Por coordenadas":
        x = st.number_input("Coordenada X (ETRS89)", format="%.2f", help="Introduce coordenadas en metros, sistema ETRS89 / UTM zona 30")
        y = st.number_input("Coordenada Y (ETRS89)", format="%.2f")
    else:
        # Muestra las coordenadas calculadas y las pone como campo oculto para el formulario
        st.info(f"Coordenadas obtenidas de la parcela: X = {x}, Y = {y}")
        
    fecha_solicitud = st.date_input("Fecha de la solicitud")
    nombre = st.text_input("Nombre")
    apellidos = st.text_input("Apellidos")
    dni = st.text_input("DNI")
    direccion = st.text_input("Dirección")
    telefono = st.text_input("Teléfono")
    email = st.text_input("Correo electrónico")
    objeto = st.text_area("Objeto de la solicitud", max_chars=255)       
    submitted = st.form_submit_button("Generar informe")

if 'mapa_html' not in st.session_state:
    st.session_state['mapa_html'] = None
if 'pdf_file' not in st.session_state:
    st.session_state['pdf_file'] = None

if submitted:
    # Validación de entradas
    if not nombre or not apellidos or not dni or x == 0 or y == 0:
        st.warning("Por favor, completa todos los campos obligatorios y asegúrate de que las coordenadas son correctas.")
    else:
        lon, lat = transformar_coordenadas(x, y)

        # Mostrar los datos seleccionados (solo si estamos en modo parcela)
        if modo == "Por parcela":
            st.write(f"Municipio seleccionado: {municipio_sel}")
            st.write(f"Polígono seleccionado: {masa_sel}")
            st.write(f"Parcela seleccionada: {parcela_sel}")
        else:
            st.write("Modo por coordenadas seleccionado. Municipio no disponible.")

        # URLs GeoJSON
        enp_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/ENP.json"
        zepa_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/ZEPA.json"
        lic_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/LIC.json"
        vp_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/VP.json"
        tm_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/TM.json"
        mup_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/MUP.json"

        # Consultas de afecciones
        afeccion_enp = consultar_geojson(x, y, enp_url, "ENP", campo_nombre="nombre")
        afeccion_zepa = consultar_geojson(x, y, zepa_url, "ZEPA", campo_nombre="SITE_NAME")
        afeccion_lic = consultar_geojson(x, y, lic_url, "LIC", campo_nombre="SITE_NAME")
        afeccion_vp = consultar_geojson(x, y, vp_url, "VP", campo_nombre="VP_NB")
        afeccion_tm = consultar_geojson(x, y, tm_url, "TM", campo_nombre="NAMEUNIT")
        afeccion_mup = consultar_mup(x, y, mup_url)

        # Compilando datos para mostrar
        afecciones = [afeccion_enp, afeccion_zepa, afeccion_lic, afeccion_vp, afeccion_tm, afeccion_mup]
        
        datos = {
            "fecha_solicitud": fecha_solicitud.strftime('%d/%m/%Y'),
            "fecha_informe": datetime.today().strftime('%d/%m/%Y'),
            "nombre": nombre,
            "apellidos": apellidos,
            "dni": dni,
            "dirección": direccion,
            "teléfono": telefono,
            "email": email,
            "objeto de la solicitud": objeto,
            "afección MUP": afeccion_mup,
            "afección VP": afeccion_vp,
            "afección ENP": afeccion_enp,
            "afección ZEPA": afeccion_zepa,
            "afección LIC": afeccion_lic,
            "afección TM": afeccion_tm,
            "coordenadas_x": x,
            "coordenadas_y": y,
            "municipio": municipio_sel if modo == "Por parcela" else "N/A",  # Solo en modo parcela
            "polígono": masa_sel if modo == "Por parcela" else "N/A",  # Solo en modo parcela
            "parcela": parcela_sel if modo == "Por parcela" else "N/A"  # Solo en modo parcela  
        }
        
        # Crear mapa con afecciones
        mapa_html, afecciones = crear_mapa(lon, lat, afecciones)

        # Guardar estado 
        st.session_state['mapa_html'] = mapa_html
        st.session_state['afecciones'] = afecciones

        # Mostrar el mapa y el PDF
        st.subheader("Resultado de las afecciones")
        for afeccion in afecciones:
            st.write(f"• {afeccion}")

        with open(mapa_html, 'r') as f:
            html(f.read(), height=500)

        # PDF generado desde los datos
        pdf_filename = f"informe_{uuid.uuid4().hex[:8]}.pdf"
        generar_pdf(datos, x, y, pdf_filename)
        st.session_state['pdf_file'] = pdf_filename

# Botones de descarga
if st.session_state['mapa_html'] and st.session_state['pdf_file']:
    with open(st.session_state['pdf_file'], "rb") as f:
        st.download_button("📄 Descargar informe PDF", f, file_name="informe_afecciones.pdf")

    with open(st.session_state['mapa_html'], "r") as f:
        st.download_button("🌍 Descargar mapa HTML", f, file_name="mapa_busqueda.html")
