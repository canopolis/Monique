"""Lee una factura electronica de Factura Dominicana (GTI) en PDF."""
import re, datetime

NUM = re.compile(r"^-?[\d,]+(\.\d+)?$")
FECHA = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
TIPO_NCF = {"E31": 1, "E32": 2, "E44": 14, "E45": 15, "E46": 16}


def _num(s):
    return float(s.replace(",", ""))


def _fecha(s):
    m = FECHA.search(s or "")
    return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def leer_gti(ruta):
    from pypdf import PdfReader
    r = PdfReader(ruta)
    texto = "\n".join(p.extract_text() or "" for p in r.pages)
    L = [x.strip() for x in texto.splitlines()]
    L = [x for x in L if x]

    def despues(etiqueta, desde=0, patron=None):
        for i in range(desde, len(L)):
            if L[i].rstrip(":").strip().lower() == etiqueta.lower().rstrip(":") or L[i].lower().startswith(etiqueta.lower()):
                resto = L[i][len(etiqueta):].strip(" :")
                cands = ([resto] if resto else []) + L[i + 1:i + 4]
                for c in cands:
                    if patron is None or re.search(patron, c):
                        return c, i
                return "", i
        return "", -1

    d = {}
    d["ncf"], _ = despues("e-NCF", patron=r"^E\d{12}$")
    d["fecha"] = _fecha(despues("Fecha Emisión", patron=FECHA.pattern)[0])
    d["vence"] = _fecha(despues("Fecha Limite Pago", patron=FECHA.pattern)[0]) or d["fecha"]
    nombre, ic = despues("Cliente:")
    d["cliente_nombre"] = nombre
    d["rnc"] = despues("RNC:", ic, r"^\d{9,11}$")[0] if ic >= 0 else ""
    d["emisor_rnc"] = despues("RNC:", 0, r"^\d{9,11}$")[0] if "Emisor:" in L else ""
    if ic >= 0:
        ie = L.index("Emisor:") if "Emisor:" in L else -1
        if ie >= 0:
            d["emisor_rnc"] = despues("RNC:", ie, r"^\d{9,11}$")[0]
    d["codigo_seguridad"] = despues("Código Seguridad", patron=r"^\S+$")[0]
    d["fecha_firma"] = despues("Fecha de Firma Digital", patron=FECHA.pattern)[0]
    d["subtotal"] = _num(despues("Subtotal:", patron=NUM.pattern)[0] or "0")
    d["itbis"] = _num(despues("ITBIS:", patron=NUM.pattern)[0] or "0")
    d["total"] = _num(despues("Total:", patron=NUM.pattern)[0] or "0")
    d["interno"] = despues("Número de Factura Interno", patron=r"^\d+$")[0]
    # productos: No, Codigo, Descripcion (1+ lineas), Cantidad, Precio, Descuento, Total Item
    items = []
    try:
        i = L.index("Total Item") + 1
    except ValueError:
        i = len(L)
    while i < len(L) and re.fullmatch(r"\d+", L[i]):
        try:
            code = L[i + 1]; j = i + 2; desc = []
            while j < len(L) and not NUM.match(L[j]):
                desc.append(L[j]); j += 1
            qty, price, dsc, tot = (_num(L[j + k]) for k in range(4))
        except (IndexError, ValueError):
            break
        items.append(dict(code=code, descr=" ".join(desc).strip(), qty=qty, price=price, descuento=dsc, total=tot))
        i = j + 4
    if not items:
        # formato con cada producto en una sola linea: No Codigo Descripcion Cantidad Precio Descuento Total
        fila = re.compile(r"^(\d+)\s+(\S+)\s+(.*?)\s+(-?[\d,]+(?:\.\d+)?)\s+(-?[\d,]+(?:\.\d+)?)\s+"
                          r"(-?[\d,]+(?:\.\d+)?)\s+(-?[\d,]+(?:\.\d+)?)$")
        ini = next((k + 1 for k, x in enumerate(L) if "Total Item" in x), None)
        if ini is not None:
            for x in L[ini:]:
                m = fila.match(x.strip())
                if not m:
                    break
                items.append(dict(code=m.group(2), descr=m.group(3).strip(), qty=_num(m.group(4)), price=_num(m.group(5)),
                                  descuento=_num(m.group(6)), total=_num(m.group(7))))
    d["items"] = items
    # codigo QR: la imagen cuadrada mas grande de la factura
    qr = None; mejor = 0
    for p in r.pages:
        for im in p.images:
            try:
                w, h = im.image.size
            except Exception:
                continue
            if abs(w - h) <= 2 and w > mejor:
                mejor = w; qr = im
    if qr is not None:
        import io
        b = io.BytesIO(); qr.image.convert("RGB").save(b, "PNG"); d["qr"] = b.getvalue()
    else:
        d["qr"] = None
    d["tipo"] = TIPO_NCF.get((d["ncf"] or "")[:3], 0)
    return d
