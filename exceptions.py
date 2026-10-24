"""Jerarquía de errores del scraper (permite mensajes y códigos de salida claros)."""


class ScraperError(Exception):
    """Error genérico del scraper."""


class CookieError(ScraperError):
    """El archivo de cookies no existe, está mal formado o incompleto."""


class SessionExpiredError(ScraperError):
    """Las cookies ya no son válidas: Instagram pide iniciar sesión."""


class ChallengeRequiredError(SessionExpiredError):
    """Instagram exige un checkpoint/verificación manual de la cuenta."""


class RateLimitError(ScraperError):
    """Instagram respondió con HTTP 429 o con un aviso de 'espera unos minutos'."""


class ProfileNotFoundError(ScraperError):
    """El perfil no existe o no está disponible."""


# --- Errores del análisis con Gemini (analyze.py) ------------------------------
class AnalysisError(Exception):
    """Error genérico del análisis de personalidad."""


class MissingApiKeyError(AnalysisError):
    """No hay GEMINI_API_KEY en el .env ni en las variables de entorno."""


class InputDataError(AnalysisError):
    """output.json no existe, no es válido o no tiene datos suficientes."""


class GeminiRateLimitError(AnalysisError):
    """Gemini respondió 429 (límite de uso) incluso tras los reintentos."""


class GeminiAPIError(AnalysisError):
    """Error de la API de Gemini: key inválida, modelo inexistente, servidor caído..."""


class InvalidResponseError(AnalysisError):
    """La respuesta de Gemini está vacía o no cumple el esquema JSON pedido."""
