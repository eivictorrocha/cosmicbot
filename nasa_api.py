"""
nasa_api.py — Comunicação com as APIs da NASA.

Responsabilidade: fazer as requisições HTTP, tratar os erros de rede/HTTP,
ler o JSON retornado e devolver dicionários simples, já organizados,
para que o arquivo handlers.py só precise montar as mensagens.
"""

import logging
import random
import re
from datetime import date, datetime, timedelta
from html import unescape

import httpx

import config

logger = logging.getLogger(__name__)


class NasaAPIError(Exception):
    """
    Erro "amigável" da integração com a NASA.
    A mensagem (str do erro) já está pronta para ser mostrada ao usuário.
    O atributo `status` guarda o código HTTP, quando existir.
    """

    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


# ---------------------------------------------------------------------------
# Função base de requisição
# ---------------------------------------------------------------------------
async def _requisitar(url, params=None, usar_chave=True):
    """
    Faz uma requisição GET e devolve o JSON já convertido em dict/list.

    Trata: falha de conexão, tempo esgotado, erros HTTP (incluindo o
    limite de requisições 429) e respostas que não são JSON válido.
    """
    parametros = dict(params or {})
    if usar_chave:
        parametros["api_key"] = config.NASA_API_KEY

    try:
        async with httpx.AsyncClient(
            timeout=config.TEMPO_LIMITE_SEGUNDOS, follow_redirects=True
        ) as cliente:
            resposta = await cliente.get(url, params=parametros)
    except httpx.TimeoutException:
        raise NasaAPIError("⏳ A NASA demorou demais para responder. Tente novamente em instantes.")
    except httpx.RequestError:
        # Não registramos a URL completa porque ela contém a api_key.
        logger.warning("Falha de conexão ao acessar %s", url)
        raise NasaAPIError("📡 Não consegui me conectar à NASA. Verifique a internet e tente de novo.")

    status = resposta.status_code
    if status != 200:
        logger.warning("NASA respondeu com status HTTP %s (%s)", status, url)

    # Estruturas condicionais para cada tipo de erro HTTP
    if status == 429:
        raise NasaAPIError(
            "🚦 Limite de consultas à NASA atingido. Aguarde alguns minutos e tente novamente.",
            status,
        )
    if status in (401, 403):
        raise NasaAPIError("🔑 A chave da API da NASA foi recusada. Verifique o arquivo .env.", status)
    if status == 404:
        raise NasaAPIError("🔍 A NASA não encontrou dados para essa consulta.", status)
    if status == 400:
        raise NasaAPIError("⚠️ A NASA considerou a consulta inválida (verifique a data informada).", status)
    if status >= 500:
        raise NasaAPIError("🛠️ O serviço da NASA está indisponível no momento. Tente mais tarde.", status)
    if status != 200:
        raise NasaAPIError(f"⚠️ Erro inesperado da NASA (HTTP {status}).", status)

    # Manipulação do JSON
    try:
        return resposta.json()
    except ValueError:
        logger.warning("Resposta não-JSON recebida de %s", url)
        raise NasaAPIError("🧩 A NASA enviou uma resposta em formato inválido. Tente novamente.")


# ---------------------------------------------------------------------------
# APOD — Astronomy Picture of the Day
# ---------------------------------------------------------------------------
# Formatos de data aceitos: o padrão brasileiro e o padrão da NASA
FORMATOS_DATA = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")


def validar_data_apod(texto):
    """
    Converte o texto digitado (ex.: '20/07/2024' ou '2024-07-20') em um
    objeto date e verifica se está dentro do intervalo aceito pela APOD.
    Lança ValueError com mensagem amigável quando a data é inválida.
    """
    data = None
    for formato in FORMATOS_DATA:
        try:
            data = datetime.strptime(texto.strip(), formato).date()
            break
        except ValueError:
            continue  # tenta o próximo formato
    if data is None:
        raise ValueError("📅 Data inválida! Use o formato DD/MM/AAAA, por exemplo: 20/07/2024")

    hoje = date.today()
    if data < config.APOD_DATA_MINIMA:
        raise ValueError("📅 A primeira foto da APOD é de 16/06/1995. Escolha uma data a partir dela.")
    if data > hoje:
        raise ValueError("🔮 Ainda não consigo ver o futuro! Escolha uma data até hoje.")
    return data


def _apod_incompleta(dados):
    """
    Algumas datas da APOD voltam com a página genérica do site da NASA
    (título "NASA Science", logo da NASA e o slogan "Discover the cosmos!")
    em vez da foto real. Esta função identifica esse caso.
    """
    titulo = (dados.get("title") or "").strip().lower()
    explicacao = (dados.get("explanation") or "").strip().lower()
    return titulo in ("nasa science", "") or explicacao.startswith("discover the cosmos")


def _organizar_apod(dados):
    """Extrai do JSON da APOD apenas os campos que o bot utiliza."""
    tipo = dados.get("media_type", "image")
    # hdurl é a versão em alta resolução; pode ser grande demais para o Telegram,
    # por isso guardamos as duas e tentamos primeiro a versão normal.
    urls_imagem = []
    if tipo == "image":
        for chave in ("url", "hdurl"):
            if dados.get(chave):
                urls_imagem.append(dados[chave])

    return {
        "titulo": dados.get("title", "Sem título"),
        "data": dados.get("date", ""),
        "explicacao": dados.get("explanation", "Explicação não disponível."),
        "tipo_midia": tipo,
        "urls_imagem": urls_imagem,
        "url": dados.get("url") or dados.get("thumbnail_url") or "",
        "credito": (dados.get("copyright") or "").replace("\n", " ").strip(),
    }


async def _consultar_apod(params):
    """
    Consulta a APOD. Se a NASA responder com erro interno (5xx), tenta
    mais uma vez sem o parâmetro opcional "thumbs" antes de desistir.
    """
    try:
        return await _requisitar(config.APOD_URL, params)
    except NasaAPIError as erro:
        if erro.status and erro.status >= 500:
            logger.info("APOD respondeu %s; tentando novamente.", erro.status)
            params = {k: v for k, v in params.items() if k != "thumbs"}
            return await _requisitar(config.APOD_URL, params)
        raise


async def _buscar_apod_legado(data=None):
    """
    API antiga (api.nasa.gov/planetary/apod). Desde a mudança da APOD para
    science.nasa.gov, ela costuma devolver só o logo da NASA — por isso é
    usada apenas como reserva.
    """
    params = {"thumbs": "true"}
    if data:
        params["date"] = data.isoformat()
    dados = await _consultar_apod(params)
    if not isinstance(dados, dict) or "title" not in dados or _apod_incompleta(dados):
        raise NasaAPIError("🛰️ A NASA devolveu dados incompletos para essa data.")
    return _organizar_apod(dados)


# --- Nova fonte: science.nasa.gov ------------------------------------------
def _limpar_html(texto):
    """Remove tags HTML e converte entidades (&amp; etc.) em texto simples."""
    if isinstance(texto, dict):  # o WordPress às vezes envia {"rendered": "..."}
        texto = texto.get("rendered", "")
    texto = re.sub(r"<br\s*/?>", "\n", str(texto or ""), flags=re.IGNORECASE)
    texto = unescape(re.sub(r"<[^>]+>", "", texto))
    texto = re.sub(r"[ \t\r]+", " ", texto)
    return re.sub(r"\n\s*\n+", "\n\n", texto).strip()


def _url_absoluta(url):
    url = unescape(url.strip())
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://science.nasa.gov" + url
    return url


def _organizar_apod_nova(item, data_pedida=None):
    """Converte um registro de science.nasa.gov para o formato usado pelo bot."""
    html_basico = item.get("basic_html") or ""
    if isinstance(html_basico, dict):
        html_basico = html_basico.get("rendered", "")
    # A mídia real fica no primeiro bloco <center> do basic_html
    bloco = re.search(r"<center>(.*?)</center>", html_basico, re.IGNORECASE | re.DOTALL)
    bloco = bloco.group(1) if bloco else html_basico

    # Procura vídeo (YouTube/Vimeo) e imagens dentro do HTML
    video = re.search(r'src="([^"]*(?:youtube|youtu\.be|vimeo)[^"]*)"', bloco, re.IGNORECASE)
    imagens = re.findall(r'(?:href|src)="([^"]+\.(?:jpe?g|png|gif)[^"]*)"', bloco, re.IGNORECASE)

    candidatas = []
    hdurl = item.get("hdurl") or ""
    for url in imagens + ([hdurl] if hdurl else []):
        url = _url_absoluta(url)
        base = url.split("?")[0]
        if "logo" in base.lower():
            continue  # descarta o logo da NASA
        # versão reduzida primeiro (o Telegram recusa fotos muito grandes)
        for opcao in (base + "?w=1280", base):
            if opcao not in candidatas:
                candidatas.append(opcao)

    tipo = "video" if (video or item.get("media_type") == "video") else "image"
    link_pagina = item.get("link") or item.get("url") or ""

    explicacao = _limpar_html(item.get("explanation", ""))
    explicacao = re.sub(r"^\s*Explanation:\s*", "", explicacao, flags=re.IGNORECASE)
    explicacao = re.split(r"Tomorrow'?s picture", explicacao, flags=re.IGNORECASE)[0].strip()

    credito = _limpar_html(item.get("copyright") or item.get("credit") or "")
    credito = re.sub(r"^.*?(Credit|Copyright)[^:]*:\s*", "", credito, flags=re.IGNORECASE).strip()

    dia = str(item.get("date", ""))[:10] or (data_pedida.isoformat() if data_pedida else "")

    resultado = {
        "titulo": _limpar_html(item.get("title", "")),
        "data": dia,
        "explicacao": explicacao or "Explicação não disponível.",
        "tipo_midia": tipo,
        "urls_imagem": candidatas[:4] if tipo == "image" else [],
        "url": _url_absoluta(video.group(1)).replace("/embed/", "/watch?v=") if video else link_pagina,
        "credito": credito,
    }
    if not resultado["titulo"] or resultado["titulo"].lower() == "nasa science" or (
        tipo == "image" and not candidatas
    ):
        logger.warning("Formato inesperado da APOD nova. Campos recebidos: %s", list(item.keys()))
        raise NasaAPIError("🛰️ A NASA devolveu dados incompletos para essa data.")
    return resultado


async def _buscar_apod_nova(data=None):
    """
    Consulta a APOD em science.nasa.gov.
    - Sem data: a mais recente (?per_page=1)
    - Com data: /apod-basic/AAMMDD (ex.: 20/07/2024 -> 240720)
    """
    if data:
        dados = await _requisitar(f"{config.APOD_NOVA_URL}/{data.strftime('%y%m%d')}", usar_chave=False)
    else:
        dados = await _requisitar(config.APOD_NOVA_URL, {"per_page": 1}, usar_chave=False)
    if isinstance(dados, list):
        dados = dados[0] if dados else None
    if not isinstance(dados, dict):
        raise NasaAPIError("🔍 A NASA não publicou foto nessa data.")
    return _organizar_apod_nova(dados, data)


async def buscar_apod(data=None):
    """
    Busca a APOD de hoje (data=None) ou de uma data específica.
    Usa a nova fonte da NASA e, se ela falhar, tenta a API antiga.
    """
    try:
        return await _buscar_apod_nova(data)
    except NasaAPIError as erro_principal:
        logger.info("Fonte nova da APOD falhou (%s); tentando a API antiga.", erro_principal.status)
        try:
            return await _buscar_apod_legado(data)
        except NasaAPIError:
            raise erro_principal  # mostra ao usuário o erro da fonte principal


async def buscar_apod_aleatoria():
    """Sorteia uma data entre 16/06/1995 e hoje e busca a APOD dela."""
    dias_totais = (date.today() - config.APOD_DATA_MINIMA).days
    ultimo_erro = None
    for _ in range(4):  # algumas datas não têm foto; tenta outras
        sorteada = config.APOD_DATA_MINIMA + timedelta(days=random.randint(0, dias_totais))
        try:
            return await _buscar_apod_nova(sorteada)
        except NasaAPIError as erro:
            ultimo_erro = erro
            if erro.status == 429:
                break  # limite atingido: não adianta insistir
    # Reserva: API antiga, pedindo várias e descartando as incompletas
    try:
        dados = await _consultar_apod({"count": 5, "thumbs": "true"})
        for item in dados if isinstance(dados, list) else []:
            if isinstance(item, dict) and not _apod_incompleta(item):
                return _organizar_apod(item)
    except NasaAPIError:
        pass
    raise ultimo_erro or NasaAPIError("🛰️ Não consegui uma APOD aleatória agora. Tente novamente.")


# ---------------------------------------------------------------------------
# Marte — fotos do rover Curiosity
# ---------------------------------------------------------------------------
async def _buscar_marte_rover_photos():
    """
    Consulta o endpoint Mars Rover Photos (rover Curiosity) em sóis sorteados.
    Tenta até 3 sóis diferentes, pois em alguns dias o rover não fotografa.
    """
    for _ in range(3):
        sol = random.randint(1, config.SOL_MAXIMO_CURIOSITY)
        dados = await _requisitar(config.MARS_PHOTOS_URL, {"sol": sol})
        fotos = dados.get("photos", []) if isinstance(dados, dict) else []
        if fotos:
            foto = random.choice(fotos)
            camera = foto.get("camera", {})
            return {
                "urls_imagem": [foto.get("img_src", "").replace("http://", "https://")],
                "camera": f"{camera.get('full_name', 'Desconhecida')} ({camera.get('name', '?')})",
                "data_terrestre": foto.get("earth_date", "Não informada"),
                "sol": str(foto.get("sol", sol)),
                "titulo": "Superfície de Marte vista pelo Curiosity",
                "fonte": "NASA Mars Rover Photos API",
            }
    raise NasaAPIError("🔍 Nenhuma foto encontrada nos sóis consultados.")


# Palavras que indicam ilustração, logo ou imagem que não é foto de Marte
PALAVRAS_EXCLUIDAS = ("artist", "concept", "illustration", "logo", "animation",
                      "rendering", "model", "test", "earth", "launch", "clean room")


def _eh_foto_de_marte(item):
    """Verifica se um item da biblioteca é uma foto real tirada em Marte."""
    info = item["data"][0]
    texto = (info.get("title", "") + " " + " ".join(info.get("keywords", []))).lower()
    eh_fotojornal = info.get("nasa_id", "").startswith("PIA")  # imagens oficiais do JPL
    return eh_fotojornal and not any(palavra in texto for palavra in PALAVRAS_EXCLUIDAS)


async def _buscar_marte_biblioteca_nasa():
    """
    Alternativa: Biblioteca de Imagens e Vídeos da NASA (images-api.nasa.gov),
    filtrando fotos reais do Curiosity. Usada quando o endpoint Mars Rover
    Photos estiver fora do ar (ele foi arquivado pela NASA).
    """
    dados = await _requisitar(
        config.NASA_IMAGES_URL,
        {"q": "Curiosity rover Mars", "media_type": "image", "year_start": "2012"},
        usar_chave=False,  # esta API não exige chave
    )
    itens = dados.get("collection", {}).get("items", []) if isinstance(dados, dict) else []
    itens = [i for i in itens if i.get("links") and i.get("data")]
    fotos = [i for i in itens if _eh_foto_de_marte(i)]
    if not fotos:
        raise NasaAPIError("🔍 Não encontrei fotos de Marte no momento. Tente novamente.")

    item = random.choice(fotos)
    info = item["data"][0]
    miniatura = item["links"][0].get("href", "")
    titulo = info.get("title", "Marte")
    texto_busca = f"{titulo} {info.get('description', '')}"

    # Tenta descobrir o sol e a câmera a partir do texto da NASA (expressões regulares)
    sol = re.search(r"[Ss]ol\s+(\d+)", texto_busca)
    camera = re.search(r"(Mastcam|MAHLI|Navcam|Hazcam|ChemCam|MARDI)", texto_busca, re.IGNORECASE)

    return {
        # versão média primeiro (melhor qualidade); a miniatura serve de reserva
        "urls_imagem": [re.sub(r"~(thumb|small)\.", "~medium.", miniatura), miniatura],
        "camera": camera.group(1) if camera else "Não informada pela fonte",
        "data_terrestre": info.get("date_created", "")[:10] or "Não informada",
        "sol": sol.group(1) if sol else "Não informado pela fonte",
        "titulo": titulo,
        "fonte": "NASA Image and Video Library",
    }


async def buscar_foto_marte():
    """Busca uma foto real de Marte, usando a fonte alternativa se necessário."""
    try:
        return await _buscar_marte_rover_photos()
    except NasaAPIError as erro:
        logger.info("Mars Rover Photos indisponível (%s). Usando a biblioteca de imagens.", erro.status)
        return await _buscar_marte_biblioteca_nasa()


# ---------------------------------------------------------------------------
# Asteroides — NeoWs (Near Earth Object Web Service)
# ---------------------------------------------------------------------------
async def buscar_asteroides(dia=None):
    """
    Consulta os asteroides que passam perto da Terra no dia informado
    (padrão: hoje). Devolve o total e a lista dos mais próximos.
    """
    dia = dia or date.today()
    dados = await _requisitar(
        config.NEO_FEED_URL,
        {"start_date": dia.isoformat(), "end_date": dia.isoformat()},
    )

    objetos_por_dia = dados.get("near_earth_objects", {}) if isinstance(dados, dict) else {}
    lista_bruta = [obj for lista in objetos_por_dia.values() for obj in lista]
    if not lista_bruta:
        raise NasaAPIError("🔭 Nenhum asteroide próximo foi registrado para hoje.")

    asteroides = []
    for obj in lista_bruta:
        aproximacoes = obj.get("close_approach_data") or []
        if not aproximacoes:
            continue  # sem dados de aproximação, não há o que mostrar
        aprox = aproximacoes[0]
        diametro = obj.get("estimated_diameter", {}).get("meters", {})
        nome = obj.get("name", "Desconhecido")
        if nome.startswith("(") and nome.endswith(")"):
            nome = nome[1:-1]  # "(2024 AB)" -> "2024 AB"
        asteroides.append({
            "nome": nome,
            "diametro_min_m": float(diametro.get("estimated_diameter_min", 0)),
            "diametro_max_m": float(diametro.get("estimated_diameter_max", 0)),
            "velocidade_kmh": float(aprox.get("relative_velocity", {}).get("kilometers_per_hour", 0)),
            "distancia_km": float(aprox.get("miss_distance", {}).get("kilometers", 0)),
            "distancia_lunar": float(aprox.get("miss_distance", {}).get("lunar", 0)),
            "perigoso": bool(obj.get("is_potentially_hazardous_asteroid", False)),
            "horario": aprox.get("close_approach_date_full", aprox.get("close_approach_date", "")),
        })

    if not asteroides:
        raise NasaAPIError("🔭 A NASA não informou dados de aproximação para hoje.")

    asteroides.sort(key=lambda a: a["distancia_km"])  # mais próximos primeiro
    return {
        "data": dia.strftime("%d/%m/%Y"),
        "total": dados.get("element_count", len(asteroides)),
        "perigosos": sum(1 for a in asteroides if a["perigoso"]),
        "lista": asteroides[: config.MAX_ASTEROIDES_EXIBIDOS],
        "maior": max(asteroides, key=lambda a: a["diametro_max_m"]),
        "mais_rapido": max(asteroides, key=lambda a: a["velocidade_kmh"]),
    }
