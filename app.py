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
import textwrap
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import shutil
from PIL import Image

session = requests.Session()
retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504, 429])
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

shp_urls = {
    "ABANILLA": "ABANILLA",
    "ABARAN": "ABARAN",
    "AGUILAS": "AGUILAS",
    "ALBUDEITE": "ALBUDEITE",
    "ALCANTARILLA": "ALCANTARILLA",
    "ALEDO": "ALEDO",
    "ALGUAZAS": "ALGUAZAS",
    "ALHAMA DE MURCIA": "ALHAMA_DE_MURCIA",
    "ARCHENA": "ARCHENA",
    "BENIEL": "BENIEL",
    "BLANCA": "BLANCA",
    "BULLAS": "BULLAS",
    "CALASPARRA": "CALASPARRA",
    "CAMPOS DEL RIO": "CAMPOS_DEL_RIO",
    "CARAVACA DE LA CRUZ": "CARAVACA_DE_LA_CRUZ",
    "CARTAGENA": "CARTAGENA",
    "CEHEGIN": "CEHEGIN",
    "CEUTI": "CEUTI",
    "CIEZA": "CIEZA",
    "FORTUNA": "FORTUNA",
    "FUENTE ALAMO DE MURCIA": "FUENTE_ALAMO_DE_MURCIA",
    "JUMILLA": "JUMILLA",
    "LAS TORRES DE COTILLAS": "LAS_TORRES_DE_COTILLAS",
    "LA UNION": "LA_UNION",
    "LIBRILLA": "LIBRILLA",
    "LORCA": "LORCA",
    "LORQUI": "LORQUI",
    "LOS ALCAZARES": "LOS_ALCAZARES",
    "MAZARRON": "MAZARRON",
    "MOLINA DE SEGURA": "MOLINA_DE_SEGURA",
    "MORATALLA": "MORATALLA",
    "MULA": "MULA",
    "MURCIA": "MURCIA",
    "OJOS": "OJOS",
    "PLIEGO": "PLIEGO",
    "PUERTO LUMBRERAS": "PUERTO_LUMBRERAS",
    "RICOTE": "RICOTE",
    "SANTOMERA": "SANTOMERA",
    "SAN JAVIER": "SAN_JAVIER",
    "SAN PEDRO DEL PINATAR": "SAN_PEDRO_DEL_PINATAR",
    "TORRE PACHECO": "TORRE_PACHECO",
    "TOTANA": "TOTANA",
    "ULEA": "ULEA",
    "VILLANUEVA DEL RIO SEGURA": "VILLANUEVA_DEL_RIO_SEGURA",
    "YECLA": "YECLA",
}

@st.cache_data
def cargar_shapefile_desde_github(base_name):
    base_url = "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/CATASTRO/"
    exts = [".shp", ".shx", ".dbf", ".prj", ".cpg"]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        local_paths = {}
        for ext in exts:
            filename = base_name + ext
            url = base_url + filename
            try:
                response = requests.get(url, timeout=100)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                st.error(f"Error al descargar {url}: {str(e)}")
                return None
            
            local_path = os.path.join(tmpdir, filename)
            with open(local_path, "wb") as f:
                f.write(response.content)
            local_paths[ext] = local_path
        
        shp_path = local_paths[".shp"]
        try:
            gdf = gpd.read_file(shp_path)
            return gdf
        except Exception as e:
            st.error(f"Error al leer shapefile {shp_path}: {str(e)}")
            return None
def encontrar_municipio_poligono_parcela(x, y):
    try:
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
    except Exception as e:
        st.error(f"Error al buscar parcela: {str(e)}")
        return "N/A", "N/A", "N/A", None

def transformar_coordenadas(x, y):
    try:
        x, y = float(x), float(y)
        if not (500000 <= x <= 800000 and 4000000 <= y <= 4800000):
            st.error("Coordenadas fuera del rango esperado para ETRS89 UTM Zona 30")
            return None, None
        transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(x, y)
        return lon, lat
    except ValueError:
        st.error("Coordenadas inválidas. Asegúrate de ingresar valores numéricos.")
        return None, None

@st.cache_data(show_spinner=False, ttl=604800) 
def _descargar_geojson(url):
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return BytesIO(response.content)
    except Exception as e:
        if not hasattr(st, "_wfs_warnings"):
            st._wfs_warnings = set()
        warning_key = url.split('/')[-1]
        if warning_key not in st._wfs_warnings:
            st.warning(f"Servicio no disponible: {warning_key}")
            st._wfs_warnings.add(warning_key)
        return None

def consultar_wfs_seguro(geom, url, nombre_afeccion, campo_nombre=None, campos_mup=None):
    """
    Consulta WFS con:
    - Descarga cacheada (rápida después de la 1ª vez)
    - Geometría NO cacheada (evita UnhashableParamError)
    """
    data = _descargar_geojson(url)
    if data is None:
        return f"Indeterminado: {nombre_afeccion} (servicio no disponible)"

    try:
        gdf = gpd.read_file(data)
        seleccion = gdf[gdf.intersects(geom)]
        
        if seleccion.empty:
            return f"No afecta a {nombre_afeccion}"

        if campos_mup:
            info = []
            for _, row in seleccion.iterrows():
                valores = [str(row.get(c.split(':')[0], "Desconocido")) for c in campos_mup]
                etiquetas = [c.split(':')[1] if ':' in c else c.split(':')[0] for c in campos_mup]
                info.append("\n".join(f"{etiquetas[i]}: {valores[i]}" for i in range(len(campos_mup))))
            return f"Dentro de {nombre_afeccion}:\n" + "\n\n".join(info)

        else:
            nombres = ', '.join(seleccion[campo_nombre].dropna().unique())
            return f"Dentro de {nombre_afeccion}: {nombres}"

    except Exception as e:
        return f"Indeterminado: {nombre_afeccion} (error de datos)"

def crear_mapa(lon, lat, afecciones=[], parcela_gdf=None):
    if lon is None or lat is None:
        st.error("Coordenadas inválidas para generar el mapa.")
        return None, afecciones
    
    m = folium.Map(location=[lat, lon], zoom_start=16)
    folium.Marker([lat, lon], popup=f"Coordenadas transformadas: {lon}, {lat}").add_to(m)

    if parcela_gdf is not None and not parcela_gdf.empty:
        try:
            parcela_4326 = parcela_gdf.to_crs("EPSG:4326")
            folium.GeoJson(
                parcela_4326.to_json(),
                name="Parcela",
                style_function=lambda x: {'fillColor': 'transparent', 'color': 'blue', 'weight': 2, 'dashArray': '5, 5'}
            ).add_to(m)
        except Exception as e:
            st.error(f"Error al añadir la parcela al mapa: {str(e)}")

    wms_layers = [
        ("Red Natura 2000", "SIG_LUP_SITES_CARM:RN2000"),
        ("Montes", "PFO_ZOR_DMVP_CARM:MONTES"),
        ("Vias Pecuarias", "PFO_ZOR_DMVP_CARM:VP_CARM")
    ]
    for name, layer in wms_layers:
        try:
            folium.raster_layers.WmsTileLayer(
                url="https://mapas-gis-inter.carm.es/geoserver/ows?SERVICE=WMS&?",
                name=name,
                fmt="image/png",
                layers=layer,
                transparent=True,
                opacity=0.25,
                control=True
            ).add_to(m)
        except Exception as e:
            st.error(f"Error al cargar la capa WMS {name}: {str(e)}")

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

def generar_imagen_estatica_mapa(x, y, zoom=16, size=(800, 600)):
    lon, lat = transformar_coordenadas(x, y)
    if lon is None or lat is None:
        return None
    
    try:
        m = StaticMap(size[0], size[1], url_template='http://a.tile.openstreetmap.org/{z}/{x}/{y}.png')
        marker = CircleMarker((lon, lat), 'red', 12)
        m.add_marker(marker)
        
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "mapa.png")
        image = m.render(zoom=zoom)
        image.save(output_path)
        return output_path
    except Exception as e:
        st.error(f"Error al generar la imagen estática del mapa: {str(e)}")
        return None

class CustomPDF(FPDF):
    def __init__(self, logo_path):
        super().__init__()
        self.logo_path = logo_path

    def header(self):
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                available_width = self.w - self.l_margin - self.r_margin 

                max_logo_height = 25 

                from PIL import Image
                img = Image.open(self.logo_path)
                ratio = img.width / img.height

               
                target_width = available_width
                target_height = target_width / ratio

                if target_height > max_logo_height:
                    target_height = max_logo_height
                    target_width = target_height * ratio

                x = self.l_margin + (available_width - target_width) / 2
                y = 5

                self.image(self.logo_path, x=x, y=y, w=target_width, h=target_height)
                self.set_y(y + target_height + 3)

            except Exception as e:
                st.warning(f"Error al cargar logo: {e}")
                self.set_y(30)
        else:
            self.set_y(30)

    def footer(self):
        if self.page_no() > 0:
            self.set_y(-15)
            self.set_draw_color(0, 0, 255)
            self.set_line_width(0.5)
            page_width = self.w - 2 * self.l_margin
            self.line(self.l_margin, self.get_y(), self.l_margin + page_width, self.get_y())
            
            self.set_y(-15)
            self.set_font("Arial", "", 9)
            self.set_text_color(0, 0, 0)
            self.cell(0, 10, f"Página {self.page_no()}", align="R")

def hay_espacio_suficiente(pdf, altura_necesaria, margen_inferior=20):
    """
    Verifica si hay suficiente espacio en la página actual.
    margen_inferior: espacio mínimo que debe quedar debajo
    """
    espacio_disponible = pdf.h - pdf.get_y() - margen_inferior
    return espacio_disponible >= altura_necesaria

def generar_pdf(datos, x, y, filename):
    logo_path = "logos.jpg"

    if not os.path.exists(logo_path):
        st.error("FALTA EL ARCHIVO: 'logos.jpg' en la raíz del proyecto.")
        st.markdown(
            "Descárgalo aquí: [logos.jpg](https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/logos.jpg)"
        )
        logo_path = None
    else:
        st.success("Logo local cargado correctamente")

    query_geom = st.session_state.get('query_geom')
    if query_geom is None:
        query_geom = Point(x, y)

  
    urls = st.session_state.get('wfs_urls', {})
    vp_url = urls.get('vp')
    zepa_url = urls.get('zepa')
    lic_url = urls.get('lic')
    enp_url = urls.get('enp')
    uso_suelo_url = urls.get('uso_suelo')

    pdf = CustomPDF(logo_path)
    pdf.set_margins(left=15, top=15, right=15)
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 12, "Informe preliminar de Afecciones Forestales", ln=True, align="C")
    pdf.ln(10)

    azul_rgb = (141, 179, 226)

    campos_orden = [
        ("Fecha informe", datos.get("fecha_informe", "").strip()),
        ("Nombre", datos.get("nombre", "").strip()),
        ("Apellidos", datos.get("apellidos", "").strip()),
        ("DNI", datos.get("dni", "").strip()),
        ("Dirección", datos.get("dirección", "").strip()),
        ("Teléfono", datos.get("teléfono", "").strip()),
        ("Email", datos.get("email", "").strip()),
    ]

    def seccion_titulo(texto):
        pdf.set_fill_color(*azul_rgb)
        ancho_deseado = 190
        x = (pdf.w - ancho_deseado) / 2
        pdf.cell(ancho_deseado, 10, "", ln=False, fill=True)
        pdf.set_x(x)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, texto, ln=True, fill=True)
        pdf.ln(2)

    def campo_orden(pdf, titulo, valor):
        pdf.set_font("Arial", "B", 12)
        pdf.cell(50, 7, f"{titulo}:", ln=0)
        pdf.set_font("Arial", "", 12)
        
        valor = valor.strip() if valor else "No especificado"
        wrapped_text = textwrap.wrap(valor, width=60)
        if not wrapped_text:
            wrapped_text = ["No especificado"]
        
        for line in wrapped_text:
            pdf.cell(0, 7, line, ln=1)

    seccion_titulo("1. Datos del solicitante")
    for titulo, valor in campos_orden:
        campo_orden(pdf, titulo, valor)

    objeto = datos.get("objeto de la solicitud", "").strip()
    pdf.ln(2)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 7, "Objeto de la solicitud:", ln=True)
    pdf.set_font("Arial", "", 11)
    wrapped_objeto = textwrap.wrap(objeto if objeto else "No especificado", width=60)
    for line in wrapped_objeto:
        pdf.cell(0, 7, line, ln=1)
        
    seccion_titulo("2. Localización")
    for campo in ["municipio", "polígono", "parcela"]:
        valor = datos.get(campo, "").strip()
        campo_orden(pdf, campo.capitalize(), valor if valor else "No disponible")

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 10, f"Coordenadas ETRS89: X = {x}, Y = {y}", ln=True)

    imagen_mapa_path = generar_imagen_estatica_mapa(x, y)
    if imagen_mapa_path and os.path.exists(imagen_mapa_path):
        epw = pdf.w - 2 * pdf.l_margin
        pdf.ln(5)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 7, "Mapa de localización:", ln=True, align="C")
        image_width = epw * 0.5
        x_centered = pdf.l_margin + (epw - image_width) / 2 
        pdf.image(imagen_mapa_path, x=x_centered, w=image_width)
    else:
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 7, "No se pudo generar el mapa de localización.", ln=True)

    pdf.add_page()
    pdf.ln(10)
    seccion_titulo("3. Afecciones detectadas")

    afecciones_keys = ["Afección TM"]
    vp_key = "afección VP"
    mup_key = "afección MUP"
    zepa_key = "afección ZEPA"
    lic_key = "afección LIC"
    enp_key = "afección ENP"
    uso_suelo_key = "Afección PLANEAMIENTO"        

    def procesar_capa(url, key, valor_inicial, campos, detectado_list):
        valor = datos.get(key, "").strip()
        if valor and not valor.startswith("No afecta") and not valor.startswith("Error"):
            try:
                data = _descargar_geojson(url)
                if data is None:
                    return "Error al consultar"
                gdf = gpd.read_file(data)
                seleccion = gdf[gdf.intersects(query_geom)]
                if not seleccion.empty:
                    for _, props in seleccion.iterrows():
                        fila = tuple(props.get(campo, "N/A") for campo in campos)
                        detectado_list.append(fila)
                    return ""
                return valor_inicial
            except Exception as e:
                st.error(f"Error al procesar {key}: {e}")
                return "Error al consultar"
        return valor_inicial if not detectado_list else ""

    vp_detectado = []
    vp_valor = procesar_capa(
        vp_url, "afección VP", "No afecta a ninguna Vía Pecuaria",
        ["vp_cod", "vp_nb", "vp_mun", "vp_sit_leg", "vp_anch_lg"],
        vp_detectado
    )

    zepa_detectado = []
    zepa_valor = procesar_capa(
        zepa_url, "afección ZEPA", "No afecta a ninguna Zona de especial protección para las aves",
        ["site_code", "site_name"],
        zepa_detectado
    )

    lic_detectado = []
    lic_valor = procesar_capa(
        lic_url, "afección LIC", "No afecta a ningún Lugar de Interés Comunitario",
        ["site_code", "site_name"],
        lic_detectado
    )

    enp_detectado = []
    enp_valor = procesar_capa(
        enp_url, "afección ENP", "No afecta a ningún Espacio Natural Protegido",
        ["nombre", "figura"],
        enp_detectado
    )

    uso_suelo_detectado = []
    uso_suelo_valor = procesar_capa(
        uso_suelo_url, "afección uso_suelo", "No afecta a ningún uso del suelo protegido",
        ["Uso_Especifico", "Clasificacion"],
        uso_suelo_detectado
    )

    mup_valor = datos.get("afección MUP", "").strip()
    mup_detectado = []
    if mup_valor and not mup_valor.startswith("No afecta") and not mup_valor.startswith("Error"):
        entries = mup_valor.replace("Dentro de MUP:\n", "").split("\n\n")
        for entry in entries:
            lines = entry.split("\n")
            if lines:
                mup_detectado.append((
                    lines[0].replace("ID: ", "").strip() if len(lines) > 0 else "N/A",
                    lines[1].replace("Nombre: ", "").strip() if len(lines) > 1 else "N/A",
                    lines[2].replace("Municipio: ", "").strip() if len(lines) > 2 else "N/A",
                    lines[3].replace("Propiedad: ", "").strip() if len(lines) > 3 else "N/A"
                ))
        mup_valor = ""

    otras_afecciones = []
    for key in afecciones_keys:
        valor = datos.get(key, "").strip()
        key_corregido = key 
    
        if valor and not valor.startswith("Error"):
            otras_afecciones.append((key_corregido, valor))
        else:
            otras_afecciones.append((key_corregido, valor if valor else "No afecta"))
    if not uso_suelo_detectado:
        otras_afecciones.append(("Afección Uso del Suelo", uso_suelo_valor if uso_suelo_valor else "No afecta a ningún uso del suelo protegido"))
    if not enp_detectado:
        otras_afecciones.append(("Afección ENP", enp_valor if enp_valor else "No se encuentra en ningún ENP"))
    if not lic_detectado:
        otras_afecciones.append(("Afección LIC", lic_valor if lic_valor else "No afecta a ningún LIC"))
    if not zepa_detectado:
        otras_afecciones.append(("Afección ZEPA", zepa_valor if zepa_valor else "No afecta a ninguna ZEPA"))
    if not vp_detectado:
        otras_afecciones.append(("Afección VP", vp_valor if vp_valor else "No afecta a ninguna VP"))
    if not mup_detectado:
        otras_afecciones.append(("Afección MUP", mup_valor if mup_valor else "No afecta a ningún MUP"))
 
    if otras_afecciones:
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 8, "Otras afecciones:", ln=True)
        pdf.ln(2)

        line_height = 6
        label_width = 55
        text_width = pdf.w - 2 * pdf.l_margin - label_width

        for titulo, valor in otras_afecciones:
            if valor:
                x = pdf.get_x()
                y = pdf.get_y()

          
                pdf.set_xy(x, y)
                pdf.set_font("Arial", "B", 11)
                pdf.cell(label_width, line_height, f"{titulo}:", border=0)

  
                pdf.set_xy(x + label_width, y)
                pdf.set_font("Arial", "", 11)
                pdf.multi_cell(text_width, line_height, valor, border=0)

                pdf.ln(line_height)  
        pdf.ln(2)

    if uso_suelo_detectado:
        altura_estimada = 5 + 5 + (len(uso_suelo_detectado) * 6) + 10
        if not hay_espacio_suficiente(pdf, altura_estimada):
            pdf.add_page()  
            
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, "Afección a Planeamiento Urbano (PGOU):", ln=True)
        pdf.ln(2)
        col_w_uso = 50
        col_w_clas = 190 - col_w_uso
        row_height = 5
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_w_uso, row_height, "Uso", border=1, fill=True)
        pdf.cell(col_w_clas, row_height, "Clasificación", border=1, fill=True)
        pdf.ln()
        pdf.set_font("Arial", "", 10)
        for Uso_Especifico, Clasificacion in uso_suelo_detectado:
            uso_lines = pdf.multi_cell(col_w_uso, 5, str(Uso_Especifico), split_only=True)
            clas_lines = pdf.multi_cell(col_w_clas, 5, str(Clasificacion), split_only=True)
            row_h = max(row_height, len(uso_lines) * 5, len(clas_lines) * 5)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_w_uso, row_h)
            pdf.rect(x + col_w_uso, y, col_w_clas, row_h)
            uso_h = len(uso_lines) * 5
            y_uso = y + (row_h - uso_h) / 2
            pdf.set_xy(x, y_uso)
            pdf.multi_cell(col_w_uso, 5, str(Uso_Especifico), align="L")
            clas_h = len(clas_lines) * 5
            y_clas = y + (row_h - clas_h) / 2
            pdf.set_xy(x + col_w_uso, y_clas)
            pdf.multi_cell(col_w_clas, 5, str(Clasificacion), align="L")
            pdf.set_y(y + row_h)
        pdf.ln(5)

    if vp_detectado:
        altura_estimada = 5 + 5 + (len(vp_detectado) * 6) + 10
        if not hay_espacio_suficiente(pdf, altura_estimada):
            pdf.add_page()  
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, "Afecciones a Vías Pecuarias (VP):", ln=True)
        pdf.ln(2)

     
        col_widths = [30, 50, 40, 40, 30]  
        row_height = 5
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_widths[0], row_height, "Código", border=1, fill=True)
        pdf.cell(col_widths[1], row_height, "Nombre", border=1, fill=True)
        pdf.cell(col_widths[2], row_height, "Municipio", border=1, fill=True)
        pdf.cell(col_widths[3], row_height, "Situación Legal", border=1, fill=True)
        pdf.cell(col_widths[4], row_height, "Ancho Legal", border=1, fill=True)
        pdf.ln()

  
        pdf.set_font("Arial", "", 10)

        for codigo_vp, nombre, municipio, situacion_legal, ancho_legal in vp_detectado:

            line_height = 5 
  
            nombre_lines = pdf.multi_cell(col_widths[1], line_height, str(nombre), split_only=True)
            if not nombre_lines:
                nombre_lines = [""]  
            nombre_height = len(nombre_lines) * line_height
            
            sit_leg_lines = pdf.multi_cell(col_widths[3], line_height, str(situacion_legal), split_only=True)
            if not sit_leg_lines:
                sit_leg_lines = [""] 
            sit_leg_height = len(sit_leg_lines) * line_height

         
            row_h = max(row_height, nombre_height, sit_leg_height)    

        
            x = pdf.get_x()
            y = pdf.get_y()

         
            pdf.rect(x, y, col_widths[0], row_h)
            pdf.rect(x + col_widths[0], y, col_widths[1], row_h)
            pdf.rect(x + col_widths[0] + col_widths[1], y, col_widths[2], row_h)
            pdf.rect(x + col_widths[0] + col_widths[1] + col_widths[2], y, col_widths[3], row_h)
            pdf.rect(x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3], y, col_widths[4], row_h)

          
       
            pdf.set_xy(x, y)
            pdf.multi_cell(col_widths[0], line_height, str(codigo_vp), align="L")

      
            pdf.set_xy(x + col_widths[0], y)
            pdf.multi_cell(col_widths[1], line_height, str(nombre), align="L")

       
            pdf.set_xy(x + col_widths[0] + col_widths[1], y)
            pdf.multi_cell(col_widths[2], line_height, str(municipio), align="L")

          
            pdf.set_xy(x + col_widths[0] + col_widths[1] + col_widths[2], y)
            pdf.multi_cell(col_widths[3], line_height, str(situacion_legal), align="L")

        
            pdf.set_xy(x + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3], y)
            pdf.multi_cell(col_widths[4], line_height, str(ancho_legal), align="L")

           
            pdf.set_xy(x, y + row_h)

        pdf.ln(5) 

 
    if mup_detectado:
     
        altura_estimada = 5 + 5 + (len(mup_detectado) * 6) + 10
        if not hay_espacio_suficiente(pdf, altura_estimada):
            pdf.add_page() 
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, "Afecciones a Montes (MUP):", ln=True)
        pdf.ln(2)

       
        line_height = 5
        col_widths = [30, 80, 40, 40]
        row_height = 5
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*azul_rgb)
        
   
        pdf.cell(col_widths[0], 5, "ID", border=1, fill=True)
        pdf.cell(col_widths[1], 5, "Nombre", border=1, fill=True)
        pdf.cell(col_widths[2], 5, "Municipio", border=1, fill=True)
        pdf.cell(col_widths[3], 5, "Propiedad", border=1, fill=True)
        pdf.ln()

 
        pdf.set_font("Arial", "", 10)
        for id_monte, nombre, municipio, propiedad in mup_detectado:
        
            id_lines = pdf.multi_cell(col_widths[0], line_height, str(id_monte), split_only=True) or [""]
            nombre_lines = pdf.multi_cell(col_widths[1], line_height, str(nombre), split_only=True) or [""]
            mun_lines = pdf.multi_cell(col_widths[2], line_height, str(municipio), split_only=True) or [""]
            prop_lines = pdf.multi_cell(col_widths[3], line_height, str(propiedad), split_only=True) or [""]

   
            row_h = max(
                5,
                len(id_lines) * line_height,
                len(nombre_lines) * line_height,
                len(mun_lines) * line_height,
                len(prop_lines) * line_height
            )
         
            x = pdf.get_x()
            y = pdf.get_y()

   
            pdf.rect(x, y, col_widths[0], row_h)
            pdf.rect(x + col_widths[0], y, col_widths[1], row_h)
            pdf.rect(x + col_widths[0] + col_widths[1], y, col_widths[2], row_h)
            pdf.rect(x + col_widths[0] + col_widths[1] + col_widths[2], y, col_widths[3], row_h)
 
            id_h = len(id_lines) * line_height
            pdf.set_xy(x, y + (row_h - id_h) / 2)
            pdf.multi_cell(col_widths[0], line_height, str(id_monte), align="L")
  
            nombre_h = len(nombre_lines) * line_height
            pdf.set_xy(x + col_widths[0], y + (row_h - nombre_h) / 2)
            pdf.multi_cell(col_widths[1], line_height, str(nombre), align="L")
    
            mun_h = len(mun_lines) * line_height
            pdf.set_xy(x + col_widths[0] + col_widths[1], y + (row_h - mun_h) / 2)
            pdf.multi_cell(col_widths[2], line_height, str(municipio), align="L")

            prop_h = len(prop_lines) * line_height
            pdf.set_xy(x + col_widths[0] + col_widths[1] + col_widths[2], y + (row_h - prop_h) / 2)
            pdf.multi_cell(col_widths[3], line_height, str(propiedad), align="L")


            pdf.set_y(y + row_h)

        pdf.ln(5) 

    if zepa_detectado:

        altura_estimada = 5 + 5 + (len(zepa_detectado) * 6) + 10
        if not hay_espacio_suficiente(pdf, altura_estimada):
            pdf.add_page()  
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, "Afecciones a Zonas de Especial Protección para las Aves (ZEPA):", ln=True)
        pdf.ln(2)
        pdf.set_x(pdf.l_margin)
        col_w_code = 30
        col_w_name = 190 - col_w_code
        row_height = 5
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_w_code, row_height, "Código", border=1, fill=True)
        pdf.cell(col_w_name, row_height, "Nombre", border=1, fill=True)
        pdf.ln()
        pdf.set_font("Arial", "", 10)
        for site_code, site_name in zepa_detectado:
            code_lines = pdf.multi_cell(col_w_code, 5, str(site_code), split_only=True)
            name_lines = pdf.multi_cell(col_w_name, 5, str(site_name), split_only=True)
            row_h = max(row_height, len(code_lines) * 5, len(name_lines) * 5)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_w_code, row_h)
            pdf.rect(x + col_w_code, y, col_w_name, row_h)
            code_h = len(code_lines) * 5
            y_code = y + (row_h - code_h) / 2
            pdf.set_xy(x, y_code)
            pdf.multi_cell(col_w_code, 5, str(site_code), align="L")
            name_h = len(name_lines) * 5
            y_name = y + (row_h - name_h) / 2
            pdf.set_xy(x + col_w_code, y_name)
            pdf.multi_cell(col_w_name, 5, str(site_name), align="L")
            pdf.set_y(y + row_h)
        pdf.ln(5)

    if lic_detectado:
         altura_estimada = 5 + 5 + (len(lic_detectado) * 6) + 10
         if not hay_espacio_suficiente(pdf, altura_estimada):
            pdf.add_page() 
        
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, "Afecciones a Lugares de Importancia Comunitaria (LIC):", ln=True)
        pdf.ln(2)
        col_w_code = 30
        col_w_name = 190 - col_w_code
        row_height = 5
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_w_code, row_height, "Código", border=1, fill=True)
        pdf.cell(col_w_name, row_height, "Nombre", border=1, fill=True)
        pdf.ln()
        pdf.set_font("Arial", "", 10)
        for site_code, site_name in lic_detectado:
            code_lines = pdf.multi_cell(col_w_code, 5, str(site_code), split_only=True)
            name_lines = pdf.multi_cell(col_w_name, 5, str(site_name), split_only=True)
            row_h = max(row_height, len(code_lines) * 5, len(name_lines) * 5)
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.rect(x, y, col_w_code, row_h)
            pdf.rect(x + col_w_code, y, col_w_name, row_h)
            code_h = len(code_lines) * 5
            y_code = y + (row_h - code_h) / 2
            pdf.set_xy(x, y_code)
            pdf.multi_cell(col_w_code, 5, str(site_code), align="L")
            name_h = len(name_lines) * 5
            y_name = y + (row_h - name_h) / 2
            pdf.set_xy(x + col_w_code, y_name)
            pdf.multi_cell(col_w_name, 5, str(site_name), align="L") 
            pdf.set_y(y + row_h)
        pdf.ln(5)     

    enp_detectado = list(set(tuple(row) for row in enp_detectado)) 
    if enp_detectado:
        
        altura_estimada = 5 + 5 + (len(enp_detectado) * 6) + 10
        if not hay_espacio_suficiente(pdf, altura_estimada):
            pdf.add_page()     

        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 5, "Afecciones a Espacios Naturales Protegidos (ENP):", ln=True)
        pdf.ln(2)

        ancho_total = 190
        col_widths = [ancho_total * 0.45, ancho_total * 0.55]
        line_height = 5

        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(*azul_rgb)
        pdf.cell(col_widths[0], 5, "Nombre", border=1, fill=True)
        pdf.cell(col_widths[1], 5, "Figura", border=1, fill=True, ln=True)

        pdf.set_font("Arial", "", 10)
        for nombre, figura in enp_detectado:
            nombre = str(nombre)
            figura = str(figura)

            nombre_lines = len(pdf.multi_cell(col_widths[0], line_height, nombre, split_only=True))
            figura_lines = len(pdf.multi_cell(col_widths[1], line_height, figura, split_only=True))
            row_height = max(5, nombre_lines * line_height, figura_lines * line_height)

            x = pdf.get_x()
            y = pdf.get_y()
   
            pdf.rect(x, y, col_widths[0], row_height)
            pdf.rect(x + col_widths[0], y, col_widths[1], row_height)
    
            pdf.set_xy(x, y + (row_height - nombre_lines * line_height) / 2)
            pdf.multi_cell(col_widths[0], line_height, nombre)

            pdf.set_xy(x + col_widths[0], y + (row_height - figura_lines * line_height) / 2)
            pdf.multi_cell(col_widths[1], line_height, figura)

            pdf.set_y(y + row_height)

        pdf.ln(5)    

    pdf.set_font("Arial", "", 8)  
    procedimientos_con_enlace = [
        ("1609", "Solicitudes, escritos y comunicaciones que no disponen de un procedimiento específico en la Guía de Procedimientos y Servicios.", "https://sede.carm.es/web/pagina?IDCONTENIDO=1609&IDTIPO=240&RASTRO=c$m40288"),
        ("1802", "Emisión de certificación sobre delimitación vías pecuarias con respecto a fincas particulares para inscripción registral.", "https://sede.carm.es/web/pagina?IDCONTENIDO=1802&IDTIPO=240&RASTRO=c$m40288"),
        ("3482", "Emisión de Informe en el ejercicio de los derechos de adquisición preferente (tanteo y retracto) en transmisiones fincas forestales.", None),
        ("3483", "Autorización de proyectos o actuaciones materiales en dominio público forestal que no conlleven concesión administrativa.", "https://sede.carm.es/web/pagina?IDCONTENIDO=3483&IDTIPO=240&RASTRO=c$m40288"),
        ("3485", "Deslinde y amojonamiento de montes a instancia de parte.", "https://sede.carm.es/web/pagina?IDCONTENIDO=3485&IDTIPO=240&RASTRO=c$m40288"),
        ("3487", "Clasificación, deslinde, desafectación y amojonamiento de vías pecuarias.", "https://sede.carm.es/web/pagina?IDCONTENIDO=3487&IDTIPO=240&RASTRO=c$m40293"),
        ("3488", "Emisión de certificaciones de colindancia de fincas particulares respecto a montes incluidos en el Catálogo de Utilidad Pública.", "https://sede.carm.es/web/pagina?IDCONTENIDO=3488&IDTIPO=240&RASTRO=c$m40293"),
        ("3489", "Autorizaciones en dominio público pecuario sin uso privativo.", "https://sede.carm.es/web/pagina?IDCONTENIDO=3489&IDTIPO=240&RASTRO=c$m40288"),
        ("3490", "Emisión de certificación o informe de colindancia de finca particular respecto de vía pecuaria.", "https://sede.carm.es/web/pagina?IDCONTENIDO=3490&IDTIPO=240&RASTRO=c$m40288"),
        ("5883", "(INM) Emisión de certificación o informe para inmatriculación o inscripción registral de fincas colindantes con monte incluido en el CUP.", "https://sede.carm.es/web/pagina?IDCONTENIDO=5883&IDTIPO=240&RASTRO=c$m40288"),
        ("482", "Autorizaciones e informes en Espacios Naturales Protegidos y Red Natura 2000 de la Región de Murcia.", "https://sede.carm.es/web/pagina?IDCONTENIDO=482&IDTIPO=240&RASTRO=c$m40288"),
        ("7186", "Ocupación renovable de carácter temporal de vías pecuarias con concesión demanial.", None),
        ("7202", "Modificación de trazados en vías pecuarias.", "https://sede.carm.es/web/pagina?IDCONTENIDO=7202&IDTIPO=240&RASTRO=c$m40288"),
        ("7222", "Concesión para la utilización privativa y aprovechamiento especial del dominio público.", None),
        ("7242", "Autorización de permutas en montes públicos.", "https://sede.carm.es/web/pagina?IDCONTENIDO=7242&IDTIPO=240&RASTRO=c$m40288"),
    ]

    texto_rojo = (
        "Este informe carece validez legal y sirve solo como información general, por lo que de ser detectadas afecciones a Dominio público forestal y/o pecuario, así como a Espacios Naturales Protegidos o RN2000, solicitar informe a la D. G. de Patrimonio Natural y Acción Climática, a través de los procedimientos establecidos en sede electrónica."
    )

    margin = pdf.l_margin
    line_height = 4
    codigo_width = 9
    espacio_entre = 2
    x_codigo = margin
    x_texto = margin + codigo_width + espacio_entre
    ancho_texto = 190

 
    lineas_rojo = len(pdf.multi_cell(pdf.w - 2*margin, 5, texto_rojo, border=0, align="J", split_only=True))
    altura_cuadro = max(1, lineas_rojo) * 5 + 2  # + ln(2)

  
    lineas_resto = len(pdf.multi_cell(pdf.w - 2*margin, 5, texto_resto, border=0, align="J", split_only=True))
    altura_resto = max(1, lineas_resto) * 5 + 2  # + ln(2)


    altura_procedimientos = 0
    for codigo, texto, url in procedimientos_con_enlace:
        lineas = len(pdf.multi_cell(ancho_texto, line_height, texto, border=0, align="J", split_only=True))
        altura_procedimientos += max(1, lineas) * line_height

 
    espacio_inicial = 10
    espacio_entre = 4
    espacio_final = 5
    altura_total = espacio_inicial + altura_cuadro + espacio_entre + altura_resto + altura_procedimientos + espacio_final


    if not hay_espacio_suficiente(pdf, altura_total):
        pdf.add_page()


    pdf.ln(10) 


    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(255, 0, 0)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.5)
    pdf.set_fill_color(251, 228, 213)
    pdf.multi_cell(190, 5, texto_rojo, border=1, align="J", fill=True)
    pdf.ln(2)


    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "B", 8)
    pdf.multi_cell(190, 5, texto_resto, border=0, align="J")
    pdf.ln(2)


    pdf.set_font("Arial", "", 8)
    y = pdf.get_y()

    for codigo, texto, url in procedimientos_con_enlace:
        lineas = len(pdf.multi_cell(ancho_texto, line_height, texto, border=0, align="J", split_only=True))
        altura_linea = max(1, lineas) * line_height

        if pdf.get_y() + altura_linea > pdf.h - pdf.b_margin:
            pdf.add_page()
            y = pdf.get_y()

        pdf.set_xy(x_codigo, y)
        if url:
            pdf.set_text_color(0, 0, 255)
            pdf.cell(codigo_width, line_height, f"- {codigo}", border=0)
            pdf.link(x_codigo, y, codigo_width, line_height, url)
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.cell(codigo_width, line_height, f"- {codigo}", border=0)

        pdf.set_xy(x_texto, y)
        pdf.multi_cell(ancho_texto, line_height, texto, border=0, align="J")
        y += altura_linea

    pdf.ln(espacio_final)


    pdf.set_font("Arial", "B", 9)  
    texto_final = (
        "\nLas afecciones del presente informe se fundamentan en la cartografía oficial de la Comunidad Autónoma D. G. de Patrimonio Natural y Acción Climática:  montes y vías pecuarias https://mapas-gis-inter.carm.es/geoserver/PFO_ZOR_DMVP_CARM/wfs)
          D. G. de Ordenación del Territorio y Arquitectura: https://mapas-gis-inter.carm.es/geoserver/SIT_USU_PLA_URB_CARM/wfs? y de la Dirección General del Catastro: https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWFS.aspx
          cumpliendo el estándar técnico Web Feature Service (WFS) definido por el Open Geospatial Consortium (OGC) y la Directiva INSPIRE, eximiendo en todo caso a este centro directivo de cualquier error en la cartografía de planeamiento o catastral.\n\n"
        "El Planeamiento se rige por la Ley 13/2015, de 30 de marzo, de ordenación territorial y urbanística de la Región de Murcia, y por el PGOU de cada término municipal. El Régimen del suelo no urbanizable se recoge en el artículo 5 de la citada ley.\n\n"
        "En suelo no urbanizable se prestará especial atención a la Disposición adicional segunda de la Ley 3/2020, de 27 de julio, de recuperación y protección del Mar Menor, y artículo 5 de la Ley 43/2003, de 21 de noviembre, de Montes. Solicitando para posibles cambios de uso lo establecido en la normativa de referencia.\n\n"
        "De acuerdo con lo establecido en el artículo 22.1 de la ley 43/2003 de 21 de noviembre de Montes, toda inmatriculación o inscripción de exceso de cabida en el Registro de la Propiedad de un monte o de una finca colindante con monte demanial o ubicado en un término municipal en el que existan montes demaniales requerirá el previo informe favorable de los titulares de dichos montes y, para los montes catalogados, el del órgano forestal de la Comunidad Autónoma.\n\n\"
        "De acuerdo con lo establecido en el artículo 25.5 de la ley 43/2003 de 21 de noviembre de Montes, para posibilitar el ejercicio del derecho de adquisición preferente a través de la acción de tanteo, el transmitente deberá notificar fehacientemente a la Administración pública titular de ese derecho los datos relativos al precio y características de la transmisión proyectada, la cual dispondrá de un plazo de tres meses, a partir de dicha notificación, para ejercitar dicho derecho, mediante el abono o consignación de su importe en las referidas condiciones.\n\n"
        "En relación al Dominio Público Pecuario, salvaguardando lo que pudiera resultar de los futuros deslindes, en la parcela objeto este informe, cualquier construcción, plantación, vallado, obras, instalaciones, etc., no deberían realizarse dentro del área delimitada como Dominio Público Pecuario provisional para evitar invadir este.\n\n"
        "En cuanto a vías pecuarias, salvaguardando lo que pudiera resultar de los futuros deslindes, en las parcelas objeto este informe-borrador, cualquier construcción, plantación, vallado, obras, instalaciones, etc., no deberían realizarse dentro del área delimitada como dominio público pecuario provisional para evitar invadir éste.\n\n"
        "En todo caso, no podrá interrumpirse el tránsito por las Vías Pecuarias, dejando siempre el paso adecuado para el tránsito ganadero y otros usos legalmente establecidos en la Ley 3/1995, de 23 de marzo, de Vías Pecuarias.\n\n"
        "Este informe preliminar con carácter de borrador, se emite a efectos ambientales, sin perjuicio de terceros, no prejuzga derechos de propiedad y se habrán de obtener cuantas autorizaciones, licencias o permisos sean preceptivos conforme a la Ley."
    )
    pdf.multi_cell(190, 5, texto_final, border=0, align="J")
    pdf.ln(2)
    pdf.output(filename)
    return filename


st.image(
    "https://raw.githubusercontent.com/UDIFCARM/Afecciones_UDIF/main/logos.jpg",
    width=250
)
st.title("Informe basico de Afecciones al medio")

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
if 'afecciones' not in st.session_state:
    st.session_state['afecciones'] = []

if submitted:

    for key in ['mapa_html', 'pdf_file']:
        if key in st.session_state and st.session_state[key]:
            try:
                if os.path.exists(st.session_state[key]):
                    os.remove(st.session_state[key])
            except:
                pass
    st.session_state.pop('mapa_html', None)
    st.session_state.pop('pdf_file', None)


    if not nombre or not apellidos or not dni or x == 0 or y == 0:
        st.warning("Por favor, completa todos los campos obligatorios y asegúrate de que las coordenadas son válidas.")
    else:
 
        lon, lat = transformar_coordenadas(x, y)
        if lon is None or lat is None:
            st.error("No se pudo generar el informe debido a coordenadas inválidas.")
        else:

            if modo == "Por parcela":
                query_geom = parcela.geometry.iloc[0]
            else:
                query_geom = Point(x, y)


            st.session_state['query_geom'] = query_geom        
            uso_suelo_url = "https://mapas-gis-inter.carm.es/geoserver/SIT_USU_PLA_URB_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=SIT_USU_PLA_URB_CARM:plu_ze_37_mun_uso_suelo&outputFormat=application/json"
            enp_url = "https://mapas-gis-inter.carm.es/geoserver/SIG_LUP_SITES_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=SIG_LUP_SITES_CARM:ENP&outputFormat=application/json"
            zepa_url = "https://mapas-gis-inter.carm.es/geoserver/SIG_LUP_SITES_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=SIG_LUP_SITES_CARM:ZEPA&outputFormat=application/json"
            lic_url = "https://mapas-gis-inter.carm.es/geoserver/SIG_LUP_SITES_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=SIG_LUP_SITES_CARM:LIC-ZEC&outputFormat=application/json"
            vp_url = "https://mapas-gis-inter.carm.es/geoserver/PFO_ZOR_DMVP_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=PFO_ZOR_DMVP_CARM:VP_CARM&outputFormat=application/json"
            tm_url = "https://mapas-gis-inter.carm.es/geoserver/MAP_UAD_DIVISION-ADMINISTRATIVA_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=MAP_UAD_DIVISION-ADMINISTRATIVA_CARM:recintos_municipales_inspire_carm_etrs89&outputFormat=application/json"
            mup_url = "https://mapas-gis-inter.carm.es/geoserver/PFO_ZOR_DMVP_CARM/wfs?service=WFS&version=1.1.0&request=GetFeature&typeName=PFO_ZOR_DMVP_CARM:MONTES&outputFormat=application/json"
            st.session_state['wfs_urls'] = {
                'enp': enp_url, 'zepa': zepa_url, 'lic': lic_url,
                'vp': vp_url, 'tm': tm_url, 'mup': mup_url,                
                'uso_suelo': uso_suelo_url               
            }
      
            afeccion_uso_suelo = consultar_wfs_seguro(query_geom, uso_suelo_url, "PLANEAMIENTO", campo_nombre="Clasificacion")
            afeccion_enp = consultar_wfs_seguro(query_geom, enp_url, "ENP", campo_nombre="nombre")
            afeccion_zepa = consultar_wfs_seguro(query_geom, zepa_url, "ZEPA", campo_nombre="site_name")
            afeccion_lic = consultar_wfs_seguro(query_geom, lic_url, "LIC", campo_nombre="site_name")
            afeccion_vp = consultar_wfs_seguro(query_geom, vp_url, "VP", campo_nombre="vp_nb")
            afeccion_tm = consultar_wfs_seguro(query_geom, tm_url, "TM", campo_nombre="nameunit")
            afeccion_mup = consultar_wfs_seguro(
                query_geom, mup_url, "MUP",
                campos_mup=["id_monte:ID", "nombremont:Nombre", "municipio:Municipio", "propiedad:Propiedad"]
            )
            afecciones = [afeccion_uso_suelo, afeccion_enp, afeccion_zepa, afeccion_lic, afeccion_vp, afeccion_tm, afeccion_mup]

 
            datos = {
                "fecha_informe": datetime.today().strftime('%d/%m/%Y'),
                "nombre": nombre, "apellidos": apellidos, "dni": dni,
                "dirección": direccion, "teléfono": telefono, "email": email,
                "objeto de la solicitud": objeto,
                "afección MUP": afeccion_mup, "afección VP": afeccion_vp,
                "afección ENP": afeccion_enp, "afección ZEPA": afeccion_zepa,
                "afección LIC": afeccion_lic, "Afección TM": afeccion_tm,                
                "afección uso_suelo": afeccion_uso_suelo,                
                "coordenadas_x": x, "coordenadas_y": y,
                "municipio": municipio_sel, "polígono": masa_sel, "parcela": parcela_sel
            }


            st.write(f"Municipio seleccionado: {municipio_sel}")
            st.write(f"Polígono seleccionado: {masa_sel}")
            st.write(f"Parcela seleccionada: {parcela_sel}")

            mapa_html, afecciones_lista = crear_mapa(lon, lat, afecciones, parcela_gdf=parcela)
            if mapa_html:
                st.session_state['mapa_html'] = mapa_html
                st.session_state['afecciones'] = afecciones_lista
                st.subheader("Resultado de las afecciones")
                for afeccion in afecciones_lista:
                    st.write(f"• {afeccion}")
                with open(mapa_html, 'r') as f:
                    html(f.read(), height=500)

             pdf_filename = f"informe_{uuid.uuid4().hex[:8]}.pdf"
            try:
                generar_pdf(datos, x, y, pdf_filename)
                st.session_state['pdf_file'] = pdf_filename
            except Exception as e:
                st.error(f"Error al generar el PDF: {str(e)}")

            st.session_state.pop('query_geom', None)
            st.session_state.pop('wfs_urls', None)
if st.session_state['mapa_html'] and st.session_state['pdf_file']:
    try:
        with open(st.session_state['pdf_file'], "rb") as f:
            st.download_button("📄 Descargar informe PDF", f, file_name="informe_afecciones.pdf")
    except Exception as e:
        st.error(f"Error al descargar el PDF: {str(e)}")

    try:
        with open(st.session_state['mapa_html'], "r") as f:
            st.download_button("🌍 Descargar mapa HTML", f, file_name="mapa_busqueda.html")
    except Exception as e:
        st.error(f"Error al descargar el mapa HTML: {str(e)}")
