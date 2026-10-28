"""Ley de Benford aplicada al número de seguidores de los seguidores de un perfil.

NO hace scraping: lee el CSV (usuario, seguidores) que genera main.py en el mismo
recorrido del scraper. Así se puede repetir el análisis sin volver a abrir Instagram.

Uso:
    python benford_seguidores.py                         # usa seguidores.csv
    python benford_seguidores.py --csv otro.csv --png grafico.png --informe informe.md

Pasos:
  1. Leer el CSV y quedarse con el PRIMER dígito de cada número de seguidores.
  2. Tabla: dígito 1-9, cantidad observada, % observado, % esperado por Benford y diferencia.
  3. Gráfico de barras (observado) con la curva esperada de Benford -> PNG.
  4. Prueba chi-cuadrado (8 grados de libertad, alfa = 0.05).
  5. Conclusión automática: ¿los seguidores parecen orgánicos o hay posibles bots?
  6. Informe en Markdown (resultados/benford_informe.md) con el gráfico y un análisis
     escrito de los resultados, para leerlo o adjuntarlo sin depender de la consola.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # dibuja directamente a archivo, sin abrir ventanas
import matplotlib.pyplot as plt  # noqa: E402
from scipy import stats  # noqa: E402

import config  # noqa: E402
from models import ScrapeResult  # noqa: E402

DIGITOS = range(1, 10)
ALFA = 0.05                  # nivel de significancia
GRADOS_LIBERTAD = 8          # 9 dígitos - 1
MUESTRA_MINIMA = 100         # con menos cuentas Benford no es confiable
PNG_POR_DEFECTO = config.RESULTS_DIR / "benford_seguidores.png"
INFORME_POR_DEFECTO = config.RESULTS_DIR / "benford_informe.md"


# ---------------------------------------------------------------------- 1. datos
def leer_seguidores(ruta: Path) -> list[int]:
    """Lee la columna 'seguidores' del CSV. Ignora filas vacías o no numéricas."""
    if not ruta.exists():
        sys.exit(f"No existe {ruta}. Ejecuta primero el scraper: python main.py")
    valores = []
    with ruta.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            try:
                valores.append(int(fila["seguidores"]))
            except (KeyError, TypeError, ValueError):
                continue
    return valores


def primer_digito(numero: int) -> int:
    """Primer dígito significativo: 1234 -> 1, 87 -> 8."""
    return int(str(numero)[0])


def benford_esperado(d: int) -> float:
    """Probabilidad de que el primer dígito sea d según Benford: log10(1 + 1/d)."""
    return math.log10(1 + 1 / d)


# ---------------------------------------------------------------------- 2. tabla
def construir_tabla(valores: list[int]) -> list[dict[str, float]]:
    """Para cada dígito: observados, % observado, % esperado y diferencia (puntos %)."""
    # El 0 no tiene primer dígito significativo: esas cuentas no entran en Benford.
    positivos = [v for v in valores if v > 0]
    n = len(positivos)
    conteo = {d: 0 for d in DIGITOS}
    for v in positivos:
        conteo[primer_digito(v)] += 1

    tabla = []
    for d in DIGITOS:
        pct_obs = 100 * conteo[d] / n if n else 0.0
        pct_esp = 100 * benford_esperado(d)
        tabla.append({"digito": d, "observado": conteo[d], "pct_observado": pct_obs,
                      "pct_esperado": pct_esp, "diferencia": pct_obs - pct_esp})
    return tabla


def imprimir_tabla(tabla: list[dict[str, float]]) -> None:
    print(f"\n{'Dígito':>6} | {'Observado':>9} | {'% Obs.':>7} | {'% Benford':>9} | {'Dif.':>7}")
    print("-" * 52)
    for fila in tabla:
        print(f"{fila['digito']:>6} | {fila['observado']:>9} | {fila['pct_observado']:>6.2f}% | "
              f"{fila['pct_esperado']:>8.2f}% | {fila['diferencia']:>+6.2f}")


# ---------------------------------------------------------------------- 3. gráfico
def guardar_grafico(tabla: list[dict[str, float]], n: int, ruta: Path) -> None:
    digitos = [f["digito"] for f in tabla]
    ruta.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(digitos, [f["pct_observado"] for f in tabla], color="#4C72B0",
           label=f"Observado (n = {n})")
    ax.plot(digitos, [f["pct_esperado"] for f in tabla], color="#DD8452", marker="o",
            linewidth=2, label="Esperado (Benford)")
    ax.set_xticks(digitos)
    ax.set_xlabel("Primer dígito del número de seguidores")
    ax.set_ylabel("Porcentaje de cuentas (%)")
    ax.set_title("Ley de Benford: seguidores de los seguidores")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------- 4. chi-cuadrado
def prueba_chi_cuadrado(tabla: list[dict[str, float]]) -> tuple[float, float, float]:
    """Devuelve (chi2, p_valor, valor_critico).

    Compara las cantidades observadas con las esperadas (n * probabilidad de Benford).
    scipy usa k - 1 = 8 grados de libertad para 9 categorías."""
    observados = [f["observado"] for f in tabla]
    n = sum(observados)
    esperados = [n * benford_esperado(f["digito"]) for f in tabla]
    chi2, p_valor = stats.chisquare(observados, esperados)
    valor_critico = stats.chi2.ppf(1 - ALFA, GRADOS_LIBERTAD)  # ≈ 15.51
    return float(chi2), float(p_valor), float(valor_critico)


# ---------------------------------------------------------------------- 5. conclusión
def conclusion(p_valor: float) -> str:
    if p_valor > ALFA:
        return ("Los datos SE AJUSTAN a la ley de Benford (p > 0.05): "
                "los seguidores parecen reales/orgánicos.")
    return ("Los datos NO se ajustan a la ley de Benford (p <= 0.05): "
            "posible presencia de bots o seguidores falsos.")


# ---------------------------------------------------------------------- 6. informe
def leer_contexto() -> tuple[str | None, int | None]:
    """Perfil analizado y cuentas saltadas, tomados de output.json si existe."""
    try:
        resultado = ScrapeResult.model_validate_json(
            config.OUTPUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    return resultado.profile.username, resultado.cuentas_saltadas


def _miles(numero: int) -> str:
    """1234567 -> '1.234.567' (separador de miles en español)."""
    return f"{numero:,}".replace(",", ".")


def generar_informe(valores: list[int], tabla: list[dict[str, float]], chi2: float,
                    p_valor: float, critico: float, ruta_png: Path, ruta_md: Path,
                    usar_contexto: bool = True) -> str:
    """Arma el informe en Markdown: datos, tabla, gráfico y análisis escrito.

    ``usar_contexto``: añadir perfil y cuentas saltadas desde output.json (solo tiene
    sentido si el CSV es el que generó ese mismo scraping)."""
    positivos = [v for v in valores if v > 0]
    n = len(positivos)
    perfil, saltadas = leer_contexto() if usar_contexto else (None, None)
    # Órdenes de magnitud que cubren los datos: Benford necesita que los números
    # abarquen varios (p. ej. de decenas a cientos de miles).
    ordenes = math.log10(max(positivos) / min(positivos)) if n > 1 else 0.0
    d1 = tabla[0]
    mayores = sorted(tabla, key=lambda f: abs(f["diferencia"]), reverse=True)[:2]
    # En Benford la frecuencia baja del 1 al 9: se buscan los dígitos que "suben".
    saltos = [f["digito"] for anterior, f in zip(tabla, tabla[1:])
              if f["pct_observado"] > anterior["pct_observado"]]
    ajusta = p_valor > ALFA

    lineas = ["# Ley de Benford aplicada a los seguidores", "",
              f"*Generado el {datetime.now():%Y-%m-%d %H:%M}*", "", "## Datos", ""]
    if perfil:
        lineas.append(f"- **Perfil analizado:** @{perfil} (seguidores de sus seguidores)")
    lineas += [f"- **Cuentas en el CSV:** {len(valores)}",
               f"- **Cuentas usadas** (con al menos 1 seguidor): {n}"]
    if saltadas is not None:
        lineas.append(f"- **Cuentas saltadas** (la tarjeta emergente no cargó): {saltadas}")
    lineas += [f"- **Rango:** de {_miles(min(positivos))} a {_miles(max(positivos))} "
               f"seguidores (≈ {ordenes:.1f} órdenes de magnitud)",
               "", "## Tabla por dígito", "",
               "| Dígito | Observado | % observado | % Benford | Diferencia |",
               "|:-:|--:|--:|--:|--:|"]
    for f in tabla:
        lineas.append(f"| {f['digito']} | {f['observado']} | {f['pct_observado']:.2f} % | "
                      f"{f['pct_esperado']:.2f} % | {f['diferencia']:+.2f} |")

    # El gráfico se enlaza con ruta relativa al informe (si están en carpetas compatibles).
    imagen = ruta_png.resolve()
    try:
        imagen = imagen.relative_to(ruta_md.resolve().parent)
    except ValueError:
        pass
    lineas += ["", "## Gráfico", "", f"![Observado vs. Benford]({imagen.as_posix()})", ""]

    # --- Análisis escrito -------------------------------------------------------
    lineas += ["## Análisis", ""]
    comparacion = "más" if d1["diferencia"] > 0 else "menos"
    lineas += [
        f"**Dígito 1.** Es el más importante de la ley: Benford espera que cerca del "
        f"{d1['pct_esperado']:.1f} % de los números empiece por 1. En la muestra empiezan por 1 "
        f"el {d1['pct_observado']:.1f} % de las cuentas, {abs(d1['diferencia']):.1f} puntos "
        f"{comparacion} de lo esperado.", ""]
    desvios = "; ".join(
        f"el **{f['digito']}** ({f['pct_observado']:.1f} % frente a {f['pct_esperado']:.1f} %, "
        f"{'exceso' if f['diferencia'] > 0 else 'déficit'} de {abs(f['diferencia']):.1f} puntos)"
        for f in mayores)
    lineas += [f"**Mayores desviaciones.** Los dígitos que más se alejan de Benford son "
               f"{desvios}.", ""]
    if saltos:
        lineas.append(
            "**Forma de la distribución.** En Benford la frecuencia debería bajar de forma "
            "continua del 1 al 9. En estos datos esa tendencia se rompe en "
            + (f"el dígito {saltos[0]}, que aparece" if len(saltos) == 1 else
               f"los dígitos {', '.join(map(str, saltos))}, que aparecen")
            + " más que el dígito anterior.")
    else:
        lineas.append(
            "**Forma de la distribución.** La frecuencia baja de forma continua del 1 al 9, "
            "que es justamente la forma que predice Benford.")
    lineas += ["",
               f"**Prueba chi-cuadrado.** χ² = {chi2:.2f} con {GRADOS_LIBERTAD} grados de "
               f"libertad; el valor crítico para α = {ALFA} es {critico:.2f} y el p-valor es "
               f"{p_valor:.4f}. "
               + ("Como χ² es menor que el valor crítico (p > 0.05), las diferencias "
                  "observadas se pueden explicar por azar." if ajusta else
                  "Como χ² supera el valor crítico (p ≤ 0.05), las diferencias son demasiado "
                  "grandes para explicarlas solo por azar."),
               "", "## Conclusión", "", f"**{conclusion(p_valor)}**", "",
               "## Limitaciones", ""]

    # --- Limitaciones -----------------------------------------------------------
    if n < MUESTRA_MINIMA:
        lineas.append(f"- **Muestra pequeña:** solo {n} cuentas (se recomiendan al menos "
                      f"{MUESTRA_MINIMA}). Con pocos datos el resultado no es confiable.")
    if ordenes < 2:
        lineas.append(f"- **Poco rango:** los datos cubren solo {ordenes:.1f} órdenes de "
                      "magnitud; Benford funciona mejor cuando abarcan varios.")
    lineas += [
        '- Instagram redondea los números grandes ("1,2 mil"), pero el primer dígito casi '
        "siempre se conserva, así que el efecto en el análisis es mínimo.",
        "- La muestra son los primeros seguidores que muestra la lista, no una muestra "
        "aleatoria de todos.",
        "- Benford es un **indicio**, no una prueba: un desajuste sugiere revisar el perfil, "
        "pero no demuestra por sí solo que haya bots.", ""]
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ley de Benford sobre seguidores")
    parser.add_argument("--csv", type=Path, default=config.SEGUIDORES_CSV)
    parser.add_argument("--png", type=Path, default=PNG_POR_DEFECTO)
    parser.add_argument("--informe", type=Path, default=INFORME_POR_DEFECTO,
                        help="informe en Markdown con el análisis escrito")
    args = parser.parse_args(argv)

    valores = leer_seguidores(args.csv)
    tabla = construir_tabla(valores)
    n = sum(f["observado"] for f in tabla)
    if n == 0:
        print("El CSV no tiene cuentas con seguidores > 0; no hay nada que analizar.")
        return 1

    print(f"Cuentas en el CSV: {len(valores)} | usadas (seguidores > 0): {n}")
    imprimir_tabla(tabla)

    guardar_grafico(tabla, n, args.png)
    print(f"\nGráfico guardado en {args.png}")

    chi2, p_valor, critico = prueba_chi_cuadrado(tabla)
    print(f"\nChi-cuadrado = {chi2:.2f} | valor crítico (gl = {GRADOS_LIBERTAD}, "
          f"alfa = {ALFA}) = {critico:.2f} | p-valor = {p_valor:.4f}")
    print(f"\nCONCLUSIÓN: {conclusion(p_valor)}")
    if n < MUESTRA_MINIMA:
        print(f"ADVERTENCIA: la muestra tiene solo {n} cuentas (< {MUESTRA_MINIMA}); "
              "con tan pocos datos la ley de Benford no es confiable.")

    args.informe.parent.mkdir(parents=True, exist_ok=True)
    args.informe.write_text(
        generar_informe(valores, tabla, chi2, p_valor, critico, args.png, args.informe,
                        usar_contexto=args.csv.resolve() == config.SEGUIDORES_CSV.resolve()),
        encoding="utf-8")
    print(f"\nInforme con el análisis escrito: {args.informe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
