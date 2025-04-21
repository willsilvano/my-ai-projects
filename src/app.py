import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
import os
import uuid

from duckdb_manager import DuckDBManager
from google_sheets_manager import GoogleSheetsManager
from graph_manager import AgentManager
import json

from dotenv import load_dotenv

import pandas as pd

pd.set_option("future.no_silent_downcasting", True)

# Load environment variables from .env file
load_dotenv()


def init_app():
    st.set_page_config(page_title="Chatbot Financeiro", page_icon="🤖", layout="wide")

    st.title("Chatbot Financeiro")
    st.markdown(
        """
    Este é um chatbot financeiro que pode responder perguntas sobre suas finanças.
    Você pode perguntar sobre categorias, transações, e muito mais.
    """
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "model_option" not in st.session_state:
        st.session_state.model_option = "ollama|qwen2.5:7b"
    if "temperature" not in st.session_state:
        st.session_state.temperature = 0.2
    if "llm" not in st.session_state:
        st.session_state.llm = None
    if "graph" not in st.session_state:
        st.session_state.graph = None
    if "initialized" not in st.session_state:
        st.session_state.initialized = False
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())


def clear_chat():
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())
    st.toast("Chat limpo com sucesso!")


def setup_sidebar():
    st.sidebar.title("Configurações")

    st.sidebar.selectbox(
        "Escolha o modelo:",
        [
            "ollama|qwen2.5:7b",
            "ollama|granite3.3:8b",
            "ollama|cogito:8b",
            "google|gemini-2.5-pro-exp-03-25",
            "google|gemini-2.5-flash-preview-04-17",
            "groq|llama3-70b-8192",
            "groq|meta-llama/llama-4-scout-17b-16e-instruct",
            "groq|meta-llama/llama-4-maverick-17b-128e-instruct",
        ],
        key="model_option",
        on_change=change_model,
    )

    st.sidebar.slider(
        "Temperatura", 0.0, 1.0, key="temperature", on_change=change_model
    )

    st.sidebar.button("Limpar Chat", on_click=clear_chat)
    st.sidebar.button("Baixar Dados", on_click=init_google_sheets)


@st.cache_resource
def get_llm(model_name):
    provider, model = model_name.split("|")
    temperature = st.session_state.temperature
    if provider == "ollama":
        return ChatOllama(model=model, temperature=temperature)
    elif provider == "google":
        if os.environ.get("GOOGLE_API_KEY") is None:
            raise ValueError("Chave de API do Google não encontrada.")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)
    elif provider == "groq":
        if os.environ.get("GROQ_API_KEY") is None:
            raise ValueError("Chave de API do Groq não encontrada.")
        return ChatGroq(model=model, temperature=temperature)
    else:
        raise ValueError("Modelo não suportado")


def display_chat_history():
    messages = []

    for message in st.session_state.messages:
        role = "user" if isinstance(message, HumanMessage) else "assistant"

        tool_call_id = getattr(message, "tool_call_id", None)

        # verifica se existe alguma mensagem com o toll_call_id e atualiza o item
        messages = [m for m in messages if m["tool_calls"] is not None]
        if tool_call_id is not None:
            for m in messages:
                for call in m["tool_calls"]:
                    if call["id"] == tool_call_id:
                        call["response"] = message.content
                        break
        else:
            messages.append(
                {
                    "role": role,
                    "content": message.content,
                    "tool_calls": getattr(message, "tool_calls", []),
                }
            )

    for message in messages:
        role = message["role"]
        content = message["content"]
        tool_calls = message["tool_calls"]

        # Display the main message content
        if not tool_calls:
            with st.chat_message(role):
                st.markdown(content)

        # Display tool calls in an expander
        if tool_calls:
            with st.expander("🔧 Tool Calls", expanded=False):
                for call in tool_calls:
                    st.code(
                        json.dumps(call, ensure_ascii=False, indent=2),
                        language="json",
                    )


def handle_user_input():
    if prompt := st.chat_input("Digite sua mensagem...", key="input"):
        with st.spinner("Processando resposta..."):
            thread = {"configurable": {"thread_id": st.session_state.thread_id}}

            for event in st.session_state.graph.stream(
                {"messages": prompt}, thread, stream_mode="values"
            ):
                message = event["messages"][-1]
                st.session_state.messages.append(message)


def change_model():
    # Validate model selection
    if not st.session_state.model_option:
        st.error("Nenhum modelo selecionado")
        return

    # Reset conversation state
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []

    try:
        # Load new model
        st.session_state.llm = get_llm(st.session_state.model_option)

        # Initialize agent with new model
        agent = AgentManager(llm=st.session_state.llm)

        st.session_state.graph = agent.generate_graph()
        st.toast(f"Modelo carregado: {st.session_state.model_option}")

    except ValueError as ve:
        st.error(f"Erro de configuração: {str(ve)}")
    except Exception as e:
        st.error(f"Erro inesperado ao alterar modelo: {str(e)}")
        st.session_state.llm = None
        st.session_state.graph = None


def init_google_sheets():
    try:
        gsheets = GoogleSheetsManager()
        gsheets.connect()

        duckdb_manager = DuckDBManager()
        duckdb_manager.connect()

        table_mapping = json.load(open("table_mapping.json", "r"))

        pbar = st.progress(0, text="Baixando dados...")

        for index, sheet_name in enumerate(table_mapping.keys()):
            pct = (index + 1) / len(table_mapping)
            pbar.progress(pct, f"Baixando {sheet_name}...")
            df = gsheets.download_sheet_as_csv(os.getenv("SPREADSHEET_ID"), sheet_name)
            if df is not None:
                if sheet_name in table_mapping:
                    table_name = table_mapping[sheet_name]["table_name"]
                    table_config = table_mapping[sheet_name]
                    df = df.copy()  # Evita problemas de chained assignment

                    created = duckdb_manager.create_table_from_df(
                        df, table_name, table_config
                    )

                    if not created:
                        raise Exception(f"Erro ao atualizar tabela {sheet_name}!")
                else:
                    raise Exception(
                        f"Erro: Planilha {sheet_name} não tem mapeamento definido."
                    )
            else:
                raise Exception(f"Erro ao baixar a planilha {sheet_name}.")
        pbar.empty()
        st.toast("Dados baixados e tabelas atualizadas com sucesso!")
    except Exception as e:
        st.error(f"Erro ao conectar ao Google Sheets: {e}")


def initialize_chat():
    if not st.session_state.initialized:
        if not os.path.exists("duckdb.db"):
            init_google_sheets()
        change_model()
        st.session_state.initialized = True


init_app()
setup_sidebar()
initialize_chat()
handle_user_input()
display_chat_history()
