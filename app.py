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

def cargar_shapefile_desde_github(nombre_base):
    base_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/CATASTRO"
    extensiones = ["shp", "shx", "dbf", "prj"]
    temp_dir = tempfile.mkdtemp()
    archivos = {}

    for ext in extensiones:
        url = f"{base_url}/{nombre_base}.{ext}"
        local_path = os.path.join(temp_dir, f"{nombre_base}.{ext}")
        r = requests.get(url)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            archivos[ext] = local_path
        else:
            st.error(f"No se pudo descargar: {url}")
            os.rmdir(temp_dir)
            return None

    try:
        gdf = gpd.read_file(archivos["shp"])
        return gdf
    except Exception as e:
        st.error(f"Error al leer el shapefile: {e}")
        os.rmdir(temp_dir)
        return None

def mostrar_poligonos_y_parcelas(municipio):
    # Obtener el nombre base del archivo a partir del diccionario
    nombre_base = shp_urls.get(municipio)
    
    if nombre_base:
        gdf = cargar_shapefile_desde_github(nombre_base)
        if gdf is not None:
            # Asegúrate de que las columnas que contienen los polígonos y parcelas sean correctas
            # Suponiendo que las columnas sean 'MASA' para los polígonos y 'PARCELA' para las parcelas
            poligonos = gdf['MASA'].unique()
            parcelas = gdf['PARCELA'].unique()

            # Mostrar los polígonos y parcelas en selectores
            poligono_seleccionado = st.selectbox('Selecciona un polígono', poligonos)
            parcela_seleccionada = st.selectbox('Selecciona una parcela', parcelas)

            st.write(f"Polígono seleccionado: {poligono_seleccionado}")
            st.write(f"Parcela seleccionada: {parcela_seleccionada}")
        else:
            st.error(f"No se pudo cargar el shapefile para {municipio}")
    else:
        st.error(f"Municipio {municipio} no encontrado en el diccionario.")

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

# Función para generar el PDF con los datos de la solicitud
def generar_pdf(datos, x, y, filename):
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", "B", size=14)
    pdf.cell(200, 10, "Informe de Afecciones Ambientales", ln=True, align="C")

    pdf.set_font("Arial", size=12)
    pdf.ln(10)

    for k, v in datos.items():
        if k.lower() == "afección mup" and v.startswith("Dentro de MUP"): 
            v_lines = v.split("\n")
            for line in v_lines:
                pdf.cell(200, 10, line, ln=True)
        else:
            pdf.multi_cell(0, 10, f"{k.capitalize()}: {v}")

    pdf.ln(5)
    pdf.cell(200, 10, f"Coordenadas ETRS89: X = {x}, Y = {y}", ln=True)
    pdf.output(filename)
    return filename

# Interfaz de Streamlit
st.title("\U0001F5FA️ Informe de Afecciones Ambientales")

# Selección de modo
modo = st.radio("Selecciona el modo de búsqueda", ["Por coordenadas", "Por parcela"])

# Si el usuario selecciona "Por parcela" (municipio, polígono y parcela)
if modo == "Por parcela":
    st.header("Búsqueda por Municipio, Polígono y Parcela")

    # Selección del municipio
    municipio_sel = st.selectbox("Selecciona un municipio", ["Municipio A", "Municipio B", "Municipio C"])

    if municipio_sel:  # Verificar que el municipio ha sido seleccionado
        # Cargar el shapefile correspondiente al municipio
        gdf = cargar_shapefile_desde_github(f"https://github.com/{municipio_sel}.shp")

        if gdf is not None:
            # Selección del polígono (MASA)
            masa_sel = st.selectbox("Selecciona un polígono", sorted(gdf["MASA"].unique()))
            if masa_sel:  # Verificar que se haya seleccionado un polígono
                # Selección de la parcela
                parcela_sel = st.selectbox("Selecciona una parcela", sorted(gdf[gdf["MASA"] == masa_sel]["PARCELA"].unique()))

                if parcela_sel:  # Verificar que se haya seleccionado una parcela
                    # Obtener la parcela seleccionada
                    parcela = gdf[(gdf["MASA"] == masa_sel) & (gdf["PARCELA"] == parcela_sel)]
                    
                    # Verificar que la geometría sea válida
                    if parcela.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all():
                        # Calcular el centroide de la parcela
                        puntos = parcela.copy()
                        puntos["geometry"] = puntos.geometry.centroid
                        puntos["longitude"] = puntos.geometry.x
                        puntos["latitude"] = puntos.geometry.y
                        parcela = puntos  # Sobrescribir con los centroides

                        # Mostrar resultados
                        punto_centro = parcela.geometry.centroid.iloc[0]
                        x = punto_centro.x
                        y = punto_centro.y

                        st.success("Parcela cargada correctamente.")
                        st.write(f"Municipio: {municipio_sel}")
                        st.write(f"Polígono: {masa_sel}")
                        st.write(f"Parcela: {parcela_sel}")
                        st.write(f"Coordenadas del centroide: X = {x}, Y = {y}")
                    else:
                        st.error("La geometría seleccionada no es un polígono válido.")
                else:
                    st.warning("Por favor, selecciona una parcela.")
            else:
                st.warning("Por favor, selecciona un polígono.")
        else:
            st.error("No se pudo cargar el shapefile para el municipio seleccionado.")
    else:
        st.warning("Por favor, selecciona un municipio.")

# Si el usuario selecciona "Por coordenadas"
elif modo == "Por coordenadas":
    st.header("Búsqueda por Coordenadas")

    # Entrada de coordenadas
    x = st.number_input("Coordenada X (ETRS89)", format="%.2f")
    y = st.number_input("Coordenada Y (ETRS89)", format="%.2f")

    if x != 0 and y != 0:
        st.success("Coordenadas ingresadas correctamente.")
        st.write(f"Coordenadas introducidas: X = {x}, Y = {y}")
    else:
        st.warning("Por favor, ingresa coordenadas válidas para X y Y (no pueden ser 0).")
    
with st.form("formulario"):
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

        # Mostrar los datos seleccionados (municipio, polígono, parcela)
        st.write(f"Municipio seleccionado: {municipio_sel}")
        st.write(f"Polígono seleccionado: {masa_sel}")
        st.write(f"Parcela seleccionada: {parcela_sel}")

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
            "municipio": municipio_sel,  
            "polígono": masa_sel,       
            "parcela": parcela_sel    
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
