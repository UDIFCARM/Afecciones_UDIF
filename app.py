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
                return None
            
            with open(local_path, "wb") as f:
                f.write(response.content)
            local_paths[ext] = local_path
        
        shp_path = local_paths[".shp"]
        gdf = gpd.read_file(shp_path)
        return gdf

# Función para encontrar municipio, polígono y parcela a partir de coordenadas
def encontrar_municipio_poligono_parcela(x, y):
    punto = Point(x, y)
    for municipio, archivo_base in shp_urls.items():
        gdf = cargar_shapefile_desde_github(archivo_base)
        if gdf is None:
            continue
        seleccion = gdf[gdf.contains(punto)]
        if not seleccion.empty:
            parcela_gdf = seleccion.iloc[[0]]
            masa = parcela_gdf["MASA"].iloc[0]
            parcela = parcela_gdf["PARCELA"].iloc[0]
            return municipio, masa, parcela, parcela_gdf
    return "N/A", "N/A", "N/A", None

# Función para transformar coordenadas de ETRS89 a WGS84
def transformar_coordenadas(x, y):
    transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lon, lat

# Función para consultar si la geometría intersecta con algún polígono del GeoJSON
def consultar_geojson(geom, geojson_url, nombre_afeccion="Afección", campo_nombre="nombre"):
    try:
        gdf = gpd.read_file(geojson_url)
        seleccion = gdf[gdf.intersects(geom)]
        if not seleccion.empty:
            nombres = ', '.join(seleccion[campo_nombre].dropna().unique())
            return f"Dentro de {nombre_afeccion}: {nombres}"
        else:
            return f"No se encuentra en ninguna {nombre_afeccion}"
    except Exception as e:
        st.error(f"Error al leer GeoJSON de {nombre_afeccion}: {e}")
        return f"Error al consultar {nombre_afeccion}"

# Función para consultar si la geometría intersecta con algún MUP del GeoJSON
def consultar_mup(geom, geojson_url):
    try:
        gdf = gpd.read_file(geojson_url)
        seleccion = gdf[gdf.intersects(geom)]
        if not seleccion.empty:
            info = []
            for _, props in seleccion.iterrows():
                id_monte = props.get("ID_MONTE", "Desconocido")
                nombre_monte = props.get("NOMBREMONT", "Desconocido")
                municipio = props.get("MUNICIPIO", "Desconocido")
                propiedad = props.get("PROPIEDAD", "Desconocido")
                info.append(f"ID: {id_monte}\nNombre: {nombre_monte}\nMunicipio: {municipio}\nPropiedad: {propiedad}")
            return "Dentro de MUP:\n" + "\n\n".join(info)
        else:
            return "No se encuentra en ningún MUP"
    except Exception as e:
        st.error(f"Error al consultar MUP: {e}")
        return "Error al consultar MUP"

# Función para crear el mapa con afecciones específicas
def crear_mapa(lon, lat, afecciones=[], parcela_gdf=None):
    m = folium.Map(location=[lat, lon], zoom_start=16)
    folium.Marker([lat, lon], popup=f"Coordenadas transformadas: {lon}, {lat}").add_to(m)

    if parcela_gdf is not None:
        parcela_4326 = parcela_gdf.to_crs("EPSG:4326")
        folium.GeoJson(
            parcela_4326.to_json(),
            name="Parcela",
            style_function=lambda x: {'fillColor': 'transparent', 'color': 'blue', 'weight': 2, 'dashArray': '5, 5'}
        ).add_to(m)

    folium.raster_layers.WmsTileLayer(
        url="https://mapas-gis-inter.carm.es/geoserver/ows?SERVICE=WMS&?",
        name="Red Natura 2000",
        fmt="image/png",
        layers="SIG_LUP_SITES_CARM:RN2000",
        transparent=True,
        opacity=0.25,
        control=True
    ).add_to(m)

    folium.raster_layers.WmsTileLayer(
        url="https://mapas-gis-inter.carm.es/geoserver/ows?SERVICE=WMS&?",
        name="Montes",
        fmt="image/png",
        layers="PFO_ZOR_DMVP_CARM:MONTES",
        transparent=True,
        opacity=0.25,
        control=True
    ).add_to(m)

    folium.raster_layers.WmsTileLayer(
        url="https://mapas-gis-inter.carm.es/geoserver/ows?SERVICE=WMS&?",
        name="Vias Pecuarias",
        fmt="image/png",
        layers="PFO_ZOR_DMVP_CARM:VP_CARM",
        transparent=True,
        opacity=0.25,
        control=True
    ).add_to(m)        

    folium.LayerControl().add_to(m)

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
    transform: scale(0.75);
    transform-origin: top left;
">
    <b>Leyenda</b><br>
    <div>
        <img src="https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image%2Fpng&width=20&height=20&layer=SIG_LUP_SITES_CARM%3ARN2000" alt="Red Natura"><br>
        <img src="https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image%2Fpng&width=20&height=20&layer=PFO_ZOR_DMVP_CARM%3AMONTES" alt="Montes"><br>
        <img src="https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image%2Fpng&width=20&height=20&layer=PFO_ZOR_DMVP_CARM%3AVP_CARM" alt="Vias Pecuarias"><br>
    </div>
</div>
{% endmacro %}
"""

    legend = MacroElement()
    legend._template = Template(legend_html)
    m.get_root().add_child(legend)

    for afeccion in afecciones:
        folium.Marker([lat, lon], popup=afeccion).add_to(m)

    uid = uuid.uuid4().hex[:8]
    mapa_html = f"mapa_{uid}.html"
    m.save(mapa_html)

    return mapa_html, afecciones

# Función corregida para generar la imagen estática del mapa usando py-staticmaps
def generar_imagen_estatica_mapa(x, y, zoom=16, size=(800, 600)):
    # Transformar coordenadas de ETRS89 a WGS84
    lon, lat = transformar_coordenadas(x, y)
    
    # Crear un mapa estático con py-staticmaps
    m = StaticMap(size[0], size[1], url_template='http://a.tile.openstreetmap.org/{z}/{x}/{y}.png')
    marker = CircleMarker((lon, lat), 'red', 12)
    m.add_marker(marker)
    
    # Generar la imagen
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "mapa.png")
    image = m.render(zoom=zoom)
    image.save(output_path)
    
    return output_path

# Función para generar el PDF con los datos de la solicitud
# Función para generar el PDF con los datos de la solicitud (modificada para incluir mensaje "No se encuentra" cuando no hay afecciones)
def generar_pdf(datos, x, y, filename):
    pdf = FPDF()
    pdf.add_page()

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

    pdf.set_font("Arial", "B", size=16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "Informe de Afecciones Ambientales", ln=True, align="C")
    pdf.ln(10)

    azul_rgb = (141, 179, 226)

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

    seccion_titulo("1. Datos del solicitante")
    for titulo, valor in campos_orden:
        campo_orden(titulo, valor)

    objeto = datos.get("objeto de la solicitud", "").strip()
    pdf.ln(2)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Objeto de la solicitud:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, objeto if objeto else "No especificado")

    seccion_titulo("2. Afecciones detectadas")

    afecciones_keys = ["afección ENP", "afección ZEPA", "afección LIC", "afección TM"]
    vp_key = "afección VP"
    mup_key = "afección MUP"

    # Procesar afecciones VP
    vp_valor = datos.get(vp_key, "").strip()
    vp_detectado = []
    if vp_valor and not vp_valor.startswith("No se encuentra") and not vp_valor.startswith("Error"):
        nombres_vp = vp_valor.replace("Dentro de VP: ", "").split(", ")
        if len(nombres_vp) > 1:  # Si hay más de una vía pecuaria
            vp_detectado = [(nombre.strip(), "N/A", "N/A", "N/A") for nombre in nombres_vp]
        else:
            # Si solo hay una VP, incluir en otras afecciones
            afecciones_keys.insert(0, vp_key)

    # Procesar otras afecciones como texto, incluyendo "No se encuentra" para las no detectadas
    otras_afecciones = []
    for key in afecciones_keys:
        valor = datos.get(key, "").strip()
        if valor and not valor.startswith("No se encuentra") and not valor.startswith("Error"):
            nombre_afeccion = valor.replace(f"Dentro de {key.replace('afección ', '').strip()}: ", "").strip()
            otras_afecciones.append((key.capitalize(), nombre_afeccion))
        else:
            otras_afecciones.append((key.capitalize(), "No se encuentra"))

    # Mostrar otras afecciones con títulos en negrita
    if any(valor != "No se encuentra" for _, valor in otras_afecciones):
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Otras afecciones:", ln=True)
        pdf.ln(2)
        for titulo, valor in otras_afecciones:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(60, 8, f"{titulo}:", ln=0)
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 8, valor)
        pdf.ln(2)

    # Procesar VP para tabla si hay múltiples
    if vp_detectado:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Afecciones de Vías Pecuarias (VP):", ln=True)
        pdf.ln(2)

        # Configurar la tabla para VP
        col_widths = [30, 80, 40, 40]  # ID, Nombre, Municipio, Propiedad
        row_height = 8
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_widths[0], row_height, "ID", border=1, fill=True)
        pdf.cell(col_widths[1], row_height, "Nombre", border=1, fill=True)
        pdf.cell(col_widths[2], row_height, "Municipio", border=1, fill=True)
        pdf.cell(col_widths[3], row_height, "Propiedad", border=1, fill=True)
        pdf.ln()

        # Agregar filas a la tabla
        pdf.set_font("Arial", "", 10)
        for nombre, id_vp, municipio, propiedad in vp_detectado:
            pdf.cell(col_widths[0], row_height, id_vp, border=1)
            pdf.cell(col_widths[1], row_height, nombre, border=1)
            pdf.cell(col_widths[2], row_height, municipio, border=1)
            pdf.cell(col_widths[3], row_height, propiedad, border=1)
            pdf.ln()
        pdf.ln(10)  # Espacio adicional después de la tabla

    # Procesar MUP para tabla
    mup_valor = datos.get(mup_key, "").strip()
    mup_detectado = []
    if mup_valor and not mup_valor.startswith("No se encuentra") and not mup_valor.startswith("Error"):
        entries = mup_valor.replace("Dentro de MUP:\n", "").split("\n\n")
        for entry in entries:
            lines = entry.split("\n")
            if lines:
                id_monte = lines[0].replace("ID: ", "").strip() if len(lines) > 0 else "N/A"
                nombre = lines[1].replace("Nombre: ", "").strip() if len(lines) > 1 else "N/A"
                municipio = lines[2].replace("Municipio: ", "").strip() if len(lines) > 2 else "N/A"
                propiedad = lines[3].replace("Propiedad: ", "").strip() if len(lines) > 3 else "N/A"
                mup_detectado.append((id_monte, nombre, municipio, propiedad))

    if mup_detectado:
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Afecciones de Montes (MUP):", ln=True)
        pdf.ln(2)

        # Configurar la tabla para MUP
        col_widths = [30, 80, 40, 40]  # ID, Nombre, Municipio, Propiedad
        row_height = 8
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_widths[0], row_height, "ID", border=1, fill=True)
        pdf.cell(col_widths[1], row_height, "Nombre", border=1, fill=True)
        pdf.cell(col_widths[2], row_height, "Municipio", border=1, fill=True)
        pdf.cell(col_widths[3], row_height, "Propiedad", border=1, fill=True)
        pdf.ln()

        # Agregar filas a la tabla
        pdf.set_font("Arial", "", 10)
        for id_monte, nombre, municipio, propiedad in mup_detectado:
            pdf.cell(col_widths[0], row_height, id_monte, border=1)
            pdf.cell(col_widths[1], row_height, nombre, border=1)
            pdf.cell(col_widths[2], row_height, municipio, border=1)
            pdf.cell(col_widths[3], row_height, propiedad, border=1)
            pdf.ln()
        pdf.ln(10)  # Espacio adicional después de la tabla

    # Mostrar mensaje si no hay ninguna afección detectada
    if not mup_detectado and not vp_detectado and not any(valor != "No se encuentra" for _, valor in otras_afecciones):
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 8, "No se encuentra en ENP, ZEPA, LIC, VP, MUP", ln=True)
        pdf.ln(10)  # Espacio si no hay tabla

    seccion_titulo("3. Localización")
    for campo in ["municipio", "polígono", "parcela"]:
        valor = datos.get(campo, "").strip()
        campo_orden(campo.capitalize(), valor if valor else "No disponible")

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Coordenadas ETRS89: X = {x}, Y = {y}", ln=True)

    imagen_mapa_path = generar_imagen_estatica_mapa(x, y)

    if imagen_mapa_path and os.path.exists(imagen_mapa_path):
        epw = pdf.w - 2 * pdf.l_margin
        pdf.ln(5)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Mapa de localización:", ln=True)
        pdf.image(imagen_mapa_path, x=pdf.l_margin, w=epw)
    else:
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 8, "No se pudo generar el mapa de localización.", ln=True)

    pdf.output(filename)
    return filename
    
# Interfaz de Streamlit  
st.image("https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/logos.jpg", use_container_width=True)
st.title("Informe básico de Afecciones al Medio Natural")

modo = st.radio("Seleccione el modo de búsqueda. Recuerde que la busqueda por parcela analiza afecciones al total de la superficie de la parcela, por el contrario la busqueda por coodenadas analiza las afecciones del punto", ["Por coordenadas", "Por parcela"])

x = 0.0
y = 0.0
municipio_sel = ""
masa_sel = ""
parcela_sel = ""
parcela = None

if modo == "Por parcela":
    municipio_sel = st.selectbox("Municipio", sorted(shp_urls.keys()))
    archivo_base = shp_urls[municipio_sel]
    
    gdf = cargar_shapefile_desde_github(archivo_base)
    
    if gdf is not None:
        masa_sel = st.selectbox("Polígono", sorted(gdf["MASA"].unique()))
        parcela_sel = st.selectbox("Parcela", sorted(gdf[gdf["MASA"] == masa_sel]["PARCELA"].unique()))
        parcela = gdf[(gdf["MASA"] == masa_sel) & (gdf["PARCELA"] == parcela_sel)]
        
        if parcela.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all():
            centroide = parcela.geometry.centroid.iloc[0]
            x = centroide.x
            y = centroide.y         
                    
            st.success("Parcela cargada correctamente.")
            st.write(f"Municipio: {municipio_sel}")
            st.write(f"Polígono: {masa_sel}")
            st.write(f"Parcela: {parcela_sel}")
        else:
            st.error("La geometría seleccionada no es un polígono válido.")
    else:
        st.error(f"No se pudo cargar el shapefile para el municipio: {municipio_sel}")

with st.form("formulario"):
    if modo == "Por coordenadas":
        x = st.number_input("Coordenada X (ETRS89)", format="%.2f", help="Introduce coordenadas en metros, sistema ETRS89 / UTM zona 30")
        y = st.number_input("Coordenada Y (ETRS89)", format="%.2f")
        if x != 0.0 and y != 0.0:
            municipio_sel, masa_sel, parcela_sel, parcela = encontrar_municipio_poligono_parcela(x, y)
            if municipio_sel != "N/A":
                st.success(f"Parcela encontrada: Municipio: {municipio_sel}, Polígono: {masa_sel}, Parcela: {parcela_sel}")
            else:
                st.warning("No se encontró una parcela para las coordenadas proporcionadas.")
    else:
        st.info(f"Coordenadas obtenidas del centroide de la parcela: X = {x}, Y = {y}")
        
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
    if not nombre or not apellidos or not dni or x == 0 or y == 0:
        st.warning("Por favor, completa todos los campos obligatorios y asegúrate de que las coordenadas son correctas.")
    else:
        lon, lat = transformar_coordenadas(x, y)

        if modo == "Por parcela":
            query_geom = parcela.geometry.iloc[0]
        else:
            query_geom = Point(x, y)

        st.write(f"Municipio seleccionado: {municipio_sel}")
        st.write(f"Polígono seleccionado: {masa_sel}")
        st.write(f"Parcela seleccionada: {parcela_sel}")

        enp_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/ENP.json"
        zepa_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/ZEPA.json"
        lic_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/LIC.json"
        vp_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/VP.json"
        tm_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/TM.json"
        mup_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/MUP.json"

        afeccion_enp = consultar_geojson(query_geom, enp_url, "ENP", campo_nombre="nombre")
        afeccion_zepa = consultar_geojson(query_geom, zepa_url, "ZEPA", campo_nombre="SITE_NAME")
        afeccion_lic = consultar_geojson(query_geom, lic_url, "LIC", campo_nombre="SITE_NAME")
        afeccion_vp = consultar_geojson(query_geom, vp_url, "VP", campo_nombre="VP_NB")
        afeccion_tm = consultar_geojson(query_geom, tm_url, "TM", campo_nombre="NAMEUNIT")
        afeccion_mup = consultar_mup(query_geom, mup_url)

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
            "municipio": municipio_sel,
            "polígono": masa_sel,
            "parcela": parcela_sel
        }
        
        mapa_html, afecciones = crear_mapa(lon, lat, afecciones, parcela_gdf=parcela)

        st.session_state['mapa_html'] = mapa_html
        st.session_state['afecciones'] = afecciones

        st.subheader("Resultado de las afecciones")
        for afeccion in afecciones:
            st.write(f"• {afeccion}")

        with open(mapa_html, 'r') as f:
            html(f.read(), height=500)

        pdf_filename = f"informe_{uuid.uuid4().hex[:8]}.pdf"
        generar_pdf(datos, x, y, pdf_filename)
        st.session_state['pdf_file'] = pdf_filename

if st.session_state['mapa_html'] and st.session_state['pdf_file']:
    with open(st.session_state['pdf_file'], "rb") as f:
        st.download_button("📄 Descargar informe PDF", f, file_name="informe_afecciones.pdf")

    with open(st.session_state['mapa_html'], "r") as f:
        st.download_button("🌍 Descargar mapa HTML", f, file_name="mapa_busqueda.html")
