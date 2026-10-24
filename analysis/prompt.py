"""Texto que se le envía a Gemini.

* ``INSTRUCCIONES_SISTEMA`` va en ``system_instruction``: define el rol y las reglas.
* ``construir_prompt`` arma la petición con los datos anonimizados en JSON.
"""
from __future__ import annotations

import json
from typing import Any

INSTRUCCIONES_SISTEMA = """\
Eres un asistente de investigación en psicología de la personalidad. Estimas el \
perfil Big Five (OCEAN) de personas anónimas a partir ÚNICAMENTE de su actividad \
pública en Instagram. Es un ejercicio académico exploratorio, no un diagnóstico \
psicológico. Nunca inventas datos: si algo no está en la información recibida, \
lo dices. No haces suposiciones sobre identidad, género, salud mental, orientación \
sexual, religión, política ni otros datos sensibles. Respondes siempre en español.\
"""

_PLANTILLA = """\
Analiza la personalidad de "{perfil_id}" según el modelo Big Five (OCEAN).

## Datos disponibles
- "perfil": biografía y contadores del perfil.
- "estadisticas": frecuencia y regularidad de publicación, días y franjas horarias \
(hora de Ecuador), tipos de contenido, hashtags más usados, estilo de los captions \
e interacción recibida.
- "publicaciones": lista cronológica; cada una tiene un ID (P001, P002...), fecha \
(AAAA-MM-DD), tipo (Image/Video/Carousel), caption y hashtags.

NO hay comentarios de otras personas ni análisis de las imágenes. Los nombres, \
URLs y menciones fueron anonimizados: "[enlace]", "@usuario_N" y "{perfil_id}" \
son reemplazos, no texto original.

## Instrucciones
1. Asigna a cada rasgo un puntaje entero del 1 al 10 (1-3 bajo, 4-6 medio, 7-10 alto):
   - apertura: curiosidad, variedad de temas, creatividad, interés por el arte, \
los viajes o las ideas nuevas.
   - responsabilidad: regularidad y constancia al publicar, organización, \
referencias a metas, estudios o trabajo.
   - extraversion: contenido social, presencia de otras personas o eventos, tono \
expresivo y entusiasta, frecuencia de publicación.
   - amabilidad: tono cálido, agradecimientos, apoyo o cariño hacia otros, \
ausencia de hostilidad o sarcasmo.
   - neuroticismo: expresiones de ansiedad, tristeza, irritabilidad o cambios \
bruscos de tono. Un puntaje ALTO significa MÁS inestabilidad emocional.
2. Para cada rasgo da entre 2 y 4 evidencias concretas. En "fuente" pon el ID de \
la publicación (p. ej. "P017"), "biografia" o "estadisticas.<campo>". Usa solo IDs \
que existan en los datos.
3. Si no hay evidencia suficiente para un rasgo, asigna un puntaje cercano a 5 y \
dilo explícitamente en la justificación.
4. En "resumen_general" escribe 1-2 párrafos sobre cómo podría ser la persona, con \
lenguaje prudente ("parece", "sugiere", "podría").
5. En "confianza" indica el nivel global (bajo/medio/alto) y las limitaciones \
concretas: tamaño de la muestra, contenido curado (autopresentación), falta de \
comentarios y de análisis de imágenes, posibles sesgos.
6. En "perfil_id" devuelve exactamente "{perfil_id}".

Responde solo con el JSON del esquema indicado.

## Datos
```json
{datos}
```
"""


def construir_prompt(datos: dict[str, Any]) -> str:
    return _PLANTILLA.format(
        perfil_id=datos["perfil_id"],
        datos=json.dumps(datos, ensure_ascii=False, indent=2),
    )
