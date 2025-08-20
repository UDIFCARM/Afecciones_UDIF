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
from PIL import Image, ImageDraw
import math
import logging

# Configurar logging para diagnósticos
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Función para crear el mapa con afecciones específicas (para visualización en Streamlit)
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
        url="https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
        layers="Catastro",
        fmt='image/png',
        transparent=True,
        name="Catastro",
        control=True
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

# Función para generar la imagen estática del mapa usando Pillow
def generar_imagen_estatica_mapa(x, y, parcela_gdf=None, zoom=16, size=(800, 600)):
    logger.info("Generando imagen estática con solicitudes WMS y Pillow")
    lon, lat = transformar_coordenadas(x, y)
    
    # Calcular BBOX basado en el zoom y las coordenadas
    meters_per_pixel = 156543.03392 * math.cos(lat * math.pi / 180) / (2 ** zoom)
    delta_lon = (size[0] / 2) * meters_per_pixel / 111319.9
    delta_lat = (size[1] / 2) * meters_per_pixel / 111319.9
    bbox = f"{lon - delta_lon},{lat - delta_lat},{lon + delta_lon},{lat + delta_lat}"
    
    # URLs de las capas WMS
    wms_urls = [
        f"https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx?service=WMS&version=1.3.0&request=GetMap&layers=Catastro&format=image/png&width={size[0]}&height={size[1]}&crs=EPSG:4326&bbox={bbox}",
        f"https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=SIG_LUP_SITES_CARM:RN2000&format=image/png&width={size[0]}&height={size[1]}&crs=EPSG:4326&bbox={bbox}&transparent=true",
        f"https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=PFO_ZOR_DMVP_CARM:MONTES&format=image/png&width={size[0]}&height={size[1]}&crs=EPSG:4326&bbox={bbox}&transparent=true",
        f"https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=PFO_ZOR_DMVP_CARM:VP_CARM&format=image/png&width={size[0]}&height={size[1]}&crs=EPSG:4326&bbox={bbox}&transparent=true",
    ]
    
    # Descargar y combinar imágenes
    images = []
    for url in wms_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content)).convert("RGBA")
                images.append(img)
            else:
                logger.warning(f"Fallo al descargar capa WMS: {url} (status: {response.status_code})")
        except Exception as e:
            logger.warning(f"Error al descargar capa WMS {url}: {e}")
    
    if not images:
        st.error("No se pudieron descargar las capas WMS. Usando mapa estático de retroceso.")
        m = StaticMap(size[0], size[1], url_template='http://a.tile.openstreetmap.org/{z}/{x}/{y}.png')
        marker = CircleMarker((lon, lat), 'red', 12)
        m.add_marker(marker)
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "mapa_fallback.png")
        image = m.render(zoom=zoom)
        image.save(output_path)
        return output_path
    
    # Combinar imágenes
    base_img = Image.new("RGBA", size, (255, 255, 255, 255))  # Fondo blanco
    for img in images:
        base_img.paste(img, (0, 0), img)
    
    # Dibujar la parcela si está disponible
    if parcela_gdf is not None:
        try:
            parcela_4326 = parcela_gdf.to_crs("EPSG:4326")
            bounds = parcela_4326.bounds.iloc[0]
            minx, miny, maxx, maxy = bounds['minx'], bounds['miny'], bounds['maxx'], bounds['maxy']
            
            # Convertir coordenadas de la parcela a píxeles
            def lonlat_to_pixel(lon, lat, bbox, size):
                x = int((lon - bbox[0]) / (bbox[2] - bbox[0]) * size[0])
                y = int((bbox[3] - lat) / (bbox[3] - bbox[1]) * size[1])
                return x, y
            
            draw = ImageDraw.Draw(base_img)
            geom = parcela_4326.geometry.iloc[0]
            if geom.geom_type == 'Polygon':
                coords = list(geom.exterior.coords)
                pixel_coords = [lonlat_to_pixel(lon, lat, (lon - delta_lon, lat - delta_lat, lon + delta_lon, lat + delta_lat), size) for lon, lat in coords]
                draw.polygon(pixel_coords, outline=(0, 0, 255, 255), width=2)
            elif geom.geom_type == 'MultiPolygon':
                for poly in geom.geoms:
                    coords = list(poly.exterior.coords)
                    pixel_coords = [lonlat_to_pixel(lon, lat, (lon - delta_lon, lat - delta_lat, lon + delta_lon, lat + delta_lat), size) for lon, lat in coords]
                    draw.polygon(pixel_coords, outline=(0, 0, 255, 255), width=2)
        except Exception as e:
            logger.warning(f"Error al dibujar la parcela: {e}")
    
    # Añadir marcador en el centro
    draw = ImageDraw.Draw(base_img)
    marker_size = 12
    center_x, center_y = size[0] // 2, size[1] // 2
    draw.ellipse(
        [center_x - marker_size, center_y - marker_size, center_x + marker_size, center_y + marker_size],
        fill=(255, 0, 0, 255)
    )
    
    # Añadir leyenda
    legend_urls = [
        "https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image%2Fpng&width=20&height=20&layer=SIG_LUP_SITES_CARM%3ARN2000",
        "https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image%2Fpng&width=20&height=20&layer=PFO_ZOR_DMVP_CARM%3AMONTES",
        "https://mapas-gis-inter.carm.es/geoserver/ows?service=WMS&version=1.3.0&request=GetLegendGraphic&format=image%2Fpng&width=20&height=20&layer=PFO_ZOR_DMVP_CARM%3AVP_CARM",
    ]
    legend_images = []
    for url in legend_urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content)).convert("RGBA")
                legend_images.append(img)
        except Exception as e:
            logger.warning(f"Error al descargar leyenda WMS {url}: {e}")
    
    if legend_images:
        max_legend_width = max(img.width for img in legend_images)
        total_legend_height = sum(img.height for img in legend_images) + 30  # Espacio para título
        legend_img = Image.new("RGBA", (max_legend_width + 20, total_legend_height + 20), (255, 255, 255, 255))
        draw = ImageDraw.Draw(legend_img)
        draw.text((10, 10), "Leyenda", fill=(0, 0, 0, 255), font_size=12)
        
        y_offset = 30
        for img in legend_images:
            legend_img.paste(img, (10, y_offset), img)
            y_offset += img.height
        
        # Redimensionar leyenda si es necesario
        legend_img = legend_img.resize((int(max_legend_width * 0.75), int(total_legend_height * 0.75)))
        
        # Pegar leyenda en la esquina inferior izquierda
        base_img.paste(legend_img, (10, size[1] - legend_img.height - 10), legend_img)
    
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "mapa.png")
    base_img.save(output_path, "PNG")
    logger.info(f"Imagen WMS guardada en: {output_path}")
    return output_path

# Función para generar el PDF con los datos de la solicitud
def generar_pdf(datos, x, y, filename, parcela=None):
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

    objeto = datos.get("objeto de la solicitud", "").strip()
    pdf.ln(2)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Objeto de la solicitud:", ln=True)
    pdf.set_font("Arial", "", 12)
    pdf.multi_cell(0, 8, objeto if objeto else "No especificado")

    seccion_titulo("2. Afecciones detectadas")
    afecciones_keys = [k for k in datos if k.lower().startswith("afección")]

    if afecciones_keys:
        for key in afecciones_keys:
            valor = datos[key].strip()
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, f"{key.capitalize()}:", ln=True)
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 8, valor)
    else:
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 8, "No se han detectado afecciones.", ln=True)

    for key in ["afección vp", "afección enp", "afección zepa", "afección lic", "afección tm"]:
        valor = datos.get(key, "").strip()
        if valor:
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 8, f"{key.capitalize()}:", ln=True)
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 8, valor)

    seccion_titulo("3. Localización")
    for campo in ["municipio", "polígono", "parcela"]:
        valor = datos.get(campo, "").strip()
        campo_orden(campo.capitalize(), valor if valor else "No disponible")

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Coordenadas ETRS89: X = {x}, Y = {y}", ln=True)

    # Generar el mapa con capas WMS
    parcela_gdf = datos.get("parcela_gdf", parcela)
    imagen_mapa_path = generar_imagen_estatica_mapa(x, y, parcela_gdf=parcela_gdf)

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
            "parcela": parcela_sel,
            "afecciones": afecciones,
            "parcela_gdf": parcela
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
        generar_pdf(datos, x, y, pdf_filename, parcela=parcela)
        st.session_state['pdf_file'] = pdf_filename

if st.session_state['mapa_html'] and st.session_state['pdf_file']:
    with open(st.session_state['pdf_file'], "rb") as f:
        st.download_button("📄 Descargar informe PDF", f, file_name="informe_afecciones.pdf")

    with open(st.session_state['mapa_html'], "r") as f:
        st.download_button("🌍 Descargar mapa HTML", f, file_name="mapa_busqueda.html")
