import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials


class GoogleSheetsManager:
    """Classe para gerenciar conexão com Google Sheets"""

    def __init__(self):
        self.credentials_path = "credentials.json"
        self.client = None

    def connect(self):
        """Conecta ao Google Sheets API"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_path, scope
            )
            self.client = gspread.authorize(creds)
        except Exception as e:
            raise Exception("Erro ao conectar ao Google Sheets:", str(e))

    def download_sheet_as_csv(
        self, spreadsheet_id: str, sheet_name: str
    ) -> pd.DataFrame:
        """Baixa uma planilha específica como DataFrame"""
        try:
            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            df = pd.DataFrame(worksheet.get_all_records())
            return df
        except Exception as e:
            raise Exception("Erro ao baixar dados do Google Sheets:", str(e))
