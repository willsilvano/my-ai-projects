from langgraph.graph import END, START, StateGraph
from langgraph.graph import MessagesState
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from datetime import datetime
import json
from duckdb_manager import DuckDBManager


class AgentManager:
    def __init__(self, llm):
        self.llm = llm
        self.__prepare_tools()
        self.__init_duckdb()

    def __init_duckdb(self):
        self.duckdb_manager = DuckDBManager()
        self.duckdb_manager.connect()

    def generate_graph(self):
        builder = StateGraph(MessagesState)

        builder.add_node("assistant", self.__assistant)
        builder.add_node("tools", ToolNode(self.tools))

        builder.add_edge(START, "assistant")
        builder.add_conditional_edges("assistant", self.__router)
        builder.add_edge("tools", "assistant")

        memory = MemorySaver()

        return builder.compile(checkpointer=memory)

    def __get_db_schema(self):
        schema = {}
        tables = self.duckdb_manager.execute_query("SHOW TABLES")

        for table in tables:
            info = self.duckdb_manager.execute_query(
                f"PRAGMA table_info('{table['name']}')"
            )
            schema[table["name"]] = {
                "columns": {
                    col["name"]: {"type": col["type"], "nullable": not col["notnull"]}
                    for col in info
                }
            }

        schema_json = json.dumps({"tables": schema}, indent=2)
        return schema_json

    def __get_categories(self):
        categories = []
        rows = self.duckdb_manager.execute_query("SELECT * FROM tb_categorias")
        for row in rows:
            categories.append(row["nome"])
        return categories

    def __prepare_tools(self):
        self.tools = [
            self.__execute_sql,
        ]
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    def __get_current_date(self):
        return datetime.now().strftime("%d/%m/%Y")

    def __assistant(self, state: MessagesState):
        db_schema = self.__get_db_schema()
        categories = self.__get_categories()

        system_prompt = f"""
        Você é um assistente de IA que ajuda a responder perguntas sobre um banco de dados DuckDB.
        Você sabe converter consultas em linguagem natural para SQL e executar essas consultas.
        Você pode executar consultas SQL e atualizar o banco de dados com dados de Google Sheets.
        Você conhece o esquema do banco de dados, incluindo tabelas e colunas.
        Você sempre fala em português do Brasil.
        Sempre que o usuário perguntar algo relacionado a dados, você deve usar a função execute_sql.

        SCHEMA:
        {db_schema}

        CATEGORIAS:
        {categories}

        Exemplos de queries:

        - "Qual o saldo das metas?"
        Query: SELECT
                    m.nome,
                    COALESCE(d.total_depositos, 0) AS depositos,
                    COALESCE(e.total_despesas, 0) AS despesas,
                    COALESCE(d.total_depositos, 0) - COALESCE(e.total_despesas, 0) AS saldo
                FROM tb_metas m
                LEFT JOIN (
                    SELECT meta, SUM(valor) AS total_depositos
                    FROM tb_deposito_metas
                    GROUP BY meta
                ) d ON d.meta = m.nome
                LEFT JOIN (
                    SELECT meta, SUM(valor) AS total_despesas
                    FROM tb_despesas
                    GROUP BY meta
                ) e ON e.meta = m.nome

        - "Qual o saldo das contas?"
        Query: SELECT
                    c.nome AS conta,
                    COALESCE(r.total_receitas, 0) AS total_receitas,
                    COALESCE(d.total_despesas, 0) AS total_despesas,
                    COALESCE(tin.total_recebido, 0) AS transferencias_entradas,
                    COALESCE(tout.total_enviado, 0) AS transferencias_saidas,
                    COALESCE(r.total_receitas, 0)
                    - COALESCE(d.total_despesas, 0)
                    + COALESCE(tin.total_recebido, 0)
                    - COALESCE(tout.total_enviado, 0) AS saldo
                FROM tb_contas c
                LEFT JOIN (
                    SELECT conta, SUM(valor) AS total_receitas
                    FROM tb_receitas
                    WHERE realizado = 1
                    GROUP BY conta
                ) r ON r.conta = c.nome
                LEFT JOIN (
                    SELECT conta, SUM(valor) AS total_despesas
                    FROM tb_despesas
                    WHERE realizado = 1
                    GROUP BY conta
                ) d ON d.conta = c.nome
                LEFT JOIN (
                    SELECT conta_destino AS conta, SUM(valor) AS total_recebido
                    FROM tb_transferencias
                    WHERE realizado = 1
                    GROUP BY conta_destino
                ) tin ON tin.conta = c.nome
                LEFT JOIN (
                    SELECT conta_origem AS conta, SUM(valor) AS total_enviado
                    FROM tb_transferencias
                    WHERE realizado = 1
                    GROUP BY conta_origem
                ) tout ON tout.conta = c.nome;

        Data atual: {self.__get_current_date()}

        Os meses são representados no formato YYYY-MM, exemplo: 2025-01.

        Sempre que possível crie alias para as colunas, para evitar ambiguidade.

        Você executa apenas consultas SELECT e não pode modificar os dados.

        Você pode executar as seguintes funções:
        - execute_sql: Executa uma consulta SQL no DuckDB.

        Nos valores modalidades em R$ aplique um \\$ antes do valor.

        """
        return {
            "messages": [
                self.llm_with_tools.invoke([system_prompt] + state["messages"])
            ]
        }

    def __router(self, state: MessagesState):
        has_tool_calls = (
            hasattr(state["messages"][-1], "tool_calls")
            and state["messages"][-1].tool_calls
        )
        if has_tool_calls:
            return "tools"
        return END

    def __execute_sql(self, sql: str):
        """
        Função para executar uma consulta SQL no DuckDB.
        Essa função é chamada pelo assistente para executar consultas SQL.
        Sempre que o usuário fizer uma pergunta que requer uma consulta SQL,
        essa função será chamada para executar a consulta e retornar os resultados.

        Args:
            sql (str): A consulta SQL a ser executada.

        Returns:
            List[Dict[str, Any]]: Os resultados da consulta SQL.
        """
        try:
            result = self.duckdb_manager.execute_query(sql)
            return result
        except Exception as e:
            return f"Erro ao executar consulta SQL: {str(e)}"
