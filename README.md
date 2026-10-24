# Scraper de Instagram + análisis de personalidad Big Five con Gemini

Proyecto universitario de Programación Web. Consta de dos partes:

1. **Scraper** (`main.py`): extrae con Playwright la actividad pública de un perfil
   de Instagram (biografía, publicaciones, captions, hashtags, likes, comentarios
   destacados y tipo de post) y la guarda en `output.json`.
2. **Análisis** (`analyze.py`): anonimiza esos datos y los envía a la API de Gemini
   para estimar los cinco rasgos del modelo de personalidad **Big Five (OCEAN)**:
   apertura, responsabilidad, extraversión, amabilidad y neuroticismo.

> Es un ejercicio académico exploratorio. **No es un diagnóstico psicológico.**

---

## Cómo funciona

```
 Instagram ──► 1. Scrapear ──► 2. Preparar y anonimizar ──► 3. Enviar a Gemini ──► 4. Guardar resultados
              (main.py)        (analysis/prepare.py)        (analysis/gemini_client.py)   (resultados/)
              output.json      Perfil_01_datos_enviados.json  respuesta JSON validada      .json + .md
```

1. **Scrapear.** El navegador abre el perfil con tu sesión de Instagram (cookies),
   intercepta las respuestas de red y, como respaldo, lee el DOM. Simula un
   comportamiento humano (pausas y scrolls aleatorios). El resultado se guarda en `output.json`.
2. **Preparar y anonimizar.** Se valida `output.json`, se eliminan o reemplazan
   todos los datos que identifican a la persona y se calculan estadísticas
   (frecuencia de publicación, franjas horarias, hashtags más usados, etc.). Si la
   verificación final encuentra algún dato identificable, el proceso se detiene.
3. **Enviar a Gemini.** Se envían los datos anonimizados junto con un prompt y un
   esquema JSON obligatorio. Gemini devuelve un puntaje de 1 a 10 por rasgo, con evidencias.
4. **Guardar resultados.** La respuesta se valida con Pydantic y se guarda en
   `resultados/`, en JSON y como resumen Markdown.

### ¿Qué es la API key?

La **API key** es una clave personal que entrega Google (en Google AI Studio) y que
identifica a tu cuenta cuando el programa llama a la API de Gemini. Sirve para
autorizar las peticiones y contar tu cuota de uso. Es como una contraseña: **quien
la tenga puede usar la API a tu nombre**. Por eso se guarda solo en el archivo
local `.env`, que nunca se sube al repositorio.

---

## Estructura del proyecto

```
main.py                      CLI del scraper: perfil -> output.json
analyze.py                   CLI del análisis (--dry-run, --scrape)
config.py                    Configuración del scraper y del análisis (rutas, límites, pausas, modelo)
models.py                    Modelos Pydantic de los datos scrapeados (perfil y publicaciones)
exceptions.py                Errores propios del scraper y del análisis
requirements.txt             Dependencias de Python
.env.example                 Plantilla del archivo .env (sin claves reales)

scraper/
  instagram.py               Scraping con Playwright (intercepción de red + respaldo DOM)

utils/
  cookie_manager.py          Carga y valida cookies.json (sessionid, ds_user_id, csrftoken)
  humanize.py                Pausas, scrolls y movimientos "humanos"

analysis/
  prepare.py                 Validación, anonimización, estadísticas y detección de fugas
  prompt.py                  Instrucciones del sistema y prompt enviado a Gemini
  gemini_client.py           Llamada a Gemini (google-genai) con reintentos y validación
  models.py                  Esquema de la respuesta: puntajes, evidencias y confianza
  report.py                  Generación del resumen Markdown

# Generados localmente (ignorados por git):
cookies.json                 Tus cookies de Instagram
.env                         Tu API key de Gemini
output.json                  Datos crudos del scraper
resultados/                  Resultados del análisis
debug/                       Capturas de pantalla ante errores del scraper
```

---

## Requisitos e instalación

- Python 3.10 o superior
- Google Chrome o Chromium
- Una cuenta de Instagram y una API key de Gemini

```bash
git clone https://github.com/DavidJostin/Programaci-n-web-Scraper-APIgemini.git
cd Programaci-n-web-Scraper-APIgemini

python -m venv .venv
# Windows:      .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium     # solo si no tienes Google Chrome instalado
```

---

## Configuración

> ⚠️ **`cookies.json` y `.env` contienen datos secretos. Nunca deben subirse a
> GitHub.** Ya están en `.gitignore`, junto con `output.json`, `resultados/` y `debug/`.

### 1. `cookies.json` (para el scraper)

1. Inicia sesión en <https://www.instagram.com> desde tu navegador.
2. Exporta las cookies con una extensión como **Cookie-Editor** (formato JSON).
3. Guárdalas como `cookies.json` en la raíz del proyecto.

Se acepta la lista que exporta Cookie-Editor o un diccionario simple. Deben estar
`sessionid`, `ds_user_id` y `csrftoken`:

```json
{"sessionid": "...", "ds_user_id": "...", "csrftoken": "..."}
```

La cookie `sessionid` es equivalente a tener tu sesión abierta: no la compartas.

### 2. `.env` (para el análisis)

Copia la plantilla y completa tu clave:

```bash
cp .env.example .env        # Linux/macOS
copy .env.example .env      # Windows
```

```ini
GEMINI_API_KEY=pega_aqui_tu_api_key
GEMINI_MODEL=gemini-3.8-flash      # opcional
```

La API key se obtiene gratis en <https://aistudio.google.com/apikey>.

---

## Uso

### Scraper (`main.py`)

```bash
python main.py <usuario>                  # usuario, @usuario o URL del perfil
python main.py                            # usa TARGET_PROFILE de config.py
python main.py <usuario> --max-posts 50   # limitar publicaciones (por defecto 200)
python main.py <usuario> --headless       # sin mostrar el navegador
python main.py <usuario> -v               # logs detallados
```

Opciones extra: `--cookies RUTA` y `--output RUTA`.

### Análisis (`analyze.py`)

```bash
python analyze.py --dry-run               # prepara y guarda los datos anonimizados SIN llamar a Gemini
python analyze.py                         # análisis real a partir de output.json -> resultados/
python analyze.py <usuario> --scrape      # scrapear y analizar con un solo comando
```

Opciones extra: `--input RUTA`, `--output-dir RUTA`, `--max-posts N` y `--headless`
(estas dos últimas, con `--scrape`), y `-v`.

**Recomendación:** ejecuta siempre `--dry-run` primero y revisa
`resultados/Perfil_01_datos_enviados.json` antes de enviar nada a Gemini.

Archivos generados en `resultados/`:

| Archivo | Contenido |
|---|---|
| `Perfil_01_datos_enviados.json` | Datos anonimizados, exactamente como se envían a Gemini |
| `Perfil_01_prompt.txt` | Instrucciones del sistema y prompt completo |
| `Perfil_01_analisis.json` | Puntajes de 1 a 10, evidencias, resumen y confianza (respuesta validada) |
| `Perfil_01_resumen.md` | Resumen legible para el informe |

### Códigos de salida

| Código | Significado |
|:---:|---|
| 0 | OK |
| 1 | Error genérico |
| 2 | Problema con `cookies.json` (no existe, es inválido o falta una cookie obligatoria) |
| 3 | Sesión de Instagram inválida o caducada |
| 4 | Límite de peticiones (rate limit) de Instagram |
| 5 | Perfil no encontrado |
| 6 | Falta `GEMINI_API_KEY` |
| 7 | `output.json` inexistente, vacío o inválido, con datos insuficientes, o anonimización fallida |
| 8 | Límite de uso de Gemini (429) tras los reintentos |
| 9 | Error de la API de Gemini (key inválida, modelo inexistente o fallo del servidor) |
| 10 | La respuesta de Gemini no cumple el esquema JSON |

---

## Ejemplo de salida

> Los datos de este ejemplo son **inventados**. No corresponden a ninguna persona real
> ni al análisis hecho en el proyecto.

Extracto de `resultados/Perfil_01_resumen.md`:

```markdown
# Análisis de personalidad Big Five — Perfil_01

- **Modelo:** gemini-3.8-flash
- **Fecha del análisis:** 2026-01-15
- **Publicaciones analizadas:** 42 (2024-03-02 a 2025-12-28)
- **Confianza del análisis:** medio

## Puntajes

| Rasgo | Puntaje (1-10) | Nivel |
|---|:---:|:---:|
| Apertura a la experiencia (O) | 8 `████████░░` | alto |
| Responsabilidad (C) | 6 `██████░░░░` | medio |
| Extraversión (E) | 7 `███████░░░` | alto |
| Amabilidad (A) | 7 `███████░░░` | alto |
| Neuroticismo (N) | 3 `███░░░░░░░` | bajo |

### Apertura a la experiencia (O): 8/10

Publica con frecuencia sobre viajes, fotografía y talleres de cerámica.

- **P004**: Caption sobre probar por primera vez una ruta de montaña.
- **estadisticas.hashtags.mas_usados**: Predominan #viajes, #arte y #fotografia.
```

Extracto de `resultados/Perfil_01_analisis.json`:

```json
{
  "perfil_id": "Perfil_01",
  "rasgos": {
    "apertura": {
      "puntaje": 8,
      "nivel": "alto",
      "evidencias": [
        {"fuente": "P004", "descripcion": "Caption sobre probar por primera vez una ruta de montaña."}
      ],
      "justificacion": "Publica con frecuencia sobre viajes, fotografía y talleres de cerámica."
    }
  },
  "confianza": {
    "nivel": "medio",
    "limitaciones": ["Solo 42 publicaciones, la mayoría sin caption largo."]
  }
}
```

---

## Consideraciones éticas y limitaciones

### Consentimiento

> **[COMPLETAR antes de entregar]** Indicar la situación del perfil analizado: si
> pertenece a un integrante del grupo, si su titular dio permiso expreso (y cómo),
> o si se cambiará por el perfil de un integrante.

Solo deben analizarse perfiles con el consentimiento de su titular. El scraping
automatizado puede ir en contra de los términos de uso de Instagram. Úsalo con
moderación y solo con fines académicos.

### No es un diagnóstico psicológico

Los puntajes los genera un modelo de lenguaje a partir de muy poca información. No
tienen validez clínica, no reemplazan a un test psicométrico validado (como el
NEO-PI-R o el BFI) y no deben usarse para tomar decisiones sobre una persona.

### Datos públicos y curados

Instagram muestra una imagen **seleccionada y editada** de la persona. Lo que alguien
decide publicar no refleja toda su personalidad. Además, el análisis solo usa texto y
metadatos (no se analizan las imágenes), y puede haber sesgos del propio modelo.

### Anonimización

Antes de enviar nada a Gemini, `analysis/prepare.py`:

- **Elimina** el usuario, el nombre completo, el `user_id`, la foto y el enlace del perfil,
  y la URL, el shortcode, el ID y la imagen de cada publicación.
- **Reemplaza** el usuario y el nombre (también dentro de captions y hashtags, sin
  importar mayúsculas, tildes ni puntos) por `Perfil_01`.
- **Reemplaza** las menciones a otras cuentas por `@usuario_1`, `@usuario_2`... y los
  enlaces, emails y teléfonos por `[enlace]`, `[email]` y `[telefono]`.
- **Envía las fechas solo como `AAAA-MM-DD`** (sin hora). Las franjas horarias van
  agregadas en las estadísticas.
- **Verifica el resultado** (`buscar_fugas`): si queda algún dato identificable,
  el análisis se detiene y no se envía nada.

**Limitación:** los nombres de *otras* personas escritos en texto libre, sin `@`,
no se detectan automáticamente. Revisa `Perfil_01_datos_enviados.json` con
`--dry-run` antes del análisis real.

### Política de datos del plan gratuito de Gemini

Según los [términos adicionales de la API de Gemini](https://ai.google.dev/gemini-api/terms),
en los servicios **gratuitos** Google usa el contenido enviado y las respuestas para
mejorar sus productos, y **revisores humanos pueden leerlo**. Además, recomienda
expresamente *no enviar información sensible, confidencial o personal*.

En los servicios de pago no se usa para mejorar productos. Por eso este proyecto
anonimiza los datos antes de enviarlos y llama a la API con `store=False`.

---

## Integrantes

| Nombre | Rol |
|---|---|
| [COMPLETAR] | [COMPLETAR] |
| [COMPLETAR] | [COMPLETAR] |
| [COMPLETAR] | [COMPLETAR] |
