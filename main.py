

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import config
import handlers


class FormatadorSeguro(logging.Formatter):
    """
    Formatador de log que substitui os tokens por '***' antes de exibir
    qualquer linha — inclusive em mensagens de erro e tracebacks.
    """

    def format(self, record):
        texto = super().format(record)
        for segredo in (config.TELEGRAM_BOT_TOKEN, config.NASA_API_KEY):
            if segredo:
                texto = texto.replace(segredo, "***")
        return texto


def configurar_logs():
    saida = logging.StreamHandler()
    saida.setFormatter(FormatadorSeguro("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[saida])
    # A biblioteca httpx registra as URLs completas (que contêm os tokens).
    # Reduzimos seu nível para não poluir nem expor nada no terminal.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def registrar_comandos(aplicacao):
    """Cadastra a lista de comandos que aparece ao digitar '/' no Telegram."""
    try:
        await aplicacao.bot.set_my_commands([
            BotCommand("start", "Menu principal do CosmicBot"),
            BotCommand("apod", "Foto astronômica do dia (ou /apod DD/MM/AAAA)"),
            BotCommand("marte", "Foto real de Marte pelo rover Curiosity"),
            BotCommand("asteroides", "Asteroides próximos da Terra hoje"),
            BotCommand("curiosidade", "Curiosidade astronômica"),
            BotCommand("ajuda", "Lista de comandos"),
        ])
    except Exception as erro:  # não impede o bot de iniciar
        logging.getLogger(__name__).warning("Não foi possível registrar os comandos: %s", erro)


def main():
    configurar_logs()
    config.validar_configuracao()
    logger = logging.getLogger("cosmicbot")

    aplicacao = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(registrar_comandos)
        .build()
    )

    # Comandos (aceitamos também os nomes em inglês por conveniência)
    aplicacao.add_handler(CommandHandler("start", handlers.start))
    aplicacao.add_handler(CommandHandler(["ajuda", "help"], handlers.ajuda))
    aplicacao.add_handler(CommandHandler("apod", handlers.apod))
    aplicacao.add_handler(CommandHandler(["marte", "mars"], handlers.marte))
    aplicacao.add_handler(CommandHandler(["asteroides", "asteroids"], handlers.asteroides))
    aplicacao.add_handler(CommandHandler(["curiosidade", "curiosity"], handlers.curiosidade))

    # Botões inline e mensagens de texto comuns
    aplicacao.add_handler(CallbackQueryHandler(handlers.botoes))
    aplicacao.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.receber_texto))

    # Rede de segurança: nenhum erro isolado derruba o bot
    aplicacao.add_error_handler(handlers.tratar_erro)

    logger.info("🚀 CosmicBot em órbita! Pressione Ctrl+C para encerrar.")
    aplicacao.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
