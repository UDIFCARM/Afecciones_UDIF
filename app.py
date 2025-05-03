import streamlit as st
import folium
from streamlit.components.v1 import html
from fpdf import FPDF
from pyproj import Transformer
import requests
import xml.etree.ElementTree as ET
import geopandas as gpd
from shapely.geometry import Point
import uuid
from datetime import datetime
from docx import Document
from branca.element import Template, MacroElement

# --- URL DEL CATASTRO ---
gdf_parcelas = gpd.read_file("CATASTRO.zip", engine="fiona")
zip_parcelas_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/CATASTRO.zip"
gdf_parcelas = gpd.read_file(zip_parcelas_url)

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

modo = st.radio("Selecciona el modo de búsqueda", ["Por coordenadas", "Por parcela"])

gdf_parcelas = gpd.read_file(geojson_parcelas_url)

if modo == "Por parcela":
    municipio_sel = st.selectbox("Municipio", sorted(gdf_parcelas["TM"].unique()))
    gdf_filtrado = gdf_parcelas[gdf_parcelas["TM"] == municipio_sel]
    masa_sel = st.selectbox("Polígono", sorted(gdf_filtrado["MASA"].unique()))
    gdf_filtrado = gdf_filtrado[gdf_filtrado["MASA"] == masa_sel]
    parcela_sel = st.selectbox("Parcela", sorted(gdf_filtrado["PARCELA"].unique()))
    parcela = gdf_filtrado[gdf_filtrado["PARCELA"] == parcela_sel].iloc[0]
    punto_centro = parcela.geometry.centroid
    x = punto_centro.x
    y = punto_centro.y
else:
    x = st.number_input("Coordenada X (ETRS89)", format="%.2f")
    y = st.number_input("Coordenada Y (ETRS89)", format="%.2f")

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

        # URLs GeoJSON
        enp_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/ENP.json"
        zepa_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/ZEPA.json"
        lic_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/LIC.json"
        vp_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/VP.json"
        tm_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/TM.json"
        mup_url = "https://raw.githubusercontent.com/UDIFCARM/Informe-basico/main/MUP.json"

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
