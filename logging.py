import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

def registrar_evento(municipio, evento):
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open("metricas_afecciones").sheet1

    sheet.append_row([
        datetime.now().isoformat(),
        municipio,
        evento
    ])
