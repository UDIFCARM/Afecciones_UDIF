import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit.components.v1 import html
from streamlit_folium import folium_static
import geopandas as gpd
import pandas as pd
import requests
import tempfile
import os
from io import BytesIO
from datetime import datetime
from docxtpl import DocxTemplate
from docx2pdf import convert
from pyproj import Transformer
from fpdf import FPDF
import xml.etree.ElementTree as ET
from shapely.geometry import Point
import uuid
from branca.element import Template, MacroElement

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
        return gpd.read_file(local_paths[".shp"])
            
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
            return (f"Dentro de MUP:\nID: {props.get('ID_MONTE', 'Desconocido')}"
                    f"\nNombre: {props.get('NOMBREMONT', 'Desconocido')}"
                    f"\nMunicipio: {props.get('MUNICIPIO', 'Desconocido')}"
                    f"\nPropiedad: {props.get('PROPIEDAD', 'Desconocido')}")
        else:
            return "No se encuentra en ningún MUP"
    except Exception as e:
        st.error(f"Error al consultar MUP: {e}")
        return "Error al consultar MUP"

# Función para crear el mapa con afecciones específicas
def crear_mapa(x, y, afecciones=[]):
    m = folium.Map(location=[y, x], zoom_start=16)
    folium.Marker([y, x], popup=f"Coordenadas: {x}, {y}").add_to(m)

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
        name="Montes de Utilidad Pública",
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
    <div style='position: fixed; bottom: 20px; left: 20px; background-color: white; border: 1px solid grey; 
    z-index: 9999; font-size: 10px; padding: 5px; box-shadow: 2px 2px 6px rgba(0,0,0,0.2); 
    transform: scale(0.75); transform-origin: top left;'>
        <b>Leyenda</b><br>
        <img src="https://wms.mapama.gob.es/sig/Biodiversidad/RedNatura/wms.aspx?REQUEST=GetLegendGraphic&VERSION=1.1.1&FORMAT=image/png&LAYER=Red Natura 2000"><br>
        <img src="https://wms.mapama.gob.es/sig/Biodiversidad/PropiedadMontes_UP/wms.aspx?REQUEST=GetLegendGraphic&VERSION=1.1.1&FORMAT=image/png&LAYER=Catálogo de Montes de Utilidad Pública"><br>
    </div>
    {% endmacro %}
    """
    legend = MacroElement()
    legend._template = Template(legend_html)
    m.get_root().add_child(legend)

    for afeccion in afecciones:
        folium.Marker([y, x], popup=afeccion).add_to(m)

    return m

# Interfaz de Streamlit
st.set_page_config(page_title="Informe de Afecciones Ambientales", layout="centered")
st.title("\U0001F5FA️ Informe de Afecciones Ambientales")

modo = st.radio("Selecciona el modo de búsqueda", ["Por coordenadas", "Por parcela"])

if modo == "Por parcela":
    municipio_sel = st.text_input("Municipio:")
    masa_sel = st.text_input("Polígono:")
    parcela_sel = st.text_input("Parcela:")

x_coord = st.text_input("Coordenada X (ETRS89 UTM Zona 30N):")
y_coord = st.text_input("Coordenada Y (ETRS89 UTM Zona 30N):")

if st.button("Generar informe"):
    with st.spinner("Procesando..."):
        try:
            x = float(x_coord)
            y = float(y_coord)
        except ValueError:
            st.error("Coordenadas inválidas. Introduce valores numéricos.")
            st.stop()

        lon, lat = transformar_coordenadas(x, y)

        municipio = municipio_sel if modo == "Por parcela" else ""
        poligono = masa_sel if modo == "Por parcela" else ""
        parcela = parcela_sel if modo == "Por parcela" else ""
        coordenadas = (x, y)

        enp_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/ENP.json"
        zepa_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/ZEPA.json"
        lic_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/LIC.json"
        vp_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/VP.json"
        tm_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/TM.json"
        mup_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/GeoJSON/MUP.json"

        afecciones = {
            "ENP": [consultar_geojson(lon, lat, enp_url, "ENP")],
            "ZEPA": [consultar_geojson(lon, lat, zepa_url, "ZEPA")],
            "LIC": [consultar_geojson(lon, lat, lic_url, "LIC")],
            "VP": [consultar_geojson(lon, lat, vp_url, "Vías pecuarias")],
            "TM": [consultar_geojson(lon, lat, tm_url, "Término Municipal")],
        }

        datos_mup = {}
        mup_resultado = consultar_mup(lon, lat, mup_url)
        if "Dentro de MUP" in mup_resultado:
            partes = mup_resultado.split('\n')
            datos_mup = {
                "CUP": partes[1].split(":")[1].strip(),
                "NOMBRE": partes[2].split(":")[1].strip(),
                "MUNICIPIO": partes[3].split(":")[1].strip(),
                "PROPIEDAD": partes[4].split(":")[1].strip(),
            }

        afecciones_lista = afecciones["ENP"] + afecciones["ZEPA"] + afecciones["LIC"] + afecciones["VP"] + afecciones["TM"]
        if "Dentro de MUP" in mup_resultado:
            afecciones_lista.append(mup_resultado)

        mapa = crear_mapa(lon, lat, afecciones_lista)
        folium_static(mapa)  # Visualiza el mapa

        with open(mapa_html, "r", encoding="utf-8") as f:
            html_content = f.read()
            st.components.v1.html(html_content, height=600, scrolling=True)

        contexto = {
            "fecha": datetime.now().strftime("%d/%m/%Y"),
            "modo": modo,
            "municipio": municipio,
            "poligono": poligono,
            "parcela": parcela,
            "coordenadas_x": coordenadas[0],
            "coordenadas_y": coordenadas[1],
            "mup_id": datos_mup.get("CUP", ""),
            "mup_nombre": datos_mup.get("NOMBRE", ""),
            "mup_municipio": datos_mup.get("MUNICIPIO", ""),
            "mup_propiedad": datos_mup.get("PROPIEDAD", ""),
            "enp": afecciones["ENP"][0],
            "zepa": afecciones["ZEPA"][0],
            "lic": afecciones["LIC"][0],
            "vp": afecciones["VP"][0],
            "tm": afecciones["TM"][0],
        }

        doc = DocxTemplate("plantilla_informe.docx")
        doc.render(contexto)
        docx_output = BytesIO()
        doc.save(docx_output)
        docx_output.seek(0)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
            tmp_docx.write(docx_output.read())
            tmp_docx_path = tmp_docx.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf_path = tmp_pdf.name

        convert(tmp_docx_path, tmp_pdf_path)

        with open(tmp_pdf_path, "rb") as f:
            st.download_button(
                label="📄 Descargar informe en PDF",
                data=f.read(),
                file_name="informe_afecciones.pdf",
                mime="application/pdf"
            )
# Botones de descarga
if "mapa_html" in st.session_state:
    with open(st.session_state["mapa_html"], "r") as f:
        st.download_button("🌍 Descargar mapa HTML", f, file_name="mapa_busqueda.html")
