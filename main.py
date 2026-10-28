"""Punto de entrada: extrae un perfil de Instagram y guarda el resultado en JSON.

Uso:
    python main.py                      # usa config.TARGET_PROFILE y config.MAX_POSTS
    python main.py <usuario> [--max-posts 25] [--max-cuentas 300] [--headless] [--output output.json]

Además de output.json guarda seguidores.csv (usuario, seguidores) para benford_seguidores.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

import config
from exceptions import (
    ChallengeRequiredError,
    CookieError,
    ProfileNotFoundError,
    RateLimitError,
    ScraperError,
    SessionExpiredError,
)
from scraper import InstagramScraper
from utils.cookie_manager import load_cookies

log = logging.getLogger("main")

# Códigos de salida, útiles para automatizar reintentos.
EXIT_OK, EXIT_ERROR, EXIT_COOKIES, EXIT_SESSION, EXIT_RATE_LIMIT, EXIT_NOT_FOUND = range(6)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper de perfiles públicos de Instagram")
    parser.add_argument(
        "username", nargs="?", default=config.TARGET_PROFILE,
        help=f"usuario, @usuario o URL del perfil (por defecto: config.TARGET_PROFILE = "
             f"{config.TARGET_PROFILE})",
    )
    parser.add_argument("--max-posts", type=int, default=config.MAX_POSTS)
    parser.add_argument("--max-cuentas", type=int, default=config.MAX_CUENTAS,
                        help="cuentas de la lista de seguidores a leer con hover (0 = ninguna)")
    parser.add_argument("--csv", type=Path, default=config.SEGUIDORES_CSV,
                        help="CSV de seguidores (por defecto seguidores.csv)")
    parser.add_argument("--headless", action="store_true", help="ocultar el navegador")
    parser.add_argument("--cookies", type=Path, default=config.COOKIES_PATH)
    parser.add_argument("--output", type=Path, default=config.OUTPUT_PATH)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        cookies = load_cookies(args.cookies)
        with InstagramScraper(cookies, headless=args.headless,
                              max_posts=args.max_posts,
                              max_cuentas=args.max_cuentas) as scraper:
            result = scraper.scrape(args.username)
    except CookieError as exc:
        log.error("Problema con las cookies: %s", exc)
        return EXIT_COOKIES
    except ChallengeRequiredError as exc:
        log.error("Checkpoint de seguridad: %s", exc)
        return EXIT_SESSION
    except SessionExpiredError as exc:
        log.error("Sesión caducada: %s", exc)
        return EXIT_SESSION
    except RateLimitError as exc:
        log.error("Rate limit: %s", exc)
        return EXIT_RATE_LIMIT
    except ProfileNotFoundError as exc:
        log.error("Perfil no encontrado: %s", exc)
        return EXIT_NOT_FOUND
    except (ScraperError, ValueError) as exc:
        log.error("Error: %s", exc)
        return EXIT_ERROR
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario.")
        return EXIT_ERROR

    args.output.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if result.muestra_seguidores:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            escritor.writerow(["usuario", "seguidores"])
            escritor.writerows((s.usuario, s.seguidores) for s in result.muestra_seguidores)
        log.info("Seguidores: %d cuentas guardadas en %s (%d saltadas).",
                 len(result.muestra_seguidores), args.csv, result.cuentas_saltadas)
    profile = result.profile
    log.info("@%s | seguidores=%s seguidos=%s | %d posts -> %s",
             profile.username, profile.followers, profile.following,
             result.total_posts, args.output)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
