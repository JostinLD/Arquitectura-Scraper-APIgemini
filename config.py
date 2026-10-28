"""Configuración central del scraper: rutas, tiempos, navegador y stealth."""
from __future__ import annotations

from pathlib import Path

# --- Rutas -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
COOKIES_PATH = BASE_DIR / "cookies.json"
OUTPUT_PATH = BASE_DIR / "output.json"

DEBUG_DIR = BASE_DIR / "debug"  # capturas cuando Instagram pide login/checkpoint

# --- Objetivo ----------------------------------------------------------------
# Perfil a extraer cuando se ejecuta `python main.py` sin argumentos (o con
# "Run" del editor). Acepta "usuario", "@usuario" o la URL completa del perfil.
TARGET_PROFILE = "https://www.instagram.com/cris.estefi/"

# --- Instagram ---------------------------------------------------------------
# URL base del sitio: NO poner aquí un perfil (se usa para construir todas las URLs).
INSTAGRAM_URL = "https://www.instagram.com"
# App ID público que usa la web de Instagram en la cabecera X-IG-App-ID.
IG_APP_ID = "936619743392459"
MAX_POSTS = 20
MAX_PREVIEW_COMMENTS = 5  # comentarios de vista previa guardados por post

# Fragmentos de URL cuyas respuestas JSON se interceptan.
API_URL_PATTERNS = (
    "/api/v1/users/web_profile_info/",
    "/api/v1/feed/user/",
    "/graphql/query",
    "/api/graphql",
)

# --- Navegador ---------------------------------------------------------------
HEADLESS = False
# "chrome" usa el Google Chrome instalado (huella más realista). Si no está,
# se usa el Chromium que trae Playwright. None = usar siempre Chromium.
BROWSER_CHANNEL: str | None = "chrome"

# Si se deja vacío, el User-Agent se construye con la versión REAL del
# navegador lanzado, para que coincida con navigator.userAgentData.
USER_AGENT = ""
USER_AGENT_TEMPLATE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "es-ES"
TIMEZONE_ID = "America/Guayaquil"
ACCEPT_LANGUAGE = "es-ES,es;q=0.9,en;q=0.8"

CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    f"--window-size={VIEWPORT['width']},{VIEWPORT['height']}",
]
# Evita la barra "Chrome está siendo controlado por software automatizado".
IGNORE_DEFAULT_ARGS = ["--enable-automation"]

# Script inyectado antes de cualquier script de la página.
STEALTH_INIT_SCRIPT = """
Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined });
if (!window.chrome) { window.chrome = { runtime: {} }; }
const _origQuery = window.navigator.permissions && window.navigator.permissions.query;
if (_origQuery) {
  window.navigator.permissions.query = (params) =>
    params && params.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : _origQuery.call(window.navigator.permissions, params);
}
"""

# --- Tiempos -----------------------------------------------------------------
DEFAULT_TIMEOUT_MS = 30_000
NETWORK_IDLE_TIMEOUT_MS = 10_000
NAV_DELAY = (2.5, 5.0)       # pausa tras cada navegación (s)
SCROLL_DELAY = (2.5, 4.8)    # pausa entre scrolls (s)
MAX_SCROLL_ROUNDS = 20       # tope absoluto de scrolls
MAX_STAGNANT_ROUNDS = 4      # scrolls seguidos sin posts nuevos antes de parar

# --- Seguidores para la ley de Benford (scraper/seguidores.py) ---------------------
# Cuántas cuentas de la lista de seguidores se leen con hover. 0 = no extraer.
MAX_CUENTAS = 6
SEGUIDORES_CSV = BASE_DIR / "seguidores.csv"  # columnas: usuario, seguidores
# Tiempo TOTAL por cuenta (s), incluida la espera de la tarjeta. Si la tarjeta tardó
# 1,2 s y sale 2,5, solo se esperan 1,3 s más. Bajarlo aumenta el riesgo de bloqueo.
SEGUNDOS_POR_CUENTA = (2.0, 3.2)
HOVER_TIMEOUT_S = 5          # espera máxima a que aparezca la tarjeta emergente
MODAL_TIMEOUT_S = 20         # espera máxima a que cargue la lista de seguidores
SCROLL_MODAL_DELAY = (1.2, 2.5)  # pausa tras cada scroll dentro del modal (s)
PAUSA_LARGA_CADA = 40        # cada cuántas cuentas se hace una pausa larga
PAUSA_LARGA = (6.0, 12.0)    # duración de la pausa larga (s)
# Freno: si N tarjetas seguidas no cargan, Instagram puede estar limitándonos.
FRENO_TRAS_SALTADAS = 3
PAUSA_FRENO = (30.0, 60.0)

# --- Análisis de personalidad (analyze.py) -------------------------------------
# La API key NUNCA va aquí: se lee de GEMINI_API_KEY en el archivo .env.
ENV_PATH = BASE_DIR / ".env"
RESULTS_DIR = BASE_DIR / "resultados"
GEMINI_MODEL_DEFAULT = "gemini-3.8-flash"  # se puede cambiar con GEMINI_MODEL en .env
PROFILE_ALIAS = "Perfil_01"                # nombre anónimo que verá Gemini

MAX_POSTS_TO_SEND = 150      # publicaciones (más recientes) que se envían a Gemini
MAX_CAPTION_CHARS = 600      # recorte de cada caption para no gastar tokens de más
MIN_CAPTIONED_POSTS = 5      # con menos captions (y sin bio) no hay qué analizar
TOP_HASHTAGS = 15            # hashtags más usados incluidos en las estadísticas

GEMINI_TEMPERATURE = 0.3     # baja: respuestas más consistentes entre ejecuciones
# Razonamiento interno del modelo antes de responder: "minimal", "low", "medium" o "high".
# Por defecto Gemini usa "high", que puede tardar varios minutos; "low" basta para esta tarea.
GEMINI_THINKING_LEVEL = "low"
GEMINI_MAX_RETRIES = 3       # reintentos ante 429 / errores temporales del servidor
GEMINI_RETRY_BASE_S = 10     # espera base del backoff exponencial (10, 20, 40 s)
GEMINI_FORMAT_RETRIES = 1    # reintentos si la respuesta no cumple el esquema
GEMINI_TIMEOUT_S = 120       # espera máxima por intento antes de reintentar
