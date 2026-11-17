"""
keyboards.py — Teclados (botões interativos) do CosmicBot.

Responsabilidade: criar os botões inline do Telegram. Cada botão envia
um "callback_data" (texto curto) que o handlers.py usa para saber
qual funcionalidade o usuário escolheu.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Identificadores enviados pelos botões (usados também em handlers.py)
APOD_HOJE = "apod_hoje"
APOD_DATA = "apod_data"
APOD_ALEATORIA = "apod_aleatoria"
MARTE = "marte"
ASTEROIDES = "asteroides"
CURIOSIDADE = "curiosidade"
AJUDA = "ajuda"
MENU = "menu"


def menu_principal():
    """Menu com todas as funcionalidades do bot."""
    botoes = [
        [InlineKeyboardButton("🌌 Foto do Dia (APOD)", callback_data=APOD_HOJE)],
        [
            InlineKeyboardButton("📅 APOD por data", callback_data=APOD_DATA),
            InlineKeyboardButton("🎲 APOD aleatória", callback_data=APOD_ALEATORIA),
        ],
        [
            InlineKeyboardButton("🔴 Explorar Marte", callback_data=MARTE),
            InlineKeyboardButton("☄️ Asteroides", callback_data=ASTEROIDES),
        ],
        [
            InlineKeyboardButton("💡 Curiosidade", callback_data=CURIOSIDADE),
            InlineKeyboardButton("❓ Ajuda", callback_data=AJUDA),
        ],
    ]
    return InlineKeyboardMarkup(botoes)


def apos_acao(callback_repetir, texto_repetir="🔄 Outra"):
    """
    Botões exibidos depois de cada resposta: repetir a mesma ação
    ou voltar ao menu principal.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(texto_repetir, callback_data=callback_repetir),
            InlineKeyboardButton("🏠 Menu", callback_data=MENU),
        ]
    ])


def voltar_menu():
    """Apenas o botão de retorno ao menu."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu principal", callback_data=MENU)]])
