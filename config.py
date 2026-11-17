"""
config.py — Configurações do CosmicBot.

Responsabilidade: carregar as credenciais do arquivo .env e reunir,
em um único lugar, as constantes usadas pelo restante do projeto.
Nenhum token fica escrito diretamente no código-fonte.
"""

import os
from datetime import date

from dotenv import load_dotenv

# Lê o arquivo .env e coloca suas variáveis no ambiente do processo.
load_dotenv()

# --- Credenciais (lidas do .env) ---
NASA_API_KEY = os.getenv("NASA_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# --- Endereços das APIs da NASA ---
NASA_BASE_URL = "https://api.nasa.gov"
APOD_URL = f"{NASA_BASE_URL}/planetary/apod"  # API antiga (desativada pela NASA em 01/12/2026)
# Nova fonte oficial da APOD, no site science.nasa.gov (não exige chave)
APOD_NOVA_URL = "https://science.nasa.gov/wp-json/wp/v2/apod-basic"
MARS_PHOTOS_URL = f"{NASA_BASE_URL}/mars-photos/api/v1/rovers/curiosity/photos"
NEO_FEED_URL = f"{NASA_BASE_URL}/neo/rest/v1/feed"
# Biblioteca de Imagens e Vídeos da NASA (usada como alternativa para Marte)
NASA_IMAGES_URL = "https://images-api.nasa.gov/search"

# --- Parâmetros gerais ---
TEMPO_LIMITE_SEGUNDOS = 20          # tempo máximo de espera por uma resposta
APOD_DATA_MINIMA = date(1995, 6, 16)  # primeira APOD publicada pela NASA
SOL_MAXIMO_CURIOSITY = 4000         # faixa de sóis usada no sorteio de fotos
MAX_ASTEROIDES_EXIBIDOS = 5         # quantos asteroides mostrar por consulta


def validar_configuracao():
    """
    Verifica se as credenciais obrigatórias foram definidas.
    Encerra o programa com uma mensagem clara caso falte alguma.
    (Esta é a única situação em que o bot deixa de iniciar.)
    """
    faltando = []
    if not NASA_API_KEY:
        faltando.append("NASA_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        faltando.append("TELEGRAM_BOT_TOKEN")

    if faltando:
        raise SystemExit(
            "❌ Configuração incompleta! Defina no arquivo .env: "
            + ", ".join(faltando)
            + "\n   Dica: copie o .env.example para .env e preencha os valores."
        )
