"""Comunicación con Gemini usando el SDK oficial ``google-genai`` (Interactions API).

* La API key se lee del archivo .env (variable GEMINI_API_KEY), nunca del código.
* Reintenta con espera exponencial ante 429 (límite de uso) y errores 5xx.
* Valida la respuesta con Pydantic; si no cumple el esquema, reintenta una vez.
"""
from __future__ import annotations

import logging
import os
import random
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai._gaos.utils import RetryConfig
from pydantic import ValidationError

import config
from analysis.models import AnalisisPersonalidad
from analysis.prompt import INSTRUCCIONES_SISTEMA
from exceptions import (
    GeminiAPIError,
    GeminiRateLimitError,
    InvalidResponseError,
    MissingApiKeyError,
)

log = logging.getLogger(__name__)

_ESTADOS_TEMPORALES = {500, 502, 503, 504}  # el servidor está saturado: vale la pena reintentar


def cargar_configuracion() -> tuple[str, str]:
    """Lee GEMINI_API_KEY y GEMINI_MODEL del .env. Devuelve (api_key, modelo)."""
    load_dotenv(config.ENV_PATH)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    # El texto de plantilla cuenta como "sin key": así no se envían datos con una key falsa.
    if not api_key or api_key.startswith("PEGA_AQUI"):
        raise MissingApiKeyError(
            f"Falta GEMINI_API_KEY. Copia .env.example como .env en {config.BASE_DIR} "
            "y pega tu API key de Google AI Studio."
        )
    modelo = os.getenv("GEMINI_MODEL", "").strip() or config.GEMINI_MODEL_DEFAULT
    return api_key, modelo


def analizar(prompt: str, api_key: str, modelo: str) -> AnalisisPersonalidad:
    """Envía el prompt a Gemini y devuelve la respuesta ya validada."""
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=config.GEMINI_TIMEOUT_S * 1000,  # el SDK espera milisegundos
        ),
    )
    # Sin reintentos internos del SDK (son silenciosos): los hace _llamar_con_reintentos.
    # La API de interacciones ignora HttpRetryOptions(attempts=0) y reintenta igual,
    # así que se desactivan directamente en su configuración.
    client.interactions.sdk_configuration.retry_config = RetryConfig("none", None, False)
    intentos_formato = 0
    while True:
        texto = _llamar_con_reintentos(client, prompt, modelo)
        try:
            return AnalisisPersonalidad.model_validate_json(texto)
        except ValidationError as exc:
            intentos_formato += 1
            if intentos_formato > config.GEMINI_FORMAT_RETRIES:
                raise InvalidResponseError(
                    f"La respuesta de Gemini no cumple el esquema:\n{exc}"
                ) from exc
            log.warning("Respuesta con formato inválido; se pide de nuevo.")


def _llamar_con_reintentos(client: genai.Client, prompt: str, modelo: str) -> str:
    for intento in range(config.GEMINI_MAX_RETRIES + 1):
        try:
            log.info("Enviando a Gemini (modelo %s, razonamiento %s), puede tardar hasta %d s...",
                     modelo, config.GEMINI_THINKING_LEVEL, config.GEMINI_TIMEOUT_S)
            inicio = time.monotonic()
            interaction = client.interactions.create(
                model=modelo,
                system_instruction=INSTRUCCIONES_SISTEMA,
                input=prompt,
                # Salida estructurada: Gemini debe responder JSON con este esquema.
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": AnalisisPersonalidad.model_json_schema(),
                },
                generation_config={
                    "temperature": config.GEMINI_TEMPERATURE,
                    "thinking_level": config.GEMINI_THINKING_LEVEL,
                },
                store=False,  # no guardar la conversación en los servidores de Google
            )
        except Exception as exc:  # el SDK usa varias clases de error; se clasifican por código
            estado = _codigo_http(exc)
            temporal = estado == 429 or estado in _ESTADOS_TEMPORALES or _es_error_de_red(exc)
            if not temporal:
                raise GeminiAPIError(_mensaje_error(estado, exc)) from exc
            if intento == config.GEMINI_MAX_RETRIES:
                if estado == 429:
                    raise GeminiRateLimitError(
                        "Gemini respondió 429 (límite de uso) tras "
                        f"{config.GEMINI_MAX_RETRIES} reintentos. Espera unos minutos o "
                        "revisa tus límites en https://aistudio.google.com/rate-limit"
                    ) from exc
                raise GeminiAPIError(_mensaje_error(estado, exc)) from exc
            espera = config.GEMINI_RETRY_BASE_S * 2 ** intento + random.uniform(0, 3)
            log.warning("Error temporal (%s). Reintento %d/%d en %.0f s...",
                        estado or type(exc).__name__, intento + 1,
                        config.GEMINI_MAX_RETRIES, espera)
            time.sleep(espera)
            continue

        log.info("Respuesta de Gemini recibida en %.0f s.", time.monotonic() - inicio)
        texto = (interaction.output_text or "").strip()
        if not texto:
            # Sin texto: normalmente la respuesta fue bloqueada por filtros de seguridad.
            raise InvalidResponseError(
                f"Gemini devolvió una respuesta vacía (estado: {interaction.status})."
            )
        return texto
    raise AssertionError("inalcanzable")


def _codigo_http(exc: Exception) -> int | None:
    """Código HTTP del error, sin depender de las clases internas del SDK."""
    for atributo in ("status_code", "code"):
        valor = getattr(exc, atributo, None)
        if isinstance(valor, int):
            return valor
    return None


def _es_error_de_red(exc: Exception) -> bool:
    nombre = type(exc).__name__
    return "Connection" in nombre or "Timeout" in nombre


def _mensaje_error(estado: int | None, exc: Exception) -> str:
    detalle = getattr(exc, "message", None) or str(exc)
    if estado in (400, 401, 403) and "api key" in detalle.lower():
        return "La API key no es válida. Revisa GEMINI_API_KEY en el archivo .env."
    if estado == 404:
        return f"Modelo no encontrado. Revisa GEMINI_MODEL en el .env. Detalle: {detalle}"
    return f"Error de la API de Gemini (HTTP {estado or '?'}): {detalle}"
