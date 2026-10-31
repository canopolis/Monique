"""Genera la factura en PDF con el mismo formato que imprime Monica 8.5."""
import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from numletras import monto_letras
from db import TIPOS, parse_date

H = 792
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
LINEAS_POR_PAGINA = 20
TR, TB, TBI, HB = "Times-Roman", "Times-Bold", "Times-BoldItalic", "Helvetica-Bold"


def fecha_larga(s):
    d = parse_date(s) if isinstance(s, str) else s
    if not d:
        return ""
    return f"{d.day} de {MESES[d.month-1]} {d.year}"


def n2(v):
    return f"{v:,.2f}"


class P:
    def __init__(self, c):
        self.c = c

    def t(self, x, top, text, font=TR, size=10, align="l"):
        if text is None or text == "":
            return
        text = str(text)
        y = H - top - size * 0.80
        self.c.setFont(font, size)
        if align == "r":
            self.c.drawRightString(x, y, text)
        elif align == "c":
            self.c.drawCentredString(x, y, text)
        else:
            self.c.drawString(x, y, text)

    def box(self, x0, t0, x1, t1, fill=False):
        self.c.roundRect(x0, H - t1, x1 - x0, t1 - t0, 7, stroke=1, fill=1 if fill else 0)

    def line(self, x0, t0, x1, t1):
        self.c.line(x0, H - t0, x1, H - t1)


def fit(text, font, size, width):
    text = text or ""
    while text and stringWidth(text, font, size) > width:
        text = text[:-1]
    return text


def titulo_factura(tipo):
    return TIPOS.get(tipo, TIPOS[0])[1]


def _bloque_ecf(c, p, h):
    """QR y validaciones de la factura electronica, debajo de RECIBIDO CONFORME."""
    try:
        qr, cod, firma = h["ecf_qr"], h["ecf_cod"], h["ecf_firma"]
    except (IndexError, KeyError):
        return
    if not (qr or cod or firma):
        return
    top = 640
    if qr:
        import io
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(io.BytesIO(qr)), 32, H - top - 78, 78, 78)
    x = 118 if qr else 32
    if cod: p.t(x, top + 46, f"Código Seguridad: {cod}", HB, 8)
    if firma: p.t(x, top + 58, f"Fecha de Firma Digital: {firma}", HB, 8)


def generar_factura(db, nro, ruta):
    h, lines, comments = db.invoice_full(nro)
    tit = titulo_factura(h["tipo"] if h["ncf"] else 0)
    mensajes = [db.cfg(k).strip() for k in ("msg_fact1", "msg_fact2", "msg_fact3") if db.cfg(k).strip()]
    return _render(db, h, lines, comments, ruta, tit, f"NRO. {nro}", h["ncf"], f"Factura {nro}", mensajes=mensajes)


def generar_conduce(db, nro, ruta):
    h, lines, comments = db.odoc_full("G", nro)
    return _render(db, h, lines, comments, ruta, "CONDUCE", str(nro), "", f"Conduce {nro}", num_size=14)


def generar_nota(db, kind, nro, ruta):
    """Nota de credito (NC) o de debito (ND), con el formato de la factura."""
    h, lines, comments = db.odoc_full(kind, nro)
    tit = "NOTA DE CREDITO" if kind == "NC" else "NOTA DE DEBITO"
    inv = db.one("SELECT ncf FROM invoices WHERE nro=?", (h["factura"],)) if h["factura"] else None
    extra = f"Afecta la factura {h['factura']}" + (f"   NCF modificado: {inv['ncf']}" if inv and inv["ncf"] else "")
    if kind == "NC":
        extra += "   (con devolución de productos)" if h["status"] == "Con devolución" else ""
    return _render(db, h, lines, comments, ruta, tit, f"NRO. {nro}", h["ncf"], f"{tit.title()} {nro}", extra=extra)


def _render(db, h, lines, comments, ruta, tit, numtxt, ncf, doc_title, num_size=12, extra="", mensajes=()):
    cfg = db.cfg
    nro = h["nro"]
    # filas: lineas de producto seguidas de sus comentarios (posicion = nro de linea)
    filas = []
    com_by_pos = {}
    for cm in comments:
        com_by_pos.setdefault(cm["pos"], []).append(cm["text"])
    for l in lines:
        filas.append(("L", l))
        for txt in com_by_pos.pop(l["pos"], []):
            filas.append(("C", txt))
    for pos in sorted(com_by_pos):
        for txt in com_by_pos[pos]:
            filas.append(("C", txt))
    for m in mensajes:   # mensajes de factura (Configuracion), debajo del ultimo producto
        filas.append(("C", m))
    paginas = [filas[i:i + LINEAS_POR_PAGINA] for i in range(0, max(len(filas), 1), LINEAS_POR_PAGINA)] or [[]]

    c = canvas.Canvas(ruta, pagesize=letter)
    c.setTitle(doc_title)
    c.setLineWidth(0.8)
    for npag, filas_pag in enumerate(paginas, 1):
        p = P(c)
        # --- empresa ---
        p.t(30, 30, cfg("emp_nombre"), TBI, 22)
        for i, k in enumerate(("emp_l1", "emp_l2", "emp_l3", "emp_l4", "emp_l5")):
            p.t(30, 53 + i * 11.7, cfg(k), TR, 10)
        # --- NCF, titulo y numero ---
        if ncf:
            p.t(585, 54, "NCF:" + ncf, TB, 10, "r")
        p.box(413, 64, 585, 121)
        p.line(414, 93, 586, 93)
        if stringWidth(tit, TB, 11) > 160:
            partes = tit.rsplit(" ", 1)
            p.t(509, 69, partes[0], TB, 11, "c")
            p.t(499, 81, partes[1], TB, 11, "c")
        else:
            p.t(499, 69, tit, TB, 11, "c")
        p.t(499, 99, numtxt, TB, num_size, "c")
        # --- cliente ---
        p.box(35, 124, 303, 213)
        p.t(43, 126, "Cliente:", HB, 9)
        p.t(42, 138, fit(h["name"], TB, 10, 255), TB, 10)
        for i, k in enumerate(("dir1", "dir2", "dir3")):
            p.t(42, 150 + i * 12, fit(h[k], TB, 10, 255), TB, 10)
        p.t(42, 186, "Reg. Tribut.:", TB, 10)
        p.t(101, 186, h["rnc"], TB, 10)
        p.t(42, 198, "Código clte.:", TB, 10)
        p.t(101, 198, h["client"], TB, 10)
        # --- datos factura ---
        p.box(308, 124, 587, 213)
        p.line(308, 164, 587, 164)
        p.line(308, 187, 587, 187)
        p.line(451, 124, 451, 213)
        p.t(314, 127, "Lugar y fecha de expedición:", HB, 9)
        p.t(456, 127, "Vencimiento:", HB, 9)
        p.t(312, 140, cfg("lugar"), TB, 10)
        p.t(312, 152, fecha_larga(h["date"]), TB, 10)
        p.t(458, 143, fecha_larga(h["due"]), TB, 10)
        p.t(312, 171, "Vendedor:", HB, 9)
        p.t(357, 171, h["seller"], TB, 10)
        p.t(455, 171, "Condiciones:", HB, 9)
        p.t(519, 171, h["terms"], TB, 10)
        p.t(312, 192, "Refer.:", HB, 9)
        p.t(345, 194, fit(h["ref"], TB, 10, 100), TB, 10)
        p.t(455, 193, "Envío:", HB, 9)
        p.t(518, 194, h["ship_via"], TB, 10)
        # --- encabezado de lineas ---
        c.setFillColorRGB(1, 1, 1)
        p.box(38, 220, 588, 248, fill=True)
        c.setFillColorRGB(0, 0, 0)
        for x in (119, 331, 384, 475):
            p.line(x, 220, x, 248)
        p.t(41, 228, "Código producto", TR, 11)
        p.t(151, 229, "Descripción del producto", TR, 11)
        p.t(341, 229, "Cantidad", TR, 11)
        p.t(391, 229, "Precio Unit. Pesos", TR, 11)
        p.t(517, 229, "Subtotal  Pesos", TR, 11)
        # --- lineas ---
        top = 251
        for tipo_f, f in filas_pag:
            if tipo_f == "L":
                p.t(38, top, f["code"], TR, 10)
                p.t(121, top, fit(f["descr"], TR, 11, 205), TR, 11)
                p.t(380, top, n2(f["qty"]), TR, 11, "r")
                p.t(469, top, n2(f["price"]), TR, 11, "r")
                p.t(585, top, n2(f["qty"] * f["price"]), TR, 11, "r")
            else:
                p.t(121, top, fit(f, TR, 11, 460), TR, 11)
            top += 14.4
        p.line(26, 555, 590, 555)
        if extra:
            p.t(38, 538, extra, TB, 10)
        if npag == len(paginas):
            cant = sum(l["qty"] for l in lines)
            p.t(378, 563, n2(cant), TR, 11, "r")
            p.t(422, 562, "Subtotal:", TR, 11)
            p.t(585, 562, n2(h["subtotal"]), TR, 11, "r")
            if h["discount"]:
                p.t(422, 576, "Descuento:", TR, 11)
                p.t(585, 576, n2(h["discount"]), TR, 11, "r")
            p.t(443, 590, "ITBIS", TR, 11)
            p.t(585, 591, n2(h["itbis"]), TR, 11, "r")
            p.t(32, 592, h["comment1"], TR, 11)
            p.t(32, 606, h["comment2"], TR, 11)
            p.t(32, 620, h["comment3"], TR, 11)
            p.box(362, 630, 588, 658)
            p.t(368, 639, "TOTAL", TB, 11)
            p.t(431, 639, "Pesos", TR, 11)
            p.t(584, 638, n2(h["total"]), TR, 12, "r")
            p.t(584, 663, monto_letras(h["total"]), TR, 9, "r")
            _bloque_ecf(c, p, h)
        p.t(522, 767, "Página", TR, 9)
        p.t(578, 767, str(npag), TR, 9)
        c.showPage()
    c.save()
    return ruta


def generar_cotizacion(db, kind, nro, ruta):
    """Cotizacion (Q) u orden de compra (O), formato de la cotizacion de Monica."""
    h, lines, comments = db.odoc_full(kind, nro)
    cfg = db.cfg
    filas = []
    cb = {}
    for cm in comments:
        cb.setdefault(cm["pos"], []).append(cm["text"])
    for l in lines:
        filas.append(("L", l))
        for t in cb.pop(l["pos"], []):
            filas.append(("C", t))
    for pos in sorted(cb):
        filas += [("C", t) for t in cb[pos]]
    por = 24
    paginas = [filas[i:i + por] for i in range(0, max(len(filas), 1), por)] or [[]]
    titulo = "Cotización" if kind == "Q" else "Orden de Compra"
    c = canvas.Canvas(ruta, pagesize=letter); c.setTitle(f"{titulo} {nro}"); c.setLineWidth(0.8)
    for npag, fp in enumerate(paginas, 1):
        p = P(c)
        p.t(34, 23, cfg("emp_nombre"), TBI, 18)
        for i, k in enumerate(("emp_l1", "emp_l2", "emp_l3")):
            p.t(35, 42 + i * 13, cfg(k), TR, 11)
        p.t(480, 47, "Nro.", TR, 10); p.t(582, 47, nro, TR, 10, "r")
        p.t(480, 60, "Fecha", TR, 10); p.t(577, 60, fecha_corta(h["date"]), TR, 10, "r")
        p.t(477, 74, "Página", TR, 10); p.t(582, 73, npag, TR, 10, "r")
        p.t(308, 85, titulo, TBI, 16, "c")
        p.t(37, 125, "Propuesto  a:" if kind == "Q" else "Proveedor:", TR, 11)
        p.t(332, 125, "Enviado a:", TR, 10)
        p.box(33, 136, 285, 211); p.box(326, 135, 582, 210)
        p.t(39, 144, fit(h["name"], TR, 11, 240), TR, 11)
        for i, k in enumerate(("dir1", "dir2", "dir3")):
            p.t(39, 157 + i * 13.5, fit(h[k], TR, 11, 240), TR, 11)
        p.t(41, 198, "Código clte.:" if kind == "Q" else "Código prov.:", TR, 10); p.t(98, 199, h["client"], TR, 10)
        if kind == "O" and h["ship_to"]:   # en ordenes de compra es nuestra empresa; nunca el contacto del cliente
            p.t(332, 144, fit(h["ship_to"], TR, 11, 245), TR, 11)
        for i, k in enumerate(("sdir1", "sdir2", "sdir3")):
            p.t(332, 157 + i * 13.5, fit(h[k], TR, 11, 245), TR, 11)
        p.t(334, 199, "Reg. Tribut.:", TR, 10); p.t(393, 199, h["rnc"], TR, 10)
        p.box(33, 213, 582, 238)
        p.t(50, 222, "Enviar:", TR, 11); p.t(90, 222, h["ship_via"], TR, 11)
        p.t(167, 222, "Términos:", TR, 11); p.t(215, 222, h["terms"], TR, 11)
        p.t(307, 222, "Vendedor:", TR, 11); p.t(357, 222, h["seller"], TR, 11)
        p.t(447, 222, "Referencia:", TR, 11); p.t(500, 222, fit(h["ref"], TR, 11, 80), TR, 11)
        p.box(32, 241, 582, 269)
        for x in (113, 314, 375, 473):
            p.line(x, 241, x, 269)
        p.t(34, 249, "Código producto", TR, 11); p.t(145, 250, "Descripción del producto", TR, 11)
        p.t(327, 250, "Cantidad", TR, 11); p.t(382, 250, "Precio Unit. Pesos", TR, 11)
        p.t(485, 250, "Subtotal  Pesos", TR, 11)
        top = 275
        for t, f in fp:
            if t == "L":
                p.t(41, top, f["code"], TR, 10)
                p.t(123, top, fit(f["descr"], TR, 11, 185), TR, 11)
                p.t(380, top, n2(f["qty"]), TR, 11, "r")
                if f["price"]:
                    p.t(468, top, n2(f["price"]), TR, 11, "r")
                    p.t(581, top, n2(f["qty"] * f["price"]), TR, 11, "r")
            else:
                p.t(123, top, fit(f, TR, 11, 450), TR, 11)
            top += 14
        p.line(23, 634, 591, 634)
        if npag == len(paginas):
            p.t(377, 641, n2(sum(l["qty"] for l in lines)), TR, 11, "r")
            p.t(416, 642, "Subtotal", TR, 11); p.t(579, 642, n2(h["subtotal"]), TR, 11, "r")
            y = 656
            if h["itbis"]:
                p.t(416, y, "ITBIS", TR, 11); p.t(579, y, n2(h["itbis"]), TR, 11, "r"); y += 14
            if h["discount"]:
                p.t(416, y, "Descuento", TR, 11); p.t(579, y, n2(h["discount"]), TR, 11, "r")
            p.t(29, 642, h["comment1"], TR, 11)
            p.t(29, 656, h["comment2"], TR, 11); p.t(29, 669, h["comment3"], TR, 11)
            p.box(365, 696, 582, 721)
            p.t(374, 704, "TOTAL", TR, 11); p.t(416, 704, "Pesos", TR, 11)
            p.t(580, 704, n2(h["total"]), TB, 11, "r")
        c.showPage()
    c.save()
    return ruta


def fecha_corta(s):
    d = parse_date(s) if isinstance(s, str) else s
    return d.strftime("%d/%m/%Y") if d else ""
