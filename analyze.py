"""Punto de entrada del análisis: output.json -> anonimizar -> Gemini -> resultados/.

Uso:
    python analyze.py                        # analiza el output.json existente
    python analyze.py --dry-run              # prepara y guarda lo que se enviaría, SIN llamar a Gemini
    python analyze.py <usuario> --scrape     # ejecuta primero el scraper (main.py) y luego analiza
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
import main as scraper_main
from analysis.prepare import buscar_fugas, cargar_resultado, preparar_datos
from analysis.prompt import INSTRUCCIONES_SISTEMA, construir_prompt
from exceptions import (
    AnalysisError,
    GeminiAPIError,
    GeminiRateLimitError,
    InputDataError,
    InvalidResponseError,
    MissingApiKeyError,
)

log = logging.getLogger("analyze")

# Códigos de salida. Empiezan en 6 para no chocar con los de main.py (0-5).
EXIT_OK, EXIT_ERROR = 0, 1
EXIT_API_KEY, EXIT_INPUT, EXIT_GEMINI_RATE_LIMIT, EXIT_GEMINI_API, EXIT_INVALID_RESPONSE = range(6, 11)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Análisis Big Five (OCEAN) con Gemini")
    parser.add_argument("username", nargs="?",
                        help="usuario a scrapear (solo con --scrape; por defecto config.TARGET_PROFILE)")
    parser.add_argument("--scrape", action="store_true",
                        help="ejecutar el scraper antes del análisis")
    parser.add_argument("--dry-run", action="store_true",
                        help="preparar y guardar los datos anonimizados sin llamar a Gemini")
    parser.add_argument("--input", type=Path, default=config.OUTPUT_PATH,
                        help="JSON generado por el scraper (por defecto output.json)")
    parser.add_argument("--output-dir", type=Path, default=config.RESULTS_DIR)
    parser.add_argument("--max-posts", type=int, help="(con --scrape) máximo de posts a extraer")
    parser.add_argument("--headless", action="store_true", help="(con --scrape) ocultar el navegador")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    if args.username and not args.scrape:
        parser.error("indicar un usuario solo tiene sentido junto con --scrape")
    return args


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows (cp1252) no puede mostrar emojis: se fuerza UTF-8.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 1) Scraping opcional: si falla, se devuelve el mismo código de salida de main.py.
    if args.scrape:
        codigo = scraper_main.main(_argumentos_scraper(args))
        if codigo != scraper_main.EXIT_OK:
            log.error("El scraper terminó con código %d; no se hace el análisis.", codigo)
            return codigo

    try:
        return _analizar(args)
    except MissingApiKeyError as exc:
        log.error("API key: %s", exc)
        return EXIT_API_KEY
    except InputDataError as exc:
        log.error("Datos de entrada: %s", exc)
        return EXIT_INPUT
    except GeminiRateLimitError as exc:
        log.error("Límite de Gemini: %s", exc)
        return EXIT_GEMINI_RATE_LIMIT
    except GeminiAPIError as exc:
        log.error("Gemini: %s", exc)
        return EXIT_GEMINI_API
    except InvalidResponseError as exc:
        log.error("Respuesta inválida: %s", exc)
        return EXIT_INVALID_RESPONSE
    except (AnalysisError, OSError) as exc:
        log.error("Error: %s", exc)
        return EXIT_ERROR
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario.")
        return EXIT_ERROR


def _argumentos_scraper(args: argparse.Namespace) -> list[str]:
    argv = [args.username or config.TARGET_PROFILE, "--output", str(args.input)]
    if args.max_posts is not None:
        argv += ["--max-posts", str(args.max_posts)]
    if args.headless:
        argv.append("--headless")
    if args.verbose:
        argv.append("-v")
    return argv


def _analizar(args: argparse.Namespace) -> int:
    # 2) Cargar, validar y anonimizar.
    resultado = cargar_resultado(args.input)
    datos = preparar_datos(resultado)
    prompt = construir_prompt(datos)
    alias = datos["perfil_id"]
    log.info("Datos preparados: %d publicaciones anonimizadas como %s.",
             len(datos["publicaciones"]), alias)

    # 3) Guardar exactamente lo que se envía (sirve para revisar y para el informe).
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ruta_datos = args.output_dir / f"{alias}_datos_enviados.json"
    ruta_prompt = args.output_dir / f"{alias}_prompt.txt"
    _escribir_json(ruta_datos, datos)
    ruta_prompt.write_text(f"[INSTRUCCIONES DEL SISTEMA]\n{INSTRUCCIONES_SISTEMA}\n\n"
                           f"[PROMPT]\n{prompt}", encoding="utf-8")
    log.info("Guardado %s y %s", ruta_datos, ruta_prompt)

    # 4) Comprobación de anonimización: si queda algo identificable, no se envía nada.
    fugas = buscar_fugas(datos, resultado.profile)
    if fugas:
        raise InputDataError("La anonimización dejó datos identificables: " + "; ".join(fugas))
    log.info("Anonimización verificada: sin usuario, nombre, IDs, URLs ni menciones reales.")

    if args.dry_run:
        log.info("--dry-run: NO se llamó a Gemini. Revisa los archivos guardados.")
        return EXIT_OK

    # 5) Enviar a Gemini. Se importa aquí para que --dry-run funcione sin el SDK ni la key.
    from analysis.gemini_client import analizar, cargar_configuracion
    from analysis.report import generar_markdown

    api_key, modelo = cargar_configuracion()
    analisis = analizar(prompt, api_key, modelo)

    # 6) Guardar resultado en JSON y en Markdown.
    pubs = datos["publicaciones"]
    meta = {
        "modelo": modelo,
        "fecha_analisis": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fecha_scraping": resultado.scraped_at.isoformat(timespec="seconds"),
        "publicaciones_enviadas": len(pubs),
        "rango_fechas": f"{pubs[0]['fecha']} a {pubs[-1]['fecha']}" if pubs else "sin publicaciones",
    }
    ruta_json = args.output_dir / f"{alias}_analisis.json"
    ruta_md = args.output_dir / f"{alias}_resumen.md"
    _escribir_json(ruta_json, {"meta": meta, "analisis": analisis.model_dump(mode="json")})
    ruta_md.write_text(generar_markdown(analisis, meta, {p["id"] for p in pubs}), encoding="utf-8")

    rasgos = analisis.rasgos
    log.info("O=%d C=%d E=%d A=%d N=%d | confianza %s",
             rasgos.apertura.puntaje, rasgos.responsabilidad.puntaje,
             rasgos.extraversion.puntaje, rasgos.amabilidad.puntaje,
             rasgos.neuroticismo.puntaje, analisis.confianza.nivel)
    log.info("Resultados: %s y %s", ruta_json, ruta_md)
    return EXIT_OK


def _escribir_json(ruta: Path, contenido: object) -> None:
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
