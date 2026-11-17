

import logging
import random
from html import escape

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import keyboards
import nasa_api
import tradutor
from nasa_api import NasaAPIError

logger = logging.getLogger(__name__)

LIMITE_LEGENDA = 1024   # limite do Telegram para legendas de fotos
LIMITE_MENSAGEM = 4096  # limite do Telegram para mensagens de texto

TEXTO_BOAS_VINDAS = (
    "🌌 <b>Bem-vindo ao CosmicBot!</b>\n\n"
    "Prepare-se para explorar o universo sem sair do Telegram.\n"
    "Descubra fotografias espaciais, conheça planetas e acompanhe "
    "acontecimentos astronômicos.\n\n"
    "🚀 <i>Escolha uma opção para começar sua jornada!</i>"
)

TEXTO_AJUDA = (
    "🛰️ <b>Central de Comandos do CosmicBot</b>\n\n"
    "/start — Abre o menu principal\n"
    "/apod — Foto astronômica do dia da NASA\n"
    "/apod DD/MM/AAAA — Foto de uma data anterior (ex.: <code>/apod 20/07/2024</code>)\n"
    "/marte — Foto real da superfície de Marte (rover Curiosity)\n"
    "/asteroides — Asteroides que passam perto da Terra hoje\n"
    "/curiosidade — Uma curiosidade astronômica com dados da NASA\n"
    "/ajuda — Mostra esta lista\n\n"
    "💡 <i>Você também pode usar os botões do menu, sem digitar nada!</i>"
)


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def _numero(valor, casas=0):
    """Formata números no padrão brasileiro: 1234567.8 -> '1.234.567,8'."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _resumir(texto, limite):
    """Corta um texto longo, adicionando reticências."""
    texto = texto or ""
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


async def _carregando(context, chat_id, texto, acao=ChatAction.TYPING):
    """Mostra um indicador de carregamento ("digitando..." + mensagem temporária)."""
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=acao)
        return await context.bot.send_message(chat_id=chat_id, text=texto)
    except TelegramError:
        return None


async def _apagar(mensagem):
    """Apaga a mensagem de carregamento, ignorando falhas."""
    if mensagem is None:
        return
    try:
        await mensagem.delete()
    except TelegramError:
        pass


async def _enviar_foto(context, chat_id, urls, legenda, teclado=None):
    """
    Tenta enviar a foto usando cada URL da lista, na ordem.
    Se o Telegram recusar todas (imagem grande demais, link quebrado...),
    devolve False para que quem chamou envie uma alternativa em texto.
    """
    for url in urls:
        if not url:
            continue
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=url,
                caption=_resumir(legenda, LIMITE_LEGENDA),
                parse_mode=ParseMode.HTML,
                reply_markup=teclado,
            )
            return True
        except TelegramError as erro:
            logger.warning("Telegram não conseguiu enviar a foto: %s", erro)
    return False


async def _enviar_texto(context, chat_id, texto, teclado=None):
    """Envia uma mensagem HTML respeitando o limite de tamanho do Telegram."""
    await context.bot.send_message(
        chat_id=chat_id,
        text=_resumir(texto, LIMITE_MENSAGEM),
        parse_mode=ParseMode.HTML,
        reply_markup=teclado,
    )


async def _enviar_erro(context, chat_id, mensagem, teclado=None):
    """Mensagem de erro amigável, sempre com caminho de volta ao menu."""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{mensagem}\n\n🛸 Houston, tivemos um problema — mas o bot continua em órbita!",
            reply_markup=teclado or keyboards.voltar_menu(),
        )
    except TelegramError as erro:
        logger.error("Não foi possível enviar a mensagem de erro: %s", erro)


# ---------------------------------------------------------------------------
# Menu e ajuda
# ---------------------------------------------------------------------------
async def mostrar_menu(context, chat_id):
    await context.bot.send_message(
        chat_id=chat_id,
        text=TEXTO_BOAS_VINDAS,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.menu_principal(),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — boas-vindas e menu principal."""
    context.user_data["aguardando_data"] = False
    await mostrar_menu(context, update.effective_chat.id)


async def ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ajuda — lista de comandos."""
    await _enviar_texto(context, update.effective_chat.id, TEXTO_AJUDA, keyboards.voltar_menu())


# ---------------------------------------------------------------------------
# APOD
# ---------------------------------------------------------------------------
async def enviar_apod(context, chat_id, data=None, aleatoria=False):
    """Busca e envia a APOD (de hoje, de uma data ou aleatória)."""
    aviso = await _carregando(context, chat_id, "🔭 Apontando o telescópio para a NASA...", ChatAction.UPLOAD_PHOTO)
    try:
        if aleatoria:
            apod = await nasa_api.buscar_apod_aleatoria()
        else:
            apod = await nasa_api.buscar_apod(data)
    except NasaAPIError as erro:
        await _apagar(aviso)
        await _enviar_erro(context, chat_id, str(erro))
        return

    await _apagar(aviso)

    repetir = keyboards.APOD_ALEATORIA if aleatoria else keyboards.APOD_DATA
    texto_repetir = "🎲 Outra aleatória" if aleatoria else "📅 Outra data"
    teclado = keyboards.apos_acao(repetir, texto_repetir)

    # Tradução do título e da explicação para o português
    titulo, _ = await tradutor.traduzir(apod["titulo"])
    texto_explicacao, traduzido = await tradutor.traduzir(apod["explicacao"])
    idioma = "traduzida automaticamente" if traduzido else "em inglês — tradução indisponível"

    legenda = (
        f"🌌 <b>{escape(_resumir(titulo, 200))}</b>\n"
        f"📅 Data de publicação: {escape(apod['data'])}\n"
    )
    if apod["credito"]:
        legenda += f"📸 Crédito: {escape(_resumir(apod['credito'], 200))}\n"

    explicacao = (
        f"📖 <b>Explicação científica da NASA</b> <i>({idioma})</i>:\n\n"
        + escape(_resumir(texto_explicacao, 3800))
    )

    if apod["tipo_midia"] == "image":
        enviada = await _enviar_foto(context, chat_id, apod["urls_imagem"], legenda)
        if not enviada:
            legenda += f"\n🖼️ Não consegui exibir a imagem aqui. Veja no site: {escape(apod['url'])}"
            await _enviar_texto(context, chat_id, legenda)
    else:
        # Algumas APODs são vídeos (YouTube/Vimeo) e não podem ir como foto
        legenda += f"\n🎬 Hoje a APOD é um <b>vídeo</b>! Assista: {escape(apod['url'] or 'link indisponível')}"
        await _enviar_texto(context, chat_id, legenda)

    await _enviar_texto(context, chat_id, explicacao, teclado)


async def apod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/apod [AAAA-MM-DD] — foto do dia ou de uma data anterior."""
    chat_id = update.effective_chat.id
    data = None
    if context.args:
        try:
            data = nasa_api.validar_data_apod(context.args[0])
        except ValueError as erro:
            await _enviar_erro(context, chat_id, str(erro))
            return
    await enviar_apod(context, chat_id, data)


async def pedir_data_apod(context, chat_id):
    """Coloca o usuário em modo 'aguardando data' (próxima mensagem será a data)."""
    context.user_data["aguardando_data"] = True
    await _enviar_texto(
        context,
        chat_id,
        "📅 Digite a data desejada no formato <b>DD/MM/AAAA</b>\n"
        "Exemplo: <code>20/07/2024</code>\n\n"
        "<i>Datas válidas: de 16/06/1995 até hoje.</i>",
        keyboards.voltar_menu(),
    )


# ---------------------------------------------------------------------------
# Marte
# ---------------------------------------------------------------------------
async def enviar_marte(context, chat_id):
    aviso = await _carregando(context, chat_id, "🔴 Contatando o rover Curiosity em Marte...", ChatAction.UPLOAD_PHOTO)
    try:
        foto = await nasa_api.buscar_foto_marte()
    except NasaAPIError as erro:
        await _apagar(aviso)
        await _enviar_erro(context, chat_id, str(erro))
        return
    titulo, _ = await tradutor.traduzir(foto["titulo"])
    await _apagar(aviso)

    legenda = (
        f"🔴 <b>{escape(_resumir(titulo, 200))}</b>\n\n"
        f"🤖 Rover: Curiosity\n"
        f"📷 Câmera: {escape(foto['camera'])}\n"
        f"🌍 Data terrestre: {escape(foto['data_terrestre'])}\n"
        f"☀️ Sol marciano: {escape(foto['sol'])}\n"
        f"🛰️ Fonte: {escape(foto['fonte'])}\n\n"
        f"<i>Um “sol” é um dia marciano, com cerca de 24h39min.</i>"
    )
    teclado = keyboards.apos_acao(keyboards.MARTE, "🔴 Outra foto")
    if not await _enviar_foto(context, chat_id, foto["urls_imagem"], legenda, teclado):
        link = next((u for u in foto["urls_imagem"] if u), "")
        await _enviar_texto(
            context, chat_id,
            legenda + f"\n\n🖼️ A imagem não pôde ser exibida. Link: {escape(link)}",
            teclado,
        )


async def marte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/marte — foto real de Marte."""
    await enviar_marte(context, update.effective_chat.id)


# ---------------------------------------------------------------------------
# Asteroides
# ---------------------------------------------------------------------------
def _formatar_asteroide(posicao, a):
    """Monta o bloco de texto de um asteroide."""
    alerta = "🔴 <b>SIM</b> — potencialmente perigoso" if a["perigoso"] else "🟢 Não"
    return (
        f"<b>{posicao}. ☄️ {escape(a['nome'])}</b>\n"
        f"   📏 Diâmetro estimado: {_numero(a['diametro_min_m'])} – {_numero(a['diametro_max_m'])} m\n"
        f"   💨 Velocidade relativa: {_numero(a['velocidade_kmh'])} km/h\n"
        f"   📍 Distância: {_numero(a['distancia_km'])} km "
        f"({_numero(a['distancia_lunar'], 1)}× a distância Terra–Lua)\n"
        f"   ⚠️ Perigoso: {alerta}\n"
    )


async def enviar_asteroides(context, chat_id):
    aviso = await _carregando(context, chat_id, "☄️ Varrendo o céu em busca de asteroides...")
    try:
        dados = await nasa_api.buscar_asteroides()
    except NasaAPIError as erro:
        await _apagar(aviso)
        await _enviar_erro(context, chat_id, str(erro))
        return
    await _apagar(aviso)

    texto = (
        f"🛰️ <b>Monitoramento de Asteroides — {dados['data']}</b>\n\n"
        f"🔢 Objetos próximos da Terra hoje: <b>{dados['total']}</b>\n"
        f"⚠️ Potencialmente perigosos: <b>{dados['perigosos']}</b>\n\n"
        f"📋 <b>Os {len(dados['lista'])} mais próximos:</b>\n\n"
    )
    for posicao, asteroide in enumerate(dados["lista"], start=1):
        texto += _formatar_asteroide(posicao, asteroide) + "\n"
    texto += (
        "<i>ℹ️ \"Potencialmente perigoso\" é uma classificação técnica da NASA "
        "para objetos grandes com órbitas próximas — não significa risco de colisão.</i>"
    )
    await _enviar_texto(context, chat_id, texto, keyboards.apos_acao(keyboards.ASTEROIDES, "🔄 Atualizar"))


async def asteroides(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/asteroides — asteroides próximos da Terra."""
    await enviar_asteroides(context, update.effective_chat.id)


# ---------------------------------------------------------------------------
# Curiosidade
# ---------------------------------------------------------------------------
async def _curiosidade_asteroides():
    """Gera uma curiosidade a partir dos dados reais de asteroides de hoje."""
    dados = await nasa_api.buscar_asteroides()
    proximo = dados["lista"][0]
    maior = dados["maior"]
    rapido = dados["mais_rapido"]
    return (
        "💡 <b>Você sabia?</b>\n\n"
        f"☄️ Hoje, <b>{dados['total']}</b> asteroides passam perto da Terra!\n\n"
        f"📍 O mais próximo, <b>{escape(proximo['nome'])}</b>, passa a "
        f"{_numero(proximo['distancia_lunar'], 1)} vezes a distância entre a Terra e a Lua.\n"
        f"📏 O maior, <b>{escape(maior['nome'])}</b>, pode ter até "
        f"{_numero(maior['diametro_max_m'])} metros — cerca de "
        f"{_numero(maior['diametro_max_m'] / 105, 1)} campos de futebol enfileirados.\n"
        f"💨 O mais veloz, <b>{escape(rapido['nome'])}</b>, viaja a "
        f"{_numero(rapido['velocidade_kmh'])} km/h!"
    )


async def enviar_curiosidade(context, chat_id):
    """Sorteia entre uma curiosidade de asteroides ou uma APOD histórica."""
    aviso = await _carregando(context, chat_id, "💡 Consultando os arquivos da NASA...")
    teclado = keyboards.apos_acao(keyboards.CURIOSIDADE, "💡 Outra curiosidade")
    usar_asteroides = random.choice([True, False])
    try:
        if not usar_asteroides:
            try:
                apod_dados = await nasa_api.buscar_apod_aleatoria()
            except NasaAPIError:
                usar_asteroides = True  # APOD fora do ar: usa a outra fonte
        if usar_asteroides:
            texto = await _curiosidade_asteroides()
            await _apagar(aviso)
            await _enviar_texto(context, chat_id, texto, teclado)
            return
    except NasaAPIError as erro:
        await _apagar(aviso)
        await _enviar_erro(context, chat_id, str(erro))
        return
    await _apagar(aviso)

    # Usa apenas as duas primeiras frases da explicação como "curiosidade"
    frases = apod_dados["explicacao"].split(". ")
    trecho = ". ".join(frases[:2]).strip()
    if not trecho.endswith("."):
        trecho += "."
    trecho, _ = await tradutor.traduzir(trecho)
    titulo, _ = await tradutor.traduzir(apod_dados["titulo"])
    texto = (
        "💡 <b>Você sabia?</b>\n\n"
        f"Em <b>{escape(apod_dados['data'])}</b>, a NASA destacou:\n"
        f"🌠 <b>{escape(_resumir(titulo, 200))}</b>\n\n"
        f"<i>{escape(_resumir(trecho, 700))}</i>"
    )
    if apod_dados["tipo_midia"] != "image" or not await _enviar_foto(
        context, chat_id, apod_dados["urls_imagem"], texto, teclado
    ):
        await _enviar_texto(context, chat_id, texto + f"\n\n🔗 {escape(apod_dados['url'])}", teclado)


async def curiosidade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/curiosidade — curiosidade astronômica com dados reais."""
    await enviar_curiosidade(context, update.effective_chat.id)


# ---------------------------------------------------------------------------
# Botões e mensagens de texto
# ---------------------------------------------------------------------------
async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o clique em qualquer botão inline e direciona para a função certa."""
    consulta = update.callback_query
    try:
        await consulta.answer()  # remove o "reloginho" do botão
    except TelegramError:
        pass

    chat_id = update.effective_chat.id
    escolha = consulta.data
    context.user_data["aguardando_data"] = False

    if escolha == keyboards.APOD_HOJE:
        await enviar_apod(context, chat_id)
    elif escolha == keyboards.APOD_ALEATORIA:
        await enviar_apod(context, chat_id, aleatoria=True)
    elif escolha == keyboards.APOD_DATA:
        await pedir_data_apod(context, chat_id)
    elif escolha == keyboards.MARTE:
        await enviar_marte(context, chat_id)
    elif escolha == keyboards.ASTEROIDES:
        await enviar_asteroides(context, chat_id)
    elif escolha == keyboards.CURIOSIDADE:
        await enviar_curiosidade(context, chat_id)
    elif escolha == keyboards.AJUDA:
        await _enviar_texto(context, chat_id, TEXTO_AJUDA, keyboards.voltar_menu())
    else:  # keyboards.MENU ou qualquer valor desconhecido
        await mostrar_menu(context, chat_id)


async def receber_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Trata mensagens de texto comuns. Se o usuário clicou em
    "APOD por data", a mensagem é interpretada como a data desejada.
    """
    chat_id = update.effective_chat.id
    if context.user_data.get("aguardando_data"):
        try:
            data = nasa_api.validar_data_apod(update.message.text)
        except ValueError as erro:
            await _enviar_erro(context, chat_id, f"{erro}\n\nTente novamente:", keyboards.voltar_menu())
            return  # continua aguardando uma data válida
        context.user_data["aguardando_data"] = False
        await enviar_apod(context, chat_id, data)
    else:
        await update.message.reply_text(
            "🤔 Não entendi... Use o menu abaixo ou digite /ajuda.",
            reply_markup=keyboards.menu_principal(),
        )


# ---------------------------------------------------------------------------
# Tratamento global de erros
# ---------------------------------------------------------------------------
async def tratar_erro(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Último nível de proteção: qualquer exceção não tratada chega aqui.
    O erro é registrado no log e o usuário recebe um aviso — o bot continua rodando.
    """
    logger.error("Erro não tratado durante uma atualização", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        await _enviar_erro(context, update.effective_chat.id, "😵 Algo inesperado aconteceu.")
