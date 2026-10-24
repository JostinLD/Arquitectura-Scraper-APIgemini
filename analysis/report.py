"""Convierte el análisis validado en un resumen Markdown legible para el informe."""
from __future__ import annotations

import re
from typing import Any

from analysis.models import AnalisisPersonalidad

# Orden y nombre visible de cada rasgo.
_RASGOS = (
    ("apertura", "Apertura a la experiencia (O)"),
    ("responsabilidad", "Responsabilidad (C)"),
    ("extraversion", "Extraversión (E)"),
    ("amabilidad", "Amabilidad (A)"),
    ("neuroticismo", "Neuroticismo (N)"),
)


def generar_markdown(analisis: AnalisisPersonalidad, meta: dict[str, Any],
                     ids_validos: set[str]) -> str:
    """``ids_validos``: IDs de posts enviados, para marcar evidencias inventadas."""
    lineas = [
        f"# Análisis de personalidad Big Five — {analisis.perfil_id}",
        "",
        f"- **Modelo:** {meta['modelo']}",
        f"- **Fecha del análisis:** {meta['fecha_analisis']}",
        f"- **Publicaciones analizadas:** {meta['publicaciones_enviadas']} "
        f"({meta['rango_fechas']})",
        f"- **Confianza del análisis:** {analisis.confianza.nivel}",
        "",
        "> Ejercicio académico exploratorio basado solo en contenido público y "
        "anonimizado de Instagram. No es un diagnóstico psicológico.",
        "",
        "## Puntajes",
        "",
        "| Rasgo | Puntaje (1-10) | Nivel |",
        "|---|:---:|:---:|",
    ]
    for clave, nombre in _RASGOS:
        rasgo = getattr(analisis.rasgos, clave)
        barra = "█" * rasgo.puntaje + "░" * (10 - rasgo.puntaje)
        lineas.append(f"| {nombre} | {rasgo.puntaje} `{barra}` | {rasgo.nivel} |")

    lineas += ["", "## Resumen general", "", analisis.resumen_general.strip(), ""]

    lineas += ["## Evidencia por rasgo", ""]
    for clave, nombre in _RASGOS:
        rasgo = getattr(analisis.rasgos, clave)
        lineas += [f"### {nombre}: {rasgo.puntaje}/10", "", rasgo.justificacion.strip(), ""]
        for ev in rasgo.evidencias:
            # Si cita un post que no existe, se marca para que se note en el informe.
            citados = re.findall(r"P\d{3}", ev.fuente)
            aviso = " ⚠️ *ID no encontrado en los datos*" if (
                any(c not in ids_validos for c in citados)) else ""
            lineas.append(f"- **{ev.fuente}**{aviso}: {ev.descripcion.strip()}")
        lineas.append("")

    lineas += ["## Confianza y limitaciones", "",
               f"Nivel de confianza: **{analisis.confianza.nivel}**", ""]
    lineas += [f"- {lim.strip()}" for lim in analisis.confianza.limitaciones]
    lineas.append("")
    return "\n".join(lineas)
