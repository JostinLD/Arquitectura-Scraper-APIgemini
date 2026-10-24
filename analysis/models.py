"""Modelos Pydantic de la respuesta de Gemini.

De estos modelos sale el JSON Schema que se envía en ``response_format``, así
Gemini queda obligado a responder con esta estructura exacta. Las descripciones
de cada campo también le llegan a Gemini como instrucciones.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

NivelConfianza = Literal["bajo", "medio", "alto"]


class Evidencia(BaseModel):
    fuente: str = Field(description=(
        "De dónde sale la evidencia: el ID de una publicación (p. ej. 'P017'), "
        "'biografia' o 'estadisticas.<campo>' (p. ej. 'estadisticas.intervalo_dias')."
    ))
    descripcion: str = Field(description="Qué se observa en esa fuente y por qué apoya el puntaje.")


class RasgoOCEAN(BaseModel):
    puntaje: int = Field(ge=1, le=10, description="Entero de 1 (muy bajo) a 10 (muy alto).")
    evidencias: list[Evidencia] = Field(
        min_length=1, description="Entre 2 y 4 evidencias concretas que justifican el puntaje."
    )
    justificacion: str = Field(description="Explicación breve (2-4 frases) del puntaje.")

    @computed_field  # no forma parte del esquema enviado, pero sí del JSON guardado
    @property
    def nivel(self) -> str:
        """Se calcula aquí (no lo decide Gemini) para que siempre cuadre con el puntaje."""
        return "bajo" if self.puntaje <= 3 else "medio" if self.puntaje <= 6 else "alto"


class Rasgos(BaseModel):
    apertura: RasgoOCEAN
    responsabilidad: RasgoOCEAN
    extraversion: RasgoOCEAN
    amabilidad: RasgoOCEAN
    neuroticismo: RasgoOCEAN


class Confianza(BaseModel):
    nivel: NivelConfianza = Field(description="Confianza global en el análisis.")
    limitaciones: list[str] = Field(
        min_length=1, description="Limitaciones concretas de este análisis y de los datos."
    )


class AnalisisPersonalidad(BaseModel):
    perfil_id: str = Field(description="El identificador anónimo recibido, p. ej. 'Perfil_01'.")
    rasgos: Rasgos
    resumen_general: str = Field(description="1-2 párrafos sobre cómo podría ser la persona.")
    confianza: Confianza
