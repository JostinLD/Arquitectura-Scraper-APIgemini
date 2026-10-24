"""Prepara los datos del scraper para Gemini: valida, anonimiza y resume.

Flujo:
  1. ``cargar_resultado``: lee output.json y lo valida con el modelo ScrapeResult.
  2. ``Anonimizador``: quita usuario, nombre, IDs, URLs, menciones, emails y teléfonos.
  3. ``preparar_datos``: arma el diccionario que se envía (perfil + estadísticas + posts).
  4. ``buscar_fugas``: comprueba que en el resultado no quedó ningún dato identificable.
"""
from __future__ import annotations

import json
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

import config
from exceptions import InputDataError
from models import Post, Profile, ScrapeResult

_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")

# --- Patrones de datos personales que se borran del texto libre ------------------
_URL_RE = re.compile(
    r"(?i)\b(?:https?://|www\.)\S+"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|ec|es|io|me|ly|co|info|link|gl|tv|app|site)\b(?:/\S*)?"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_MENTION_RE = re.compile(r"(?<![\w@.])@([A-Za-z0-9._]{1,30})")
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")


# ---------------------------------------------------------------------- carga
def cargar_resultado(path: Path) -> ScrapeResult:
    """Lee output.json y lo valida; cualquier problema se convierte en InputDataError."""
    if not path.exists():
        raise InputDataError(f"No existe {path}. Ejecuta primero 'python main.py <usuario>'.")
    texto = path.read_text(encoding="utf-8").strip()
    if not texto:
        raise InputDataError(f"{path.name} está vacío.")
    try:
        return ScrapeResult.model_validate(json.loads(texto))
    except json.JSONDecodeError as exc:
        raise InputDataError(f"{path.name} no es un JSON válido: {exc}") from exc
    except ValidationError as exc:
        raise InputDataError(f"{path.name} no tiene la estructura esperada:\n{exc}") from exc


# ---------------------------------------------------------------------- anonimización
class Anonimizador:
    """Reemplaza los datos que identifican a la persona por un alias (p. ej. 'Perfil_01')."""

    def __init__(self, profile: Profile, alias: str) -> None:
        self.alias = alias
        self.terminos = _terminos_identidad(profile)
        self._identidad_re = _regex_identidad(self.terminos)
        self._menciones: dict[str, str] = {}  # @real -> @usuario_N (consistente en todo el texto)

    def texto(self, valor: str | None) -> str | None:
        if not valor:
            return valor
        valor = _EMAIL_RE.sub("[email]", valor)  # antes que las menciones (contiene '@')
        valor = _URL_RE.sub("[enlace]", valor)
        valor = _PHONE_RE.sub(_reemplazar_telefono, valor)
        valor = _MENTION_RE.sub(self._reemplazar_mencion, valor)
        valor = self._identidad_re.sub(self.alias, valor)
        # "Ana Pérez" escrito con otro espaciado deja "Perfil_01 Perfil_01": se une en uno.
        return re.sub(rf"{self.alias}(?:\s+{self.alias})+", self.alias, valor)

    def _reemplazar_mencion(self, match: re.Match[str]) -> str:
        nombre = match.group(1).rstrip(".").lower()
        if any(t.lower() == nombre for grupo in self.terminos for t in grupo):
            return f"@{self.alias}"  # la persona se menciona a sí misma
        if nombre not in self._menciones:
            self._menciones[nombre] = f"@usuario_{len(self._menciones) + 1}"
        return self._menciones[nombre]


def _terminos_identidad(profile: Profile) -> tuple[set[str], set[str]]:
    """Devuelve (subcadenas, palabras) que identifican a la persona.

    * subcadenas: el usuario y el usuario sin números finales. Son tan
      específicos que se borran aunque estén dentro de otra palabra o hashtag.
    * palabras: nombre completo y cada parte del nombre. Solo se borran como
      palabra completa, para no romper "semana" si la persona se llama "Ana".
    """
    usuario = profile.username
    sin_signos = re.sub(r"[._]", "", usuario)  # "ana.perez_92" -> "anaperez92" (típico en hashtags)
    subcadenas = {usuario, sin_signos}
    for variante in (usuario, sin_signos):
        base = re.sub(r"[\d._]+$", "", variante)  # sin números finales: "anaperez"
        if len(base) >= 4:
            subcadenas.add(base)

    palabras: set[str] = set()
    # Partes del nombre con al menos 3 letras ("Ana", "Pérez"); se ignoran emojis.
    partes = re.findall(r"[^\W\d_]{3,}", profile.full_name or "")
    if partes:
        palabras.add(" ".join(partes))   # nombre completo sin emojis: "Ana Pérez"
        palabras.update(partes)
        junto = "".join(partes)          # nombre pegado: "AnaPérez" en un hashtag
        if len(partes) > 1 and len(junto) >= 6:
            subcadenas.add(junto)
    # También sin tildes: en hashtags se suele escribir "#anaperez" en vez de "#anapérez".
    subcadenas |= {_sin_tildes(t) for t in subcadenas}
    palabras |= {_sin_tildes(t) for t in palabras}
    return {t for t in subcadenas if t}, palabras


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _regex_identidad(terminos: tuple[set[str], set[str]]) -> re.Pattern[str]:
    """Un solo regex con todos los términos, de más largo a más corto."""
    subcadenas, palabras = terminos
    patrones = [(t, re.escape(t)) for t in subcadenas]
    patrones += [(t, rf"(?<!\w){re.escape(t)}(?!\w)") for t in palabras]
    patrones.sort(key=lambda par: len(par[0]), reverse=True)
    return re.compile("|".join(p for _, p in patrones), re.IGNORECASE)


def _reemplazar_telefono(match: re.Match[str]) -> str:
    # Solo se considera teléfono si tiene 9+ dígitos (evita borrar fechas como "2023 - 2024").
    return "[telefono]" if sum(c.isdigit() for c in match.group()) >= 9 else match.group()


# ---------------------------------------------------------------------- armado de datos
def preparar_datos(result: ScrapeResult, alias: str = config.PROFILE_ALIAS) -> dict[str, Any]:
    """Devuelve el diccionario anonimizado que se le enviará a Gemini."""
    anon = Anonimizador(result.profile, alias)

    # Los posts del respaldo DOM no traen el caption real (traen el 'alt' automático
    # de Instagram) ni fecha: se excluyen para no contaminar el análisis.
    validos = [p for p in result.posts if p.source == "network" and p.timestamp is not None]
    excluidos = len(result.posts) - len(validos)
    validos.sort(key=lambda p: p.timestamp, reverse=True)
    enviados = sorted(validos[: config.MAX_POSTS_TO_SEND], key=lambda p: p.timestamp)

    biografia = anon.texto(result.profile.biography)
    con_caption = sum(1 for p in enviados if p.caption and p.caption.strip())
    if not biografia and con_caption < config.MIN_CAPTIONED_POSTS:
        raise InputDataError(
            f"Datos insuficientes: sin biografía y solo {con_caption} publicaciones con "
            f"caption (mínimo {config.MIN_CAPTIONED_POSTS}). No hay texto que analizar."
        )

    return {
        "perfil_id": alias,
        "perfil": {
            "biografia": biografia,
            "seguidores": result.profile.followers,
            "seguidos": result.profile.following,
            "publicaciones_totales": result.profile.posts_count,
            "es_privado": result.profile.is_private,
            "tiene_enlace_externo": bool(result.profile.external_url),
        },
        "estadisticas": _estadisticas(enviados, result.profile, excluidos, anon),
        "publicaciones": [_post(i, p, anon) for i, p in enumerate(enviados, start=1)],
    }


def _post(indice: int, post: Post, anon: Anonimizador) -> dict[str, Any]:
    caption = anon.texto(post.caption)
    if caption and len(caption) > config.MAX_CAPTION_CHARS:
        caption = caption[: config.MAX_CAPTION_CHARS] + "…"
    return {
        "id": f"P{indice:03d}",
        "fecha": post.timestamp.astimezone(ZoneInfo(config.TIMEZONE_ID)).date().isoformat(),
        "tipo": post.post_type,
        "elementos": post.media_count,  # solo en carruseles
        "caption": caption,
        "hashtags": [anon.texto(h) for h in post.hashtags],
        "likes": post.like_count,
        "comentarios": post.comment_count,
    }


def _estadisticas(posts: list[Post], profile: Profile, excluidos: int,
                  anon: Anonimizador) -> dict[str, Any]:
    """Métricas de comportamiento: frecuencia, regularidad, horarios, tipos y estilo."""
    zona = ZoneInfo(config.TIMEZONE_ID)
    fechas = [p.timestamp.astimezone(zona) for p in posts]  # ya vienen en orden cronológico
    n = len(posts)
    stats: dict[str, Any] = {
        "publicaciones_analizadas": n,
        "publicaciones_excluidas_sin_datos": excluidos,
    }
    if not n:
        return stats

    # Frecuencia y regularidad: días entre publicaciones consecutivas.
    intervalos = [(b - a).total_seconds() / 86400 for a, b in zip(fechas, fechas[1:])]
    dias_cubiertos = max((fechas[-1] - fechas[0]).days, 1)
    por_mes = Counter(f.strftime("%Y-%m") for f in fechas)
    stats.update({
        "fecha_primera": fechas[0].date().isoformat(),
        "fecha_ultima": fechas[-1].date().isoformat(),
        "dias_cubiertos": dias_cubiertos,
        "promedio_publicaciones_por_mes": round(n / (dias_cubiertos / 30.44), 2),
        "publicaciones_por_mes": dict(sorted(por_mes.items())),
        "intervalo_dias": {
            "promedio": _r(statistics.mean(intervalos)) if intervalos else None,
            "mediana": _r(statistics.median(intervalos)) if intervalos else None,
            "desviacion_estandar": _r(statistics.pstdev(intervalos)) if intervalos else None,
            "maximo": _r(max(intervalos)) if intervalos else None,
        },
        "por_dia_semana": {d: sum(1 for f in fechas if f.weekday() == i)
                           for i, d in enumerate(_DIAS)},
        "por_franja_horaria": dict(Counter(_franja(f.hour) for f in fechas)),
    })

    # Tipos de contenido.
    tipos = Counter(p.post_type for p in posts)
    stats["tipos_publicacion"] = {
        t: {"cantidad": c, "porcentaje": _pct(c, n)} for t, c in tipos.most_common()
    }

    # Hashtags (anonimizados por si alguno contiene el nombre del usuario).
    hashtags = Counter(anon.texto(h.lower()) for p in posts for h in p.hashtags)
    stats["hashtags"] = {
        "porcentaje_posts_con_hashtags": _pct(sum(1 for p in posts if p.hashtags), n),
        "promedio_por_post": _r(sum(len(p.hashtags) for p in posts) / n),
        "mas_usados": [{"hashtag": h, "veces": c}
                       for h, c in hashtags.most_common(config.TOP_HASHTAGS)],
    }

    # Estilo de escritura de los captions.
    captions = [p.caption.strip() for p in posts if p.caption and p.caption.strip()]
    emojis = Counter(e for c in captions for e in _EMOJI_RE.findall(c))
    stats["captions"] = {
        "porcentaje_sin_caption": _pct(n - len(captions), n),
        "longitud_media_caracteres": _r(statistics.mean(map(len, captions))) if captions else 0,
        "porcentaje_con_emojis": _pct(sum(1 for c in captions if _EMOJI_RE.search(c)),
                                      len(captions)),
        "emojis_mas_usados": [e for e, _ in emojis.most_common(10)],
    }

    # Interacción recibida.
    likes = [p.like_count for p in posts if p.like_count is not None]
    comentarios = [p.comment_count for p in posts if p.comment_count is not None]
    stats["interaccion"] = {
        "likes_promedio": _r(statistics.mean(likes)) if likes else None,
        "likes_mediana": statistics.median(likes) if likes else None,
        "comentarios_promedio": _r(statistics.mean(comentarios)) if comentarios else None,
        "relacion_seguidores_seguidos": (
            _r(profile.followers / profile.following)
            if profile.followers is not None and profile.following else None
        ),
    }
    return stats


def _franja(hora: int) -> str:
    if hora < 6:
        return "madrugada (00-06)"
    if hora < 12:
        return "manana (06-12)"
    if hora < 19:
        return "tarde (12-19)"
    return "noche (19-24)"


def _pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1) if total else 0.0


def _r(valor: float) -> float:
    return round(valor, 2)


# ---------------------------------------------------------------------- verificación
def buscar_fugas(datos: dict[str, Any], profile: Profile) -> list[str]:
    """Devuelve los datos identificables que sigan presentes (lista vacía = todo bien).

    Se ejecuta SIEMPRE antes de enviar: si encuentra algo, el análisis se detiene."""
    texto = json.dumps(datos, ensure_ascii=False)
    fugas: list[str] = []
    for coincidencia in sorted(set(_regex_identidad(_terminos_identidad(profile)).findall(texto))):
        fugas.append(f"identidad: {coincidencia!r}")
    if profile.user_id and profile.user_id in texto:
        fugas.append("user_id")
    for patron, nombre in ((r"https?://|www\.|instagram\.com|cdninstagram|fbcdn", "URL"),
                           (_EMAIL_RE.pattern, "email")):
        if re.search(patron, texto, re.IGNORECASE):
            fugas.append(nombre)
    reales = [m for m in _MENTION_RE.findall(texto)
              if not re.fullmatch(r"usuario_\d+", m) and m != datos.get("perfil_id")]
    if reales:
        fugas.append(f"menciones: {sorted(set(reales))}")
    return fugas
