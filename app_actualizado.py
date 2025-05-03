
from docx import Document
from datetime import datetime
import streamlit as st

def generar_informe(datos, plantilla_path="plantilla_informe_afecciones.docx"):
    doc = Document(plantilla_path)
    
    for p in doc.paragraphs:
        for key, value in datos.items():
            marcador = f"{{{{{key}}}}}"
            if marcador in p.text:
                p.text = p.text.replace(marcador, str(value))
    
    output_path = "informe_generado.docx"
    doc.save(output_path)
    return output_path

# Interfaz de usuario
st.title("Generador de Informe de Afecciones Ambientales")

with st.form("formulario"):
    nombre = st.text_input("Nombre")
    apellidos = st.text_input("Apellidos")
    dni = st.text_input("DNI")
    direccion = st.text_input("Dirección")
    telefono = st.text_input("Teléfono")
    email = st.text_input("Correo electrónico")
    objeto = st.text_area("Objeto de la solicitud")

    municipio = st.text_input("Municipio")
    poligono = st.text_input("Polígono")
    parcela = st.text_input("Parcela")
    coordenadas_x = st.text_input("Coordenada X")
    coordenadas_y = st.text_input("Coordenada Y")

    mup_id = st.text_input("CUP")
    mup_nombre = st.text_input("Nombre del MUP")
    mup_municipio = st.text_input("Municipio del MUP")
    mup_propiedad = st.text_input("Propiedad del MUP")

    tm = st.text_input("Términos municipales afectados")
    vp = st.text_input("Vías pecuarias")
    enp = st.text_input("Espacios Naturales Protegidos")
    zepa = st.text_input("Zonas ZEPA")
    lic = st.text_input("Lugares de Importancia Comunitaria")

    enviar = st.form_submit_button("Generar informe")

if enviar:
    datos = {
        "fecha_solicitud": datetime.today().strftime("%d/%m/%Y"),
        "fecha_informe": datetime.today().strftime("%d/%m/%Y"),
        "nombre": nombre,
        "apellidos": apellidos,
        "dni": dni,
        "direccion": direccion,
        "telefono": telefono,
        "email": email,
        "objeto": objeto,
        "municipio": municipio,
        "poligono": poligono,
        "parcela": parcela,
        "coordenadas_x": coordenadas_x,
        "coordenadas_y": coordenadas_y,
        "mup_id": mup_id,
        "mup_nombre": mup_nombre,
        "mup_municipio": mup_municipio,
        "mup_propiedad": mup_propiedad,
        "tm": tm,
        "vp": vp,
        "enp": enp,
        "zepa": zepa,
        "lic": lic
    }

    informe_path = generar_informe(datos)
    with open(informe_path, "rb") as file:
        st.download_button("Descargar informe", file, file_name="informe_afecciones.docx")
