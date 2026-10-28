# Scraper de Instagram: personalidad Big Five con Gemini y ley de Benford en seguidores

Proyecto universitario de Programación Web. A partir de **un solo scraping** de un
perfil de Instagram se hacen dos análisis independientes:

| Parte | Script | Qué responde |
|---|---|---|
| **1. Scraper** | `main.py` | Extrae con Playwright el perfil, sus publicaciones y una muestra de sus seguidores con su número de seguidores. |
| **2. Big Five** | `analyze.py` | Estima los cinco rasgos de personalidad **OCEAN** con la API de Gemini, usando los datos anonimizados. |
| **3. Ley de Benford** | `benford_seguidores.py` | ¿El número de seguidores de los seguidores sigue la ley de Benford? Si no la sigue, puede haber cuentas falsas o bots. |

> Es un ejercicio académico exploratorio. **El análisis Big Five no es un diagnóstico
> psicológico** y **Benford no demuestra por sí solo que haya bots**: los dos dan indicios.

---

## Índice

1. [Arquitectura y flujo de datos](#arquitectura-y-flujo-de-datos)
2. [Estructura del proyecto](#estructura-del-proyecto)
3. [Requisitos e instalación](#requisitos-e-instalación)
4. [Configuración](#configuración)
5. [Uso](#uso)
6. [Parte 1: Scraper](#parte-1-scraper)
7. [Parte 2: Análisis Big Five con Gemini](#parte-2-análisis-big-five-con-gemini)
8. [Parte 3: Ley de Benford en los seguidores](#parte-3-ley-de-benford-en-los-seguidores)
9. [Parámetros configurables](#parámetros-configurables-configpy)
10. [Códigos de salida](#códigos-de-salida)
11. [Solución de problemas](#solución-de-problemas)
12. [Consideraciones éticas y limitaciones](#consideraciones-éticas-y-limitaciones)
13. [Integrantes](#integrantes)

---

## Arquitectura y flujo de datos

```
                         ┌──────────────────────── output.json ───► analyze.py ──► Gemini ──► resultados/Perfil_01_*
                         │                         (perfil + posts)   anonimizar     (Big Five)  .json / .md
 Instagram ──► main.py ──┤
            (Playwright) │
                         └──────────────────────── seguidores.csv ─► benford_seguidores.py ──► resultados/benford_*
                                                   (usuario,          tabla + chi-cuadrado       .png / .md
                                                    seguidores)
```

- **Un solo scraping alimenta los dos análisis.** La lista de seguidores se lee en el
  mismo recorrido del navegador que extrae el perfil. Así no hay que volver a abrir
  Instagram para cada análisis, y se reduce el riesgo de bloqueo.
- **Los análisis trabajan sin conexión a Instagram.** `analyze.py` y
  `benford_seguidores.py` leen los archivos que dejó `main.py`, así que se pueden
  repetir todas las veces que se quiera.

---

## Estructura del proyecto

```
main.py                      Punto de entrada del scraper: perfil -> output.json + seguidores.csv
analyze.py                   Punto de entrada del análisis Big Five (--dry-run, --scrape)
benford_seguidores.py        Ley de Benford: tabla, gráfico, chi-cuadrado, conclusión e informe
config.py                    Toda la configuración: rutas, límites, pausas, modelo de Gemini
models.py                    Modelos Pydantic de los datos extraídos (Profile, Post, SeguidorMuestra, ScrapeResult)
exceptions.py                Errores propios del scraper y del análisis
requirements.txt             Dependencias de Python
.env.example                 Plantilla del archivo .env (sin claves reales)

scraper/
  instagram.py               InstagramScraper: navegador, sesión, intercepción de red y respaldo DOM
  seguidores.py              ExtractorSeguidores: modal de seguidores + hover; convertir_numero()

utils/
  cookie_manager.py          Carga y valida cookies.json (sessionid, ds_user_id, csrftoken)
  humanize.py                Pausas, scrolls y movimientos del ratón "humanos"

analysis/
  prepare.py                 Validación, anonimización, estadísticas y detección de fugas
  prompt.py                  Instrucciones del sistema y prompt enviado a Gemini
  gemini_client.py           Llamada a Gemini (google-genai) con reintentos propios y validación
  models.py                  Esquema obligatorio de la respuesta: puntajes, evidencias y confianza
  report.py                  Resumen Markdown del análisis

# Generados localmente (ignorados por git):
cookies.json                 Tus cookies de Instagram                      (SECRETO)
.env                         Tu API key de Gemini                          (SECRETO)
output.json                  Datos crudos del scraper
seguidores.csv               Muestra de seguidores: usuario, seguidores
resultados/                  Resultados de Big Five y de Benford
debug/                       Capturas y HTML de diagnóstico ante errores del scraper
```

### Orden recomendado para estudiar el código

| Fase | Archivos |
|---|---|
| 1. Bases | `config.py` → `exceptions.py` → `models.py` |
| 2. Scraper | `main.py` → `utils/cookie_manager.py` → `utils/humanize.py` → `scraper/instagram.py` → `scraper/seguidores.py` |
| 3. Big Five | `analyze.py` → `analysis/prepare.py` → `analysis/prompt.py` → `analysis/models.py` → `analysis/gemini_client.py` → `analysis/report.py` |
| 4. Benford | `benford_seguidores.py` (dividido en las secciones 1 a 6 del enunciado) |

---

## Requisitos e instalación

- Python 3.10 o superior
- Google Chrome (recomendado) o el Chromium que instala Playwright
- Una cuenta de Instagram con la sesión iniciada en el navegador
- Una API key de Gemini (solo para la parte Big Five)

```bash
git clone https://github.com/DavidJostin/Arquitectura-Scraper-APIgemini.git
cd Arquitectura-Scraper-APIgemini

python -m venv .venv
# Windows:      .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium     # solo si no tienes Google Chrome instalado
```

| Dependencia | Para qué se usa |
|---|---|
| `playwright` | Controlar el navegador e interceptar las respuestas de Instagram |
| `playwright-stealth` *(opcional)* | Ocultar señales de automatización; si falta, se usa el script propio de `config.py` |
| `pydantic` | Validar los datos extraídos y la respuesta de Gemini |
| `google-genai` | SDK oficial de la API de Gemini |
| `python-dotenv` | Leer la API key desde `.env` |
| `matplotlib` | Gráfico de barras de Benford |
| `scipy` | Prueba chi-cuadrado |

---

## Configuración

> ⚠️ **`cookies.json` y `.env` contienen datos secretos. Nunca deben subirse a
> GitHub.** Ya están en `.gitignore`, junto con `output.json`, `seguidores.csv`,
> `resultados/` y `debug/`.

### 1. `cookies.json` (para el scraper)

El scraper **no inicia sesión con usuario y contraseña**: reutiliza la sesión que ya
tienes abierta en tu navegador.

1. Inicia sesión en <https://www.instagram.com> desde tu navegador.
2. Exporta las cookies con una extensión como **Cookie-Editor** (formato JSON).
3. Guárdalas como `cookies.json` en la raíz del proyecto.

Se acepta la lista que exporta Cookie-Editor o un diccionario simple. Deben estar
`sessionid`, `ds_user_id` y `csrftoken`:

```json
{"sessionid": "...", "ds_user_id": "...", "csrftoken": "..."}
```

La cookie `sessionid` equivale a tener tu sesión abierta: no la compartas.

### 2. `.env` (para el análisis Big Five)

Copia la plantilla, o crea el archivo a mano, y completa tu clave:

```bash
cp .env.example .env        # Linux/macOS
copy .env.example .env      # Windows
```

```ini
GEMINI_API_KEY=pega_aqui_tu_api_key
GEMINI_MODEL=gemini-3.5-flash-lite   # opcional; si falta se usa GEMINI_MODEL_DEFAULT de config.py
```

La API key se obtiene gratis en <https://aistudio.google.com/apikey>.

**¿Qué es la API key?** Es una clave personal que entrega Google y que identifica a
tu cuenta cuando el programa llama a Gemini. Sirve para autorizar las peticiones y
contar tu cuota de uso. Es como una contraseña: **quien la tenga puede usar la API a
tu nombre**. Por eso se guarda solo en `.env` y nunca en el código.

**¿Qué modelo usar?** Los modelos *flash-lite* responden mucho más rápido y fallan
menos por saturación (error 503). Los modelos *flash* razonan más, pero tardan más.
Si un modelo devuelve 503 con frecuencia, prueba otro en `GEMINI_MODEL`.

> 💡 Si usas OneDrive y VS Code avisa *"Failed to save '.env': the content of the file
> is newer"*, elige **Overwrite**. Ocurre porque OneDrive sincronizó el archivo
> mientras estaba abierto.

---

## Uso

### Flujo completo recomendado

```bash
python main.py <usuario> --max-cuentas 300   # 1. scraping: output.json + seguidores.csv
python benford_seguidores.py                 # 2. Benford: resultados/benford_informe.md + .png
python analyze.py --dry-run                  # 3. revisar lo que se enviaría a Gemini (sin enviarlo)
python analyze.py                            # 4. análisis Big Five real
```

### Scraper: `main.py`

```bash
python main.py <usuario>                     # usuario, @usuario o URL del perfil
python main.py                               # usa TARGET_PROFILE de config.py
python main.py <usuario> --max-posts 50      # publicaciones a extraer (por defecto MAX_POSTS)
python main.py <usuario> --max-cuentas 300   # seguidores a leer con hover (0 = no extraer)
python main.py <usuario> --headless          # sin mostrar el navegador
python main.py <usuario> -v                  # logs detallados
```

Opciones extra: `--cookies RUTA`, `--output RUTA` (JSON) y `--csv RUTA` (seguidores).

### Ley de Benford: `benford_seguidores.py`

```bash
python benford_seguidores.py                                       # lee seguidores.csv
python benford_seguidores.py --csv otro.csv --png g.png --informe i.md
```

No abre Instagram: solo lee el CSV. Muestra la tabla y la conclusión en consola y
genera `resultados/benford_seguidores.png` y `resultados/benford_informe.md`.

### Análisis Big Five: `analyze.py`

```bash
python analyze.py --dry-run                  # prepara y guarda los datos anonimizados SIN llamar a Gemini
python analyze.py                            # análisis real a partir de output.json -> resultados/
python analyze.py <usuario> --scrape         # scrapear y analizar con un solo comando
```

Opciones extra: `--input RUTA`, `--output-dir RUTA`, `--max-posts N` y `--headless`
(estas dos últimas, con `--scrape`), y `-v`.

**Recomendación:** ejecuta siempre `--dry-run` primero y revisa
`resultados/Perfil_01_datos_enviados.json` antes de enviar nada a Gemini.

---

## Parte 1: Scraper

### Perfil y publicaciones (`scraper/instagram.py`)

1. **Abre el navegador** (Google Chrome si está instalado) con un script *stealth* que
   oculta las señales de automatización (`navigator.webdriver`, la barra "Chrome está
   siendo controlado…") y un User-Agent coherente con la versión real del navegador.
2. **Carga las cookies** y comprueba que la sesión siga activa. Si Instagram pide
   login o un *checkpoint* de seguridad, se detiene, guarda una captura en `debug/` y
   devuelve un código de salida específico.
3. **Intercepta las respuestas de red.** Instagram carga los datos del perfil y del
   feed en JSON (`web_profile_info`, `feed/user`, `graphql`). El scraper los lee
   directamente, lo que es más fiable que leer el HTML.
4. **Usa el DOM como respaldo.** Si no llega el JSON, lee los contadores y las
   publicaciones de la página.
5. **Se comporta como una persona.** Hace scrolls de distancia variable, pausas
   aleatorias y movimientos del ratón (`utils/humanize.py`), y se detiene tras varios
   scrolls sin publicaciones nuevas.

Por cada publicación se guarda: fecha, tipo (foto, video, carrusel o reel), caption,
hashtags, likes, número de comentarios y algunos comentarios de vista previa.

### Seguidores sin entrar a cada perfil (`scraper/seguidores.py`)

Para Benford hace falta el número de seguidores de **muchas** cuentas. Entrar perfil
por perfil sería lento y llamativo para Instagram, así que se usa la **tarjeta
emergente (hover card)** que Instagram muestra al pasar el ratón sobre un usuario:

```
 Perfil objetivo                 Modal de seguidores               Tarjeta emergente
┌──────────────────┐   clic     ┌────────────────────┐   hover    ┌────────────────────┐
│ 1.234 seguidores ├──────────► │ @cuenta_a          ├──────────► │ @cuenta_a          │
└──────────────────┘            │ @cuenta_b          │            │ 15,3 mil seguidores│ ──► 15300
                                │ ...  (scroll ▼)    │            └────────────────────┘
                                └────────────────────┘
```

1. **Abrir el modal.** Se busca el enlace "N seguidores" con varias estrategias, de
   la más precisa a la más general: `a[href*="/<usuario>/followers"]`, cualquier
   enlace a `/followers`, y el texto "seguidores/followers" en la cabecera o en la
   página. Si ninguna funciona, se guardan una captura y el HTML en `debug/`.
2. **Detectar el modal.** Es un `div[role="dialog"]`, un atributo de accesibilidad
   más estable que las clases CSS, que Instagram cambia en cada versión. Si hay
   varios diálogos abiertos, se elige el que contiene más enlaces a usuarios.
3. **Hover sobre cada cuenta.** El ratón se mueve en varios pasos (no salta) hasta el
   nombre del usuario. Luego se espera a que aparezca un texto nuevo del tipo
   "N seguidores", revisando cada 100 ms y con un máximo de `HOVER_TIMEOUT_S`.
4. **Convertir el número.** `convertir_numero()` entiende los formatos que muestra
   Instagram:

   | Texto | Resultado |
   |---|---:|
   | `1.234` / `1,234` | 1234 |
   | `1,2 mil` / `15,3 k` / `1.2K` | 1200 / 15300 / 1200 |
   | `2 M` / `2 mill.` / `1,5 millones` | 2000000 / 2000000 / 1500000 |

5. **Scroll dentro del modal** para que Instagram cargue más cuentas, hasta llegar a
   `MAX_CUENTAS`.
6. **Las cuentas que fallan se saltan y se cuentan.** Si una tarjeta no carga a tiempo,
   esa cuenta no se guarda y se suma a `cuentas_saltadas`.

**Medidas para no levantar sospechas:**

| Medida | Parámetro |
|---|---|
| Tiempo **total** aleatorio por cuenta (la espera de la tarjeta cuenta dentro de ese tiempo) | `SEGUNDOS_POR_CUENTA = (2.0, 3.2)` |
| Pausa larga cada cierto número de cuentas | `PAUSA_LARGA_CADA = 40`, `PAUSA_LARGA = (6, 12)` s |
| **Freno**: si varias tarjetas seguidas no cargan, se espera más | `FRENO_TRAS_SALTADAS = 3`, `PAUSA_FRENO = (30, 60)` s |
| El ratón vuelve a una zona neutra entre cuentas, así cada tarjeta se abre de nuevo | — |
| Si Instagram limita las peticiones, se conserva la muestra parcial | `RateLimitError` |

Con la configuración por defecto, cada cuenta tarda unos **3 s**, es decir, unos
**15 minutos para 300 cuentas**.

### Archivos que genera

- **`output.json`**: perfil, publicaciones, `muestra_seguidores` y `cuentas_saltadas`
  (validado con `ScrapeResult`, en `models.py`).
- **`seguidores.csv`**: lo que pide el enunciado de Benford.

  ```csv
  usuario,seguidores
  cuenta_a,15300
  cuenta_b,842
  ```

---

## Parte 2: Análisis Big Five con Gemini

```
 output.json ──► 1. Validar ──► 2. Anonimizar ──► 3. Verificar fugas ──► 4. Gemini ──► 5. Validar respuesta ──► resultados/
                 (Pydantic)     (prepare.py)      (buscar_fugas)         (JSON schema)  (analysis/models.py)
```

1. **Validar.** `output.json` se carga con Pydantic. Si hay muy pocas publicaciones con
   texto, el análisis se detiene.
2. **Anonimizar y calcular estadísticas** (`analysis/prepare.py`): frecuencia de
   publicación, franjas horarias, tipos de publicación, hashtags más usados e
   interacción promedio. Se envían como máximo `MAX_POSTS_TO_SEND` publicaciones, y
   cada caption se recorta a `MAX_CAPTION_CHARS` caracteres.
3. **Verificar fugas** (`buscar_fugas`). Hay dos niveles:
   - **Críticas (bloquean el envío):** usuario, nombre completo, `user_id`, URLs,
     emails, teléfonos (9 dígitos o más) o menciones reales a otras cuentas.
   - **Avisos (no bloquean):** palabras sueltas del nombre que aparezcan en el texto.
     Los días, meses y palabras comunes ("martes", "vida", "amor"…) se ignoran para
     no bloquear por falsos positivos.
4. **Llamar a Gemini** (`analysis/gemini_client.py`). Se envían las instrucciones del
   sistema, el prompt y un **esquema JSON obligatorio**, con `temperature = 0.3`,
   `thinking_level = "low"` y `store = False`.
5. **Validar la respuesta** con `AnalisisPersonalidad` (`analysis/models.py`): un
   puntaje de 1 a 10 por rasgo, su nivel, evidencias que citan publicaciones reales,
   una justificación y la confianza con sus limitaciones. Si la respuesta no cumple el
   esquema, se pide una vez más.

### Manejo de errores y tiempos de Gemini

| Situación | Comportamiento |
|---|---|
| `429` (cuota) o `5xx` (servidor saturado, por ejemplo `503`) | Hasta `GEMINI_MAX_RETRIES` reintentos con espera exponencial: 10, 20 y 40 s, más un margen aleatorio |
| El modelo tarda demasiado | Cada intento se corta a los `GEMINI_TIMEOUT_S = 120` s |
| Reintentos ocultos del SDK | **Desactivados**, porque duplicaban las peticiones. Solo se usan los reintentos propios, que se ven en el log |
| Razonamiento lento | `thinking_level = "low"` (por defecto Gemini usa `high`, que puede tardar minutos) |

En el log se ve el modelo, el nivel de razonamiento y el tiempo de cada respuesta
(*"Respuesta de Gemini recibida en N s"*).

### Archivos generados en `resultados/`

| Archivo | Contenido |
|---|---|
| `Perfil_01_datos_enviados.json` | Datos anonimizados, exactamente como se envían a Gemini |
| `Perfil_01_prompt.txt` | Instrucciones del sistema y prompt completo |
| `Perfil_01_analisis.json` | Puntajes, evidencias, resumen y confianza (respuesta validada) |
| `Perfil_01_resumen.md` | Resumen legible para el informe |

### Ejemplo de salida

> Los datos de este ejemplo son **inventados**. No corresponden a ninguna persona real
> ni al análisis hecho en el proyecto.

```markdown
# Análisis de personalidad Big Five — Perfil_01

- **Modelo:** gemini-3.5-flash-lite
- **Publicaciones analizadas:** 20 (2024-03-02 a 2025-12-28)
- **Confianza del análisis:** medio

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
```

---

## Parte 3: Ley de Benford en los seguidores

### ¿Qué es la ley de Benford?

En muchos conjuntos de datos reales que abarcan varios órdenes de magnitud (como
poblaciones, precios o seguidores), el **primer dígito** no se reparte por igual:
el 1 aparece cerca del 30 % de las veces y el 9 menos del 5 %. La probabilidad
esperada de cada dígito *d* es:

$$P(d) = \log_{10}\left(1 + \frac{1}{d}\right)$$

| Dígito | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| % esperado | 30,1 | 17,6 | 12,5 | 9,7 | 7,9 | 6,7 | 5,8 | 5,1 | 4,6 |

**La idea del proyecto:** los seguidores orgánicos crecen de forma natural y tienden
a seguir esta distribución. Las cuentas falsas o compradas se crean en serie, a
menudo con números de seguidores parecidos, y rompen el patrón.

### Pasos de `benford_seguidores.py`

| # | Paso | Función |
|:-:|---|---|
| 1 | Leer el CSV y tomar el primer dígito de cada número (se ignoran las cuentas con 0 seguidores) | `leer_seguidores`, `primer_digito` |
| 2 | Tabla: dígito, cantidad observada, % observado, % esperado y diferencia | `construir_tabla`, `benford_esperado` |
| 3 | Gráfico de barras (observado) con la curva de Benford (esperado) | `guardar_grafico` |
| 4 | Prueba chi-cuadrado | `prueba_chi_cuadrado` |
| 5 | Conclusión automática | `conclusion` |
| 6 | Informe en Markdown con el análisis escrito | `generar_informe` |

### Prueba chi-cuadrado

$$\chi^2 = \sum_{d=1}^{9} \frac{(O_d - E_d)^2}{E_d}$$

- *O<sub>d</sub>*: cuentas observadas con primer dígito *d*.
  *E<sub>d</sub>* = *n* · *P(d)*: las que se esperarían según Benford.
- **8 grados de libertad** (9 dígitos − 1) y **α = 0,05**, así que el valor crítico es
  **≈ 15,51**. Se calcula con `scipy.stats.chisquare`.

| Resultado | Conclusión automática |
|---|---|
| p-valor > 0,05 (χ² < 15,51) | Los seguidores **parecen orgánicos**: las diferencias se pueden explicar por azar. |
| p-valor ≤ 0,05 (χ² ≥ 15,51) | La distribución **no sigue Benford**: posible presencia de bots o seguidores comprados. |

Si la muestra tiene **menos de 100 cuentas**, se muestra una advertencia, porque con
tan pocos datos la prueba no es confiable.

### Informe escrito (`resultados/benford_informe.md`)

Además de la consola, se genera un informe listo para leer o adjuntar. Incluye:

- **Datos:** perfil analizado, cuentas usadas y saltadas, y rango de seguidores en
  órdenes de magnitud.
- **Tabla** por dígito y **gráfico** incrustado.
- **Análisis escrito:** comportamiento del dígito 1, los dos dígitos con mayor
  desviación, si la frecuencia baja de forma continua del 1 al 9 (o en qué dígitos se
  rompe), y la interpretación de chi-cuadrado.
- **Conclusión** y **limitaciones** detectadas automáticamente: muestra pequeña, poco
  rango, redondeo de Instagram ("1,2 mil") y muestra no aleatoria.

Ejemplo de salida en consola (datos **inventados**):

```
Cuentas en el CSV: 300 | usadas (seguidores > 0): 298
Dígito | Observado |  % Obs. | % Benford |    Dif.
----------------------------------------------------
     1 |        91 |  30.54% |    30.10% |  +0.44
     2 |        50 |  16.78% |    17.61% |  -0.83
   ...
Chi-cuadrado = 6.21 | valor crítico (gl = 8, alfa = 0.05) = 15.51 | p-valor = 0.6237

CONCLUSIÓN: Los datos SE AJUSTAN a la ley de Benford (p > 0.05): los seguidores parecen reales/orgánicos.
```

---

## Parámetros configurables (`config.py`)

| Parámetro | Valor | Descripción |
|---|---|---|
| `TARGET_PROFILE` | URL | Perfil por defecto si no se indica uno en la terminal |
| `MAX_POSTS` | 20 | Publicaciones a extraer |
| `HEADLESS` | `False` | Ocultar el navegador |
| `BROWSER_CHANNEL` | `"chrome"` | Navegador a usar (`None` = Chromium de Playwright) |
| `NAV_DELAY`, `SCROLL_DELAY` | (2,5–5), (2,5–4,8) s | Pausas aleatorias del scraper |
| `MAX_CUENTAS` | — | Seguidores a leer con hover. **Para la tarea de Benford usa 300** (o `--max-cuentas 300`) |
| `SEGUNDOS_POR_CUENTA` | (2,0–3,2) s | Tiempo total por cuenta. Bajarlo aumenta el riesgo de bloqueo |
| `HOVER_TIMEOUT_S` / `MODAL_TIMEOUT_S` | 5 / 20 s | Espera máxima de la tarjeta y del modal |
| `PAUSA_LARGA_CADA`, `PAUSA_LARGA` | 40, (6–12) s | Pausas largas periódicas |
| `FRENO_TRAS_SALTADAS`, `PAUSA_FRENO` | 3, (30–60) s | Freno ante posibles límites de Instagram |
| `GEMINI_MODEL_DEFAULT` | — | Modelo si `.env` no define `GEMINI_MODEL` |
| `GEMINI_TEMPERATURE` | 0,3 | Respuestas más consistentes |
| `GEMINI_THINKING_LEVEL` | `"low"` | Nivel de razonamiento del modelo (`minimal`, `low`, `medium` o `high`) |
| `GEMINI_TIMEOUT_S` | 120 s | Tiempo máximo por intento |
| `GEMINI_MAX_RETRIES`, `GEMINI_RETRY_BASE_S` | 3, 10 s | Reintentos con espera exponencial |
| `MAX_POSTS_TO_SEND`, `MAX_CAPTION_CHARS` | 150, 600 | Límite de datos enviados (tokens) |

---

## Códigos de salida

| Código | Script | Significado |
|:---:|---|---|
| 0 | todos | OK |
| 1 | todos | Error genérico (en Benford: CSV sin cuentas válidas) |
| 2 | `main.py` | Problema con `cookies.json` (no existe, es inválido o falta una cookie obligatoria) |
| 3 | `main.py` | Sesión de Instagram inválida, caducada o con *checkpoint* |
| 4 | `main.py` | Límite de peticiones (rate limit) de Instagram |
| 5 | `main.py` | Perfil no encontrado |
| 6 | `analyze.py` | Falta `GEMINI_API_KEY` |
| 7 | `analyze.py` | `output.json` inexistente, vacío o inválido, datos insuficientes, o anonimización fallida |
| 8 | `analyze.py` | Límite de uso de Gemini (429) tras los reintentos |
| 9 | `analyze.py` | Error de la API de Gemini (key inválida, modelo inexistente o servidor saturado) |
| 10 | `analyze.py` | La respuesta de Gemini no cumple el esquema JSON |

---

## Solución de problemas

| Mensaje o síntoma | Causa probable | Solución |
|---|---|---|
| `No se encontró el enlace de seguidores` | Cambió el HTML de Instagram o el perfil es privado | Revisa la captura y el HTML en `debug/` |
| `El modal de seguidores no cargó` | Conexión lenta o Instagram no abrió la lista | Vuelve a intentarlo; sube `MODAL_TIMEOUT_S` |
| Muchas cuentas **saltadas** | Instagram está limitando las tarjetas | Sube `SEGUNDOS_POR_CUENTA` y espera un rato antes de repetir |
| Código 3 o *checkpoint* | Las cookies caducaron | Inicia sesión otra vez y exporta un `cookies.json` nuevo |
| `503 Service Unavailable` en Gemini | Servidores de Google saturados | El programa reintenta solo; si persiste, cambia `GEMINI_MODEL` a un *flash-lite* |
| Gemini tarda varios minutos | Modelo con mucho razonamiento | Usa un modelo *flash-lite* o deja `GEMINI_THINKING_LEVEL = "low"` |
| `La anonimización dejó datos identificables` | Quedó un dato crítico en el texto | Revisa `Perfil_01_datos_enviados.json` con `--dry-run` |
| `No existe seguidores.csv` | No se ejecutó el scraper con `MAX_CUENTAS > 0` | `python main.py <usuario> --max-cuentas 300` |

---

## Consideraciones éticas y limitaciones

### Consentimiento

> **[COMPLETAR antes de entregar]** Indicar la situación del perfil analizado: si
> pertenece a un integrante del grupo, si su titular dio permiso expreso (y cómo),
> o si se cambiará por el perfil de un integrante.

Solo deben analizarse perfiles con el consentimiento de su titular. El scraping
automatizado puede ir en contra de los términos de uso de Instagram. Úsalo con
moderación y solo con fines académicos.

### Big Five: no es un diagnóstico psicológico

Los puntajes los genera un modelo de lenguaje a partir de muy poca información. No
tienen validez clínica, no reemplazan a un test psicométrico validado (como el
NEO-PI-R o el BFI) y no deben usarse para tomar decisiones sobre una persona.
Instagram muestra una imagen **seleccionada y editada** de la persona. Además, solo
se analizan texto y metadatos (no las imágenes), y el propio modelo puede tener sesgos.

### Benford: un indicio, no una prueba

- La muestra son los **primeros** seguidores que muestra la lista, no una muestra
  aleatoria de todos los seguidores.
- Instagram redondea los números grandes ("1,2 mil"). El primer dígito casi siempre
  se conserva, así que el efecto es mínimo.
- Benford funciona mejor con **muestras grandes (100 o más)** y datos que abarcan
  **varios órdenes de magnitud**.
- Que los datos no sigan Benford sugiere revisar el perfil, pero **no demuestra** por
  sí solo que haya bots.

### Datos de terceros

`seguidores.csv` contiene nombres de usuario de **otras personas** (los seguidores).
Por eso está en `.gitignore`, **nunca se envía a Gemini** y solo se usa para el
análisis estadístico agregado.

### Anonimización antes de Gemini

`analysis/prepare.py`:

- **Elimina** el usuario, el nombre completo, el `user_id`, la foto y el enlace del perfil,
  y la URL, el shortcode, el ID y la imagen de cada publicación.
- **Reemplaza** el usuario y el nombre (también dentro de captions y hashtags, sin
  importar mayúsculas, tildes ni puntos) por `Perfil_01`.
- **Reemplaza** las menciones a otras cuentas por `@usuario_1`, `@usuario_2`… y los
  enlaces, emails y teléfonos por `[enlace]`, `[email]` y `[telefono]`.
- **Envía las fechas solo como `AAAA-MM-DD`** (sin hora). Las franjas horarias van
  agregadas en las estadísticas.
- **Verifica el resultado** antes de enviar (ver [Parte 2](#parte-2-análisis-big-five-con-gemini)).

**Limitación:** los nombres de *otras* personas escritos en texto libre, sin `@`, no
se detectan automáticamente. Revisa `Perfil_01_datos_enviados.json` con `--dry-run`
antes del análisis real.

### Política de datos del plan gratuito de Gemini

Según los [términos adicionales de la API de Gemini](https://ai.google.dev/gemini-api/terms),
en los servicios **gratuitos** Google usa el contenido enviado y las respuestas para
mejorar sus productos, y **revisores humanos pueden leerlo**. Además, recomienda
expresamente *no enviar información sensible, confidencial o personal*. Por eso este
proyecto anonimiza los datos antes de enviarlos y llama a la API con `store=False`.

---

## Integrantes

| Nombre | Rol |
|---|---|
| [COMPLETAR] | [COMPLETAR] |
| [COMPLETAR] | [COMPLETAR] |
| [COMPLETAR] | [COMPLETAR] |
