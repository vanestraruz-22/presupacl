"""calculadora_cotizacion: importes, subtotal, utilidad, IVA y total (RF-08, HU-08).

Todo el dinero se maneja en centavos (int) y las cantidades en milésimas (int);
las tasas son texto decimal ("0.16") y se operan con Decimal. Nunca se usa float.

SUPUESTOS — validar con ACL (D01):
- Redondeo: al centavo, mitad hacia arriba (ROUND_HALF_UP), en cada importe,
  en la utilidad y en el IVA.
- Recargo: utilidad = subtotal × tasa.
- Margen: precio de venta = subtotal ÷ (1 − tasa); utilidad = venta − subtotal.
- IVA = (subtotal + utilidad) × tasa de IVA. Total = subtotal + utilidad + IVA.
- Límites (D07): precio unitario hasta 10,000,000.00 y cantidad hasta 100,000.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PRECIO_MAXIMO_CENTAVOS = 1_000_000_000  # 10,000,000.00
CANTIDAD_MAXIMA_MILESIMAS = 100_000_000  # 100,000 unidades


class ErrorCalculo(Exception):
    """Dato numérico inválido; no se calcula ni se guarda un total (CA-46)."""


def _redondear(valor):
    return int(Decimal(valor).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _decimal(texto, nombre):
    if isinstance(texto, bool):
        raise ErrorCalculo(f"{nombre}: valor no numérico.")
    limpio = str(texto if texto is not None else "").strip().replace(",", "").replace("$", "")
    try:
        valor = Decimal(limpio)
    except InvalidOperation:
        raise ErrorCalculo(f"{nombre}: «{texto}» no es un número válido.") from None
    if not valor.is_finite():
        raise ErrorCalculo(f"{nombre}: «{texto}» no es un número válido.")
    if abs(valor) > 10**12:
        raise ErrorCalculo(f"{nombre}: excede el máximo permitido.")
    return valor


def texto_a_centavos(texto, nombre="Precio"):
    """'1,500.50' -> 150050. Acepta hasta 2 decimales, no negativos."""
    valor = _decimal(texto, nombre)
    if valor < 0:
        raise ErrorCalculo(f"{nombre}: no puede ser negativo.")
    if valor != valor.quantize(Decimal("0.01")):
        raise ErrorCalculo(f"{nombre}: use como máximo dos decimales.")
    centavos = int(valor * 100)
    if centavos > PRECIO_MAXIMO_CENTAVOS:
        raise ErrorCalculo(f"{nombre}: excede el máximo permitido.")
    return centavos


def texto_a_milesimas(texto, nombre="Cantidad"):
    """'2.5' -> 2500. Mayor que cero y hasta 3 decimales (CA-16, CA-43)."""
    valor = _decimal(texto, nombre)
    if valor <= 0:
        raise ErrorCalculo(f"{nombre}: debe ser mayor que cero.")
    if valor != valor.quantize(Decimal("0.001")):
        raise ErrorCalculo(f"{nombre}: use como máximo tres decimales.")
    milesimas = int(valor * 1000)
    if milesimas > CANTIDAD_MAXIMA_MILESIMAS:
        raise ErrorCalculo(f"{nombre}: excede el máximo permitido.")
    return milesimas


def tasa_valida(texto, nombre="Tasa"):
    valor = _decimal(texto, nombre)
    if valor < 0 or valor >= 1:
        raise ErrorCalculo(f"{nombre}: debe ser una fracción entre 0 y 1 (ej. 0.16).")
    return valor


def importe_centavos(cantidad_milesimas, precio_unitario_centavos):
    """cantidad × precio, redondeado al centavo (CA-13, CA-42)."""
    for nombre, valor in (("Cantidad", cantidad_milesimas), ("Precio", precio_unitario_centavos)):
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise ErrorCalculo(f"{nombre}: valor no numérico.")
    if cantidad_milesimas <= 0:
        raise ErrorCalculo("Cantidad: debe ser mayor que cero.")
    if precio_unitario_centavos < 0:
        raise ErrorCalculo("Precio: no puede ser negativo.")
    return _redondear(Decimal(cantidad_milesimas) * precio_unitario_centavos / 1000)


def calcular(partidas, metodo_utilidad, utilidad_tasa, iva_tasa):
    """Calcula la cotización completa.

    partidas: lista de dicts con cantidad_milesimas y precio_unitario_centavos.
    Regresa {"importes": [...], "subtotal_centavos", "utilidad_centavos",
    "iva_centavos", "total_centavos"}. Lanza ErrorCalculo ante cualquier dato inválido.
    """
    utilidad = tasa_valida(utilidad_tasa, "Utilidad")
    iva = tasa_valida(iva_tasa, "IVA")
    importes = [importe_centavos(p["cantidad_milesimas"], p["precio_unitario_centavos"]) for p in partidas]
    subtotal = sum(importes)

    if metodo_utilidad == "recargo":
        utilidad_centavos = _redondear(subtotal * utilidad)
    elif metodo_utilidad == "margen":
        utilidad_centavos = _redondear(Decimal(subtotal) / (1 - utilidad) - subtotal)
    else:
        raise ErrorCalculo("Método de utilidad desconocido; use margen o recargo.")

    iva_centavos = _redondear((subtotal + utilidad_centavos) * iva)
    return {
        "importes": importes,
        "subtotal_centavos": subtotal,
        "utilidad_centavos": utilidad_centavos,
        "iva_centavos": iva_centavos,
        "total_centavos": subtotal + utilidad_centavos + iva_centavos,
    }


def formato_moneda(centavos, moneda="MXN"):
    """150050 -> '$1,500.50 MXN'."""
    signo = "-" if centavos < 0 else ""
    centavos = abs(centavos)
    return f"{signo}${centavos // 100:,}.{centavos % 100:02d} {moneda}".strip()


def formato_cantidad(milesimas):
    """2500 -> '2.5'; 1000 -> '1'."""
    entero, fraccion = divmod(milesimas, 1000)
    return f"{entero:,}" + (f".{fraccion:03d}".rstrip("0") if fraccion else "")
