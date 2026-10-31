"""Reportes de cuentas por cobrar con el formato de Monica 8.5."""
import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from db import fmt_date, parse_date

H = 792
TR, TB, H_, HB, HBI = "Times-Roman", "Times-Bold", "Helvetica", "Helvetica-Bold", "Helvetica-BoldOblique"


def dmy(s):
    d = parse_date(s) if isinstance(s, str) else s
    return d.strftime("%d/%m/%Y") if d else ""


def n2(v):
    return f"{v:,.2f}"


def fit(t, font, size, w):
    t = t or ""
    while t and stringWidth(t, font, size) > w:
        t = t[:-1]
    return t


class P:
    def __init__(self, c): self.c = c

    def t(self, x, top, text, font=TR, size=9, align="l"):
        if text in (None, ""): return
        y = H - top - size * 0.80
        self.c.setFont(font, size)
        {"r": self.c.drawRightString, "c": self.c.drawCentredString}.get(align, self.c.drawString)(x, y, str(text))

    def line(self, x0, t0, x1, t1): self.c.line(x0, H - t0, x1, H - t1)


# ------------------------------------------------------------------ estado de cuenta
def estado_cuenta(db, clientes, desde, hasta, ruta, ap=False):
    """clientes: lista de codigos. desde/hasta: date."""
    c = canvas.Canvas(ruta, pagesize=letter); c.setTitle("Estado de cuenta"); c.setLineWidth(0.7)
    pag = [0]
    d1, d2 = fmt_date(desde), fmt_date(hasta)
    hechos = 0
    for code in clientes:
        cl = db.one("SELECT * FROM clients WHERE code=?", (code,))
        if not cl: continue
        ents = db.ap_entries(code) if ap else db.ledger_entries(code)
        previo = sum(e["monto"] for e in ents if (e["date"] or "") < d1)
        rango = [e for e in ents if d1 <= (e["date"] or "") <= d2]
        hechos += 1

        def cabecera():
            pag[0] += 1
            p = P(c)
            p.t(23, 33, db.cfg("emp_nombre"), HBI, 14)
            p.t(543, 32, "Pag.", HB, 8); p.t(580, 33, pag[0], H_, 8, "r")
            p.t(23, 51, db.cfg("emp_l1"), H_, 8); p.t(23, 61, db.cfg("emp_l2"), H_, 8)
            p.t(295, 72, "E S T A D O    D E   C U E N T A", HB, 10, "c")
            p.t(44, 92, "Proveedor" if ap else "Cliente", HB, 8); p.t(233, 95, "Código Prov." if ap else "Código Clte.", HB, 8)
            p.t(44, 103, "------------------", HB, 8); p.t(239, 102, "--------------", HB, 8)
            p.t(27, 119, cl["name"], H_, 8); p.t(233, 119, code, H_, 8)
            p.t(27, 129, cl["addr1"], H_, 8)
            if cl["addr2"]: p.t(27, 139, cl["addr2"], H_, 8)
            p.t(34, 164, "Desde :", TB, 9); p.t(66, 165, dmy(desde), H_, 8)
            p.t(145, 164, "Hasta :", TB, 9); p.t(176, 165, dmy(hasta), H_, 8)
            p.t(27, 193, "Fecha", TB, 9); p.t(79, 192, "Nro. Comp" if ap else "Nro. Fact", TB, 9); p.t(125, 192, "Vencmto.", TB, 9)
            p.t(176, 192, "Tipo", TB, 9); p.t(217, 193, "Referencia", TB, 9)
            p.t(353, 194, "Compras  Pesos" if ap else "Debitos  Pesos", TB, 9)
            p.t(435, 194, "Pagos  Pesos" if ap else "Creditos  Pesos", TB, 9)
            p.t(520, 192, "Balance  Pesos", TB, 9)
            return p

        p = cabecera()
        bal = previo
        p.t(26, 213, dmy(desde - datetime.timedelta(days=1)), TR, 9)
        p.t(208, 212, "Balance Previo --->", TR, 9)
        p.t(408, 213, n2(previo), TR, 9, "r"); p.t(491, 213, n2(0), TR, 9, "r"); p.t(581, 214, n2(previo), TR, 9, "r")
        deb = previo; cre = 0.0
        top = 231
        for e in rango:
            if top > 730:
                c.showPage(); p = cabecera(); top = 213
            bal += e["monto"]
            p.t(23, top, dmy(e["date"]), TR, 9)
            if e["nro"]: p.t(116, top, e["nro"], TR, 9, "r")
            p.t(122, top, dmy(e["due"]), TR, 9)
            p.t(172, top, e["tipo"], TR, 9)
            p.t(199, top, fit(e["descr"], TR, 9, 150), TR, 9)
            if e["monto"] >= 0:
                p.t(408, top, n2(e["monto"]), TR, 9, "r"); deb += e["monto"]
            else:
                p.t(491, top, n2(e["monto"]), TR, 9, "r"); cre += e["monto"]
            p.t(581, top, n2(bal), TR, 9, "r")
            top += 12
        if top > 740:
            c.showPage(); p = cabecera(); top = 213
        top += 3
        p.line(297, top, 581, top)
        if not ap: p.t(30, top + 18, "Favor responder a la presente", H_, 8)
        p.t(230, top + 14, "T  O  T  A  L ===>", HB, 8)
        p.t(299, top + 13, "Pesos", TB, 9)
        p.t(409, top + 12, n2(deb), TR, 9, "r"); p.t(491, top + 13, n2(cre), TR, 9, "r")
        p.t(581, top + 13, n2(bal), TR, 9, "r")
        c.rect(492, H - (top + 28), 92, 22, stroke=1, fill=0)
        c.showPage(); pag[0] = 0
    if not hechos:
        c.setFont(H_, 10); c.drawString(40, 700, "Sin clientes."); c.showPage()
    c.save()
    return ruta


# ------------------------------------------------------------------ saldos vencidos
def saldos_datos(db, desde, hasta, al, ap=False):
    """Por cliente: corriente, 1-30, 31-60, 61-90, +91, total (saldo de facturas emitidas en el rango)."""
    d1, d2 = fmt_date(desde), fmt_date(hasta)
    names = {r["code"]: r["name"] for r in db.q("SELECT code,name FROM clients")}
    res = {}
    for inv, saldo in (db.open_payables() if ap else db.open_invoices()):
        if not (d1 <= (inv["date"] or "") <= d2):
            continue
        due = parse_date(inv["due"]) or parse_date(inv["date"])
        dias = (al - due).days
        k = 0 if dias <= 0 else 1 if dias <= 30 else 2 if dias <= 60 else 3 if dias <= 90 else 4
        row = res.setdefault(inv["client"], [names.get(inv["client"], inv["name"] or inv["client"]), 0, 0, 0, 0, 0])
        row[1 + k] += saldo
    rows = [(code, *v, sum(v[1:])) for code, v in res.items()]
    rows.sort(key=lambda r: (r[2], r[1]))
    return rows


def saldos_vencidos(db, desde, hasta, al, ruta, ap=False):
    rows = saldos_datos(db, desde, hasta, al, ap)
    c = canvas.Canvas(ruta, pagesize=letter); c.setTitle("Saldos vencidos"); c.setLineWidth(0.7)
    xs = (231, 303, 376, 448, 518, 590)
    pag = 0

    def cab():
        nonlocal pag
        pag += 1
        p = P(c)
        p.t(15, 17, db.cfg("emp_nombre"), TB, 12)
        p.t(552, 16, "Pag.", TR, 8); p.t(590, 16, pag, TR, 8, "r")
        p.t(586, 27, dmy(datetime.date.today()), TR, 8, "r")
        p.t(15, 32, db.cfg("emp_l2"), TR, 8); p.t(15, 43, db.cfg("emp_l3"), TR, 8)
        p.t(303, 57, f"REPORTE DE SALDOS VENCIDOS{' (CUENTAS POR PAGAR)' if ap else ''} AL {dmy(al)}", TB, 10, "c")
        p.t(303, 70, f"Para {'compras' if ap else 'facturas y/ó debitos'} emitidas desde {dmy(desde)} hasta {dmy(hasta)}.  ---  No incluye cargos financieros", TR, 10, "c")
        p.t(69, 94, "Proveedor" if ap else "Cliente", TB, 8)
        for x, h in zip(xs, ("Corriente", "Vence 1-30 dias", "Vence 31-60 dias", "Vence 61-90 dias", "Mas de 91 dias", "Total Pesos")):
            p.t(x - 6 if x != 590 else 572, 94, h, TB, 8, "r")
        return p

    p = cab(); top = 108
    tot = [0.0] * 6
    for r in rows:
        if top > 720:
            c.showPage(); p = cab(); top = 108
        p.t(15, top, (r[1] or "")[:28], TR, 8)
        for i, x in enumerate(xs):
            p.t(x, top, n2(r[2 + i]), TR, 8, "r"); tot[i] += r[2 + i]
        top += 13.5
    p.line(15, top, 591, top)
    for i, x in enumerate(xs):
        p.t(x + (2 if i < 5 else 1), top + 3, n2(tot[i]), TR, 8, "r")
    c.showPage(); c.save()
    return ruta


# ================================================================== reportes de ventas e inventario
class Tabla:
    """Reporte tabular estilo Monica: encabezado, columnas, grupos con subtotales y total general."""
    def __init__(self, db, ruta, titulos, cols, font_size=8, landscape=False):
        self.db = db; self.cols = cols; self.fs = font_size
        self.c = canvas.Canvas(ruta, pagesize=letter); self.c.setTitle(titulos[0]); self.c.setLineWidth(0.6)
        self.titulos = titulos; self.pag = 0; self.top = 0; self.ruta = ruta
        self.page()

    def page(self):
        if self.pag:
            self.c.showPage()
        self.pag += 1
        p = P(self.c); self.p = p
        p.t(15, 17, self.db.cfg("emp_nombre"), TB, 12)
        p.t(552, 16, "Pag.", TR, 8); p.t(590, 16, self.pag, TR, 8, "r")
        p.t(590, 27, dmy(datetime.date.today()), TR, 8, "r")
        p.t(15, 32, self.db.cfg("emp_l2"), TR, 8); p.t(15, 43, self.db.cfg("emp_l3"), TR, 8)
        top = 62
        for i, t in enumerate(self.titulos):
            p.t(303, top, t, TB if i == 0 else TR, 10 if i == 0 else 9, "c"); top += 13
        top += 8
        for x, al, h1, h2 in self.cols:
            p.t(x, top, h1, TB, 8, al)
            p.t(x, top + 10, h2, TB, 8, al)
        self.top = top + 26

    def need(self, h=12):
        if self.top + h > 755:
            self.page()

    def row(self, vals, bold=False, size=None):
        self.need()
        f = TB if bold else TR
        for (x, al, _, _), v in zip(self.cols, vals):
            if v not in (None, ""):
                self.p.t(x, self.top, v, f, size or self.fs, al)
        self.top += 11.5

    def text(self, x, s, bold=False, size=9):
        self.need(14)
        self.p.t(x, self.top, s, TB if bold else TR, size)
        self.top += 13

    def line(self):
        self.p.line(15, self.top - 2, 591, self.top - 2); self.top += 3

    def space(self, h=8):
        self.top += h

    def save(self):
        self.c.showPage(); self.c.save(); return self.ruta


def _facturas_rango(db, d1, d2):
    out = []
    for r in db.q("SELECT * FROM invoices WHERE deleted=0 AND date BETWEEN ? AND ? ORDER BY date DESC, nro DESC",
                  (fmt_date(d1), fmt_date(d2))):
        ls = db.q("SELECT qty,price,cost FROM lines WHERE nro=?", (r["nro"],))
        costo = round(sum(l["qty"] * (l["cost"] or 0) for l in ls), 2)
        out.append(dict(r=r, items=len(ls), costo=costo, imp=round((r["itbis"] or 0) - (r["discount"] or 0), 2)))
    return out


def _clase(db, r):
    from db import TIPOS
    lab = {0: "Sin comprobante", 1: "Fact. Credito Fiscal", 2: "Fact. Consumidor Final", 14: "Fact. Regimenes Especiales",
           15: "Fact. Gubernamental"}
    return lab.get(r["tipo"] if r["ncf"] else 0, "Factura")


def relacion_facturas(db, d1, d2, ruta, por_clase=False):
    dias = (d2 - d1).days
    tit = [f"Relación de Facturas desde {dmy(d1)} hasta {dmy(d2)}" + (" Por clase" if por_clase else ""),
           f"( Para {dias} dias, En Pesos )"]
    cols = [(15, "l", "", "Fecha"), (65, "l", "", "Cliente"), (232, "r", "Nro.", "Factura"), (258, "r", "Total", "Items"),
            (318, "r", "Costo", "factura"), (380, "r", "Subtotal", "valor neto"), (440, "r", "Imp. + Misc. -", "Descuento"),
            (505, "r", "Total", "Factura"), (588, "r", "Subtotal -", "Costo")]
    t = Tabla(db, ruta, tit, cols)
    fs = _facturas_rango(db, d1, d2)
    grupos = {}
    for f in fs:
        grupos.setdefault(_clase(db, f["r"]), []).append(f)
    G = [0, 0, 0, 0, 0, 0, 0]
    for g in sorted(grupos):
        t.space(4); t.text(25, g, True)
        S = [0, 0, 0, 0, 0, 0, 0]
        for f in grupos[g]:
            r = f["r"]
            t.row([dmy(r["date"]), (r["name"] or "")[:25], r["nro"], f["items"], n2(f["costo"]), n2(r["subtotal"]),
                   n2(f["imp"]), n2(r["total"]), n2(r["subtotal"] - f["costo"])])
            for i, v in enumerate((1, f["items"], f["costo"], r["subtotal"], f["imp"], r["total"], r["subtotal"] - f["costo"])):
                S[i] += v
        t.line()
        t.row(["", "", S[0], S[1], n2(S[2]), n2(S[3]), n2(S[4]), n2(S[5]), n2(S[6])], True)
        G = [a + b for a, b in zip(G, S)]
    t.space(10)
    t.row(["", "Total factura(s):", G[0], G[1], n2(G[2]), n2(G[3]), n2(G[4]), n2(G[5]), n2(G[6])], True)
    return t.save()


def facturas_por_ncf(db, d1, d2, ruta):
    dias = (d2 - d1).days
    tit = [f"Relación de Facturas por NCF desde {dmy(d1)} hasta {dmy(d2)}", f"( Para {dias} dias, En Pesos )"]
    cols = [(30, "l", "", "Nro. Comprobante fiscal"), (160, "l", "", "Fecha"), (215, "l", "", "Cliente"),
            (378, "r", "Nro.", "Factura"), (440, "r", "Costo", "factura"), (510, "r", "Subtotal", "valor neto"),
            (585, "r", "Total", "Factura")]
    t = Tabla(db, ruta, tit, cols)
    fs = _facturas_rango(db, d1, d2)
    grupos = {}
    for f in fs:
        grupos.setdefault(_clase(db, f["r"]), []).append(f)
    G = [0, 0, 0, 0]
    for g in sorted(grupos):
        t.space(4); t.text(25, g, True)
        S = [0, 0, 0, 0]
        for f in sorted(grupos[g], key=lambda f: f["r"]["ncf"] or "", reverse=True):
            r = f["r"]
            t.row([r["ncf"] or "(sin NCF)", dmy(r["date"]), (r["name"] or "")[:25], r["nro"], n2(f["costo"]),
                   n2(r["subtotal"]), n2(r["total"])])
            for i, v in enumerate((1, f["costo"], r["subtotal"], r["total"])):
                S[i] += v
        t.line(); t.row(["", "", "", S[0], n2(S[1]), n2(S[2]), n2(S[3])], True)
        G = [a + b for a, b in zip(G, S)]
    t.space(10); t.row(["", "", "Total factura(s):", G[0], n2(G[1]), n2(G[2]), n2(G[3])], True)
    return t.save()


def itbis_cobrado(db, d1, d2, ruta):
    tit = ["Impuestos cobrados en facturas", "ITBIS", f"Desde {dmy(d1)} hasta {dmy(d2)}"]
    cols = [(60, "r", "", "Factura nro."), (70, "l", "", ""), (90, "l", "", "Cliente"), (285, "l", "", "Emitido en"),
            (390, "r", "", "Total Pesos"), (460, "r", "", "Imponible"), (540, "r", "", "ITBIS Pesos")]
    t = Tabla(db, ruta, tit, cols)
    tasas = {}
    for r in db.q("SELECT * FROM invoices WHERE deleted=0 AND date BETWEEN ? AND ? ORDER BY nro",
                  (fmt_date(d1), fmt_date(d2))):
        por = {}
        for l in db.q("SELECT qty,price,itbis FROM lines WHERE nro=?", (r["nro"],)):
            por[l["itbis"] or 0] = por.get(l["itbis"] or 0, 0) + l["qty"] * l["price"]
        for tasa, base in por.items():
            tasas.setdefault(tasa, []).append((r, base, base * tasa / 100))
    GT = [0, 0, 0, 0]
    for tasa in sorted(tasas):
        t.space(4); t.text(15, f"ITBIS {tasa:10.2f} %", True)
        S = [0, 0, 0, 0]
        for r, base, imp in tasas[tasa]:
            t.row([r["nro"], "Fac", (r["name"] or "")[:30], dmy(r["date"]), n2(r["total"]), n2(base), n2(imp) if imp else ""])
            S = [S[0] + 1, S[1] + r["total"], S[2] + base, S[3] + imp]
        t.line(); t.row([S[0], "", "factura(s)", "Total :", n2(S[1]), n2(S[2]), n2(S[3])], True)
        GT = [a + b for a, b in zip(GT, S)]
    t.space(10); t.row([GT[0], "", "factura(s) en total", "", n2(GT[1]), n2(GT[2]), n2(GT[3])], True)
    return t.save()


def facturas_por_producto(db, d1, d2, ruta):
    tit = ["RELACION DE FACTURAS POR PRODUCTO, (ORDENADO POR CODIGO DE ARTICULO)",
           f"Desde {dmy(d1)} hasta {dmy(d2)}. En Pesos"]
    cols = [(52, "r", "", "Factura"), (58, "l", "", ""), (72, "l", "", "Fecha"), (122, "l", "", "Cliente"),
            (225, "r", "", "Cantidad"), (272, "r", "", "Precio"), (335, "r", "", "Vta. en Prod."),
            (388, "r", "Costo", "factura"), (445, "r", "Subtotal", "Factura"), (510, "r", "Total", "Factura"),
            (588, "r", "Subtotal -", "Costo")]
    t = Tabla(db, ruta, tit, cols)
    rows = db.q("SELECT l.*, i.date, i.name, i.subtotal, i.total FROM lines l JOIN invoices i ON i.nro=l.nro "
                "WHERE i.deleted=0 AND i.date BETWEEN ? AND ? ORDER BY l.code, i.date, i.nro",
                (fmt_date(d1), fmt_date(d2)))
    costos = {}
    for f in _facturas_rango(db, d1, d2):
        costos[f["r"]["nro"]] = f["costo"]
    prods = {}
    for r in rows:
        prods.setdefault(r["code"], []).append(r)
    GT = [0, 0, 0]
    for code in sorted(prods):
        p = db.one("SELECT * FROM products WHERE code=?", (code,))
        t.need(60); t.space(6)
        t.text(20, f"Item:   {p['descr'] if p else ''}", True)
        t.top -= 13; t.p.t(430, t.top, f"Precio:  {n2(p['price']) if p else ''}", TR, 9); t.top += 13
        t.text(20, f"Código:  {code}")
        t.top -= 13; t.p.t(430, t.top, f"En inventario:  {db.stock(code):,.0f}", TR, 9); t.top += 13
        t.text(20, f"Costo:   {n2(p['cost']) if p else ''}")
        S = [0, 0, 0, 0, 0, 0, 0]
        for r in prods[code]:
            vta = r["qty"] * r["price"]; cst = costos.get(r["nro"], 0)
            t.row([r["nro"], "Fa", dmy(r["date"]), (r["name"] or "")[:16], n2(r["qty"]), n2(r["price"]), n2(vta),
                   n2(cst), n2(r["subtotal"]), n2(r["total"]), n2(r["subtotal"] - cst)])
            for i, v in enumerate((1, r["qty"], vta, cst, r["subtotal"], r["total"], r["subtotal"] - cst)):
                S[i] += v
        t.line()
        t.row([S[0], "", "", "Total:", n2(S[1]), "", n2(S[2]), n2(S[3]), n2(S[4]), n2(S[5]), n2(S[6])], True)
        GT = [GT[0] + S[0], GT[1] + S[1], GT[2] + S[2]]
    t.space(12); t.row([GT[0], "", "", "Total general", n2(GT[1]), "", n2(GT[2]), "", "", "", ""], True)
    return t.save()


def _costo_factura(db, nro):
    return round(sum(l["qty"] * (l["cost"] or 0) for l in db.q("SELECT qty, cost FROM lines WHERE nro=?", (nro,))), 2)


def ventas_por_cliente(db, d1, d2, ruta, cliente=None):
    """Por cliente: cada factura con su costo de adquisicion, ITBIS, total y ganancia (total - ITBIS - costo)."""
    dias = (d2 - d1).days
    tit = ["Ventas por Cliente", f"Desde {dmy(d1)} hasta {dmy(d2)}  ( Para {dias} dias, En Pesos )"]
    cols = [(15, "l", "", "Fecha"), (130, "r", "Nro.", "Factura"), (250, "r", "Costo de", "adquisición"),
            (350, "r", "", "ITBIS"), (460, "r", "Total", "Factura"), (580, "r", "", "Ganancia")]
    t = Tabla(db, ruta, tit, cols)
    grupos = {}
    for r in db.q("SELECT * FROM invoices WHERE deleted=0 AND date BETWEEN ? AND ? ORDER BY date, nro",
                  (fmt_date(d1), fmt_date(d2))):
        if cliente and r["client"] != cliente: continue
        grupos.setdefault(r["client"], []).append(r)
    nombres = {}
    for c in grupos:
        cl = db.one("SELECT name FROM clients WHERE code=?", (c,))
        nombres[c] = (cl["name"] if cl and cl["name"] else grupos[c][0]["name"]) or ""
    G = [0, 0, 0, 0, 0]
    for c in sorted(grupos, key=lambda c: nombres[c].upper()):
        t.need(50); t.space(6); t.text(15, f"{c}  -  {nombres[c]}", True)
        S = [0, 0, 0, 0, 0]
        for r in grupos[c]:
            costo = _costo_factura(db, r["nro"]); itb = r["itbis"] or 0
            gan = r["total"] - itb - costo
            t.row([dmy(r["date"]), r["nro"], n2(costo), n2(itb), n2(r["total"]), n2(gan)])
            for k, v in enumerate((1, costo, itb, r["total"], gan)):
                S[k] += v
        G = [a + b for a, b in zip(G, S)]
    t.space(6); t.line()
    t.row([f"TOTAL ({G[0]} fact.)", "", n2(G[1]), n2(G[2]), n2(G[3]), n2(G[4])], True)
    return t.save()


def ventas_por_producto(db, d1, d2, ruta, producto=None):
    """Por producto: cada venta con cliente, costo de adquisicion, ITBIS, total y ganancia (total - ITBIS - costo)."""
    dias = (d2 - d1).days
    tit = ["Ventas por Producto", f"Desde {dmy(d1)} hasta {dmy(d2)}  ( Para {dias} dias, En Pesos )"]
    cols = [(15, "l", "", "Fecha"), (95, "r", "Nro.", "Factura"), (105, "l", "", "Cliente"), (305, "r", "", "Cant."),
            (380, "r", "Costo de", "adquisición"), (440, "r", "", "ITBIS"), (515, "r", "", "Total"), (588, "r", "", "Ganancia")]
    t = Tabla(db, ruta, tit, cols)
    prods = {}
    for l in db.q("SELECT l.code, l.descr, l.qty, l.price, l.cost, l.itbis, l.nro, i.date, i.name "
                  "FROM lines l JOIN invoices i ON i.nro=l.nro "
                  "WHERE i.deleted=0 AND i.date BETWEEN ? AND ? ORDER BY l.code, i.date, i.nro",
                  (fmt_date(d1), fmt_date(d2))):
        if producto and l["code"] != producto: continue
        prods.setdefault(l["code"], []).append(l)
    G = [0, 0, 0, 0, 0]
    for code in sorted(prods):
        ficha = db.one("SELECT descr FROM products WHERE code=?", (code,))
        t.need(50); t.space(6); t.text(15, f"{code}  -  {(ficha['descr'] if ficha else prods[code][0]['descr']) or ''}", True)
        S = [0, 0, 0, 0, 0]
        for l in prods[code]:
            sub = l["qty"] * l["price"]; costo = l["qty"] * (l["cost"] or 0)
            itb = round(sub * (l["itbis"] or 0) / 100, 2); tot = sub + itb; gan = tot - itb - costo
            t.row([dmy(l["date"]), l["nro"], (l["name"] or "")[:34], n2(l["qty"]), n2(costo), n2(itb), n2(tot), n2(gan)])
            for k, v in enumerate((l["qty"], costo, itb, tot, gan)):
                S[k] += v
        G = [a + b for a, b in zip(G, S)]
    t.space(6); t.line()
    t.row(["TOTAL", "", "", n2(G[0]) if producto else "", n2(G[1]), n2(G[2]), n2(G[3]), n2(G[4])], True)
    return t.save()


def valor_inventario(db, al, ruta):
    tit = [f"Valor del Inventario al {dmy(al)} Por codigo", "( En Pesos, Método : Ultimo precio de compra )"]
    cols = [(15, "l", "", "Código"), (85, "l", "", "Descripción"), (338, "r", "", "Costo"), (400, "r", "", "Precio"),
            (460, "r", "", "En Almacén"), (528, "r", "", "Valor Invent."), (590, "r", "", "Valor Venta")]
    t = Tabla(db, ruta, tit, cols)
    n = 0; S = [0, 0, 0]
    for p in db.q("SELECT * FROM products ORDER BY code"):
        st = db.stock(p["code"])
        if abs(st) < 1e-9:
            continue
        vi = st * (p["cost"] or 0); vv = st * (p["price"] or 0)
        t.row([p["code"], (p["descr"] or "")[:45], n2(p["cost"] or 0), n2(p["price"] or 0), n2(st), n2(vi), n2(vv)])
        n += 1; S = [S[0] + st, S[1] + vi, S[2] + vv]
    t.line(); t.row([f"Total item(s): {n}", "", "", "", n2(S[0]), n2(S[1]), n2(S[2])], True)
    return t.save()


def ordenes_compra(db, d1, d2, ruta):
    dias = (d2 - d1).days
    tit = [f"Relación de Ordenes de Compra desde {dmy(d1)} hasta {dmy(d2)}", f"( Para {dias} dias, En Pesos )"]
    cols = [(15, "l", "", "Fecha"), (70, "l", "", "Proveedor"), (225, "r", "Nro.", "Compra"), (265, "r", "Total", "Items"),
            (340, "r", "Subtotal", "valor neto"), (405, "r", "Imp. + Misc. -", "Descuento"), (475, "r", "Total", "Compra"),
            (535, "r", "", "Saldo"), (545, "l", "", "Estado")]
    t = Tabla(db, ruta, tit, cols)
    S = [0, 0, 0, 0, 0, 0]
    for o in db.q("SELECT * FROM odocs WHERE kind='O' AND deleted=0 AND date BETWEEN ? AND ? ORDER BY date DESC, nro",
                  (fmt_date(d1), fmt_date(d2))):
        items = db.one("SELECT COUNT(*) FROM olines WHERE kind='O' AND nro=?", (o["nro"],))[0]
        imp = (o["itbis"] or 0) - (o["discount"] or 0); saldo = (o["total"] or 0) - (o["paid"] or 0)
        t.row([dmy(o["date"]), (o["name"] or "")[:25], o["nro"], items, n2(o["subtotal"]), n2(imp), n2(o["total"]),
               n2(saldo), o["status"]])
        S = [S[0] + 1, S[1] + items, S[2] + o["subtotal"], S[3] + imp, S[4] + o["total"], S[5] + saldo]
    t.line(); t.row(["", "Total compra(s):", S[0], S[1], n2(S[2]), n2(S[3]), n2(S[4]), n2(S[5]), ""], True)
    return t.save()
