"""Base de datos local (SQLite) y logica del negocio."""
import sqlite3, os, datetime, shutil, glob, sys

APP_NAME = "Facturacion Canopolis"
APP_VIEJO = "FacturacionCanopolis"
CARPETA_RESPALDO = "Respaldo Facturacion Canopolis"   # nombre usado por versiones anteriores

# Subcarpetas dentro de la carpeta que elige el usuario
SUB = {"F": "Facturas", "Q": "Cotizaciones", "G": "Conduces", "O": "Ordenes de compra",
       "NC": "Notas de credito", "ND": "Notas de debito", "R": "Reportes", "B": "Respaldos"}
RESP_CIERRE = "Cierre"
RESP_ANTES = "Antes de cerrar"
PREF = {"fa": "F", "es": "Q", "guia": "G", "orden": "O", "nc": "NC", "nd": "ND"}

def _puntero():
    """Solo anota que carpeta eligio el usuario (en el registro de Windows, no crea carpetas)."""
    return os.path.join(os.path.expanduser("~"), ".facturacion_canopolis")

_REG = r"Software\Canopolis\Facturacion"

def leer_ubicacion():
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG) as k:
                return (winreg.QueryValueEx(k, "Carpeta")[0] or "").strip() or None
        except OSError:
            return None
    try:
        with open(_puntero(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None

def guardar_ubicacion(loc):
    if sys.platform.startswith("win"):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG) as k:
            winreg.SetValueEx(k, "Carpeta", 0, winreg.REG_SZ, loc)
        return
    with open(_puntero(), "w", encoding="utf-8") as f:
        f.write(loc)

def crear_subcarpetas(loc):
    for s in SUB.values():
        os.makedirs(os.path.join(loc, s), exist_ok=True)
    rb = os.path.join(loc, SUB["B"])
    for s in (RESP_CIERRE, RESP_ANTES):
        os.makedirs(os.path.join(rb, s), exist_ok=True)
    for f in glob.glob(os.path.join(rb, "respaldo_*.db")):   # respaldos sueltos de versiones anteriores
        _mv(f, os.path.join(rb, RESP_CIERRE if f.endswith("_cierre.db") else RESP_ANTES))

def _mv(f, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    dst = os.path.join(carpeta, os.path.basename(f))
    if not os.path.exists(dst):
        shutil.move(f, dst)

def _mover_pdf(f, loc):
    nombre = os.path.basename(f)
    k = PREF.get(nombre.split("_", 1)[0], "F")
    _mv(f, os.path.join(loc, SUB[k]))

def _mover_contenido(origen, loc):
    """Pasa datos.db, respaldos y PDF de 'origen' (estructura vieja o nueva) a 'loc'."""
    crear_subcarpetas(loc)
    db = os.path.join(origen, "datos.db")
    if os.path.exists(db):
        _mv(db, loc)
    rb = os.path.join(loc, SUB["B"])
    for b in (origen, os.path.join(origen, SUB["B"])):
        for f in glob.glob(os.path.join(b, "respaldo_*.db")):
            _mv(f, os.path.join(rb, RESP_CIERRE if f.endswith("_cierre.db") else RESP_ANTES))
        for s in (RESP_CIERRE, RESP_ANTES):
            for f in glob.glob(os.path.join(b, s, "respaldo_*.db")):
                _mv(f, os.path.join(rb, s))
    vieja = os.path.join(origen, "facturas_pdf")
    if os.path.isdir(vieja):
        for f in glob.glob(os.path.join(vieja, "*")):
            _mover_pdf(f, loc)
    for k, s in SUB.items():
        if k == "B": continue
        o = os.path.join(origen, s)
        if os.path.isdir(o):
            for f in glob.glob(os.path.join(o, "*")):
                _mv(f, os.path.join(loc, s))
    o = os.path.join(origen, "reportes")
    if os.path.isdir(o):
        for f in glob.glob(os.path.join(o, "*")):
            _mv(f, os.path.join(loc, SUB["R"]))

def _borrar_si_vacia(carpeta):
    for raiz, dirs, files in os.walk(carpeta, topdown=False):
        for f in files:
            if f in ("ubicacion.txt", "error.log", ".prueba_escritura"):
                try: os.remove(os.path.join(raiz, f))
                except OSError: pass
        try: os.rmdir(raiz)
        except OSError: pass

def con_carpeta_app(loc):
    """Todo vive dentro de una carpeta llamada APP_NAME. Si la anotada no se llama asi, se pasa todo adentro."""
    loc = os.path.normpath(loc)
    if os.path.basename(loc).lower() == APP_NAME.lower():
        return loc
    nueva = os.path.join(loc, APP_NAME)
    _mover_contenido(loc, nueva)
    for s in SUB.values():
        try: os.rmdir(os.path.join(loc, s))
        except OSError: pass
    guardar_ubicacion(nueva)
    return nueva

def carpetas_viejas():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return [p for p in (os.path.join(docs, APP_NAME), os.path.join(docs, APP_VIEJO)) if os.path.isdir(p)]

def migrar_viejas(loc):
    """Todo lo de versiones anteriores (en Documentos) pasa a la carpeta elegida; lo viejo se borra si queda vacio."""
    for base in carpetas_viejas():
        fuentes = [os.path.join(base, CARPETA_RESPALDO), os.path.join(base, "respaldos"), base]
        try:
            with open(os.path.join(base, "ubicacion.txt"), encoding="utf-8") as f:
                p = f.read().strip()
            if p: fuentes.insert(0, p)
        except OSError:
            pass
        for cand in (os.path.join(base, "datos.db"), os.path.join(base, CARPETA_RESPALDO, "datos.db")):
            if not os.path.exists(cand): continue
            try:
                c = sqlite3.connect(cand); r = c.execute("SELECT v FROM config WHERE k='carpeta_respaldos'").fetchone(); c.close()
                if r and (r[0] or "").strip(): fuentes.append(r[0].strip())
            except sqlite3.Error:
                pass
        for o in fuentes:
            if os.path.isdir(o) and os.path.normcase(os.path.normpath(o)) != os.path.normcase(os.path.normpath(loc)):
                _mover_contenido(o, loc)
                if not os.path.normcase(o).startswith(os.path.normcase(base)):
                    pass   # carpeta elegida antes por el usuario: no se borra
        _borrar_si_vacia(base)

SCHEMA = """
CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS clients(
  code TEXT PRIMARY KEY, name TEXT, addr1 TEXT, addr2 TEXT, addr3 TEXT, city TEXT,
  phone TEXT, fax TEXT, rnc TEXT, email TEXT, contact TEXT, terms TEXT,
  origin TEXT DEFAULT 'app');
CREATE TABLE IF NOT EXISTS products(
  code TEXT PRIMARY KEY, descr TEXT, price REAL DEFAULT 0, price2 REAL DEFAULT 0,
  cost REAL DEFAULT 0, stock_base REAL DEFAULT 0, itbis REAL DEFAULT 0,
  category TEXT, active INTEGER DEFAULT 1, origin TEXT DEFAULT 'app');
CREATE TABLE IF NOT EXISTS sequences(
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo INTEGER, name TEXT, fixed TEXT, monica_id INTEGER,
  next_num INTEGER, limit_num INTEGER, active INTEGER DEFAULT 1, auth_date TEXT,
  origin TEXT DEFAULT 'app');
CREATE TABLE IF NOT EXISTS invoices(
  nro INTEGER PRIMARY KEY, date TEXT, due TEXT, client TEXT, name TEXT,
  dir1 TEXT, dir2 TEXT, dir3 TEXT, rnc TEXT, terms TEXT, ship_via TEXT, seller TEXT,
  ref TEXT, comment1 TEXT, comment2 TEXT, comment3 TEXT, ncf TEXT DEFAULT '',
  tipo INTEGER DEFAULT 0, subtotal REAL DEFAULT 0, itbis REAL DEFAULT 0,
  discount REAL DEFAULT 0, total REAL DEFAULT 0, saldo_base REAL DEFAULT 0,
  deleted INTEGER DEFAULT 0, origin TEXT DEFAULT 'app', modified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS lines(
  id INTEGER PRIMARY KEY AUTOINCREMENT, nro INTEGER, pos INTEGER, code TEXT, descr TEXT,
  qty REAL, price REAL, cost REAL DEFAULT 0, itbis REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_lines ON lines(nro);
CREATE TABLE IF NOT EXISTS orig_lines(nro INTEGER, code TEXT, qty REAL);
CREATE INDEX IF NOT EXISTS ix_orig ON orig_lines(nro);
CREATE TABLE IF NOT EXISTS comments(nro INTEGER, pos INTEGER, ord INTEGER, text TEXT);
CREATE INDEX IF NOT EXISTS ix_com ON comments(nro);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, nro INTEGER, date TEXT, amount REAL, method TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS ledger(
  client TEXT, tipo TEXT, date TEXT, due TEXT, nro_fact INTEGER, descr TEXT, monto REAL, saldo REAL);
CREATE INDEX IF NOT EXISTS ix_led ON ledger(client);
CREATE TABLE IF NOT EXISTS stock_moves(nro INTEGER, code TEXT, qty REAL);
CREATE TABLE IF NOT EXISTS odocs(
  kind TEXT, nro INTEGER, date TEXT, due TEXT, client TEXT, name TEXT, dir1 TEXT, dir2 TEXT, dir3 TEXT,
  ship_to TEXT, sdir1 TEXT, sdir2 TEXT, sdir3 TEXT, rnc TEXT, terms TEXT, ship_via TEXT, seller TEXT, ref TEXT,
  comment1 TEXT, comment2 TEXT, comment3 TEXT, subtotal REAL DEFAULT 0, itbis REAL DEFAULT 0,
  discount REAL DEFAULT 0, total REAL DEFAULT 0, paid REAL DEFAULT 0, status TEXT DEFAULT '',
  factura INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0, origin TEXT DEFAULT 'app', modified INTEGER DEFAULT 0,
  PRIMARY KEY(kind, nro));
CREATE TABLE IF NOT EXISTS olines(kind TEXT, nro INTEGER, pos INTEGER, code TEXT, descr TEXT, qty REAL,
  price REAL, cost REAL DEFAULT 0, itbis REAL DEFAULT 0, received REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_olines ON olines(kind, nro);
CREATE TABLE IF NOT EXISTS ap_ledger(
  supplier TEXT, tipo TEXT, date TEXT, due TEXT, nro_orden INTEGER, descr TEXT, monto REAL, saldo REAL);
CREATE INDEX IF NOT EXISTS ix_apl ON ap_ledger(supplier);
CREATE TABLE IF NOT EXISTS ap_payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, nro INTEGER, date TEXT, amount REAL, method TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS ocomments(kind TEXT, nro INTEGER, pos INTEGER, ord INTEGER, text TEXT);
CREATE INDEX IF NOT EXISTS ix_ocom ON ocomments(kind, nro);
CREATE INDEX IF NOT EXISTS ix_mov ON stock_moves(nro);
"""

# Tipos de comprobante (tipo_cf de Monica + los nuevos)
TIPOS = {
    0: ("Sin comprobante", "FACTURA"),
    1: ("Factura. Crédito fiscal", "FACTURA. CREDITO FISCAL"),
    2: ("Factura. Consumidor final", "FACTURA. CONSUMIDOR FINAL"),
    3: ("Nota de crédito", "NOTA DE CREDITO"),
    4: ("Nota de débito", "NOTA DE DEBITO"),
    14: ("Factura. Regímenes especiales", "FACTURA. REGIMENES ESPECIALES"),
    15: ("Factura. Gubernamental", "FACTURA. GUBERNAMENTAL"),
    16: ("Factura. Exportaciones", "FACTURA. EXPORTACIONES"),
}
TIPOS_FACTURA = [1, 2, 14, 15, 16, 0]

DEFAULT_CONFIG = {
    "emp_nombre": "Canopolis",
    "emp_l1": "RNC 130561974",
    "emp_l2": "SANTO DOMINGO",
    "emp_l3": "Tel 829-851-1579",
    "emp_l4": "",
    "emp_l5": "130561974",
    "lugar": "Sto. Domingo",
    "envio": "Entrega",
    "coment2": "_______________________",
    "coment3": "RECIBIDO CONFORME",
    "aviso_pocos": "10",
    "max_respaldos": "60",
    "carpeta_respaldos": "",
    "msg_fact1": "",
    "msg_fact2": "",
    "msg_fact3": "",
}

def calc_itbis(lines, discount=0):
    """ITBIS segun el art. 339 de la Ley 11-92: sobre el precio neto, menos descuentos.
    El descuento de la factura se reparte entre las lineas en proporcion a su monto."""
    sub = sum(l["qty"] * l["price"] for l in lines)
    bruto = sum(l["qty"] * l["price"] * (l.get("itbis", 0) or 0) / 100 for l in lines)
    if sub > 0 and discount:
        bruto *= max(0.0, 1 - discount / sub)
    return round(bruto, 2)


def fmt_date(d):
    return d.isoformat() if d else ""

def parse_date(s):
    return datetime.date.fromisoformat(s) if s else None


class DB:
    def __init__(self, path=None, loc=None):
        if path is None:
            self.loc = loc or leer_ubicacion()
            if not self.loc:
                raise RuntimeError("No se ha elegido la carpeta de datos.")
        else:
            self.loc = os.path.dirname(path)
        os.makedirs(self.loc, exist_ok=True)
        if path is None: crear_subcarpetas(self.loc)
        self.dir = self.loc
        self.path = path or os.path.join(self.loc, "datos.db")
        self._abrir()

    def cambiar_ubicacion(self, nueva):
        """Mueve todo (datos, documentos y respaldos) a la carpeta nueva (se crea si no existe)."""
        nueva = os.path.normpath(nueva)
        if os.path.normcase(nueva) == os.path.normcase(os.path.normpath(self.loc)):
            return nueva
        if os.path.normcase(nueva).startswith(os.path.normcase(os.path.normpath(self.loc)) + os.sep):
            raise OSError("La carpeta nueva no puede estar dentro de la actual.")
        os.makedirs(nueva, exist_ok=True)
        if os.path.exists(os.path.join(nueva, "datos.db")):
            raise OSError("Esa carpeta ya tiene un archivo datos.db. Elija otra carpeta.")
        self.con.commit(); self.con.close()
        vieja = self.loc
        try:
            _mover_contenido(vieja, nueva)
        finally:
            if os.path.exists(os.path.join(nueva, "datos.db")):
                self.loc = self.dir = nueva; self.path = os.path.join(nueva, "datos.db")
                guardar_ubicacion(nueva)
                for s in SUB.values():
                    try: os.rmdir(os.path.join(vieja, s))
                    except OSError: pass
            self._abrir()
        return self.loc

    def carpeta(self, k):
        c = os.path.join(self.loc, SUB[k]); os.makedirs(c, exist_ok=True); return c

    def _abrir(self):
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self._migrate()
        try:
            self.fix_contact_names()
        except sqlite3.Error:
            pass
        for k, v in DEFAULT_CONFIG.items():
            self.con.execute("INSERT OR IGNORE INTO config VALUES(?,?)", (k, v))
        self.con.commit()

    def _migrate(self):
        def cols(t):
            return {r[1] for r in self.con.execute(f"PRAGMA table_info({t})")}
        if "ctype" not in cols("clients"):
            self.con.execute("ALTER TABLE clients ADD COLUMN ctype TEXT DEFAULT 'C'")
        if "kind" not in cols("stock_moves"):
            self.con.execute("ALTER TABLE stock_moves ADD COLUMN kind TEXT DEFAULT 'F'")
        if "kind" not in cols("orig_lines"):
            self.con.execute("ALTER TABLE orig_lines ADD COLUMN kind TEXT DEFAULT 'F'")
        self.con.execute("UPDATE stock_moves SET kind='A' WHERE nro=0 AND kind='F'")
        for col, typ in (("ecf_cod", "TEXT"), ("ecf_firma", "TEXT"), ("ecf_qr", "BLOB")):
            if col not in cols("invoices"):
                self.con.execute(f"ALTER TABLE invoices ADD COLUMN {col} {typ}")
        if "unpaid" not in cols("invoices"):
            self.con.execute("ALTER TABLE invoices ADD COLUMN unpaid INTEGER DEFAULT 0")
        if "ncf" not in cols("odocs"):
            self.con.execute("ALTER TABLE odocs ADD COLUMN ncf TEXT DEFAULT ''")
        self.con.commit()

    def fix_contact_names(self):
        """Corrige facturas que muestran el contacto (encargado) en vez del nombre comercial del cliente."""
        self.con.execute("""UPDATE invoices SET name=(SELECT c.name FROM clients c WHERE c.code=invoices.client)
            WHERE EXISTS (SELECT 1 FROM clients c WHERE c.code=invoices.client AND c.name<>''
                          AND invoices.name<>c.name
                          AND (invoices.name=c.contact OR lower(invoices.name)=lower(c.name)))""")
        # el "enviado a" de cotizaciones y conduces de Monica traia el contacto: no se usa como nombre
        self.con.execute("UPDATE odocs SET ship_to='' WHERE kind IN ('Q','G') AND ship_to<>''")
        self.con.execute("""UPDATE odocs SET name=(SELECT c.name FROM clients c WHERE c.code=odocs.client)
            WHERE kind<>'O' AND EXISTS (SELECT 1 FROM clients c WHERE c.code=odocs.client AND c.name<>''
                          AND odocs.name<>c.name AND odocs.name=c.contact)""")
        self.con.commit()

    # ---------- config ----------
    def cfg(self, k):
        r = self.con.execute("SELECT v FROM config WHERE k=?", (k,)).fetchone()
        return r[0] if r else DEFAULT_CONFIG.get(k, "")

    def set_cfg(self, k, v):
        self.con.execute("INSERT OR REPLACE INTO config VALUES(?,?)", (k, str(v)))
        self.con.commit()

    def q(self, sql, args=()):
        return self.con.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.con.execute(sql, args).fetchone()

    # ---------- clientes ----------
    def save_client(self, d):
        cols = ["code", "name", "addr1", "addr2", "addr3", "city", "phone", "fax", "rnc",
                "email", "contact", "terms", "ctype"]
        d = dict(d); d.setdefault("ctype", "C")
        old = self.one("SELECT origin FROM clients WHERE code=?", (d["code"],))
        origin = old["origin"] if old else "app"
        self.con.execute(
            f"INSERT OR REPLACE INTO clients({','.join(cols)},origin) VALUES({','.join('?'*len(cols))},?)",
            [d.get(c, "") for c in cols] + [origin if origin == "app" else "app-mod"])
        self.con.commit()

    def next_client_code(self, prefix="A"):
        mx = 0
        for (c,) in self.con.execute("SELECT code FROM clients"):
            if c and c[0] == prefix and c[1:].isdigit():
                mx = max(mx, int(c[1:]))
        return f"{prefix}{mx+1}"

    def client_print_block(self, code):
        c = self.one("SELECT * FROM clients WHERE code=?", (code,))
        if not c:
            return dict(name="", dir1="", dir2="", dir3="", rnc="", terms="Efectivo")
        tel = "Tlf.: " + (c["phone"] or "")
        if c["fax"]:
            tel += "  Fx: " + c["fax"]
        return dict(name=c["name"], dir1=tel, dir2=c["addr1"] or "",
                    dir3=c["addr3"] or c["city"] or c["addr2"] or "",
                    rnc=(c["rnc"] or "").strip(), terms=c["terms"] or "Efectivo")

    # ---------- productos ----------
    def stock(self, code):
        p = self.one("SELECT stock_base FROM products WHERE code=?", (code,))
        base = p[0] if p else 0
        m = self.one("SELECT COALESCE(SUM(qty),0) FROM stock_moves WHERE code=?", (code,))[0]
        return base + m

    def stock_al(self, al):
        """Existencia de cada producto a la fecha al: a la existencia de hoy se le revierten los documentos
        con fecha posterior (facturas, conduces, ordenes recibidas, notas de credito con devolucion).
        Los ajustes manuales del programa no tienen fecha: cuentan solo si al es hoy o despues."""
        al_s = al if isinstance(al, str) else fmt_date(al)
        hoy = fmt_date(datetime.date.today())
        st = {}
        for p in self.q("SELECT code, stock_base FROM products"):
            st[p["code"]] = p["stock_base"] or 0
        for m in self.q("SELECT code, SUM(qty) q FROM stock_moves GROUP BY code"):
            st[m["code"]] = st.get(m["code"], 0) + m["q"]
        def mover(code, q):
            st[code] = st.get(code, 0) + q
        # facturas posteriores: devolver lo vendido
        for l in self.q("SELECT l.code, l.qty FROM lines l JOIN invoices i ON i.nro=l.nro "
                        "WHERE i.deleted=0 AND i.date>?", (al_s,)):
            if l["code"]:
                mover(l["code"], l["qty"] or 0)
        # otros documentos posteriores que mueven inventario
        for h in self.q("SELECT * FROM odocs WHERE kind IN ('G','O','NC') AND deleted=0 AND date>?", (al_s,)):
            sign = 1 if h["kind"] in ("O", "NC") else -1
            for code, q in self._odoc_qty(h["kind"], h["nro"], h, None).items():
                if code:
                    mover(code, -sign * q)
        if al_s < hoy:
            for m in self.q("SELECT code, SUM(qty) q FROM stock_moves WHERE kind='A' GROUP BY code"):
                mover(m["code"], -m["q"])
        return st

    def set_sale_price(self, code, price):
        """Precio de venta puesto en una orden de compra: queda en la ficha del producto."""
        p = self.one("SELECT price FROM products WHERE code=?", (code,))
        if not p or abs((p["price"] or 0) - round(price, 2)) < 0.005:
            return   # sin cambio: no se toca la ficha
        self.con.execute("UPDATE products SET price=?, origin=CASE WHEN origin='app' THEN 'app' ELSE 'app-mod' END "
                         "WHERE code=?", (round(price, 2), code))
        self.con.commit()

    def save_product(self, d):
        old = self.one("SELECT origin, stock_base FROM products WHERE code=?", (d["code"],))
        origin = "app" if not old or old["origin"] == "app" else "app-mod"
        self.con.execute(
            "INSERT OR REPLACE INTO products(code,descr,price,price2,cost,stock_base,itbis,category,active,origin)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (d["code"], d["descr"], d["price"], d.get("price2", 0), d.get("cost", 0),
             d.get("stock_base", old["stock_base"] if old else 0), d.get("itbis", 0),
             d.get("category", ""), d.get("active", 1), origin))
        self.con.commit()

    def can_delete_product(self, code):
        """Solo se elimina si tiene existencia 0 y no esta en facturas con saldo (vencidas o vigentes).
        Devuelve (True, '') o (False, motivo)."""
        st = self.stock(code)
        if abs(st) > 1e-9:
            return False, f"Tiene existencia {st:,.2f}. Debe estar en 0."
        abiertas = {inv["nro"] for inv, _ in self.open_invoices()}
        usadas = sorted({r["nro"] for r in self.q("SELECT DISTINCT nro FROM lines WHERE code=?", (code,))} & abiertas)
        if usadas:
            lista = ", ".join(str(n) for n in usadas[:10]) + (" ..." if len(usadas) > 10 else "")
            return False, f"Está en facturas vencidas o vigentes (con saldo): {lista}"
        return True, ""

    def delete_product(self, code):
        self.con.execute("DELETE FROM products WHERE code=?", (code,))
        self.con.commit()

    # ---------- secuencias ----------
    @staticmethod
    def ncf_text(fixed, num):
        return f"{fixed}{int(num):08d}"

    def seq_remaining(self, s):
        return max(0, int(s["limit_num"]) - int(s["next_num"]) + 1)

    def active_seq(self, tipo):
        for s in self.q("SELECT * FROM sequences WHERE tipo=? AND active=1 ORDER BY id DESC", (tipo,)):
            if self.seq_remaining(s) > 0:
                return s
        return None

    def take_ncf(self, tipo):
        """Devuelve el siguiente NCF del tipo o '' si no hay secuencia disponible (no bloquea)."""
        s = self.active_seq(tipo)
        if not s:
            return ""
        ncf = self.ncf_text(s["fixed"], s["next_num"])
        self.con.execute("UPDATE sequences SET next_num=next_num+1 WHERE id=?", (s["id"],))
        return ncf

    def low_sequences(self):
        lim = int(self.cfg("aviso_pocos") or 10)
        out = []
        for t in (1, 2, 14, 15, 16):
            s = self.active_seq(t)
            if t == 16 and not self.one("SELECT 1 FROM sequences WHERE tipo=16"):
                continue   # exportaciones: solo se avisa si se cargo su secuencia
            if s is None:
                out.append(f"{TIPOS[t][0]}: SIN comprobantes disponibles")
            elif self.seq_remaining(s) <= lim:
                out.append(f"{TIPOS[t][0]}: quedan {self.seq_remaining(s)}")
        return out

    def tipo_from_ncf(self, ncf):
        if not ncf:
            return 0
        best = None
        for s in self.q("SELECT fixed,tipo FROM sequences"):
            f = s["fixed"]
            if f and ncf.startswith(f) and (best is None or len(f) > len(best[0])):
                best = (f, s["tipo"])
        if best:
            return best[1]
        clean = ncf.lstrip(".*0")
        for pref, t in (("E31", 1), ("E32", 2), ("E33", 4), ("E34", 3), ("E44", 14), ("E45", 15), ("E46", 16),
                        ("B01", 1), ("B02", 2), ("B03", 4), ("B04", 3), ("B14", 14), ("B15", 15)):
            if clean.startswith(pref):
                return t
        return 1

    # ---------- facturas ----------
    def next_invoice_no(self):
        r = self.one("SELECT MAX(nro) FROM invoices")[0]
        return int(r or 0) + 1

    def invoice_saldo(self, nro):
        inv = self.one("SELECT total,saldo_base,deleted FROM invoices WHERE nro=?", (nro,))
        if not inv or inv["deleted"]:
            return 0
        paid = self.one("SELECT COALESCE(SUM(amount),0) FROM payments WHERE nro=?", (nro,))[0]
        return round(inv["saldo_base"] - paid + self.notes_adj().get(nro, 0), 2)

    def notes_adj(self):
        """Ajuste al saldo de cada factura por notas hechas en este programa: credito resta, debito suma."""
        adj = {}
        for r in self.q("SELECT kind, factura, total FROM odocs WHERE kind IN ('NC','ND') AND deleted=0 "
                        "AND origin='app' AND factura>0"):
            adj[r["factura"]] = adj.get(r["factura"], 0) + (r["total"] if r["kind"] == "ND" else -r["total"])
        return adj

    def _rebuild_moves(self, nro):
        self.con.execute("DELETE FROM stock_moves WHERE nro=? AND kind='F'", (nro,))
        inv = self.one("SELECT deleted FROM invoices WHERE nro=?", (nro,))
        cur = {}
        if inv and not inv["deleted"]:
            for l in self.q("SELECT code,qty FROM lines WHERE nro=?", (nro,)):
                cur[l["code"]] = cur.get(l["code"], 0) + l["qty"]
        orig = {}
        for l in self.q("SELECT code,qty FROM orig_lines WHERE nro=? AND kind='F'", (nro,)):
            orig[l["code"]] = orig.get(l["code"], 0) + l["qty"]
        for code in set(cur) | set(orig):
            diff = orig.get(code, 0) - cur.get(code, 0)
            if abs(diff) > 1e-9:
                self.con.execute("INSERT INTO stock_moves(nro,code,qty,kind) VALUES(?,?,?,'F')", (nro, code, diff))

    def save_invoice(self, h, lines, comments):
        """h: dict cabecera (incluye nro). lines: list of dict(code,descr,qty,price,cost,itbis).
        comments: list of (pos, text)."""
        nro = int(h["nro"])
        old = self.one("SELECT * FROM invoices WHERE nro=?", (nro,))
        subtotal = round(sum(l["qty"] * l["price"] for l in lines), 2)
        itbis = calc_itbis(lines, h.get("discount") or 0)
        total = round(subtotal + itbis - (h.get("discount") or 0), 2)
        if old:
            paid_before = old["total"] - old["saldo_base"]
            saldo_base = round(total - paid_before, 2)
            origin = old["origin"]
            modified = 1 if origin == "monica" else 0
        else:
            saldo_base = total
            origin, modified = "app", 0
        cols = ["nro", "date", "due", "client", "name", "dir1", "dir2", "dir3", "rnc", "terms",
                "ship_via", "seller", "ref", "comment1", "comment2", "comment3", "ncf", "tipo",
                "subtotal", "itbis", "discount", "total", "saldo_base", "deleted", "origin", "modified"]
        vals = dict(h, subtotal=subtotal, itbis=itbis, total=total, saldo_base=saldo_base,
                    deleted=0, origin=origin, modified=modified)
        ecf = {k: (h.get(k) if h.get(k) is not None else (old[k] if old else None)) for k in ("ecf_cod", "ecf_firma", "ecf_qr")}
        vals.setdefault("discount", 0)
        self.con.execute(f"INSERT OR REPLACE INTO invoices({','.join(cols)}) VALUES({','.join('?'*len(cols))})",
                         [vals.get(c, "") for c in cols])
        self.con.execute("UPDATE invoices SET ecf_cod=?, ecf_firma=?, ecf_qr=? WHERE nro=?",
                         (ecf["ecf_cod"], ecf["ecf_firma"], ecf["ecf_qr"], nro))
        self.con.execute("DELETE FROM lines WHERE nro=?", (nro,))
        for i, l in enumerate(lines, 1):
            self.con.execute("INSERT INTO lines(nro,pos,code,descr,qty,price,cost,itbis) VALUES(?,?,?,?,?,?,?,?)",
                             (nro, i, l["code"], l["descr"], l["qty"], l["price"], l.get("cost", 0), l.get("itbis", 0)))
        self.con.execute("DELETE FROM comments WHERE nro=?", (nro,))
        for k, (pos, text) in enumerate(comments):
            self.con.execute("INSERT INTO comments VALUES(?,?,?,?)", (nro, pos, k, text))
        self._rebuild_moves(nro)
        self.con.commit()
        return nro

    def delete_invoice(self, nro):
        """Elimina la factura y devuelve los productos al inventario."""
        inv = self.one("SELECT origin FROM invoices WHERE nro=?", (nro,))
        if not inv:
            return
        if inv["origin"] == "app":
            self.con.execute("DELETE FROM invoices WHERE nro=?", (nro,))
            self.con.execute("DELETE FROM lines WHERE nro=?", (nro,))
            self.con.execute("DELETE FROM comments WHERE nro=?", (nro,))
            self.con.execute("DELETE FROM payments WHERE nro=?", (nro,))
            self.con.execute("DELETE FROM stock_moves WHERE nro=? AND kind='F'", (nro,))
        else:
            self.con.execute("UPDATE invoices SET deleted=1, modified=1 WHERE nro=?", (nro,))
            self._rebuild_moves(nro)
        self.con.commit()

    def mark_unpaid(self, nro):
        """Corrige una factura marcada como pagada por error: quita los pagos y la deja con saldo = total."""
        self.con.execute("DELETE FROM payments WHERE nro=?", (nro,))
        self.con.execute("UPDATE invoices SET saldo_base=total, unpaid=1, "
                         "modified=CASE WHEN origin='monica' THEN 1 ELSE modified END WHERE nro=?", (nro,))
        self.con.commit()

    def add_payment(self, nro, amount, method="Efectivo", date=None, note=""):
        self.con.execute("INSERT INTO payments(nro,date,amount,method,note) VALUES(?,?,?,?,?)",
                         (nro, fmt_date(date or datetime.date.today()), amount, method, note))
        self.con.commit()

    def ncf_desde_gti(self, ncf):
        """e-NCF de Factura Dominicana (ej. E310000000174) en el formato de las secuencias del programa.
        Marca ese numero como usado (el proximo de la secuencia queda despues de el)."""
        pref, num = ncf[:3], int(ncf[3:])
        for s in self.q("SELECT * FROM sequences ORDER BY active DESC, id DESC"):
            limpio = (s["fixed"] or "").lstrip(".*")
            if limpio.startswith(pref) and self.ncf_text(s["fixed"], num).lstrip(".*") == ncf:
                if int(s["next_num"]) <= num:
                    self.con.execute("UPDATE sequences SET next_num=? WHERE id=?", (num + 1, s["id"]))
                return self.ncf_text(s["fixed"], num)
        return ncf

    def ncf_usado(self, ncf):
        for r in self.q("SELECT nro, ncf FROM invoices WHERE deleted=0 AND ncf<>''"):
            if (r["ncf"] or "").lstrip(".*") == ncf:
                return r["nro"]
        return None

    def assign_ncf(self, nro, tipo):
        ncf = self.take_ncf(tipo)
        if not ncf:
            return ""
        inv = self.one("SELECT origin FROM invoices WHERE nro=?", (nro,))
        self.con.execute("UPDATE invoices SET ncf=?, tipo=?, modified=CASE WHEN origin='monica' THEN 1 ELSE modified END WHERE nro=?",
                         (ncf, tipo, nro))
        self.con.commit()
        return ncf

    def invoice_full(self, nro):
        h = self.one("SELECT * FROM invoices WHERE nro=?", (nro,))
        lines = self.q("SELECT * FROM lines WHERE nro=? ORDER BY pos", (nro,))
        comments = self.q("SELECT * FROM comments WHERE nro=? ORDER BY ord", (nro,))
        return h, lines, comments

    # ---------- cotizaciones (Q), conduces (G), ordenes de compra (O) ----------
    def next_odoc_no(self, kind):
        r = self.one("SELECT MAX(nro) FROM odocs WHERE kind=?", (kind,))[0]
        return int(r or 0) + 1

    def odoc_full(self, kind, nro):
        h = self.one("SELECT * FROM odocs WHERE kind=? AND nro=?", (kind, nro))
        ls = self.q("SELECT * FROM olines WHERE kind=? AND nro=? ORDER BY pos", (kind, nro))
        cs = self.q("SELECT * FROM ocomments WHERE kind=? AND nro=? ORDER BY ord", (kind, nro))
        return h, ls, cs

    def _odoc_qty(self, kind, nro, h, lines_attr):
        """Cantidades que afectan inventario segun el estado actual del documento."""
        out = {}
        if not h or h["deleted"]:
            return out
        if kind == "G" and h["factura"]:
            return out  # convertido en factura: la factura descuenta
        if kind == "O" and h["status"] != "Recibida":
            return out
        if kind == "ND" or (kind == "NC" and h["status"] != "Con devolución"):
            return out
        for l in self.q("SELECT code,qty FROM olines WHERE kind=? AND nro=?", (kind, nro)):
            out[l["code"]] = out.get(l["code"], 0) + l["qty"]
        return out

    def _rebuild_odoc_moves(self, kind, nro):
        if kind == "Q":
            return
        self.con.execute("DELETE FROM stock_moves WHERE kind=? AND nro=?", (kind, nro))
        h = self.one("SELECT * FROM odocs WHERE kind=? AND nro=?", (kind, nro))
        cur = self._odoc_qty(kind, nro, h, None)
        orig = {}
        for l in self.q("SELECT code,qty FROM orig_lines WHERE kind=? AND nro=?", (kind, nro)):
            orig[l["code"]] = orig.get(l["code"], 0) + l["qty"]
        sign = 1 if kind in ("O", "NC") else -1   # orden recibida y devolucion suman, conduce resta
        for code in set(cur) | set(orig):
            diff = sign * (cur.get(code, 0) - orig.get(code, 0))
            if abs(diff) > 1e-9:
                self.con.execute("INSERT INTO stock_moves(nro,code,qty,kind) VALUES(?,?,?,?)", (nro, code, diff, kind))

    def save_odoc(self, kind, h, lines, comments):
        nro = int(h["nro"])
        old = self.one("SELECT * FROM odocs WHERE kind=? AND nro=?", (kind, nro))
        subtotal = round(sum(l["qty"] * l["price"] for l in lines), 2)
        itbis = calc_itbis(lines, h.get("discount") or 0)
        total = round(subtotal + itbis - (h.get("discount") or 0), 2)
        cols = ["kind", "nro", "date", "due", "client", "name", "dir1", "dir2", "dir3", "ship_to", "sdir1", "sdir2",
                "sdir3", "rnc", "terms", "ship_via", "seller", "ref", "comment1", "comment2", "comment3", "subtotal",
                "itbis", "discount", "total", "paid", "status", "factura", "deleted", "origin", "modified", "ncf"]
        vals = dict(h, kind=kind, subtotal=subtotal, itbis=itbis, total=total, deleted=0,
                    origin=old["origin"] if old else "app",
                    modified=1 if old and old["origin"] == "monica" else 0,
                    paid=old["paid"] if old else 0,
                    factura=h.get("factura") or (old["factura"] if old else 0))
        vals.setdefault("ncf", old["ncf"] if old else "")
        vals.setdefault("status", old["status"] if old else ("Pendiente" if kind == "O" else ""))
        vals.setdefault("discount", 0)
        self.con.execute(f"INSERT OR REPLACE INTO odocs({','.join(cols)}) VALUES({','.join('?'*len(cols))})",
                         [vals.get(c, "") for c in cols])
        self.con.execute("DELETE FROM olines WHERE kind=? AND nro=?", (kind, nro))
        for i, l in enumerate(lines, 1):
            self.con.execute("INSERT INTO olines(kind,nro,pos,code,descr,qty,price,cost,itbis) VALUES(?,?,?,?,?,?,?,?,?)",
                             (kind, nro, i, l["code"], l["descr"], l["qty"], l["price"], l.get("cost", 0), l.get("itbis", 0)))
        self.con.execute("DELETE FROM ocomments WHERE kind=? AND nro=?", (kind, nro))
        for k, (pos, text) in enumerate(comments):
            self.con.execute("INSERT INTO ocomments VALUES(?,?,?,?,?)", (kind, nro, pos, k, text))
        self._rebuild_odoc_moves(kind, nro)
        self.con.commit()
        return nro

    def set_odoc(self, kind, nro, **kw):
        sets = ", ".join(f"{k}=?" for k in kw)
        self.con.execute(f"UPDATE odocs SET {sets}, modified=CASE WHEN origin='monica' THEN 1 ELSE modified END "
                         "WHERE kind=? AND nro=?", (*kw.values(), kind, nro))
        self._rebuild_odoc_moves(kind, nro)
        self.con.commit()

    def assign_odoc_ncf(self, kind, nro):
        tipo = 3 if kind == "NC" else 4
        ncf = self.take_ncf(tipo)
        if ncf:
            self.set_odoc(kind, nro, ncf=ncf)
        return ncf

    def delete_odoc(self, kind, nro):
        h = self.one("SELECT origin FROM odocs WHERE kind=? AND nro=?", (kind, nro))
        if not h:
            return
        if h["origin"] == "app":
            for t in ("odocs", "olines", "ocomments"):
                self.con.execute(f"DELETE FROM {t} WHERE kind=? AND nro=?", (kind, nro))
            self.con.execute("DELETE FROM stock_moves WHERE kind=? AND nro=?", (kind, nro))
        else:
            self.con.execute("UPDATE odocs SET deleted=1, modified=1 WHERE kind=? AND nro=?", (kind, nro))
            self._rebuild_odoc_moves(kind, nro)
        self.con.commit()

    # ---------- cuentas por cobrar ----------
    def ledger_entries(self, client):
        """Movimientos del cliente como los lleva Monica: facturas y debitos (+), pagos y creditos (-)."""
        inv = {r["nro"]: r for r in self.q("SELECT * FROM invoices WHERE client=?", (client,))}
        out = []
        for r in self.q("SELECT * FROM ledger WHERE client=?", (client,)):
            if r["tipo"] == "P" and r["nro_fact"] in inv and inv[r["nro_fact"]]["unpaid"]:
                continue  # pago de Monica anulado: la factura se corrigio como NO pagada
            if r["tipo"] == "F":
                i = inv.get(r["nro_fact"])
                if i is not None and (i["modified"] or i["origin"] != "monica"):
                    continue  # se toma de la factura actual
            sign = 1 if r["tipo"] in ("F", "D") else -1
            out.append(dict(date=r["date"], due=r["due"], nro=r["nro_fact"] if r["tipo"] == "F" else None,
                            tipo={"F": "Fact.", "P": "Pago", "D": "N/Déb", "C": "N/Cré"}[r["tipo"]],
                            descr=r["descr"], monto=sign * r["monto"]))
        for i in inv.values():
            if i["deleted"] or not (i["modified"] or i["origin"] != "monica"):
                continue
            out.append(dict(date=i["date"], due=i["due"], nro=i["nro"], tipo="Fact.",
                            descr=self.invoice_label(i), monto=i["total"]))
        for p in self.q("SELECT p.*, i.client FROM payments p JOIN invoices i ON i.nro=p.nro WHERE i.client=?", (client,)):
            out.append(dict(date=p["date"], due=p["date"], nro=None, tipo="Pago",
                            descr=f"{p['method']} x Fact.{p['nro']}", monto=-p["amount"]))
        for n in self.q("SELECT * FROM odocs WHERE kind IN ('NC','ND') AND deleted=0 AND origin='app' AND client=?", (client,)):
            nc = n["kind"] == "NC"
            out.append(dict(date=n["date"], due=n["date"], nro=None, tipo="N/Cré" if nc else "N/Déb",
                            descr=f"{'Nota crédito' if nc else 'Nota débito'} {n['nro']} Fact.{n['factura']}",
                            monto=-n["total"] if nc else n["total"]))
        out.sort(key=lambda e: (e["date"] or "", 0 if e["monto"] < 0 else 1))
        return out

    # ---------- cuentas por pagar ----------
    def ap_entries(self, supplier):
        ords = {r["nro"]: r for r in self.q("SELECT * FROM odocs WHERE kind='O' AND client=?", (supplier,))}
        out = []
        for r in self.q("SELECT * FROM ap_ledger WHERE supplier=?", (supplier,)):
            if r["tipo"] == "F":
                o = ords.get(r["nro_orden"])
                if o is not None and (o["modified"] or o["origin"] != "monica"):
                    continue
            sign = 1 if r["tipo"] in ("F", "D") else -1
            out.append(dict(date=r["date"], due=r["due"], nro=r["nro_orden"] if r["tipo"] == "F" else None,
                            tipo={"F": "Compra", "P": "Pago", "D": "N/Déb", "C": "N/Cré"}[r["tipo"]],
                            descr=r["descr"], monto=sign * r["monto"]))
        for o in ords.values():
            if o["deleted"] or o["status"] != "Recibida" or not (o["modified"] or o["origin"] != "monica"):
                continue
            out.append(dict(date=o["date"], due=o["due"] or o["date"], nro=o["nro"], tipo="Compra",
                            descr=f"Compra Nro. {o['nro']}", monto=o["total"]))
        for p in self.q("SELECT p.* FROM ap_payments p JOIN odocs o ON o.kind='O' AND o.nro=p.nro WHERE o.client=?", (supplier,)):
            out.append(dict(date=p["date"], due=p["date"], nro=None, tipo="Pago",
                            descr=f"{p['method']} x Compra {p['nro']}", monto=-p["amount"]))
        out.sort(key=lambda e: (e["date"] or "", 0 if e["monto"] < 0 else 1))
        return out

    def open_payables(self, supplier=None):
        """Compras con saldo, como Monica: saldo de sus documentos por pagar (o total si la compra es de aqui)
        menos los pagos registrados aqui. Devuelve [(dict, saldo)]."""
        pays = {r[0]: r[1] for r in self.q("SELECT nro, SUM(amount) FROM ap_payments GROUP BY nro")}
        names = {r["code"]: r["name"] for r in self.q("SELECT code,name FROM clients")}
        ords = {r["nro"]: r for r in self.q("SELECT * FROM odocs WHERE kind='O'")}
        out = []
        mon = {}
        for r in self.q("SELECT * FROM ap_ledger WHERE tipo='F'" + (" AND supplier=?" if supplier else ""),
                        (supplier,) if supplier else ()):
            m = mon.setdefault(r["nro_orden"], dict(nro=r["nro_orden"], date=r["date"], due=r["due"],
                                                    client=r["supplier"], monto=0, saldo=0))
            m["monto"] += r["monto"]; m["saldo"] += r["saldo"]
        for nro, m in mon.items():
            o = ords.get(nro)
            if o is not None and (o["modified"] or o["origin"] != "monica"):
                continue
            s = round(m["saldo"] - pays.get(nro, 0), 2)
            if s > 0.005:
                out.append((dict(nro=nro, date=m["date"], due=m["due"], client=m["client"],
                                 name=names.get(m["client"], m["client"]), total=m["monto"]), s))
        for o in ords.values():
            if o["deleted"] or o["status"] != "Recibida" or not (o["modified"] or o["origin"] != "monica"):
                continue
            if supplier and o["client"] != supplier:
                continue
            pagado_m = 0
            if o["origin"] == "monica" and o["nro"] in mon:
                pagado_m = max(0, mon[o["nro"]]["monto"] - mon[o["nro"]]["saldo"])
            s = round(o["total"] - pagado_m - pays.get(o["nro"], 0), 2)
            if s > 0.005:
                out.append((dict(nro=o["nro"], date=o["date"], due=o["due"] or o["date"], client=o["client"],
                                 name=o["name"], total=o["total"]), s))
        out.sort(key=lambda t: (t[0]["date"] or "", t[0]["nro"]))
        return out

    def _ap_monica_total(self, nro):
        r = self.one("SELECT SUM(monto) FROM ap_ledger WHERE tipo='F' AND nro_orden=?", (nro,))
        return r[0] if r else None

    def ap_saldo(self, nro):
        for o, s in self.open_payables():
            if o["nro"] == nro:
                return s
        return 0

    def add_ap_payment(self, nro, amount, method="Transferencia", date=None, note=""):
        self.con.execute("INSERT INTO ap_payments(nro,date,amount,method,note) VALUES(?,?,?,?,?)",
                         (nro, fmt_date(date or datetime.date.today()), amount, method, note))
        self.con.commit()

    def invoice_label(self, i):
        lab = {0: "Factura", 1: "Fact. Credito Fiscal", 2: "Fact. Consumidor Final", 14: "Fact. Reg. Especial",
               15: "Fact. Gubernamental", 16: "Fact. Exportaciones"}.get(i["tipo"] if i["ncf"] else 0, "Factura")
        return f"{lab} {i['nro']}"

    def open_invoices(self, client=None):
        """Facturas con saldo > 0 (saldo de Monica menos pagos registrados aqui)."""
        pays = {r[0]: r[1] for r in self.q("SELECT nro, SUM(amount) FROM payments GROUP BY nro")}
        adj = self.notes_adj()
        sql = "SELECT * FROM invoices WHERE deleted=0" + (" AND client=?" if client else "")
        out = []
        for r in self.q(sql + " ORDER BY date, nro", (client,) if client else ()):
            s = round(r["saldo_base"] - pays.get(r["nro"], 0) + adj.get(r["nro"], 0), 2)
            if s > 0.005:
                out.append((r, s))
        return out

    def open_invoices_al(self, al):
        """Facturas con saldo > 0 a la fecha al (date o 'AAAA-MM-DD'): al saldo de hoy se le devuelven
        los pagos, notas de credito y notas de debito con fecha posterior; no entran facturas posteriores."""
        al = al if isinstance(al, str) else fmt_date(al)
        inv = {r["nro"]: r for r in self.q("SELECT * FROM invoices WHERE deleted=0")}
        pays = {r[0]: r[1] for r in self.q("SELECT nro, SUM(amount) FROM payments GROUP BY nro")}
        adj = self.notes_adj()
        despues = {}
        def suma(n, m):
            despues[n] = despues.get(n, 0) + m
        for r in self.q("SELECT nro_fact, tipo, monto FROM ledger WHERE tipo IN ('P','C','D') AND date>?", (al,)):
            i = inv.get(r["nro_fact"])
            if i is None or (r["tipo"] == "P" and i["unpaid"]):
                continue
            suma(r["nro_fact"], r["monto"] if r["tipo"] in ("P", "C") else -r["monto"])
        for r in self.q("SELECT nro, amount FROM payments WHERE date>?", (al,)):
            suma(r["nro"], r["amount"])
        for r in self.q("SELECT kind, factura, total FROM odocs WHERE kind IN ('NC','ND') AND deleted=0 "
                        "AND origin='app' AND factura>0 AND date>?", (al,)):
            suma(r["factura"], r["total"] if r["kind"] == "NC" else -r["total"])
        out = []
        for n, r in sorted(inv.items(), key=lambda kv: (kv[1]["date"] or "", kv[0])):
            if (r["date"] or "") > al:
                continue
            s = round(r["saldo_base"] - pays.get(n, 0) + adj.get(n, 0) + despues.get(n, 0), 2)
            if s > 0.005:
                out.append((r, s))
        return out

    # ---------- respaldo ----------
    def backup_dir(self):
        """Carpeta de respaldos elegida en Configuracion (se crea si no existe) o la de siempre."""
        return self.carpeta("B")

    def _ultimo_respaldo(self):
        fs = glob.glob(os.path.join(self.backup_dir(), "*", "respaldo_*.db"))
        return max(fs, key=os.path.getmtime) if fs else None

    def backup(self, motivo="cierre"):
        """Al cerrar solo se hace respaldo si hubo cambios desde el ultimo respaldo. Devuelve la ruta o None."""
        import filecmp
        self.con.commit()
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        bdir = os.path.join(self.backup_dir(), RESP_CIERRE if motivo == "cierre" else RESP_ANTES)
        os.makedirs(bdir, exist_ok=True)
        dst = os.path.join(bdir, f"respaldo_{ts}_{motivo}.db")
        tmp = dst + ".tmp"
        b = sqlite3.connect(tmp)
        with b:
            self.con.backup(b)
        b.close()
        if motivo == "cierre":
            ult = self._ultimo_respaldo()
            if ult and filecmp.cmp(tmp, ult, shallow=False):
                os.remove(tmp)
                return None   # sin cambios: no se repite el respaldo
        os.replace(tmp, dst)
        keep = int(self.cfg("max_respaldos") or 60)
        files = sorted(glob.glob(os.path.join(bdir, "respaldo_*.db")))
        for f in files[:-keep]:
            try: os.remove(f)
            except OSError: pass
        return dst

    def close(self):
        self.con.commit()
        self.con.close()
