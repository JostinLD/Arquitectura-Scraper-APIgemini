"""Extracción de seguidores SIN entrar a cada perfil (hover sobre la lista de seguidores).

Se ejecuta dentro del mismo recorrido del scraper (``InstagramScraper.scrape``), así no
hay que volver a abrir el navegador ni repetir el scraping del perfil.

Flujo:
  1. En el perfil objetivo se hace clic en el enlace "N seguidores" -> se abre el modal.
  2. Se leen los nombres de usuario visibles dentro del modal.
  3. Para cada cuenta: se pasa el ratón por encima de su nombre (hover), Instagram muestra
     una tarjeta emergente con "N seguidores", y se lee ese número.
  4. Cuando ya se procesaron todas las cuentas visibles, se hace scroll DENTRO del modal
     para que Instagram cargue más, hasta llegar a ``max_cuentas``.
  5. Si una tarjeta no aparece a tiempo, la cuenta se salta y se cuenta como "saltada".
"""
from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from playwright.sync_api import ElementHandle, Error as PlaywrightError, Locator, Page

import config
from exceptions import RateLimitError
from models import SeguidorMuestra
from utils.humanize import jitter

log = logging.getLogger(__name__)

# --- Selectores ------------------------------------------------------------------
# El modal de la lista es un <div role="dialog"> (atributo de accesibilidad, más estable
# que las clases CSS de Instagram, que cambian en cada versión).
_MODAL = 'div[role="dialog"]'
# "288 seguidores" / "1,2 mil seguidores" / "1.2K followers" (sin anclar: busca dentro).
_TEXTO_CONTADOR = r"\d[\d.,]*\s*(?:mill(?:ones|\.)?|millón|mil|k|m)?\.?\s*(?:seguidores?|followers?)"
# Rutas de Instagram que tienen forma de "/algo/" pero no son perfiles.
_RUTAS_RESERVADAS = {"explore", "accounts", "reels", "direct", "stories", "p", "reel"}

# Texto de la tarjeta emergente: "1.234 seguidores", "1,2 mil seguidores", "15,3 k
# followers", "2 mill. seguidores"... El número va en el grupo 1.
_TEXTO_SEGUIDORES = r"^\s*(\d[\d.,]*\s*(?:mill(?:ones|\.)?|millón|mil|k|m)?\.?)\s*(?:seguidores?|followers?)\s*$"

# JS que devuelve, EN ORDEN, los usuarios listados dentro del modal. Cada fila tiene dos
# enlaces al perfil (la foto y el nombre); nos quedamos solo con los que tienen texto.
_USUARIOS_DEL_MODAL_JS = """
modal => [...modal.querySelectorAll('a[href^="/"]')]
  .filter(a => /^\\/[A-Za-z0-9._]+\\/$/.test(a.getAttribute('href')) && a.textContent.trim())
  .map(a => a.getAttribute('href').slice(1, -1))
"""

# JS que busca en TODA la página los elementos con el texto "N seguidores".
#  - modo "marcar": marca como vistos los que ya existen (p. ej. la cabecera del perfil).
#  - modo "buscar": devuelve el primero visible que NO estaba marcado -> es la tarjeta
#    que acaba de aparecer por el hover. Si el número tiene atributo title (Instagram
#    suele poner ahí la cifra exacta), se usa ese valor.
# Se usa textContent para filtrar (es barato) y se toma el elemento más interno.
_TARJETA_JS = """
([patron, modo]) => {
  const re = new RegExp(patron, 'i');
  const coincide = el => {
    const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
    return t.length <= 40 && re.test(t);
  };
  for (const el of document.body.querySelectorAll('span, div, li, a')) {
    if (el.dataset.benfordVisto || !coincide(el)) continue;
    if ([...el.children].some(coincide)) continue;   // hay un hijo más específico
    if (modo === 'marcar') { el.dataset.benfordVisto = '1'; continue; }
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;   // oculto
    el.dataset.benfordVisto = '1';
    const conTitulo = el.querySelector('[title]');
    return conTitulo ? conTitulo.getAttribute('title') : el.textContent.replace(/\\s+/g, ' ').trim();
  }
  return null;
}
"""

# JS que encuentra el contenedor con scroll dentro del modal (el que tiene la lista).
_CONTENEDOR_SCROLL_JS = """
modal => {
  const candidatos = [modal, ...modal.querySelectorAll('div')];
  const c = candidatos.find(d => d.scrollHeight > d.clientHeight + 20 &&
                                 /(auto|scroll)/.test(getComputedStyle(d).overflowY));
  if (!c) return null;
  const r = c.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2,
           arriba: c.scrollTop, maximo: c.scrollHeight - c.clientHeight };
}
"""


# ---------------------------------------------------------------------- conversión
_NUMERO_RE = re.compile(r"(\d[\d.,]*)\s*(mill(?:ones|\.)?|millón|mil|k|m)?", re.IGNORECASE)


def convertir_numero(texto: str | None) -> int | None:
    """Convierte el texto de Instagram en un entero.

    >>> convertir_numero("1.234"), convertir_numero("1,2 mil"), convertir_numero("15,3 k")
    (1234, 1200, 15300)
    >>> convertir_numero("1.2K"), convertir_numero("2 M"), convertir_numero("2 mill.")
    (1200, 2000000, 2000000)
    """
    if not texto:
        return None
    match = _NUMERO_RE.search(texto.replace("\xa0", " ").lower())
    if not match:
        return None
    numero, sufijo = match.group(1).rstrip(".,"), (match.group(2) or "").rstrip(".")

    if sufijo.startswith("mill") or sufijo == "m":
        multiplicador = 1_000_000
    elif sufijo in ("mil", "k"):
        multiplicador = 1_000
    else:
        multiplicador = 1

    if multiplicador == 1:
        # Sin sufijo, el punto y la coma son separadores de miles: "1.234" o "1,234".
        return int(re.sub(r"[.,]", "", numero))
    # Con sufijo, el separador es decimal: "1,2 mil" o "1.2K". Si aparecen los dos
    # ("1.234,5 mil"), el último es el decimal y el otro se elimina.
    if "," in numero and "." in numero:
        decimal = "," if numero.rfind(",") > numero.rfind(".") else "."
        numero = numero.replace("." if decimal == "," else ",", "")
    return round(float(numero.replace(",", ".")) * multiplicador)


# ---------------------------------------------------------------------- extractor
class ExtractorSeguidores:
    """Abre el modal de seguidores del perfil ya cargado y lee cada cuenta con hover."""

    def __init__(self, page: Page, objetivo: str, max_cuentas: int,
                 revisar_bloqueo: Callable[[], None]) -> None:
        self.page = page
        self.objetivo = objetivo
        self.max_cuentas = max_cuentas
        # Función del scraper que revisa las respuestas de red y lanza RateLimitError
        # o SessionExpiredError si Instagram nos bloqueó.
        self.revisar_bloqueo = revisar_bloqueo

        self.muestra: list[SeguidorMuestra] = []
        self.saltadas = 0
        self._saltadas_seguidas = 0  # para detectar si Instagram empezó a frenarnos
        self._procesados: set[str] = set()
        self._modal: ElementHandle | None = None

    def extraer(self) -> tuple[list[SeguidorMuestra], int]:
        """Devuelve (cuentas leídas, cuántas se saltaron)."""
        if not self._abrir_modal():
            return self.muestra, self.saltadas
        inicio = time.monotonic()
        try:
            self._recorrer_lista()
        except RateLimitError as exc:
            # Se conservan los datos ya leídos: mejor una muestra parcial que nada.
            log.warning("Instagram limitó las peticiones; se detiene con %d cuentas. (%s)",
                        len(self.muestra), exc)
        finally:
            self.page.keyboard.press("Escape")  # cerrar el modal
        duracion = time.monotonic() - inicio
        log.info("Seguidores: %d cuentas leídas, %d saltadas (tarjeta no cargó) en %.1f min "
                 "(%.1f s por cuenta).", len(self.muestra), self.saltadas, duracion / 60,
                 duracion / max(len(self._procesados), 1))
        return self.muestra, self.saltadas

    # ------------------------------------------------------------------ pasos
    def _abrir_modal(self) -> bool:
        # Volver arriba: después de recorrer las publicaciones la cabecera ya no se ve.
        self.page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        jitter(1.0, 2.0, page=self.page)

        enlace = self._buscar_enlace_seguidores()
        if enlace is None:
            ruta = self._guardar_diagnostico("sin_enlace_seguidores", "header")
            log.warning("No se encontró el enlace de seguidores. Diagnóstico guardado en %s", ruta)
            return False
        log.info("Abriendo la lista de seguidores de @%s...", self.objetivo)
        enlace.scroll_into_view_if_needed()
        enlace.click()

        self._modal = self._esperar_modal()
        if self._modal is None:
            ruta = self._guardar_diagnostico("modal_seguidores", _MODAL)
            log.warning("El modal de seguidores no cargó (URL: %s). Diagnóstico guardado en %s",
                        self.page.url, ruta)
            return False
        jitter(1.0, 2.0, page=self.page)
        return True

    def _esperar_modal(self) -> ElementHandle | None:
        """Espera a que aparezca el modal con la lista y lo devuelve.

        Instagram puede tener varios ``div[role="dialog"]`` a la vez (notificaciones,
        avisos...), así que no basta con tomar el primero: se revisan todos y se elige
        el que contiene más cuentas listadas."""
        limite = time.monotonic() + config.MODAL_TIMEOUT_S
        while time.monotonic() < limite:
            mejor, max_cuentas = None, 0
            for dialogo in self.page.query_selector_all(_MODAL):
                try:
                    cantidad = len(dialogo.evaluate(_USUARIOS_DEL_MODAL_JS))
                except PlaywrightError:
                    continue  # el diálogo desapareció mientras se revisaba
                if cantidad > max_cuentas:
                    mejor, max_cuentas = dialogo, cantidad
            if mejor is not None:
                log.info("Modal de seguidores abierto (%d cuentas visibles).", max_cuentas)
                return mejor
            self.page.wait_for_timeout(500)
        return None

    def _buscar_enlace_seguidores(self) -> Locator | None:
        """Prueba varias formas de encontrar el "N seguidores" de la cabecera, de la más
        precisa a la más general, porque Instagram cambia su HTML con frecuencia."""
        texto = re.compile(_TEXTO_CONTADOR, re.IGNORECASE)
        clicables = 'a, [role="link"], [role="button"]'
        estrategias = [
            # 1) Enlace con la ruta del perfil ("/usuario/followers/", con o sin "?...").
            ("href del perfil", self.page.locator(
                f'a[href*="/{self.objetivo}/followers" i]')),
            # 2) Cualquier enlace que lleve a "/followers".
            ("href /followers", self.page.locator('a[href*="/followers" i]')),
            # 3) Elemento clicable de la cabecera cuyo texto sea "288 seguidores".
            ("texto en cabecera", self.page.locator("header").locator(clicables)
             .filter(has_text=texto)),
            # 4) El texto "288 seguidores" en cualquier parte de la cabecera.
            ("texto suelto", self.page.locator("header").get_by_text(texto)),
            # 5) Igual que 3, pero en toda la página (por si no hay <header>).
            ("texto en página", self.page.locator(clicables).filter(has_text=texto)),
        ]
        for nombre, locator in estrategias:
            try:
                if locator.count():
                    log.info("Enlace de seguidores encontrado (estrategia: %s).", nombre)
                    return locator.first
            except PlaywrightError:
                continue
        return None

    def _guardar_diagnostico(self, motivo: str, selector: str) -> Path:
        """Guarda una captura y el HTML de ``selector`` (o de toda la página si no existe)
        en config.DEBUG_DIR, para poder ajustar los selectores con el HTML real."""
        config.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        base = config.DEBUG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{motivo}"
        try:
            self.page.screenshot(path=str(base.with_suffix(".png")))
            partes = [e.evaluate("e => e.outerHTML") for e in self.page.query_selector_all(selector)]
            html = "\n\n<!-- ======== -->\n\n".join(partes) or self.page.content()
            base.with_suffix(".html").write_text(html, encoding="utf-8")
        except PlaywrightError as exc:
            log.debug("No se pudo guardar el diagnóstico: %s", exc)
        return base.with_suffix(".png")

    def _recorrer_lista(self) -> None:
        scrolls_sin_nuevos = 0
        while len(self._procesados) < self.max_cuentas:
            pendientes = [u for u in self._usuarios_visibles() if u not in self._procesados]
            if not pendientes:
                # Ya se leyeron todas las visibles: scroll dentro del modal para cargar más.
                if self._scroll_modal() and self._hay_nuevos():
                    scrolls_sin_nuevos = 0
                else:
                    scrolls_sin_nuevos += 1
                if scrolls_sin_nuevos >= config.MAX_STAGNANT_ROUNDS:
                    log.info("La lista no carga más cuentas; se detiene.")
                    return
                continue
            scrolls_sin_nuevos = 0

            for usuario in pendientes:
                if len(self._procesados) >= self.max_cuentas:
                    return
                self._procesar_cuenta(usuario)

    def _procesar_cuenta(self, usuario: str) -> None:
        self._procesados.add(usuario)
        inicio = time.monotonic()
        texto = self._leer_tarjeta(usuario)
        seguidores = convertir_numero(texto)
        if seguidores is None:
            self.saltadas += 1
            self._saltadas_seguidas += 1
            log.debug("@%s: la tarjeta no cargó; se salta.", usuario)
        else:
            self._saltadas_seguidas = 0
            self.muestra.append(SeguidorMuestra(usuario=usuario, seguidores=seguidores))
            log.debug("@%s: %r -> %d", usuario, texto, seguidores)

        n = len(self._procesados)
        if n % 10 == 0:
            log.info("Seguidores: %d/%d cuentas (%d saltadas)", n, self.max_cuentas, self.saltadas)
        self.revisar_bloqueo()

        # Freno de seguridad: varias tarjetas seguidas sin cargar suele ser la primera
        # señal de que Instagram nos está limitando, antes de un bloqueo (429).
        if self._saltadas_seguidas >= config.FRENO_TRAS_SALTADAS:
            log.warning("%d tarjetas seguidas sin cargar: pausa de seguridad...",
                        self._saltadas_seguidas)
            jitter(*config.PAUSA_FRENO, page=self.page)
            self._saltadas_seguidas = 0
        elif n % config.PAUSA_LARGA_CADA == 0:
            log.info("Pausa larga para no ser bloqueado...")
            jitter(*config.PAUSA_LARGA, page=self.page)
        else:
            # Ritmo por cuenta: el tiempo que tardó la tarjeta en aparecer ya cuenta como
            # "tiempo leyendo" (una persona también mira la tarjeta un momento), así que
            # solo se espera lo que falte para completar un ritmo aleatorio por cuenta.
            # La frecuencia de peticiones a Instagram queda igual de controlada, pero sin
            # sumar dos esperas seguidas.
            ritmo = random.uniform(*config.SEGUNDOS_POR_CUENTA)
            restante = ritmo - (time.monotonic() - inicio)
            if restante > 0:
                self.page.wait_for_timeout(restante * 1000)

    def _leer_tarjeta(self, usuario: str) -> str | None:
        """Hace hover sobre el nombre de ``usuario`` y devuelve el texto "N seguidores"."""
        assert self._modal is not None
        # Cada fila tiene dos enlaces al perfil: la foto y el nombre. Se usa el que tiene texto.
        enlaces = self._modal.query_selector_all(f'a[href="/{usuario}/"]')
        enlace = next((e for e in enlaces if (e.text_content() or "").strip()), None)
        if enlace is None:
            return None
        try:
            # 1) Alejar el ratón para que se cierre la tarjeta anterior y marcar lo que ya
            #    había en pantalla: así sabemos que lo que aparezca después es la tarjeta nueva.
            self._mover_a_zona_neutra()
            self.page.evaluate(_TARJETA_JS, [_TEXTO_SEGUIDORES, "marcar"])

            # 2) Mover el ratón (en varios pasos, como una persona) al centro del nombre.
            enlace.scroll_into_view_if_needed()
            caja = enlace.bounding_box()
            if caja is None:
                return None
            x = caja["x"] + caja["width"] * random.uniform(0.3, 0.7)
            y = caja["y"] + caja["height"] * random.uniform(0.3, 0.7)
            self.page.mouse.move(x, y, steps=random.randint(8, 18))

            # 3) Esperar a que la tarjeta aparezca (Instagram la muestra tras ~0,5-2 s).
            limite = time.monotonic() + config.HOVER_TIMEOUT_S
            while time.monotonic() < limite:
                texto = self.page.evaluate(_TARJETA_JS, [_TEXTO_SEGUIDORES, "buscar"])
                if texto:
                    return texto
                self.page.wait_for_timeout(100)  # revisar cada 0,1 s: se detecta antes
        except PlaywrightError as exc:
            log.debug("@%s: error durante el hover: %s", usuario, exc)
        return None

    # ------------------------------------------------------------------ auxiliares
    def _usuarios_visibles(self) -> list[str]:
        assert self._modal is not None
        usuarios = self._modal.evaluate(_USUARIOS_DEL_MODAL_JS)
        vistos: list[str] = []
        for u in usuarios:
            if u.lower() in _RUTAS_RESERVADAS or u.lower() == self.objetivo or u in vistos:
                continue
            vistos.append(u)
        return vistos

    def _hay_nuevos(self) -> bool:
        return any(u not in self._procesados for u in self._usuarios_visibles())

    def _scroll_modal(self) -> bool:
        """Scroll con la rueda del ratón sobre la lista. Devuelve False si ya no baja más."""
        assert self._modal is not None
        info = self._modal.evaluate(_CONTENEDOR_SCROLL_JS)
        if not info or info["arriba"] >= info["maximo"] - 5:
            return False
        self.page.mouse.move(info["x"], info["y"], steps=random.randint(5, 12))
        for _ in range(random.randint(3, 6)):
            self.page.mouse.wheel(0, random.randint(120, 260))
            self.page.wait_for_timeout(random.uniform(60, 180))
        jitter(*config.SCROLL_MODAL_DELAY, page=self.page)  # dar tiempo a que carguen más
        self.revisar_bloqueo()
        return True

    def _mover_a_zona_neutra(self) -> None:
        """Lleva el ratón al título del modal, donde no hay nombres de usuario."""
        assert self._modal is not None
        caja = self._modal.bounding_box()
        if caja:
            self.page.mouse.move(caja["x"] + caja["width"] / 2 + random.uniform(-30, 30),
                                 caja["y"] + random.uniform(12, 24),
                                 steps=random.randint(3, 6))
            self.page.wait_for_timeout(random.uniform(60, 150))
