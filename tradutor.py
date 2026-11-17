"""
tradutor.py — Tradução dos textos da NASA para o português.

Responsabilidade: traduzir títulos e explicações (que a NASA fornece em
inglês) usando a biblioteca deep-translator (Google Tradutor, sem chave).
Se a tradução falhar, o texto original em inglês é devolvido, para que
o bot nunca deixe de responder por causa disso.
"""

import asyncio
import logging

from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

LIMITE_CARACTERES = 4900  # o serviço aceita no máximo 5000 caracteres por vez


def _traduzir_sincrono(texto):
    return GoogleTranslator(source="en", target="pt").translate(texto[:LIMITE_CARACTERES])


async def traduzir(texto):
    """
    Traduz um texto do inglês para o português.
    Devolve uma tupla (texto, foi_traduzido).
    """
    if not texto or not texto.strip():
        return texto, False
    try:
        # A biblioteca é síncrona; to_thread evita travar o bot durante a tradução
        traducao = await asyncio.to_thread(_traduzir_sincrono, texto)
        if traducao:
            return traducao, True
    except Exception as erro:  # sem internet, serviço fora do ar, limite atingido...
        logger.warning("Falha na tradução: %s", erro)
    return texto, False
