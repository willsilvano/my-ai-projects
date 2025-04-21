import duckdb
import pandas as pd
import re
from typing import List, Dict, Any


class DuckDBManager:
    """Classe para gerenciar operações no DuckDB"""

    def __init__(self):
        self.db_path = "duckdb.db"
        self.conn = None

    def connect(self):
        """Conecta ao banco de dados DuckDB"""
        try:
            self.conn = duckdb.connect(self.db_path)
        except Exception as e:
            raise Exception("Erro ao conectar ao DuckDB:", str(e))

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Executa uma query no banco de dados e retorna os resultados."""
        result = self.conn.execute(query).fetchall()
        columns = [desc[0] for desc in self.conn.description]
        return [dict(zip(columns, row)) for row in result]

    def convert_currency_to_decimal(self, value):
        """Converte valores no formato R$ 1.999,99 para decimal mantendo precisão correta"""
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = re.sub(r"[^0-9,]", "", value)
            value = value.replace(",", ".")
            return value

    def create_table_from_df(
        self, df: pd.DataFrame, table_name: str, table_config: dict
    ):
        """Cria uma tabela a partir de um DataFrame considerando os tipos e nulabilidade definidos"""
        try:
            columns_def = []
            for original_name, details in table_config["columns"].items():
                col_name = details["name"]
                col_type = details["type"].upper()
                if col_type == "DECIMAL":
                    col_type = "DECIMAL(10,2)"
                nullable = "NULL" if details["nullable"] else "NOT NULL"
                columns_def.append(f"{col_name} {col_type} {nullable}")

            columns_sql = ", ".join(columns_def)
            create_table_sql = f"""
                CREATE OR REPLACE TABLE {table_name} (
                    {columns_sql}
                )
            """

            self.conn.execute(create_table_sql)

            # Inserir os dados convertendo para os tipos definidos
            df = df.rename(
                columns={
                    orig: details["name"]
                    for orig, details in table_config["columns"].items()
                }
            )
            df = df.copy()  # Evita problemas de chained assignment
            for col, details in table_config["columns"].items():
                col_name = details["name"]
                col_type = details["type"].upper()

                if col_type == "INTEGER":
                    df[col_name] = (
                        pd.to_numeric(df[col_name], errors="coerce")
                        .fillna(0)
                        .astype(pd.Int64Dtype())
                    )
                elif col_type == "DECIMAL":
                    df[col_name] = df[col_name].apply(self.convert_currency_to_decimal)
                elif col_type == "BOOLEAN":
                    df[col_name] = (
                        df[col_name]
                        .astype(str)
                        .str.lower()
                        .map({"true": True, "false": False})
                        .fillna(False)
                    )
                elif col_type == "DATE":
                    df[col_name] = pd.to_datetime(df[col_name], errors="coerce").dt.date
                elif col_type == "TEXT":
                    df[col_name] = df[col_name].astype(str).fillna("N/A")

                if not details["nullable"]:
                    df[col_name] = df[col_name].fillna(
                        "N/A" if col_type == "TEXT" else 0
                    )

            df = df.infer_objects(copy=False)  # Resolve o warning sobre downcasting

            self.conn.execute(f"INSERT INTO {table_name} SELECT * FROM df")
            return True
        except Exception as _:
            return False
