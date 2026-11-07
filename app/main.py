"""Facturacion Canopolis - reemplazo de Monica 8.5 (primera entrega)."""
import os, sys, datetime, traceback, subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db import calc_itbis, DB, APP_NAME, con_carpeta_app, leer_ubicacion, guardar_ubicacion, migrar_viejas, crear_subcarpetas, SUB, TIPOS, TIPOS_FACTURA, fmt_date, parse_date
from importer import import_backup
from pdf_factura import generar_factura, generar_conduce, generar_cotizacion, generar_nota
import reportes

VERSION = "1.61"


def _askyesno_si_no(title=None, message=None, **opts):
    """Pregunta con botones Sí / No (reemplaza el Yes/No de Windows)."""
    parent = opts.get("parent") or tk._default_root
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title or "")
    win.resizable(False, False)
    try:
        if parent is not None and parent.winfo_viewable():
            win.transient(parent)
    except Exception:
        pass
    res = {"v": False}
    def responder(v):
        res["v"] = v
        win.destroy()
    cuerpo = ttk.Frame(win, padding=(18, 16, 18, 8))
    cuerpo.pack(fill="both", expand=True)
    try:
        ttk.Label(cuerpo, image="::tk::icons::question").grid(row=0, column=0, sticky="n", padx=(0, 12))
    except Exception:
        pass
    ttk.Label(cuerpo, text=message or "", justify="left", wraplength=460).grid(row=0, column=1, sticky="w")
    botones = ttk.Frame(win, padding=(18, 4, 18, 14))
    botones.pack(fill="x")
    b_no = ttk.Button(botones, text="No", width=10, command=lambda: responder(False))
    b_no.pack(side="right")
    b_si = ttk.Button(botones, text="Sí", width=10, command=lambda: responder(True))
    b_si.pack(side="right", padx=(0, 8))
    win.protocol("WM_DELETE_WINDOW", lambda: responder(False))
    win.bind("<Escape>", lambda e: responder(False))
    win.bind("<Return>", lambda e: responder(e.widget is not b_no))
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if pw < 50 or ph < 50:
            raise ValueError
        x, y = px + (pw - w) // 2, py + (ph - h) // 3
    except Exception:
        x, y = (win.winfo_screenwidth() - w) // 2, (win.winfo_screenheight() - h) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.deiconify()
    win.lift()
    win.attributes("-topmost", True)
    win.after(200, lambda: win.winfo_exists() and win.attributes("-topmost", False))
    try:
        win.bell()
    except Exception:
        pass
    b_si.focus_set()
    try:
        win.grab_set()
    except Exception:
        pass
    win.wait_window()
    return res["v"]


messagebox.askyesno = _askyesno_si_no
TERMINOS = ["Efectivo", "Tarjeta de crédito/débito", "15 Días", "30 Días", "45 Días", "60 Días", "Credito", "Otros"]
DIAS = {"15 Días": 15, "30 Días": 30, "45 Días": 45, "60 Días": 60, "Credito": 30}


# ---------------- utilidades ----------------
def dmy(s):
    d = parse_date(s) if isinstance(s, str) else s
    return d.strftime("%d/%m/%Y") if d else ""

def read_dmy(s):
    s = (s or "").strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha no válida: '{s}'. Use DD/MM/AAAA")


class FechaEntry(ttk.Frame):
    """Fecha en tres casillas DD / MM / AAAA. DD y MM aceptan solo 2 digitos y AAAA 4;
    al completar una casilla pasa sola a la siguiente. Las / siempre se ven."""
    def __init__(self, parent, var):
        super().__init__(parent)
        self.var = var; self._sync = False
        self.vs = [tk.StringVar(), tk.StringVar(), tk.StringVar()]
        self.lens = (2, 2, 4); self.es = []
        for k, (v, n) in enumerate(zip(self.vs, self.lens)):
            if k: ttk.Label(self, text="/").pack(side="left")
            vc = (self.register(lambda P, n=n: P == "" or (P.isdigit() and len(P) <= n)), "%P")
            e = ttk.Entry(self, textvariable=v, width=n + 1, justify="center", validate="key", validatecommand=vc)
            e.pack(side="left"); self.es.append(e)
            e.bind("<FocusIn>", lambda ev, e=e: e.selection_range(0, "end"))
            e.bind("<KeyPress-BackSpace>", lambda ev, k=k: self._atras(k))
            e.bind("<<Paste>>", lambda ev: self._pegar())
            v.trace_add("write", lambda *a, k=k: self._cambio(k))
        self._desde_var()
        var.trace_add("write", lambda *a: self._desde_var())

    def _desde_var(self):
        if self._sync: return
        t = self.var.get().strip()
        try:
            p = read_dmy(t) if t else None
            partes = (f"{p.day:02d}", f"{p.month:02d}", f"{p.year:04d}") if p else ("", "", "")
        except ValueError:
            partes = ("", "", "")
        self._sync = True
        for v, x in zip(self.vs, partes): v.set(x)
        self._sync = False

    def _cambio(self, k):
        if self._sync: return
        d, m, a = (v.get() for v in self.vs)
        self._sync = True
        self.var.set(f"{d}/{m}/{a}" if (d or m or a) else "")
        self._sync = False
        if len(self.vs[k].get()) == self.lens[k] and k < 2 and self.focus_get() == self.es[k]:
            self.es[k + 1].focus_set(); self.es[k + 1].selection_range(0, "end")

    def _atras(self, k):
        e = self.es[k]
        if k and not self.vs[k].get() and not e.selection_present():
            p = self.es[k - 1]; p.focus_set(); p.icursor("end")
            self.vs[k - 1].set(self.vs[k - 1].get()[:-1]); return "break"
        return None

    def _pegar(self):
        try: dg = "".join(c for c in self.clipboard_get() if c.isdigit())[:8]
        except tk.TclError: return "break"
        self._sync = True
        self.vs[0].set(dg[:2]); self.vs[1].set(dg[2:4]); self.vs[2].set(dg[4:8])
        self._sync = False; self._cambio(2); return "break"

    def bind(self, seq=None, func=None, add=None):
        if seq == "<FocusOut>":
            for e in self.es: e.bind(seq, func, add)
            return
        return super().bind(seq, func, add)


def fecha_entry(parent, var, width=11):
    return FechaEntry(parent, var)

def pedir_fecha(parent, titulo, texto, inicial):
    """Ventana para escribir una fecha DD / MM / AAAA. OK o Enter acepta. Devuelve date o None."""
    top = tk.Toplevel(parent); top.title(titulo); top.transient(parent); top.grab_set(); top.resizable(False, False)
    v = tk.StringVar(value=inicial); res = {}
    ttk.Label(top, text=texto).pack(padx=14, pady=(12, 6))
    fe = FechaEntry(top, v); fe.pack(padx=14)
    def ok(*a):
        try:
            res["d"] = read_dmy(v.get())
        except ValueError as e:
            messagebox.showwarning("Fecha", str(e), parent=top); return
        top.destroy()
    bf = ttk.Frame(top); bf.pack(pady=10)
    ttk.Button(bf, text="OK", command=ok).pack(side="left", padx=6)
    ttk.Button(bf, text="Cancelar", command=top.destroy).pack(side="left", padx=6)
    top.bind("<Return>", ok); top.bind("<KP_Enter>", ok); top.bind("<Escape>", lambda e: top.destroy())
    try:
        fe.es[0].focus_set(); fe.es[0].select_range(0, "end")
    except Exception:
        pass
    top.wait_window()
    return res.get("d")

def pedir_hoy_o_fecha(parent, titulo):
    """Hoy (fecha del sistema) o Al DD / MM / AAAA. OK o Enter acepta. Devuelve date o None."""
    hoy = datetime.date.today()
    top = tk.Toplevel(parent); top.title(titulo); top.transient(parent); top.grab_set(); top.resizable(False, False)
    modo = tk.StringVar(value="hoy"); v = tk.StringVar(value=dmy(hoy)); res = {}
    fr = ttk.Frame(top); fr.pack(padx=14, pady=(12, 4), anchor="w")
    ttk.Radiobutton(fr, text=f"Hoy ({dmy(hoy)})", value="hoy", variable=modo).grid(row=0, column=0, sticky="w", pady=3)
    ttk.Radiobutton(fr, text="Al", value="al", variable=modo).grid(row=1, column=0, sticky="w", pady=3)
    fe = FechaEntry(fr, v); fe.grid(row=1, column=1, sticky="w", padx=6)
    for e in fe.es:
        e.bind("<FocusIn>", lambda ev: modo.set("al"), add="+")
    def ok(*a):
        if modo.get() == "hoy":
            res["d"] = hoy
        else:
            try:
                res["d"] = read_dmy(v.get())
            except ValueError as e:
                messagebox.showwarning("Fecha", str(e), parent=top); return
        top.destroy()
    bf = ttk.Frame(top); bf.pack(pady=10)
    ttk.Button(bf, text="OK", command=ok).pack(side="left", padx=6)
    ttk.Button(bf, text="Cancelar", command=top.destroy).pack(side="left", padx=6)
    top.bind("<Return>", ok); top.bind("<KP_Enter>", ok); top.bind("<Escape>", lambda e: top.destroy())
    top.focus_set()
    top.wait_window()
    return res.get("d")

def menu_edicion(root):
    """Clic derecho en cualquier casilla: Cortar, Copiar, Pegar, Borrar y Seleccionar todo."""
    m = tk.Menu(root, tearoff=0)
    def estado_editable(w):
        try:
            if hasattr(w, "instate") and (w.instate(["readonly"]) or w.instate(["disabled"])):
                return False
            return str(w.cget("state")) not in ("disabled", "readonly")
        except Exception:
            return True
    def hay_sel(w):
        try:
            if isinstance(w, tk.Text):
                return bool(w.tag_ranges("sel"))
            return w.selection_present()
        except Exception:
            return False
    def borrar(w):
        if isinstance(w, tk.Text):
            if w.tag_ranges("sel"): w.delete("sel.first", "sel.last")
            else: w.delete("1.0", "end")
        else:
            if w.selection_present(): w.delete("sel.first", "sel.last")
            else: w.delete(0, "end")
    def sel_todo(w):
        if isinstance(w, tk.Text):
            w.tag_add("sel", "1.0", "end-1c")
        else:
            w.selection_range(0, "end"); w.icursor("end")
    def mostrar(ev):
        w = ev.widget
        try:
            w.focus_set()
        except Exception:
            pass
        ed, sel = estado_editable(w), hay_sel(w)
        try:
            pegable = bool(root.clipboard_get())
        except Exception:
            pegable = False
        m.delete(0, "end")
        m.add_command(label="Cortar", state="normal" if ed and sel else "disabled", command=lambda: w.event_generate("<<Cut>>"))
        m.add_command(label="Copiar", state="normal" if sel else "disabled", command=lambda: w.event_generate("<<Copy>>"))
        m.add_command(label="Pegar", state="normal" if ed and pegable else "disabled", command=lambda: w.event_generate("<<Paste>>"))
        m.add_command(label="Borrar", state="normal" if ed else "disabled", command=lambda: borrar(w))
        m.add_separator()
        m.add_command(label="Seleccionar todo", command=lambda: sel_todo(w))
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            m.grab_release()
        return "break"
    for clase in ("Entry", "TEntry", "TCombobox", "Text", "Spinbox", "TSpinbox"):
        root.bind_class(clase, "<Button-3>", mostrar, add="+")


def confirmar_existencias(db, lines, nro, titulo, parent=None, kind="F", doc="la factura"):
    """Avisa si algun producto no alcanza. Devuelve True si se puede seguir."""
    f = db.faltantes(lines, nro, kind)
    if not f:
        return True
    q = lambda n: f"{n:,.2f}".rstrip("0").rstrip(".")
    det = "\n".join(f"{c} {d}: hay {q(h)}, {doc} lleva {q(l)}, quedaría en {q(r)}" for c, d, h, l, r in f[:20])
    if len(f) > 20:
        det += f"\n... y {len(f) - 20} más"
    return messagebox.askyesno(titulo, "No hay existencia suficiente de:\n\n" + det +
                               f"\n\n¿Crear {doc} de todos modos?", parent=parent)


def num(s, default=0.0):
    s = str(s).replace(",", "").strip()
    if not s:
        return default
    return float(s)

def m2(v):
    return f"{v:,.2f}"

def open_file(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass

ITBIS_OPC = ["0", "16", "18"]

def itbis_txt(v):
    try:
        return f"{float(v or 0):g}"
    except (TypeError, ValueError):
        return "0"

def tipo_nombre(t):
    return TIPOS.get(t, TIPOS[0])[0]


def menu_derecho(tv, parent, opciones):
    """Menu de clic derecho estilo Windows sobre la fila ya seleccionada con clic izquierdo."""
    mnu = tk.Menu(parent, tearoff=0)
    for t, cmd in opciones:
        mnu.add_command(label=t, command=cmd)
    mnu.add_separator()
    mnu.add_command(label="Cerrar", command=mnu.unpost)
    def abrir(ev):
        fila = tv.identify_row(ev.y)
        if not fila or fila not in tv.selection():
            return "break"
        try:
            mnu.tk_popup(ev.x_root, ev.y_root)
        finally:
            mnu.grab_release()
        return "break"
    tv.bind("<Button-3>", abrir)
    return mnu


class Picker(tk.Toplevel):
    """Ventana de busqueda: escribe para filtrar, doble clic o Enter para elegir."""
    def __init__(self, parent, title, cols, rows, widths=None, inicial=""):
        super().__init__(parent)
        self.title(title); self.result = None; self.rows = rows
        self.transient(parent); self.grab_set(); self.geometry("760x460")
        self.var = tk.StringVar(value=inicial)
        e = ttk.Entry(self, textvariable=self.var); e.pack(fill="x", padx=8, pady=6); e.focus_set()
        self.tv = ttk.Treeview(self, columns=cols, show="headings")
        for i, c in enumerate(cols):
            self.tv.heading(c, text=c); self.tv.column(c, width=(widths or [120]*len(cols))[i])
        self.tv.pack(fill="both", expand=True, padx=8)
        ttk.Button(self, text="Elegir", command=self.ok).pack(pady=6)
        self.var.trace_add("write", lambda *a: self.fill())
        self.tv.bind("<Double-1>", lambda e: self.ok())
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        e.bind("<Down>", lambda ev: (self.tv.focus_set(), self.tv.selection_set(self.tv.get_children()[:1])))
        self.fill(); self.wait_window()

    def fill(self):
        f = self.var.get().lower()
        self.tv.delete(*self.tv.get_children())
        for r in self.rows:
            if not f or f in " ".join(str(x) for x in r).lower():
                self.tv.insert("", "end", values=r)
        ch = self.tv.get_children()
        if ch: self.tv.selection_set(ch[0])

    def ok(self):
        sel = self.tv.selection()
        if sel:
            self.result = self.tv.item(sel[0], "values")
        self.destroy()


def form_dialog(parent, title, fields, values):
    """fields: list of (key, label, kind) kind in 'text','combo:a|b','num'. Returns dict or None."""
    top = tk.Toplevel(parent); top.title(title); top.transient(parent); top.grab_set()
    vars_ = {}; res = {}
    for i, (k, lab, kind) in enumerate(fields):
        ttk.Label(top, text=lab).grid(row=i, column=0, sticky="e", padx=6, pady=3)
        v = tk.StringVar(value=str(values.get(k, "") if values.get(k) is not None else ""))
        if kind.startswith("combo:"):
            w = ttk.Combobox(top, textvariable=v, values=kind[6:].split("|"), width=48)
        else:
            w = fecha_entry(top, v, 12) if kind == "date" else ttk.Entry(top, textvariable=v, width=50)
            if kind == "readonly": w.state(["readonly"])
        w.grid(row=i, column=1, sticky="w", padx=6, pady=3); vars_[k] = v
    def ok():
        for k, v in vars_.items(): res[k] = v.get().strip()
        top.destroy()
    bf = ttk.Frame(top); bf.grid(row=len(fields), column=0, columnspan=2, pady=8)
    ttk.Button(bf, text="Guardar", command=ok).pack(side="left", padx=6)
    ttk.Button(bf, text="Cancelar", command=top.destroy).pack(side="left", padx=6)
    top.wait_window()
    return res or None


KIND_NAME = {"F": "Factura", "Q": "Cotización", "G": "Conduce", "O": "Orden de compra",
             "NC": "Nota de crédito", "ND": "Nota de débito"}


def gen_doc(db, kind, nro, ruta):
    if kind == "G":
        return generar_conduce(db, nro, ruta)
    if kind in ("NC", "ND"):
        return generar_nota(db, kind, nro, ruta)
    return generar_cotizacion(db, kind, nro, ruta)

# ---------------- editor de factura / documentos ----------------
class InvoiceEditor(tk.Toplevel):
    def __init__(self, app, nro=None, kind="F", prefill=None, ref_invoice=0):
        super().__init__(app.root)
        self.app = app; self.db = app.db; self.saved = False; self.kind = kind; self.saved_nro = None
        self.ref_invoice = ref_invoice
        self.devol = tk.BooleanVar(value=True)
        kn = KIND_NAME[kind]
        self.title(f"{kn} nueva" if nro is None else f"Editar {kn.lower()} {nro}")
        self.geometry("1050x700"); self.transient(app.root); self.grab_set()
        self.lines = []      # dicts code,descr,qty,price,cost,itbis
        self.comments = []   # [pos, text]
        self.orig = None
        if prefill is not None:
            h, ls, cs = prefill
            self.lines = [dict(code=l["code"], descr=l["descr"], qty=l["qty"], price=l["price"],
                               cost=l["cost"], itbis=l["itbis"]) for l in ls]
            self.comments = [[c["pos"], c["text"]] for c in cs]
        if nro is not None:
            h, ls, cs = self.db.invoice_full(nro) if kind == "F" else self.db.odoc_full(kind, nro)
            self.orig = dict(h)
            if kind in ("NC", "ND"):
                self.ref_invoice = h["factura"]; self.devol.set(h["status"] == "Con devolución")
            self.lines = [dict(code=l["code"], descr=l["descr"], qty=l["qty"], price=l["price"],
                               cost=l["cost"], itbis=l["itbis"]) for l in ls]
            self.comments = [[c["pos"], c["text"]] for c in cs]
        self.build()
        if self.orig:
            self.load_header(self.orig)
        else:
            self.v["nro"].set(str(self.db.next_invoice_no() if kind == "F" else self.db.next_odoc_no(kind)))
            self.v["date"].set(dmy(datetime.date.today()))
            self.v["ship_via"].set(self.db.cfg("envio"))
            self.v["comment2"].set(self.db.cfg("coment2"))
            self.v["comment3"].set(self.db.cfg("coment3"))
            self.v["tipo"].set(tipo_nombre(1))
            self.v["terms"].set("Efectivo"); self.upd_due()
            if prefill is not None:
                ph = prefill[0]
                self.fill_client(ph["client"])
                for k in ("name", "dir1", "dir2", "dir3", "rnc", "terms", "ship_via", "seller", "ref"):
                    if ph[k]: self.v[k].set(ph[k])
                self.upd_due()
        self.refresh_lines()

    def build(self):
        self.v = {k: tk.StringVar() for k in ("nro", "date", "due", "client", "name", "dir1", "dir2", "dir3",
                                             "rnc", "terms", "ship_via", "seller", "ref", "comment1",
                                             "comment2", "comment3", "tipo", "ncf", "discount",
                                             "ship_to", "sdir1", "sdir2", "sdir3")}
        f = ttk.Frame(self); f.pack(fill="x", padx=8, pady=6)
        def L(r, c, t): ttk.Label(f, text=t).grid(row=r, column=c, sticky="e", padx=4, pady=2)
        def E(r, c, k, w=30, **kw):
            e = fecha_entry(f, self.v[k], w) if k in ("date", "due") else ttk.Entry(f, textvariable=self.v[k], width=w, **kw); e.grid(row=r, column=c, sticky="w", padx=4, pady=2); return e
        L(0, 0, f"{KIND_NAME[self.kind]} Nro."); E(0, 1, "nro", 10).state(["readonly"])
        if self.kind == "F":
            L(0, 2, "Tipo"); cb = ttk.Combobox(f, textvariable=self.v["tipo"], width=30, state="readonly",
                                                values=[tipo_nombre(t) for t in TIPOS_FACTURA])
            cb.grid(row=0, column=3, sticky="w", padx=4)
            L(0, 4, "NCF"); E(0, 5, "ncf", 24).state(["readonly"])
        if self.kind in ("NC", "ND"):
            inv = self.db.one("SELECT ncf FROM invoices WHERE nro=?", (self.ref_invoice,))
            ttk.Label(f, text=f"Afecta la factura {self.ref_invoice}   NCF modificado: {(inv['ncf'] if inv else '') or '(sin NCF)'}",
                      font=("Segoe UI", 10, "bold")).grid(row=0, column=2, columnspan=3, sticky="w", padx=6)
            if self.kind == "NC":
                ttk.Checkbutton(f, text="Devolver los productos al inventario", variable=self.devol).grid(
                    row=0, column=5, sticky="w")
        quien = "Proveedor" if self.kind == "O" else "Cliente"
        L(1, 0, quien); ce = E(1, 1, "client", 10)
        ttk.Button(f, text=f"Buscar {quien.lower()}", command=self.pick_client).grid(row=1, column=2, sticky="w")
        ce.bind("<Return>", lambda e: self.fill_client(self.v["client"].get().strip()))

        L(2, 0, "Nombre"); E(2, 1, "name", 45).grid(columnspan=3)
        L(3, 0, "Línea 1"); E(3, 1, "dir1", 45).grid(columnspan=3)
        L(4, 0, "Línea 2"); E(4, 1, "dir2", 45).grid(columnspan=3)
        L(5, 0, "Línea 3"); E(5, 1, "dir3", 45).grid(columnspan=3)
        L(6, 0, "Reg. Tribut."); E(6, 1, "rnc", 20)
        L(1, 4, "Fecha (DD/MM/AAAA)"); de = E(1, 5, "date", 12)
        de.bind("<FocusOut>", lambda e: self.upd_due())
        L(2, 4, "Condiciones"); tc = ttk.Combobox(f, textvariable=self.v["terms"], values=TERMINOS, width=12)
        tc.grid(row=2, column=5, sticky="w", padx=4); tc.bind("<<ComboboxSelected>>", lambda e: self.upd_due())
        L(3, 4, "Vencimiento"); E(3, 5, "due", 12)
        L(4, 4, "Envío"); E(4, 5, "ship_via", 14)
        L(5, 4, "Vendedor"); E(5, 5, "seller", 14)
        L(6, 4, "Referencia"); E(6, 5, "ref", 24)
        L(7, 0, "Comentario 1"); E(7, 1, "comment1", 45).grid(columnspan=3)
        L(7, 4, "Descuento"); E(7, 5, "discount", 12)
        L(8, 0, "Comentario 2"); E(8, 1, "comment2", 45).grid(columnspan=3)
        L(9, 0, "Comentario 3"); E(9, 1, "comment3", 45).grid(columnspan=3)

        lf = ttk.LabelFrame(self, text="Productos"); lf.pack(fill="both", expand=True, padx=8, pady=4)
        add = ttk.Frame(lf); add.pack(fill="x", pady=4)
        self.pv = {k: tk.StringVar() for k in ("code", "descr", "qty", "price", "venta", "itbis")}
        self.pv["itbis"].set("0")
        ttk.Label(add, text="Código").pack(side="left")
        pe = ttk.Entry(add, textvariable=self.pv["code"], width=12); pe.pack(side="left", padx=3)
        pe.bind("<Return>", lambda e: self.fill_product(self.pv["code"].get().strip()))
        ttk.Button(add, text="Buscar", command=self.pick_product).pack(side="left")
        ttk.Label(add, text="Descripción").pack(side="left", padx=(8, 0))
        ttk.Entry(add, textvariable=self.pv["descr"], width=38).pack(side="left", padx=3)
        ttk.Label(add, text="Cant.").pack(side="left")
        qe = ttk.Entry(add, textvariable=self.pv["qty"], width=8); qe.pack(side="left", padx=3)
        ttk.Label(add, text="Costo" if self.kind == "O" else "Precio").pack(side="left")
        pr = ttk.Entry(add, textvariable=self.pv["price"], width=10); pr.pack(side="left", padx=3)
        if self.kind == "O":
            ttk.Label(add, text="Precio venta").pack(side="left")
            ttk.Entry(add, textvariable=self.pv["venta"], width=10).pack(side="left", padx=3)
        ttk.Label(add, text="ITBIS %").pack(side="left")
        ttk.Combobox(add, textvariable=self.pv["itbis"], values=ITBIS_OPC, width=4, state="readonly").pack(side="left", padx=3)
        ttk.Button(add, text="Agregar línea", command=self.add_line).pack(side="left", padx=6)
        pr.bind("<Return>", lambda e: self.add_line()); qe.bind("<Return>", lambda e: self.add_line())

        if self.kind == "O":
            cols = ("#", "Código", "Descripción / comentario", "Cantidad", "Costo", "ITBIS %", "Subtotal", "Precio venta", "Existencia")
            anchos = (40, 100, 300, 80, 100, 60, 110, 100, 90)
        else:
            cols = ("#", "Código", "Descripción / comentario", "Cantidad", "Precio", "ITBIS %", "Subtotal", "Existencia")
            anchos = (40, 100, 340, 80, 100, 60, 110, 90)
        self.tv = ttk.Treeview(lf, columns=cols, show="headings", height=12)
        for c, w in zip(cols, anchos):
            self.tv.heading(c, text=c); self.tv.column(c, width=w, anchor="e" if c in ("Cantidad", "Precio", "Costo", "ITBIS %", "Subtotal", "Precio venta", "Existencia") else "w")
        self.tv.pack(fill="both", expand=True)
        self.tv.bind("<Double-1>", lambda e: self.edit_line())
        menu_derecho(self.tv, self, (("Cambiar cantidad/precio", self.edit_line), ("Quitar línea", self.del_line),
                                     ("Agregar comentario a la línea", self.add_comment)))
        bf = ttk.Frame(lf); bf.pack(fill="x", pady=4)
        ttk.Button(bf, text="Cambiar cantidad/precio", command=self.edit_line).pack(side="left", padx=3)
        ttk.Button(bf, text="Quitar línea", command=self.del_line).pack(side="left", padx=3)
        ttk.Button(bf, text="Agregar comentario a la línea", command=self.add_comment).pack(side="left", padx=3)
        self.tot = ttk.Label(bf, text="", font=("Segoe UI", 11, "bold")); self.tot.pack(side="right", padx=8)

        b = ttk.Frame(self); b.pack(fill="x", padx=8, pady=8)
        ttk.Button(b, text="Guardar y abrir PDF", command=self.save).pack(side="right", padx=4)
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)

    def load_header(self, h):
        h = dict(h)
        for k in ("tipo", "ncf"): h.setdefault(k, 0 if k == "tipo" else "")
        for k in ("ship_to", "sdir1", "sdir2", "sdir3"): h.setdefault(k, "")
        for k in self.v:
            if k == "tipo":
                self.v[k].set(tipo_nombre(h["tipo"] if h["ncf"] or h["tipo"] else 0))
            elif k in ("date", "due"):
                self.v[k].set(dmy(h[k]))
            elif k == "discount":
                self.v[k].set(m2(h["discount"]) if h["discount"] else "")
            else:
                self.v[k].set(h[k] if h[k] is not None else "")

    def tipo_code(self):
        n = self.v["tipo"].get()
        for t in TIPOS_FACTURA:
            if tipo_nombre(t) == n:
                return t
        return 0

    def upd_due(self):
        try:
            d = read_dmy(self.v["date"].get())
        except ValueError:
            return
        self.v["due"].set(dmy(d + datetime.timedelta(days=DIAS.get(self.v["terms"].get(), 0))))

    def pick_client(self):
        ct = "S" if self.kind == "O" else "C"
        rows = [(c["code"], c["name"], c["rnc"] or "", c["phone"] or "") for c in
                self.db.q("SELECT * FROM clients WHERE COALESCE(ctype,'C')=? ORDER BY name", (ct,))]
        p = Picker(self, "Buscar proveedor" if ct == "S" else "Buscar cliente", ("Código", "Nombre", "RNC", "Teléfono"), rows, [90, 330, 140, 150])
        if p.result:
            self.fill_client(p.result[0])

    def fill_client(self, code):
        if not self.db.one("SELECT 1 FROM clients WHERE code=?", (code,)):
            messagebox.showwarning("Cliente", f"No existe el cliente '{code}'.", parent=self); return
        b = self.db.client_print_block(code)
        self.v["client"].set(code)
        for k in ("name", "dir1", "dir2", "dir3", "rnc"):
            self.v[k].set(b[k])
        if b["terms"] in TERMINOS:
            self.v["terms"].set(b["terms"])
        if self.kind == "O":
            self.v["ship_to"].set(self.db.cfg("emp_nombre").upper())
            self.v["sdir1"].set(self.db.cfg("emp_l1")); self.v["sdir2"].set(self.db.cfg("emp_l3")); self.v["sdir3"].set("")
        else:
            self.v["ship_to"].set("")
            for a, b2 in (("sdir1", "dir1"), ("sdir2", "dir2"), ("sdir3", "dir3")):
                self.v[a].set(self.v[b2].get())
        self.upd_due()

    def pick_product(self):
        rows = [(p["code"], p["descr"], m2(p["price"]), m2(self.db.stock(p["code"]))) for p in
                self.db.q("SELECT * FROM products WHERE active=1 ORDER BY code")]
        p = Picker(self, "Buscar producto", ("Código", "Descripción", "Precio", "Existencia"), rows, [110, 380, 110, 100])
        if p.result:
            self.fill_product(p.result[0])

    def fill_product(self, code):
        p = self.db.one("SELECT * FROM products WHERE code=?", (code,))
        if not p:
            messagebox.showwarning("Producto", f"No existe el producto '{code}'.", parent=self); return
        self.pv["code"].set(p["code"]); self.pv["descr"].set(p["descr"])
        if self.kind == "O":
            self.pv["price"].set(f"{(p['cost'] or 0):.2f}"); self.pv["venta"].set(f"{p['price']:.2f}")
        else:
            self.pv["price"].set(f"{p['price']:.2f}")
        if not self.pv["qty"].get(): self.pv["qty"].set("1")
        self.pv["itbis"].set(itbis_txt(p["itbis"]))

    def add_line(self):
        code = self.pv["code"].get().strip()
        p = self.db.one("SELECT * FROM products WHERE code=?", (code,))
        if not p and self.kind in ("NC", "ND") and self.pv["descr"].get().strip():
            p = {"descr": self.pv["descr"].get().strip(), "price": 0, "cost": 0, "itbis": 0}
        if not p:
            messagebox.showwarning("Producto", "Elija un producto existente.", parent=self); return
        try:
            qty = num(self.pv["qty"].get(), 1)
            price = num(self.pv["price"].get(), (p["cost"] or 0) if self.kind == "O" else p["price"])
            venta = self.pv["venta"].get().strip()
            if venta: num(venta)
        except ValueError:
            messagebox.showwarning("Producto", "Cantidad o precio no válido.", parent=self); return
        self.lines.append(dict(code=code, descr=self.pv["descr"].get() or p["descr"], qty=qty, price=price,
                               cost=p["cost"], itbis=num(self.pv["itbis"].get(), 0), venta=venta))
        for k in self.pv: self.pv[k].set("")
        self.pv["itbis"].set("0")
        self.refresh_lines()

    def refresh_lines(self):
        self.tv.delete(*self.tv.get_children())
        for i, l in enumerate(self.lines, 1):
            vals = [i, l["code"], l["descr"], m2(l["qty"]), m2(l["price"]), itbis_txt(l["itbis"]), m2(l["qty"] * l["price"])]
            if self.kind == "O":
                vals.append(m2(num(l["venta"])) if l.get("venta") else "")
            vals.append(m2(self.db.stock(l["code"])))
            self.tv.insert("", "end", iid=f"L{i}", values=vals)
            for k, (pos, txt) in enumerate(self.comments):
                if pos == i:
                    self.tv.insert("", "end", iid=f"C{k}", values=["", "", "   " + txt] + [""] * (len(vals) - 3))
        sub = sum(l["qty"] * l["price"] for l in self.lines)
        try: dsc = num(self.v["discount"].get())
        except ValueError: dsc = 0
        itb = calc_itbis([dict(l, itbis=l["itbis"] or 0) for l in self.lines], dsc)
        self.tot.config(text=f"Subtotal {m2(sub)}   ITBIS {m2(itb)}   TOTAL {m2(sub + itb - dsc)}")

    def sel(self):
        s = self.tv.selection()
        return s[0] if s else None

    def edit_line(self):
        s = self.sel()
        if not s: return
        if s.startswith("C"):
            k = int(s[1:])
            r = form_dialog(self, "Comentario", [("text", "Texto", "text")], {"text": self.comments[k][1]})
            if r is not None: self.comments[k][1] = r["text"]
        else:
            i = int(s[1:]) - 1; l = self.lines[i]
            campos = [("descr", "Descripción", "text"), ("qty", "Cantidad", "num"),
                      ("price", "Costo" if self.kind == "O" else "Precio", "num")]
            if self.kind == "O":
                campos.append(("venta", "Precio venta (vacío = no cambia)", "num"))
            campos.append(("itbis", "ITBIS %", "combo:" + "|".join(ITBIS_OPC)))
            r = form_dialog(self, "Línea", campos,
                            {"descr": l["descr"], "qty": l["qty"], "price": l["price"], "venta": l.get("venta", ""),
                             "itbis": itbis_txt(l["itbis"])})
            if r is not None:
                try:
                    if r.get("venta"): num(r["venta"])
                    l.update(descr=r["descr"], qty=num(r["qty"]), price=num(r["price"]), itbis=num(r["itbis"], 0))
                    if self.kind == "O": l["venta"] = r.get("venta", "")
                except ValueError:
                    messagebox.showwarning("Línea", "Valor no válido.", parent=self)
        self.refresh_lines()

    def del_line(self):
        s = self.sel()
        if not s: return
        if s.startswith("C"):
            del self.comments[int(s[1:])]
        else:
            i = int(s[1:])
            del self.lines[i - 1]
            self.comments = [[p if p < i else p - 1, t] for p, t in self.comments if p != i]
        self.refresh_lines()

    def add_comment(self):
        s = self.sel()
        pos = len(self.lines)
        if s and s.startswith("L"): pos = int(s[1:])
        if not pos:
            messagebox.showinfo("Comentario", "Primero agregue una línea de producto.", parent=self); return
        r = form_dialog(self, "Comentario", [("text", "Texto", "text")], {})
        if r and r["text"]:
            self.comments.append([pos, r["text"]]); self.refresh_lines()

    def save(self):
        if not self.lines:
            messagebox.showwarning("Factura", "La factura no tiene productos.", parent=self); return
        if not self.v["client"].get().strip():
            messagebox.showwarning("Factura", "Elija el cliente.", parent=self); return
        try:
            d = read_dmy(self.v["date"].get()); due = read_dmy(self.v["due"].get() or self.v["date"].get())
            dsc = num(self.v["discount"].get())
        except ValueError as e:
            messagebox.showwarning("Factura", str(e), parent=self); return
        h = {k: self.v[k].get().strip() for k in self.v}
        if self.kind != "F":
            for k in ("tipo", "ncf"): h.pop(k, None)
            h.update(nro=int(h["nro"]), date=fmt_date(d), due=fmt_date(due), discount=dsc)
            aviso = ""
            if self.kind == "G" and not getattr(self, "ref_invoice", None):
                existe = self.db.one("SELECT factura FROM odocs WHERE kind='G' AND nro=?", (h["nro"],))
                if not (existe and existe["factura"]) and not confirmar_existencias(
                        self.db, self.lines, h["nro"] if existe else None, "Conduce", self, "G", "el conduce"):
                    return
            if self.kind in ("NC", "ND"):
                h["factura"] = self.ref_invoice
                h["status"] = ("Con devolución" if self.devol.get() else "Sin devolución") if self.kind == "NC" else ""
            try:
                nro = self.db.save_odoc(self.kind, h, self.lines, [tuple(c) for c in self.comments])
                if self.kind == "O":
                    for l in self.lines:
                        if l.get("venta"):
                            self.db.set_sale_price(l["code"], num(l["venta"]))
                if self.kind in ("NC", "ND") and not self.db.one("SELECT ncf FROM odocs WHERE kind=? AND nro=?", (self.kind, nro))[0]:
                    if not self.db.assign_odoc_ncf(self.kind, nro):
                        aviso = (f"No hay comprobantes disponibles para {KIND_NAME[self.kind].lower()}.\n"
                                 "Se guardó sin NCF; asígnelo después desde su pestaña con 'Asignar NCF'.")
                ruta = self.app.doc_path(self.kind, nro)
                gen_doc(self.db, self.kind, nro, ruta)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self); return
            self.saved = True; self.saved_nro = nro
            if aviso: messagebox.showwarning("Comprobante", aviso, parent=self)
            open_file(ruta); self.destroy(); return
        tipo = self.tipo_code()
        h.update(nro=int(h["nro"]), date=fmt_date(d), due=fmt_date(due), discount=dsc, tipo=tipo)
        if not confirmar_existencias(self.db, self.lines, h["nro"] if self.orig else None, "Factura", self):
            return
        aviso = ""
        ncf = h["ncf"]
        if self.orig and ncf and tipo != self.orig["tipo"]:
            if not messagebox.askyesno("NCF", "Cambió el tipo de una factura que ya tiene NCF.\n"
                                       "El NCF actual se quitará y la factura quedará pendiente de comprobante. ¿Seguir?", parent=self):
                return
            ncf = ""
        if not ncf and tipo != 0:
            ncf = self.db.take_ncf(tipo)
            if not ncf:
                aviso = (f"No hay comprobantes disponibles para '{tipo_nombre(tipo)}'.\n"
                         "La factura se guardó sin NCF (pendiente). Cuando cargue la secuencia nueva, "
                         "asígnelo desde Ventas > Asignar NCF.")
        h["ncf"] = ncf
        try:
            nro = self.db.save_invoice(h, self.lines, [tuple(c) for c in self.comments])
            ruta = self.app.pdf_path(nro)
            generar_factura(self.db, nro, ruta)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self); return
        self.saved = True; self.saved_nro = nro
        if aviso:
            messagebox.showwarning("Comprobante", aviso, parent=self)
        open_file(ruta)
        self.destroy()


# ---------------- pestañas de cotizaciones / conduces / ordenes ----------------
class DocTab:
    def __init__(self, app, kind):
        self.app = app; self.db = app.db; self.kind = kind
        fr = ttk.Frame(app.nb)
        app.nb.add(fr, text={"Q": "Cotizaciones", "G": "Conduces", "O": "Órdenes de compra",
                             "NC": "Notas de crédito", "ND": "Notas de débito"}[kind])
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        first = self.db.one("SELECT MIN(date) FROM odocs WHERE kind=?", (kind,))[0]
        self.vd = tk.StringVar(value=dmy(first) if first else dmy(datetime.date.today()))
        self.vh = tk.StringVar(value=dmy(datetime.date.today())); self.vs = tk.StringVar()
        ttk.Label(top, text="Desde").pack(side="left", padx=3); fecha_entry(top, self.vd, 11).pack(side="left")
        ttk.Label(top, text="Hasta").pack(side="left", padx=3); fecha_entry(top, self.vh, 11).pack(side="left")
        ttk.Label(top, text="Buscar").pack(side="left", padx=(10, 3))
        e = ttk.Entry(top, textvariable=self.vs, width=25); e.pack(side="left"); e.bind("<Return>", lambda ev: self.load())
        ttk.Button(top, text="Mostrar", command=self.load).pack(side="left", padx=4)
        cols = ("Nro", "Fecha", "Proveedor" if kind == "O" else "Cliente", "Nombre", "Total",
                "NCF / Factura" if kind in ("NC", "ND") else "Estado")
        self.tv = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (70, 90, 80, 380, 120, 150)):
            self.tv.heading(c, text=c); self.tv.column(c, width=w, anchor="e" if c in ("Nro", "Total") else "w")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv.yview); self.tv.configure(yscrollcommand=sb.set)
        b = ttk.Frame(fr); b.pack(side="bottom", fill="x", pady=4)
        sb.pack(side="right", fill="y"); self.tv.pack(fill="both", expand=True)
        self.tv.bind("<Double-1>", lambda ev: self.pdf())
        acts = [("Nuevo", self.new), ("Editar", self.edit), ("Ver / descargar PDF", self.pdf)]
        if kind in ("Q", "G"):
            acts.append(("Convertir en factura", self.to_invoice))
        if kind == "O":
            acts.append(("Marcar recibida / pendiente", self.toggle_recv))
        if kind in ("NC", "ND"):
            acts.append(("Asignar NCF", self.assign_ncf))
        acts.append(("Eliminar", self.delete))
        for t, cmd in acts:
            ttk.Button(b, text=t, command=cmd).pack(side="left", padx=3)
        self.lbl = ttk.Label(b, text=""); self.lbl.pack(side="right", padx=8)
        if True:   # menu de clic derecho en todas estas pestanas
            self.mnu = tk.Menu(app.root, tearoff=0)
            for t, cmd in acts:
                if t != "Nuevo":
                    self.mnu.add_command(label=t, command=cmd)
            self.mnu.add_separator()
            self.mnu.add_command(label="Cerrar", command=self.mnu.unpost)
            self.tv.bind("<Button-3>", self.menu)

    def menu(self, ev):
        fila = self.tv.identify_row(ev.y)
        if not fila or fila not in self.tv.selection():
            return "break"
        try:
            self.mnu.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.mnu.grab_release()
        return "break"

    def load(self):
        try:
            d1 = fmt_date(read_dmy(self.vd.get())); d2 = fmt_date(read_dmy(self.vh.get()))
        except ValueError as e:
            messagebox.showwarning("Fechas", str(e)); return
        self.tv.delete(*self.tv.get_children())
        s = self.vs.get().strip().lower(); n = 0; tot = 0
        for r in self.db.q("SELECT * FROM odocs WHERE kind=? AND deleted=0 AND date BETWEEN ? AND ? ORDER BY nro DESC",
                           (self.kind, d1, d2)):
            if s and s not in f"{r['nro']} {r['client']} {r['name']}".lower(): continue
            if self.kind in ("NC", "ND"):
                est = f"{r['ncf'] or '(sin NCF)'}  Fact. {r['factura']}"
            elif self.kind == "O":
                est = r["status"] or "Pendiente"
            else:
                est = f"Facturada ({r['factura']})" if r["factura"] else ""
            self.tv.insert("", "end", iid=str(r["nro"]), values=(r["nro"], dmy(r["date"]), r["client"], r["name"],
                                                                 m2(r["total"]), est))
            n += 1; tot += r["total"]
        self.lbl.config(text=f"{n} documentos   Total {m2(tot)}")

    def sel(self):
        s = self.tv.selection()
        if not s:
            messagebox.showinfo(KIND_NAME[self.kind], "Seleccione un documento."); return None
        return int(s[0])

    def new(self):
        if self.kind in ("NC", "ND"):
            r = form_dialog(self.app.root, KIND_NAME[self.kind], [("f", "Número de la factura afectada", "num")], {})
            if not r: return
            try: f = int(num(r["f"]))
            except ValueError: return
            self.app.nota(self.kind, f); return
        e = InvoiceEditor(self.app, None, self.kind); self.app.root.wait_window(e)
        if e.saved: self.app.refresh_all()

    def edit(self):
        n = self.sel()
        if n is None: return
        e = InvoiceEditor(self.app, n, self.kind); self.app.root.wait_window(e)
        if e.saved: self.app.refresh_all()

    def pdf(self):
        n = self.sel()
        if n is None: return
        ruta = self.app.doc_path(self.kind, n)
        try:
            gen_doc(self.db, self.kind, n, ruta)
        except PermissionError:
            messagebox.showwarning("PDF", "Ese PDF está abierto. Ciérrelo y vuelva a intentar."); return
        open_file(ruta)

    def to_invoice(self):
        n = self.sel()
        if n is None: return
        h, ls, cs = self.db.odoc_full(self.kind, n)
        if h["factura"]:
            if not messagebox.askyesno("Convertir", f"Este documento ya se facturó (factura {h['factura']}). ¿Hacer otra factura?"):
                return
        e = InvoiceEditor(self.app, None, "F", prefill=(h, ls, cs)); self.app.root.wait_window(e)
        if e.saved and e.saved_nro:
            self.db.set_odoc(self.kind, n, factura=e.saved_nro)
            self.app.refresh_all()

    def toggle_recv(self):
        n = self.sel()
        if n is None: return
        h = self.db.one("SELECT status FROM odocs WHERE kind='O' AND nro=?", (n,))
        nuevo = "Pendiente" if h["status"] == "Recibida" else "Recibida"
        msg = "Los productos se suman al inventario." if nuevo == "Recibida" else "Los productos se restan del inventario."
        if messagebox.askyesno("Orden de compra", f"¿Marcar la orden {n} como {nuevo}?\n{msg}"):
            self.db.set_odoc("O", n, status=nuevo); self.app.refresh_all()

    def assign_ncf(self):
        n = self.sel()
        if n is None: return
        h = self.db.one("SELECT ncf FROM odocs WHERE kind=? AND nro=?", (self.kind, n))
        if h["ncf"]:
            messagebox.showinfo("NCF", f"Ya tiene NCF {h['ncf']}."); return
        ncf = self.db.assign_odoc_ncf(self.kind, n)
        if not ncf:
            messagebox.showwarning("NCF", "No hay comprobantes disponibles. Agregue la secuencia en 'Comprobantes'.")
        else:
            gen_doc(self.db, self.kind, n, self.app.doc_path(self.kind, n)); messagebox.showinfo("NCF", f"NCF {ncf}")
        self.app.refresh_all()

    def delete(self):
        n = self.sel()
        if n is None: return
        extra = {"G": "\nLos productos vuelven al inventario.",
                 "NC": "\nSi tenía devolución, los productos vuelven a salir del inventario."}.get(self.kind, "")
        if messagebox.askyesno("Eliminar", f"¿Eliminar {KIND_NAME[self.kind].lower()} {n}?{extra}"):
            self.db.delete_odoc(self.kind, n); self.app.refresh_all()


# ---------------- ventana principal ----------------
def dialogo_pago(parent, n, saldo, doc="factura", forma="Transferencia"):
    """Pago total (el sistema pone el saldo) o parcial (se escribe el monto). Devuelve (monto, fecha, forma, nota) o None."""
    top = tk.Toplevel(parent); top.title(f"Pago {doc} {n}"); top.transient(parent); top.grab_set(); top.resizable(False, False)
    tipo = tk.StringVar(value="total"); vm = tk.StringVar(value=f"{saldo:.2f}")
    vf = tk.StringVar(value=dmy(datetime.date.today())); vp = tk.StringVar(value=forma); vn = tk.StringVar()
    res = {}
    ttk.Label(top, text=f"{doc.capitalize()} {n}    Saldo pendiente: {m2(saldo)}", font=("Segoe UI", 10, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6))
    fr = ttk.Frame(top); fr.grid(row=1, column=0, columnspan=2, sticky="w", padx=10)
    em = ttk.Entry(top, textvariable=vm, width=16)
    def cambio(*a):
        if tipo.get() == "total":
            vm.set(f"{saldo:.2f}"); em.state(["readonly"])
        else:
            em.state(["!readonly"]); vm.set(""); em.focus_set()
    ttk.Radiobutton(fr, text="Pago total", value="total", variable=tipo, command=cambio).pack(side="left", padx=(0, 12))
    ttk.Radiobutton(fr, text="Pago parcial", value="parcial", variable=tipo, command=cambio).pack(side="left")
    filas = [("Monto", em), ("Fecha", fecha_entry(top, vf)),
             ("Forma de pago", ttk.Combobox(top, textvariable=vp, values=["Efectivo", "Transferencia", "Cheque", "Tarjeta"],
                                            width=14, state="readonly")),
             ("Nota", ttk.Entry(top, textvariable=vn, width=30))]
    for i, (lab, w) in enumerate(filas, 2):
        ttk.Label(top, text=lab).grid(row=i, column=0, sticky="e", padx=(10, 6), pady=3)
        w.grid(row=i, column=1, sticky="w", padx=(0, 10), pady=3)
    cambio()
    def ok():
        try:
            monto = saldo if tipo.get() == "total" else num(vm.get())
            fecha = read_dmy(vf.get())
        except ValueError as e:
            messagebox.showwarning("Pago", str(e) if "Fecha" in str(e) else "Monto no válido.", parent=top); return
        if monto <= 0:
            messagebox.showwarning("Pago", "Escriba el monto del pago parcial.", parent=top); return
        if monto > saldo + 0.005:
            messagebox.showwarning("Pago", f"El monto no puede ser mayor que el saldo ({m2(saldo)}).", parent=top); return
        res["r"] = (round(monto, 2), fecha, vp.get(), vn.get().strip() or ("Pago total" if tipo.get() == "total" else "Pago parcial"))
        top.destroy()
    bf = ttk.Frame(top); bf.grid(row=len(filas) + 2, column=0, columnspan=2, pady=10)
    ttk.Button(bf, text="Registrar pago", command=ok).pack(side="left", padx=6)
    ttk.Button(bf, text="Cancelar", command=top.destroy).pack(side="left", padx=6)
    top.wait_window()
    return res.get("r")


def elegir_carpeta_inicial(root):
    """La carpeta la escoge el usuario. Se pregunta la primera vez o si ya no se encuentra."""
    loc = leer_ubicacion()
    if loc and os.path.isdir(loc):
        return con_carpeta_app(loc)
    msg = (f"Elija dónde crear la carpeta '{APP_NAME}'.\nDentro de ella se guardará todo:\nlos datos, las facturas, conduces, cotizaciones,\n"
           "órdenes, notas, reportes y respaldos.") if not loc else (
           f"No se encuentra la carpeta:\n{loc}\n\nElija dónde está, o una carpeta nueva.")
    while True:
        messagebox.showinfo("Carpeta del programa", msg, parent=root)
        d = filedialog.askdirectory(title="Carpeta del programa", mustexist=False, parent=root)
        if not d:
            if messagebox.askyesno("Carpeta del programa", "Sin carpeta el programa no puede abrir.\n¿Salir?", parent=root):
                root.destroy(); sys.exit(0)
            continue
        d = os.path.normpath(d)
        if os.path.basename(d).lower() != APP_NAME.lower():
            d = os.path.join(d, APP_NAME)
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, ".prueba_escritura"); open(p, "w").close(); os.remove(p)
        except OSError as e:
            messagebox.showwarning("Carpeta del programa", f"No se puede usar esa carpeta:\n{e}", parent=root); continue
        migrar_viejas(d); crear_subcarpetas(d); guardar_ubicacion(d)
        return d


class App:
    def __init__(self):
        self.root = tk.Tk(); self.root.withdraw(); menu_edicion(self.root)
        loc = elegir_carpeta_inicial(self.root)
        self.db = DB(loc=loc)
        self.root.deiconify()
        self.root.title(f"Facturación Canopolis {VERSION}")
        self.root.geometry("1200x720")
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            self.root.iconbitmap(default=os.path.join(base, "icono.ico"))
        except Exception:
            pass
        try:
            ttk.Style().theme_use("vista" if sys.platform.startswith("win") else "clam")
        except tk.TclError:
            pass
        self.root.configure(bg="#f4f4f4")
        self.banner = tk.Label(self.root, text="", bg="#fff3cd", fg="#7a5200", anchor="w",
                               font=("Segoe UI", 10, "bold"), padx=8)
        self.banner.pack(fill="x")
        nb = ttk.Notebook(self.root); nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.nb = nb
        self.tab_ventas(ttk.Frame(nb)); self.tab_clientes(ttk.Frame(nb)); self.tab_productos(ttk.Frame(nb))
        self.tab_cxc(ttk.Frame(nb))
        self.tab_cxp(ttk.Frame(nb))
        self.docs = {k: DocTab(self, k) for k in ("Q", "G", "O", "NC", "ND")}
        self.tab_reportes(ttk.Frame(nb)); self.tab_seq(ttk.Frame(nb)); self.tab_respaldo(ttk.Frame(nb)); self.tab_config(ttk.Frame(nb))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_all()
        if not self.db.one("SELECT 1 FROM invoices LIMIT 1"):
            self.root.after(300, lambda: messagebox.showinfo(
                "Bienvenido", "Para empezar, vaya a la pestaña 'Respaldo' y pulse\n"
                              "'Importar respaldo de Monica' (el .zip o la carpeta, por ejemplo JUEVES)."))

    def doc_path(self, kind, nro):
        pref = {"Q": "es", "G": "guia", "O": "orden", "NC": "nc", "ND": "nd"}[kind]
        return os.path.join(self.db.carpeta(kind), f"{pref}_{nro}.pdf")

    def pdf_path(self, nro):
        return os.path.join(self.db.carpeta("F"), f"fa_{nro}.pdf")

    def refresh_all(self):
        self.load_ventas(); self.load_clientes(); self.load_productos(); self.load_seq(); self.load_cxc(); self.load_cxp(); self.update_banner()
        for t in getattr(self, "docs", {}).values(): t.load()

    def update_banner(self):
        avisos = self.db.low_sequences()
        pend = self.db.one("SELECT COUNT(*) FROM invoices WHERE deleted=0 AND (ncf IS NULL OR ncf='') AND date>=?",
                           (fmt_date(datetime.date.today() - datetime.timedelta(days=90)),))[0]
        txt = []
        if avisos: txt.append("Comprobantes: " + " | ".join(avisos))
        if pend: txt.append(f"Facturas recientes sin NCF: {pend}")
        self.banner.config(text="   ".join(txt) if txt else "Comprobantes OK")
        self.banner.config(bg="#fff3cd" if txt else "#e6f4ea", fg="#7a5200" if txt else "#1e6b34")

    # ----- Ventas -----
    def tab_ventas(self, fr):
        self.nb.add(fr, text="Ventas")
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        first = self.db.one("SELECT MIN(date) FROM invoices")[0]
        self.vd = tk.StringVar(value=dmy(first) if first else dmy(datetime.date.today()))
        self.vh = tk.StringVar(value=dmy(datetime.date.today()))
        self.vs = tk.StringVar(); self.vf = tk.StringVar(value="Todas")
        ttk.Label(top, text="Desde").pack(side="left", padx=3); fecha_entry(top, self.vd, 11).pack(side="left")
        ttk.Label(top, text="Hasta").pack(side="left", padx=3); fecha_entry(top, self.vh, 11).pack(side="left")
        ttk.Label(top, text="Buscar").pack(side="left", padx=(10, 3))
        se = ttk.Entry(top, textvariable=self.vs, width=25); se.pack(side="left")
        se.bind("<Return>", lambda e: self.load_ventas())
        ttk.Combobox(top, textvariable=self.vf, state="readonly", width=22,
                     values=["Todas", "Con saldo pendiente", "Sin NCF (pendientes)"] + [tipo_nombre(t) for t in TIPOS_FACTURA]
                     ).pack(side="left", padx=6)
        ttk.Button(top, text="Mostrar", command=self.load_ventas).pack(side="left", padx=4)
        ttk.Button(top, text="Desde la primera factura", command=self.rango_total).pack(side="left", padx=4)
        cols = ("Nro", "Fecha", "Cliente", "Nombre", "NCF", "Tipo", "Total", "Saldo", "Estado")
        self.tv_v = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (70, 85, 70, 280, 170, 170, 100, 100, 90)):
            self.tv_v.heading(c, text=c)
            self.tv_v.column(c, width=w, anchor="e" if c in ("Total", "Saldo", "Nro") else "w")
        self.tv_v.tag_configure("Vencida", foreground="#c00000")
        self.tv_v.tag_configure("Pendiente", foreground="#1a7f37")
        self.tv_v.tag_configure("Pagada", foreground="#0b4fd6")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv_v.yview); self.tv_v.configure(yscrollcommand=sb.set)
        b = ttk.Frame(fr); b.pack(side="bottom", fill="x", pady=4)
        sb.pack(side="right", fill="y"); self.tv_v.pack(fill="both", expand=True)
        self.tv_v.bind("<Double-1>", lambda e: self.ver_pdf())
        for t, cmd in (("Nueva factura", self.nueva), ("Facturación rápida", self.facturacion_rapida), ("Editar", self.editar), ("Ver / descargar PDF", self.ver_pdf),
                       ("Marcar pagada", self.marcar_pagada),
                       ("Marcar NO pagada (corregir)", self.marcar_no_pagada),
                       ("Asignar NCF", self.asignar_ncf), ("Nota de crédito", lambda: self.nota("NC")),
                       ("Nota de débito", lambda: self.nota("ND")), ("Eliminar (devuelve inventario)", self.eliminar)):
            ttk.Button(b, text=t, command=cmd).pack(side="left", padx=3)
        self.lbl_v = ttk.Label(b, text=""); self.lbl_v.pack(side="right", padx=8)
        # Menu contextual (clic derecho) con las opciones de la factura
        self.menu_v = tk.Menu(self.root, tearoff=0)
        for t, cmd in (("Editar", self.editar), ("Ver / descargar PDF", self.ver_pdf),
                       ("Marcar pagada", self.marcar_pagada),
                       ("Marcar NO pagada (corregir)", self.marcar_no_pagada),
                       ("Asignar NCF", self.asignar_ncf), ("Nota de crédito", lambda: self.nota("NC")),
                       ("Nota de débito", lambda: self.nota("ND")), ("Eliminar (devuelve inventario)", self.eliminar)):
            self.menu_v.add_command(label=t, command=cmd)
        self.menu_v.add_separator()
        self.menu_v.add_command(label="Cerrar", command=self.menu_v.unpost)
        self.tv_v.bind("<Button-3>", self.menu_ventas)

    def rango_total(self):
        first = self.db.one("SELECT MIN(date) FROM invoices")[0]
        if first: self.vd.set(dmy(first))
        self.vh.set(dmy(datetime.date.today())); self.load_ventas()

    def load_ventas(self):
        try:
            d1 = fmt_date(read_dmy(self.vd.get())); d2 = fmt_date(read_dmy(self.vh.get()))
        except ValueError as e:
            messagebox.showwarning("Fechas", str(e)); return
        self.tv_v.delete(*self.tv_v.get_children())
        s = self.vs.get().strip().lower(); f = self.vf.get()
        pays = {r[0]: r[1] for r in self.db.q("SELECT nro, SUM(amount) FROM payments GROUP BY nro")}
        tot = 0; n = 0
        for r in self.db.q("SELECT * FROM invoices WHERE deleted=0 AND date BETWEEN ? AND ? ORDER BY nro DESC", (d1, d2)):
            saldo = round(r["saldo_base"] - pays.get(r["nro"], 0), 2)
            tipo = r["tipo"] if r["ncf"] else 0
            if s and s not in f"{r['nro']} {r['client']} {r['name']} {r['ncf']}".lower(): continue
            if f == "Con saldo pendiente" and saldo <= 0.005: continue
            if f == "Sin NCF (pendientes)" and r["ncf"]: continue
            if f not in ("Todas", "Con saldo pendiente", "Sin NCF (pendientes)") and tipo_nombre(tipo) != f: continue
            estado = "Pagada" if saldo <= 0.005 else ("Vencida" if r["due"] and r["due"] < fmt_date(datetime.date.today()) else "Pendiente")
            self.tv_v.insert("", "end", iid=str(r["nro"]), tags=(estado,), values=(
                r["nro"], dmy(r["date"]), r["client"], r["name"], r["ncf"] or "(sin NCF)",
                tipo_nombre(tipo), m2(r["total"]), m2(saldo), estado))
            tot += r["total"]; n += 1
        self.lbl_v.config(text=f"{n} facturas   Total {m2(tot)}")

    def menu_ventas(self, ev):
        fila = self.tv_v.identify_row(ev.y)
        if not fila or fila not in self.tv_v.selection():
            return "break"
        try:
            self.menu_v.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.menu_v.grab_release()
        return "break"

    def sel_v(self):
        s = self.tv_v.selection()
        if not s:
            messagebox.showinfo("Ventas", "Seleccione una factura."); return None
        return int(s[0])

    def nueva(self):
        e = InvoiceEditor(self); self.root.wait_window(e)
        if e.saved: self.refresh_all()

    def facturacion_rapida(self):
        """Crea la factura a partir del PDF de Factura Dominicana (GTI)."""
        from gti import leer_gti
        top = tk.Toplevel(self.root); top.title("Facturación rápida"); top.transient(self.root); top.grab_set()
        top.resizable(False, False)
        ruta = tk.StringVar()
        ttk.Label(top, text="Por favor subir factura Dominicana GTI", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 8))
        ttk.Entry(top, textvariable=ruta, width=60).grid(row=1, column=0, columnspan=2, padx=(12, 4))
        ttk.Button(top, text="Aquí", command=lambda: ruta.set(filedialog.askopenfilename(
            parent=top, title="Factura Dominicana GTI", filetypes=[("PDF", "*.pdf")]) or ruta.get())).grid(row=1, column=2, padx=(0, 12))
        ok = {}
        bf = ttk.Frame(top); bf.grid(row=2, column=0, columnspan=3, pady=12)
        ttk.Button(bf, text="OK", command=lambda: (ok.setdefault("r", ruta.get().strip()), top.destroy())).pack(side="left", padx=6)
        ttk.Button(bf, text="Cancelar", command=top.destroy).pack(side="left", padx=6)
        top.wait_window()
        path = ok.get("r")
        if not path: return
        try:
            g = leer_gti(path)
        except Exception as e:
            messagebox.showerror("Facturación rápida", f"No se pudo leer el PDF:\n{e}"); return
        if self.completar_desde_gti(g):
            return
        errores = []
        if not g["ncf"]: errores.append("No se encontró el e-NCF en el PDF.")
        elif g["tipo"] not in TIPOS_FACTURA or not g["tipo"]:
            errores.append(f"El comprobante {g['ncf'][:3]} no es una factura que maneje el programa "
                           "(se aceptan E31, E32, E44, E45 y E46). Las notas de crédito y débito se registran a mano.")
        if not g["items"]: errores.append("No se encontraron productos en el PDF.")
        # cliente: por RNC; si no trae RNC (consumidor final), por nombre
        cl = None
        if g["rnc"]:
            mismos = [c for c in self.db.q("SELECT * FROM clients WHERE COALESCE(ctype,'C')='C' ORDER BY name, code")
                      if "".join(ch for ch in (c["rnc"] or "") if ch.isdigit()) == g["rnc"]]
            if len(mismos) == 1:
                cl = mismos[0]
            elif len(mismos) > 1:
                # mismo RNC con varias sucursales: el usuario elige a cual corresponde
                rows = [(c["code"], c["name"], " ".join(x for x in (c["addr1"], c["addr2"], c["addr3"]) if x)) for c in mismos]
                p = Picker(self.root, f"RNC {g['rnc']}: ¿a cuál sucursal corresponde esta factura?",
                           ("Código", "Cliente", "Dirección"), rows, [90, 280, 360])
                if not p.result: return
                cl = self.db.one("SELECT * FROM clients WHERE code=?", (p.result[0],))
            else:
                errores.append(f"No hay cliente con RNC {g['rnc']} ({g['cliente_nombre']}).")
        else:
            # sin RNC: cliente independiente (consumidor final)
            indep = self.db.one("SELECT * FROM clients WHERE code='CLIENTE'") or \
                self.db.one("SELECT * FROM clients WHERE upper(name) LIKE '%INDEPENDIENTE%' ORDER BY code")
            nom = g["cliente_nombre"] or "consumidor final"
            if messagebox.askyesno("Facturación rápida", f"La factura es de un cliente independiente ({nom}).\n\n"
                                   "¿Asignar esta factura a otro cliente?"):
                rows = [(c["code"], c["name"]) for c in self.db.q("SELECT code,name FROM clients WHERE COALESCE(ctype,'C')='C' ORDER BY name")]
                p = Picker(self.root, "Elija el cliente para esta factura", ("Código", "Cliente"), rows, [120, 560])
                if not p.result: return
                cl = self.db.one("SELECT * FROM clients WHERE code=?", (p.result[0],))
            else:
                cl = indep
                if cl is None: errores.append("No existe el cliente independiente en el programa.")
        lines = []
        for it in g["items"]:
            # el codigo debe ser identico al del inventario (sin importar mayusculas/minusculas); el nombre puede variar
            pr = self.db.one("SELECT * FROM products WHERE upper(trim(code))=upper(trim(?)) ORDER BY code", (str(it["code"]),))
            if not pr:
                errores.append(f"No existe el producto {it['code']} ({it['descr']})."); continue
            precio = round(it["total"] / it["qty"], 4) if it["descuento"] and it["qty"] else it["price"]
            lines.append(dict(code=pr["code"], descr=pr["descr"], qty=it["qty"], price=precio, cost=pr["cost"] or 0,
                              itbis=(pr["itbis"] or 0) if g["itbis"] else 0))
        if g["ncf"]:
            usado = self.db.ncf_usado(g["ncf"])
            if usado: errores.append(f"El e-NCF {g['ncf']} ya está en la factura {usado}.")
        if g["emisor_rnc"] and self.db.cfg("emp_l5") and g["emisor_rnc"] != "".join(ch for ch in self.db.cfg("emp_l5") if ch.isdigit()):
            errores.append(f"La factura es de otro emisor (RNC {g['emisor_rnc']}).")
        if errores:
            messagebox.showwarning("Facturación rápida", "No se creó la factura:\n\n" + "\n".join(errores)); return
        sub = sum(l["qty"] * l["price"] for l in lines)
        itb = sum(l["qty"] * l["price"] * l["itbis"] / 100 for l in lines)
        if abs(sub + itb - g["total"]) > 0.05:
            if not messagebox.askyesno("Facturación rápida", f"El total de la GTI es {m2(g['total'])} y la suma de los productos da "
                                       f"{m2(sub + itb)}.\n¿Crear la factura igual?"):
                return
        if not confirmar_existencias(self.db, lines, None, "Facturación rápida"):
            return
        nro = self.db.next_invoice_no()   # siempre el numero que corresponde en el programa
        b = self.db.client_print_block(cl["code"])
        dias = (g["vence"] - g["fecha"]).days if g["vence"] and g["fecha"] else 0
        terms = "Efectivo" if dias <= 0 else next((t for t, n in DIAS.items() if n == dias and t != "Credito"), "Credito")
        h = dict(nro=nro, date=fmt_date(g["fecha"] or datetime.date.today()), due=fmt_date(g["vence"] or g["fecha"]),
                 client=cl["code"], name=b["name"], dir1=b["dir1"], dir2=b["dir2"], dir3=b["dir3"], rnc=b["rnc"],
                 terms=terms, ship_via=self.db.cfg("envio"), seller="", ref="", comment1="",
                 comment2=self.db.cfg("coment2"), comment3=self.db.cfg("coment3"),
                 ncf=self.db.ncf_desde_gti(g["ncf"]), tipo=g["tipo"], discount=0,
                 ecf_cod=g["codigo_seguridad"], ecf_firma=g["fecha_firma"], ecf_qr=g["qr"])
        try:
            self.db.save_invoice(h, lines, [])
            ruta = self.pdf_path(nro); generar_factura(self.db, nro, ruta)
        except Exception as e:
            messagebox.showerror("Facturación rápida", f"No se pudo crear la factura:\n{e}"); return
        self.refresh_all()
        messagebox.showinfo("Facturación rápida", f"Factura {nro} creada para {b['name']}\n"
                            f"e-NCF {g['ncf']}   Total {m2(sub + itb)}\nSe descontó el inventario.")
        open_file(ruta)

    def completar_desde_gti(self, g):
        """Si el e-NCF de la GTI ya esta en una factura del programa (y el numero interno coincide),
        no crea factura nueva: completa en esa factura lo que le falte (QR, codigo de seguridad, firma)."""
        if not g.get("ncf"):
            return False
        nro = self.db.ncf_usado(g["ncf"])
        if nro is None:
            return False
        interno = (g.get("interno") or "").strip()
        if interno and interno.isdigit() and int(interno) != int(nro):
            return False   # el e-NCF esta en otra factura: sigue el flujo normal (avisa el error)
        emp = "".join(ch for ch in (self.db.cfg("emp_l5") or "") if ch.isdigit())
        if g.get("emisor_rnc") and emp and g["emisor_rnc"] != emp:
            return False
        h = self.db.one("SELECT * FROM invoices WHERE nro=?", (nro,))
        nuevo = {}
        if g.get("qr") and not h["ecf_qr"]: nuevo["ecf_qr"] = g["qr"]
        if g.get("codigo_seguridad") and not (h["ecf_cod"] or "").strip(): nuevo["ecf_cod"] = g["codigo_seguridad"]
        if g.get("fecha_firma") and not (h["ecf_firma"] or "").strip(): nuevo["ecf_firma"] = g["fecha_firma"]
        if not nuevo:
            messagebox.showinfo("Facturación rápida", f"La factura {nro} con e-NCF {g['ncf']} ya existe y está completa.\n"
                                "No se creó ninguna factura nueva."); return True
        try:
            self.db.con.execute("UPDATE invoices SET " + ", ".join(f"{k}=?" for k in nuevo) + " WHERE nro=?",
                                (*nuevo.values(), nro))
            self.db.con.commit()
            ruta = self.pdf_path(nro); generar_factura(self.db, nro, ruta)
        except Exception as e:
            messagebox.showerror("Facturación rápida", f"No se pudo completar la factura {nro}:\n{e}"); return True
        nombres = {"ecf_qr": "código QR", "ecf_cod": "código de seguridad", "ecf_firma": "fecha de firma digital"}
        self.refresh_all()
        messagebox.showinfo("Facturación rápida", f"La factura {nro} con e-NCF {g['ncf']} ya existía.\n"
                            "No se creó factura nueva. Se le añadió: " + ", ".join(nombres[k] for k in nuevo) + ".")
        open_file(ruta)
        return True

    def editar(self):
        n = self.sel_v()
        if n is None: return
        e = InvoiceEditor(self, n); self.root.wait_window(e)
        if e.saved: self.refresh_all()

    def ver_pdf(self):
        n = self.sel_v()
        if n is None: return
        ruta = self.pdf_path(n)
        try:
            generar_factura(self.db, n, ruta)
        except PermissionError:
            messagebox.showwarning("PDF", "El PDF de esa factura está abierto. Ciérrelo y vuelva a intentar."); return
        open_file(ruta)

    def pagar(self, n=None):
        n = n if n is not None else self.sel_v()
        if n is None: return
        saldo = self.db.invoice_saldo(n)
        r = form_dialog(self.root, f"Pago factura {n}", [("amount", "Monto", "num"), ("date", "Fecha (DD/MM/AAAA)", "date"),
                        ("method", "Forma de pago", "combo:Efectivo|Transferencia|Cheque|Tarjeta"), ("note", "Nota", "text")],
                        {"amount": f"{saldo:.2f}", "date": dmy(datetime.date.today()), "method": "Transferencia"})
        if not r: return
        try:
            self.db.add_payment(n, num(r["amount"]), r["method"], read_dmy(r["date"]), r["note"])
        except ValueError as e:
            messagebox.showwarning("Pago", str(e)); return
        self.refresh_all()

    def marcar_pagada(self, n=None):
        n = n if n is not None else self.sel_v()
        if n is None: return
        saldo = self.db.invoice_saldo(n)
        if saldo <= 0.005:
            messagebox.showinfo("Pago", "Esa factura ya está pagada."); return
        r = dialogo_pago(self.root, n, saldo)
        if not r: return
        monto, fecha, forma, nota = r
        self.db.add_payment(n, monto, forma, fecha, nota)
        self.refresh_all()

    def marcar_no_pagada(self):
        n = self.sel_v()
        if n is None: return
        inv = self.db.one("SELECT total FROM invoices WHERE nro=?", (n,))
        saldo = self.db.invoice_saldo(n)
        if saldo >= inv["total"] - 0.005:
            messagebox.showinfo("Corregir", f"La factura {n} no tiene pagos; ya está con su saldo completo."); return
        if messagebox.askyesno("Corregir factura", f"La factura {n} aparece pagada (saldo {m2(saldo)}).\n\n"
                               f"¿Marcarla como NO pagada?\nSe quitan sus pagos y queda con saldo {m2(inv['total'])}."):
            self.db.mark_unpaid(n); self.refresh_all()

    def asignar_ncf(self):
        n = self.sel_v()
        if n is None: return
        inv = self.db.one("SELECT * FROM invoices WHERE nro=?", (n,))
        if inv["ncf"]:
            messagebox.showinfo("NCF", f"La factura {n} ya tiene NCF {inv['ncf']}."); return
        opciones = [tipo_nombre(t) for t in (1, 2, 14, 15, 16)]
        r = form_dialog(self.root, f"Asignar NCF a la factura {n}", [("tipo", "Tipo de comprobante", "combo:" + "|".join(opciones))],
                        {"tipo": tipo_nombre(inv["tipo"] or 1)})
        if not r: return
        tipo = next((t for t in (1, 2, 14, 15, 16) if tipo_nombre(t) == r["tipo"]), 1)
        ncf = self.db.assign_ncf(n, tipo)
        if not ncf:
            messagebox.showwarning("NCF", "No hay comprobantes disponibles de ese tipo. Agregue la secuencia en 'Comprobantes'.")
        else:
            generar_factura(self.db, n, self.pdf_path(n))
            messagebox.showinfo("NCF", f"Factura {n}: NCF {ncf}")
        self.refresh_all()

    def eliminar(self):
        n = self.sel_v()
        if n is None: return
        if messagebox.askyesno("Eliminar", f"¿Eliminar la factura {n}?\nLos productos vuelven al inventario."):
            self.db.delete_invoice(n); self.refresh_all()

    # ----- Clientes -----
    def tab_clientes(self, fr):
        self.nb.add(fr, text="Clientes")
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        self.cs = tk.StringVar()
        ttk.Label(top, text="Buscar").pack(side="left", padx=3)
        e = ttk.Entry(top, textvariable=self.cs, width=30); e.pack(side="left")
        self.cs.trace_add("write", lambda *a: self.load_clientes())
        self.cprov = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Ver proveedores", variable=self.cprov, command=self.load_clientes).pack(side="left", padx=6)
        ttk.Button(top, text="Nuevo cliente", command=lambda: self.edit_client(None)).pack(side="left", padx=6)
        ttk.Button(top, text="Nuevo proveedor", command=lambda: self.edit_client(None, prov=True)).pack(side="left", padx=2)
        ttk.Button(top, text="Editar", command=lambda: self.edit_client(self.tv_c.selection()[0] if self.tv_c.selection() else None, True)).pack(side="left")
        cols = ("Código", "Nombre", "RNC", "Teléfono", "Dirección", "Ciudad", "Condiciones", "Saldo")
        self.tv_c = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (70, 280, 120, 150, 250, 120, 90, 100)):
            self.tv_c.heading(c, text=c); self.tv_c.column(c, width=w, anchor="e" if c == "Saldo" else "w")
        self.tv_c.pack(fill="both", expand=True)
        self.tv_c.bind("<Double-1>", lambda e: self.edit_client(self.tv_c.selection()[0] if self.tv_c.selection() else None, True))
        menu_derecho(self.tv_c, self.root, (("Editar", lambda: self.edit_client(self.tv_c.selection()[0] if self.tv_c.selection() else None, True)),))

    def load_clientes(self):
        self.tv_c.delete(*self.tv_c.get_children())
        s = self.cs.get().lower()
        pays = {r[0]: r[1] for r in self.db.q("SELECT nro, SUM(amount) FROM payments GROUP BY nro")}
        saldo = {}
        for r in self.db.q("SELECT nro,client,saldo_base FROM invoices WHERE deleted=0"):
            saldo[r["client"]] = saldo.get(r["client"], 0) + r["saldo_base"] - pays.get(r["nro"], 0)
        ct = "S" if self.cprov.get() else "C"
        for c in self.db.q("SELECT * FROM clients WHERE COALESCE(ctype,'C')=? ORDER BY name", (ct,)):
            if s and s not in f"{c['code']} {c['name']} {c['rnc']} {c['phone']}".lower(): continue
            self.tv_c.insert("", "end", iid=c["code"], values=(c["code"], c["name"], c["rnc"], c["phone"], c["addr1"],
                                                               c["city"], c["terms"], m2(saldo.get(c["code"], 0))))

    def edit_client(self, code, need=False, prov=False):
        if need and not code:
            messagebox.showinfo("Clientes", "Seleccione un cliente."); return
        vals = dict(self.db.one("SELECT * FROM clients WHERE code=?", (code,))) if code else {"code": self.db.next_client_code("B" if prov else "A"), "terms": "Efectivo", "ctype": "S" if prov else "C"}
        fields = [("code", "Código", "readonly" if code else "text"), ("name", "Nombre", "text"), ("rnc", "RNC / Cédula", "text"),
                  ("phone", "Teléfono", "text"), ("fax", "Fax", "text"), ("addr1", "Dirección", "text"), ("addr2", "Dirección 2", "text"),
                  ("addr3", "Dirección 3", "text"), ("city", "Ciudad", "text"), ("email", "Correo", "text"),
                  ("contact", "Contacto", "text"), ("terms", "Condiciones", "combo:" + "|".join(TERMINOS))]
        r = form_dialog(self.root, "Cliente", fields, vals)
        if not r: return
        if not r["code"] or not r["name"]:
            messagebox.showwarning("Cliente", "Código y nombre son obligatorios."); return
        if not code and self.db.one("SELECT 1 FROM clients WHERE code=?", (r["code"],)):
            messagebox.showwarning("Cliente", "Ese código ya existe."); return
        r["ctype"] = vals.get("ctype") or "C"
        self.db.save_client(r); self.load_clientes()

    # ----- Productos -----
    def tab_productos(self, fr):
        self.nb.add(fr, text="Inventario")
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        self.ps = tk.StringVar(); self.pinact = tk.BooleanVar(value=False)
        ttk.Label(top, text="Buscar").pack(side="left", padx=3)
        ttk.Entry(top, textvariable=self.ps, width=30).pack(side="left")
        self.ps.trace_add("write", lambda *a: self.load_productos())
        ttk.Checkbutton(top, text="Ver desactivados", variable=self.pinact, command=self.load_productos).pack(side="left", padx=6)
        ttk.Button(top, text="Nuevo producto", command=lambda: self.edit_prod(None)).pack(side="left", padx=6)
        ttk.Button(top, text="Editar", command=lambda: self.edit_prod(self.sel_p(), True)).pack(side="left")
        ttk.Button(top, text="Ajustar existencia", command=self.ajustar).pack(side="left", padx=6)
        ttk.Button(top, text="Desactivar / activar", command=self.toggle_prod).pack(side="left")
        ttk.Button(top, text="Eliminar producto", command=self.eliminar_prod).pack(side="left", padx=6)
        cols = ("Código", "Descripción", "Precio", "Precio 2", "Costo", "ITBIS %", "Existencia", "Estado")
        self.tv_p = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (110, 380, 100, 100, 100, 70, 100, 90)):
            self.tv_p.heading(c, text=c); self.tv_p.column(c, width=w, anchor="w" if c in ("Código", "Descripción", "Estado") else "e")
        self.tv_p.pack(fill="both", expand=True)
        self.tv_p.bind("<Double-1>", lambda e: self.edit_prod(self.sel_p(), True))
        self.mnu_p = tk.Menu(self.root, tearoff=0)
        self.mnu_p.add_command(label="Editar", command=lambda: self.edit_prod(self.sel_p(), True))
        self.mnu_p.add_command(label="Ajustar existencia", command=self.ajustar)
        self.mnu_p.add_command(label="Desactivar / activar", command=self.toggle_prod)
        self.mnu_p.add_command(label="Eliminar producto", command=self.eliminar_prod)
        self.mnu_p.add_separator()
        self.mnu_p.add_command(label="Cerrar", command=self.mnu_p.unpost)
        self.tv_p.bind("<Button-3>", self.prod_menu)

    def prod_menu(self, ev):
        fila = self.tv_p.identify_row(ev.y)
        if not fila or fila not in self.tv_p.selection():
            return "break"
        try:
            self.mnu_p.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.mnu_p.grab_release()
        return "break"

    def sel_p(self):
        s = self.tv_p.selection(); return s[0] if s else None

    def load_productos(self):
        self.tv_p.delete(*self.tv_p.get_children())
        s = self.ps.get().lower()
        mv = {r[0]: r[1] for r in self.db.q("SELECT code, SUM(qty) FROM stock_moves GROUP BY code")}
        for p in self.db.q("SELECT * FROM products ORDER BY code"):
            if not p["active"] and not self.pinact.get(): continue
            if s and s not in f"{p['code']} {p['descr']}".lower(): continue
            self.tv_p.insert("", "end", iid=p["code"], values=(p["code"], p["descr"], m2(p["price"]), m2(p["price2"] or 0),
                                                               m2(p["cost"] or 0), m2(p["itbis"] or 0),
                                                               m2((p["stock_base"] or 0) + mv.get(p["code"], 0)),
                                                               "Activo" if p["active"] else "Desactivado"))

    def edit_prod(self, code, need=False):
        if need and not code:
            messagebox.showinfo("Productos", "Seleccione un producto."); return
        vals = dict(self.db.one("SELECT * FROM products WHERE code=?", (code,))) if code else {"itbis": "0", "price2": 0, "cost": 0, "stock_base": 0}
        vals["itbis"] = itbis_txt(vals.get("itbis"))
        fields = [("code", "Código", "readonly" if code else "text"), ("descr", "Descripción", "text"), ("price", "Precio", "num"),
                  ("price2", "Precio 2", "num"), ("cost", "Costo", "num"), ("itbis", "ITBIS %", "combo:" + "|".join(ITBIS_OPC)), ("category", "Categoría", "text")]
        if not code: fields.append(("stock_base", "Existencia inicial", "num"))
        r = form_dialog(self.root, "Producto", fields, vals)
        if not r: return
        if not r["code"] or not r["descr"]:
            messagebox.showwarning("Producto", "Código y descripción son obligatorios."); return
        if not code and self.db.one("SELECT 1 FROM products WHERE code=?", (r["code"],)):
            messagebox.showwarning("Producto", "Ese código ya existe."); return
        try:
            d = dict(code=r["code"], descr=r["descr"], price=num(r["price"]), price2=num(r["price2"]), cost=num(r["cost"]),
                     itbis=num(r["itbis"]), category=r["category"], active=vals.get("active", 1))
            if not code: d["stock_base"] = num(r["stock_base"])
        except ValueError:
            messagebox.showwarning("Producto", "Número no válido."); return
        self.db.save_product(d); self.load_productos()

    def ajustar(self):
        code = self.sel_p()
        if not code:
            messagebox.showinfo("Productos", "Seleccione un producto."); return
        r = form_dialog(self.root, f"Existencia de {code}", [("qty", "Existencia real", "num")], {"qty": f"{self.db.stock(code):.2f}"})
        if not r: return
        try:
            diff = num(r["qty"]) - self.db.stock(code)
        except ValueError:
            return
        self.db.con.execute("INSERT INTO stock_moves(nro,code,qty,kind) VALUES(0,?,?,'A')", (code, diff)); self.db.con.commit()
        self.load_productos()

    def eliminar_prod(self):
        code = self.sel_p()
        if not code:
            messagebox.showinfo("Productos", "Seleccione un producto."); return
        p = self.db.one("SELECT descr FROM products WHERE code=?", (code,))
        ok, motivo = self.db.can_delete_product(code)
        if not ok:
            messagebox.showwarning("Eliminar producto", f"No se puede eliminar {code} - {p['descr']}.\n\n{motivo}"); return
        if messagebox.askyesno("Confirmar", f"¿Eliminar definitivamente el producto\n{code} - {p['descr']}?\n\n"
                                            "Las facturas viejas lo siguen mostrando con su código y descripción."):
            self.db.delete_product(code); self.load_productos()

    def toggle_prod(self):
        code = self.sel_p()
        if not code:
            messagebox.showinfo("Productos", "Seleccione un producto."); return
        p = self.db.one("SELECT descr, active FROM products WHERE code=?", (code,))
        accion = "desactivar" if p["active"] else "activar"
        if not messagebox.askyesno("Confirmar", f"¿Seguro que desea {accion} el producto\n{code} - {p['descr']}?"):
            return
        self.db.con.execute("UPDATE products SET active=1-active WHERE code=?", (code,)); self.db.con.commit()
        self.load_productos()

    def nota(self, kind, nro=None):
        n = nro if nro is not None else self.sel_v()
        if n is None: return
        h, ls, cs = self.db.invoice_full(n)
        if not h or h["deleted"]:
            messagebox.showwarning(KIND_NAME[kind], f"No existe la factura {n}."); return
        pre = (h, ls if kind == "NC" else [], [])
        e = InvoiceEditor(self, None, kind, prefill=pre, ref_invoice=n); self.root.wait_window(e)
        if e.saved: self.refresh_all()

    # ----- Cuentas por pagar -----
    def tab_cxp(self, fr):
        self.nb.add(fr, text="Cuentas por pagar")
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        self.pc = tk.StringVar(); self.pn = tk.StringVar(value="(todos los proveedores)")
        ttk.Label(top, text="Proveedor").pack(side="left", padx=3)
        ttk.Entry(top, textvariable=self.pc, width=10).pack(side="left")
        ttk.Button(top, text="Buscar", command=self.cxp_pick).pack(side="left", padx=3)
        ttk.Button(top, text="Todos", command=lambda: (self.pc.set(""), self.pn.set("(todos los proveedores)"), self.load_cxp())).pack(side="left")
        ttk.Label(top, textvariable=self.pn, font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
        r2 = ttk.Frame(fr); r2.pack(fill="x", pady=4)
        hoy = datetime.date.today()
        self.pd = tk.StringVar(value=dmy(hoy - datetime.timedelta(days=30))); self.ph = tk.StringVar(value=dmy(hoy))
        ttk.Label(r2, text="Estado de cuenta  Desde").pack(side="left", padx=3)
        fecha_entry(r2, self.pd, 11).pack(side="left")
        ttk.Label(r2, text="Hasta").pack(side="left", padx=3)
        fecha_entry(r2, self.ph, 11).pack(side="left")
        ttk.Button(r2, text="Estado de cuenta proveedor (PDF)", command=self.pdf_estado_p).pack(side="left", padx=6)
        ttk.Button(r2, text="Saldos vencidos por pagar (PDF)", command=self.pdf_saldos_p).pack(side="left", padx=6)
        cols = ("Compra", "Fecha", "Vence", "Proveedor", "Nombre", "Total", "Saldo", "Días vencida")
        self.tv_p2 = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (70, 90, 90, 80, 320, 120, 120, 90)):
            self.tv_p2.heading(c, text=c)
            self.tv_p2.column(c, width=w, anchor="e" if c in ("Compra", "Total", "Saldo", "Días vencida") else "w")
        self.tv_p2.column("Días vencida", width=95, minwidth=80, stretch=False, anchor="center")
        self.tv_p2.tag_configure("venc", foreground="#b00020")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv_p2.yview); self.tv_p2.configure(yscrollcommand=sb.set)
        b = ttk.Frame(fr); b.pack(side="bottom", fill="x", pady=4)
        sb.pack(side="right", fill="y"); self.tv_p2.pack(fill="both", expand=True)
        ttk.Button(b, text="Marcar pagada", command=self.cxp_marcar).pack(side="left", padx=3)
        self.lbl_p2 = ttk.Label(b, text="", font=("Segoe UI", 10, "bold")); self.lbl_p2.pack(side="right", padx=8)
        self.mnu_p2 = tk.Menu(self.root, tearoff=0)
        self.mnu_p2.add_command(label="Marcar pagada", command=self.cxp_marcar)
        self.mnu_p2.add_separator()
        self.mnu_p2.add_command(label="Cerrar", command=self.mnu_p2.unpost)
        self.tv_p2.bind("<Button-3>", self.cxp_menu)

    def cxp_menu(self, ev):
        fila = self.tv_p2.identify_row(ev.y)
        if not fila or fila not in self.tv_p2.selection():
            return "break"
        try:
            self.mnu_p2.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.mnu_p2.grab_release()
        return "break"

    def cxp_pick(self):
        rows = [(c["code"], c["name"]) for c in self.db.q("SELECT * FROM clients WHERE ctype='S' ORDER BY name")]
        p = Picker(self.root, "Buscar proveedor", ("Código", "Nombre"), rows, [100, 420])
        if p.result:
            self.pc.set(p.result[0]); self.pn.set(p.result[1]); self.load_cxp()

    def load_cxp(self):
        self.tv_p2.delete(*self.tv_p2.get_children())
        hoy = datetime.date.today(); tot = 0
        for o, saldo in self.db.open_payables(self.pc.get().strip() or None):
            due = parse_date(o["due"]) or parse_date(o["date"])
            dias = (hoy - due).days if due else 0
            self.tv_p2.insert("", "end", iid=str(o["nro"]), tags=("venc",) if dias > 0 else (), values=(
                o["nro"], dmy(o["date"]), dmy(o["due"]), o["client"], o["name"], m2(o["total"]), m2(saldo),
                dias if dias > 0 else ""))
            tot += saldo
        self.lbl_p2.config(text=f"Total por pagar {m2(tot)}")

    def cxp_sel(self):
        s = self.tv_p2.selection()
        if not s:
            messagebox.showinfo("Cuentas por pagar", "Seleccione una compra."); return None
        return int(s[0])

    def cxp_pagar(self):
        n = self.cxp_sel()
        if n is None: return
        r = form_dialog(self.root, f"Pago compra {n}", [("amount", "Monto", "num"), ("date", "Fecha (DD/MM/AAAA)", "date"),
                        ("method", "Forma de pago", "combo:Transferencia|Efectivo|Cheque|Tarjeta"), ("note", "Nota", "text")],
                        {"amount": f"{self.db.ap_saldo(n):.2f}", "date": dmy(datetime.date.today()), "method": "Transferencia"})
        if not r: return
        try:
            self.db.add_ap_payment(n, num(r["amount"]), r["method"], read_dmy(r["date"]), r["note"])
        except ValueError as e:
            messagebox.showwarning("Pago", str(e)); return
        self.refresh_all()

    def cxp_marcar(self):
        n = self.cxp_sel()
        if n is None: return
        s = self.db.ap_saldo(n)
        if s <= 0.005:
            messagebox.showinfo("Pago", "Esa compra ya está pagada."); return
        r = dialogo_pago(self.root, n, s, doc="compra")
        if not r: return
        monto, fecha, forma, nota = r
        try:
            self.db.add_ap_payment(n, monto, forma, fecha, nota)
        except ValueError as e:
            messagebox.showwarning("Pago", str(e)); return
        self.refresh_all()

    def pdf_estado_p(self):
        try:
            d1, d2 = read_dmy(self.pd.get()), read_dmy(self.ph.get())
        except ValueError as e:
            messagebox.showwarning("Fechas", str(e)); return
        code = self.pc.get().strip()
        provs = [code] if code else sorted({o["client"] for o, _ in self.db.open_payables()})
        ruta = self.rep_path(f"Estado_Cta_Prov_{code or 'todos'}")
        reportes.estado_cuenta(self.db, provs, d1, d2, ruta, ap=True); open_file(ruta)

    def pdf_saldos_p(self):
        first = self.db.one("SELECT MIN(date) FROM ap_ledger")[0] or fmt_date(datetime.date.today())
        hoy = datetime.date.today()
        ruta = self.rep_path("Saldos_por_pagar")
        reportes.saldos_vencidos(self.db, parse_date(first), hoy, hoy, ruta, ap=True); open_file(ruta)

    # ----- Cuentas por cobrar -----
    def tab_cxc(self, fr):
        self.nb.add(fr, text="Cuentas por cobrar")
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        self.xc = tk.StringVar(); self.xn = tk.StringVar(value="(todos los clientes)")
        ttk.Label(top, text="Cliente").pack(side="left", padx=3)
        ex = ttk.Entry(top, textvariable=self.xc, width=18); ex.pack(side="left")
        ex.bind("<Return>", lambda e: self.cxc_pick())
        ttk.Button(top, text="Buscar", command=self.cxc_pick).pack(side="left", padx=3)
        ttk.Button(top, text="Todos", command=lambda: (self.xc.set(""), self.xn.set("(todos los clientes)"), self.load_cxc())).pack(side="left")
        ttk.Label(top, textvariable=self.xn, font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
        r2 = ttk.Frame(fr); r2.pack(fill="x", pady=4)
        hoy = datetime.date.today()
        self.xd = tk.StringVar(value=dmy(hoy - datetime.timedelta(days=30))); self.xh = tk.StringVar(value=dmy(hoy))
        ttk.Label(r2, text="Estado de cuenta  Desde").pack(side="left", padx=3)
        fecha_entry(r2, self.xd, 11).pack(side="left")
        ttk.Label(r2, text="Hasta").pack(side="left", padx=3)
        fecha_entry(r2, self.xh, 11).pack(side="left")
        ttk.Button(r2, text="Estado de cuenta (PDF)", command=self.pdf_estado).pack(side="left", padx=6)
        ttk.Separator(r2, orient="vertical").pack(side="left", fill="y", padx=10)
        first = self.db.one("SELECT MIN(date) FROM invoices")[0]
        self.sd = tk.StringVar(value=dmy(first) if first else dmy(hoy)); self.sh = tk.StringVar(value=dmy(hoy))
        self.sa = tk.StringVar(value=dmy(hoy))
        ttk.Label(r2, text="Saldos vencidos  Facturas desde").pack(side="left", padx=3)
        fecha_entry(r2, self.sd, 11).pack(side="left")
        ttk.Label(r2, text="al").pack(side="left", padx=3)
        fecha_entry(r2, self.sa, 11).pack(side="left")
        ttk.Button(r2, text="Saldos vencidos (PDF)", command=self.pdf_saldos).pack(side="left", padx=6)
        cols = ("Nro", "Fecha", "Vence", "Cliente", "Nombre", "Total", "Saldo", "Días vencida")
        self.tv_x = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (70, 90, 90, 70, 330, 110, 110, 90)):
            self.tv_x.heading(c, text=c)
            self.tv_x.column(c, width=w, anchor="e" if c in ("Nro", "Total", "Saldo", "Días vencida") else "w")
        self.tv_x.column("Días vencida", width=95, minwidth=80, stretch=False, anchor="center")
        self.tv_x.tag_configure("venc", foreground="#b00020")
        sb = ttk.Scrollbar(fr, orient="vertical", command=self.tv_x.yview); self.tv_x.configure(yscrollcommand=sb.set)
        b = ttk.Frame(fr); b.pack(side="bottom", fill="x", pady=4)
        sb.pack(side="right", fill="y"); self.tv_x.pack(fill="both", expand=True)
        ttk.Button(b, text="Marcar pagada", command=lambda: self.cxc_do(self.marcar_pagada)).pack(side="left", padx=3)
        ttk.Button(b, text="Ver factura (PDF)", command=lambda: self.cxc_do(self.ver_pdf_nro)).pack(side="left", padx=3)
        ttk.Button(b, text="Pagadas recientemente", command=self.cxc_pagadas).pack(side="left", padx=12)
        self.mnu_x = tk.Menu(self.root, tearoff=0)
        self.mnu_x.add_command(label="Ver factura", command=lambda: self.cxc_do(self.ver_pdf_nro))
        self.mnu_x.add_command(label="Pagar", command=lambda: self.cxc_do(self.marcar_pagada))
        self.mnu_x.add_separator()
        self.mnu_x.add_command(label="Cancelar", command=lambda: self.mnu_x.unpost())
        self.tv_x.bind("<Button-3>", self.cxc_menu)
        self.lbl_x = ttk.Label(b, text="", font=("Segoe UI", 10, "bold")); self.lbl_x.pack(side="right", padx=8)

    def cxc_pick(self):
        rows = [(c["code"], c["name"], c["rnc"] or "") for c in self.db.q("SELECT * FROM clients WHERE COALESCE(ctype,'C')='C' ORDER BY name")]
        txt = self.xc.get().strip()
        if txt:
            t = txt.lower()
            if not any(t in " ".join(str(x) for x in r).lower() for r in rows):
                messagebox.showinfo("Cuentas por cobrar", f"Cliente no encontrado: {txt}"); return
        p = Picker(self.root, "Buscar cliente", ("Código", "Nombre", "RNC"), rows, [90, 380, 150], inicial=txt)
        if p.result:
            cod = str(p.result[0]); nom = str(p.result[1])
            for r in rows:
                if str(r[0]).strip().lower() == cod.strip().lower():
                    cod, nom = r[0], r[1]; break
            self.xc.set(cod); self.xn.set(nom); self.load_cxc()

    def load_cxc(self):
        self.tv_x.delete(*self.tv_x.get_children())
        code = self.xc.get().strip() or None
        hoy = datetime.date.today(); tot = 0
        for inv, saldo in self.db.open_invoices(code):
            due = parse_date(inv["due"]) or parse_date(inv["date"])
            dias = (hoy - due).days if due else 0
            self.tv_x.insert("", "end", iid=str(inv["nro"]), tags=("venc",) if dias > 0 else (), values=(
                inv["nro"], dmy(inv["date"]), dmy(inv["due"]), inv["client"], inv["name"], m2(inv["total"]), m2(saldo),
                dias if dias > 0 else ""))
            tot += saldo
        self.lbl_x.config(text=f"Total por cobrar {m2(tot)}")

    def cxc_menu(self, ev):
        fila = self.tv_x.identify_row(ev.y)
        if not fila:
            return
        self.tv_x.selection_set(fila); self.tv_x.focus(fila)
        try:
            self.mnu_x.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.mnu_x.grab_release()

    def cxc_pagadas(self):
        top = tk.Toplevel(self.root); top.title("Pagadas recientemente"); top.transient(self.root)
        ttk.Label(top, text="Últimas 10 facturas pagadas por completo").pack(anchor="w", padx=10, pady=(10, 4))
        cols = ("Nro", "Fecha", "Cliente", "Total", "Pagada el")
        tv = ttk.Treeview(top, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (70, 90, 330, 110, 90)):
            tv.heading(c, text=c); tv.column(c, width=w, anchor="e" if c in ("Nro", "Total") else "w")
        tv.pack(fill="both", expand=True, padx=10)
        def cargar():
            tv.delete(*tv.get_children())
            for inv, fp in self.db.pagadas_recientes(10):
                tv.insert("", "end", iid=str(inv["nro"]), values=(inv["nro"], dmy(inv["date"]), inv["name"], m2(inv["total"]), dmy(fp)))
        def sel():
            s = tv.selection()
            if not s:
                messagebox.showinfo("Pagadas recientemente", "Seleccione una factura.", parent=top); return None
            return int(s[0])
        def ver():
            n = sel()
            if n is not None: self.ver_pdf_nro(n)
        def reversar():
            n = sel()
            if n is None: return
            inv = self.db.one("SELECT total FROM invoices WHERE nro=?", (n,))
            if messagebox.askyesno("Corregir factura", f"La factura {n} aparece pagada.\n\n¿Marcarla como NO pagada?\n"
                                   f"Se quitan sus pagos y queda con saldo {m2(inv['total'])}.", parent=top):
                self.db.mark_unpaid(n); self.refresh_all(); cargar()
        bf = ttk.Frame(top); bf.pack(fill="x", padx=10, pady=10)
        ttk.Button(bf, text="Ver factura", command=ver).pack(side="left", padx=3)
        ttk.Button(bf, text="Marcar NO pagada (corregir)", command=reversar).pack(side="left", padx=3)
        ttk.Button(bf, text="Cerrar", command=top.destroy).pack(side="right", padx=3)
        tv.bind("<Double-1>", lambda e: ver())
        mnu = tk.Menu(top, tearoff=0)
        mnu.add_command(label="Ver factura", command=ver)
        mnu.add_command(label="Marcar NO pagada (corregir)", command=reversar)
        mnu.add_separator()
        mnu.add_command(label="Cerrar", command=mnu.unpost)
        def menu(ev):
            fila = tv.identify_row(ev.y)
            if not fila or fila not in tv.selection():
                return "break"
            try:
                mnu.tk_popup(ev.x_root, ev.y_root)
            finally:
                mnu.grab_release()
            return "break"
        tv.bind("<Button-3>", menu)
        cargar()

    def cxc_do(self, fn):
        s = self.tv_x.selection()
        if not s:
            messagebox.showinfo("Cuentas por cobrar", "Seleccione una factura."); return
        fn(int(s[0]))

    def ver_pdf_nro(self, n):
        ruta = self.pdf_path(n)
        try:
            generar_factura(self.db, n, ruta)
        except PermissionError:
            messagebox.showwarning("PDF", "Ese PDF está abierto. Ciérrelo y vuelva a intentar."); return
        open_file(ruta)

    def rep_path(self, nombre):
        d = self.db.carpeta("R")
        return os.path.join(d, f"{nombre}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

    def pdf_estado(self):
        try:
            d1, d2 = read_dmy(self.xd.get()), read_dmy(self.xh.get())
        except ValueError as e:
            messagebox.showwarning("Fechas", str(e)); return
        code = self.xc.get().strip()
        if code:
            clientes = [code]
        else:
            if not messagebox.askyesno("Estado de cuenta", "No eligió cliente.\n¿Hacer el estado de cuenta de todos los clientes con balance?"):
                return
            clientes = sorted({inv["client"] for inv, _ in self.db.open_invoices()})
        ruta = self.rep_path(f"Estado_Cta_{code}" if code else "Estado_Cta_todos")
        try:
            ruta, hechos, fallos = reportes.estado_cuenta(self.db, clientes, d1, d2, ruta)
        except Exception as e:
            messagebox.showerror("Estado de cuenta", f"No se pudo hacer el estado de cuenta:\n{e}"); return
        if fallos:
            det = "\n".join(f"{c}: {m}" for c, m in fallos[:15]) + ("\n..." if len(fallos) > 15 else "")
            messagebox.showwarning("Estado de cuenta", f"Se hicieron {len(hechos)} de {len(clientes)} clientes.\n"
                                   f"Problemas:\n{det}")
        elif not code:
            messagebox.showinfo("Estado de cuenta", f"Estados de cuenta hechos: {len(hechos)} clientes.")
        open_file(ruta)

    def pdf_saldos(self):
        try:
            d1, al = read_dmy(self.sd.get()), read_dmy(self.sa.get())
            d2 = al   # "hasta" es la misma fecha "al"
        except ValueError as e:
            messagebox.showwarning("Fechas", str(e)); return
        ruta = self.rep_path("Saldos_vencidos")
        reportes.saldos_vencidos(self.db, d1, d2, al, ruta); open_file(ruta)

    # ----- Reportes -----
    def tab_reportes(self, fr):
        self.nb.add(fr, text="Reportes")
        box = ttk.Frame(fr); box.pack(anchor="nw", padx=20, pady=16)
        hoy = datetime.date.today()
        self.rd = tk.StringVar(value=dmy(hoy.replace(day=1))); self.rh = tk.StringVar(value=dmy(hoy))
        ttk.Label(box, text="Desde").grid(row=0, column=0, sticky="e"); fecha_entry(box, self.rd, 12).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(box, text="Hasta").grid(row=0, column=2, sticky="e"); fecha_entry(box, self.rh, 12).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(box, text="Desde la primera factura", command=lambda: self.rd.set(dmy(self.db.one("SELECT MIN(date) FROM invoices")[0] or fmt_date(hoy)))).grid(row=0, column=4, padx=8)
        items = [("Ventas por fechas", lambda a, b, r: reportes.relacion_facturas(self.db, a, b, r)),
                 ("Facturas por NCF", lambda a, b, r: reportes.facturas_por_ncf(self.db, a, b, r)),
                 ("ITBIS cobrado", lambda a, b, r: reportes.itbis_cobrado(self.db, a, b, r)),
                 ("Facturas por producto", lambda a, b, r: reportes.facturas_por_producto(self.db, a, b, r)),
                 ("Ventas por cliente", lambda a, b, r, x: reportes.ventas_por_cliente(self.db, a, b, r, x)),
                 ("Ventas por producto", lambda a, b, r, x: reportes.ventas_por_producto(self.db, a, b, r, x)),
                 ("Valor del inventario (a una fecha determinada)", lambda a, b, r: reportes.valor_inventario(self.db, b, r)),
                 ("Órdenes de compra", lambda a, b, r: reportes.ordenes_compra(self.db, a, b, r)),
                 ("Saldos vencidos (a una fecha determinada)", lambda a, b, r: reportes.saldos_vencidos(self.db, a, b, b, r)),
                 ("Llenado de IT1", lambda a, b, r: reportes.llenado_it1(self.db, b, r))]
        for i, (lab, fn) in enumerate(items):
            ttk.Button(box, text=lab, width=48, command=lambda lab=lab, fn=fn: self.run_rep(lab, fn)).grid(
                row=1 + i, column=0, columnspan=5, sticky="w", pady=3)

    def elegir_para_reporte(self, lab):
        """Ventas por cliente / producto: se elige uno o todos. Devuelve codigo, '' = todos, None = cancelado."""
        if lab == "Ventas por cliente":
            rows = [("(Todos)", "Todos los clientes")] + [(c["code"], c["name"]) for c in self.db.q(
                "SELECT code, name FROM clients WHERE COALESCE(ctype,'C')='C' ORDER BY name")]
            p = Picker(self.root, "Ventas por cliente: elija el cliente", ("Código", "Cliente"), rows, [120, 560])
        else:
            rows = [("(Todos)", "Todos los productos")] + [(x["code"], x["descr"]) for x in self.db.q(
                "SELECT code, descr FROM products ORDER BY code")]
            p = Picker(self.root, "Ventas por producto: elija el producto", ("Código", "Producto"), rows, [120, 560])
        if not p.result: return None
        return "" if p.result[0] == "(Todos)" else p.result[0]

    def run_rep(self, lab, fn):
        try:
            a, b = read_dmy(self.rd.get()), read_dmy(self.rh.get())
        except ValueError as e:
            if not lab.startswith(("Valor del inventario", "Saldos vencidos", "Llenado de IT1")):
                messagebox.showwarning("Fechas", str(e)); return
            a = b = datetime.date.today()
        if lab in ("Ventas por cliente", "Ventas por producto"):
            x = self.elegir_para_reporte(lab)
            if x is None: return
            fn = (lambda f, x: lambda a, b, r: f(a, b, r, x or None))(fn, x)
        if lab.startswith("Saldos vencidos"):
            d = pedir_hoy_o_fecha(self.root, "Saldos vencidos")
            if d is None: return
            primera = self.db.one("SELECT MIN(date) FROM invoices WHERE deleted=0")[0]
            a = parse_date(primera) if primera else d
            b = d
        elif lab == "Llenado de IT1":
            hoy = datetime.date.today()
            ult = (hoy.replace(day=1) - datetime.timedelta(days=1))
            while True:
                d = pedir_fecha(self.root, "Llenado de IT1", "Último día del mes:", dmy(ult))
                if d is None: return
                if (d + datetime.timedelta(days=1)).day == 1: break
                fin_mes = (d.replace(day=28) + datetime.timedelta(days=4))
                fin_mes = fin_mes - datetime.timedelta(days=fin_mes.day)
                messagebox.showwarning("Llenado de IT1", f"{dmy(d)} no es el último día del mes.\n"
                                       f"El último día de ese mes es {dmy(fin_mes)}.")
                ult = fin_mes
            a, b = d.replace(day=1), d
        elif lab.startswith("Valor del inventario"):
            d = pedir_fecha(self.root, "Valor del inventario", "Inventario a la fecha:", dmy(datetime.date.today()))
            if d is None: return
            b = d
        self.root.config(cursor="watch"); self.root.update()
        try:
            ruta = fn(a, b, self.rep_path(lab.split(" (")[0].replace(" ", "_")))
        except Exception as e:
            self.root.config(cursor=""); messagebox.showerror("Reporte", f"No se pudo generar:\n{e}"); return
        self.root.config(cursor=""); open_file(ruta)

    # ----- Comprobantes -----
    def tab_seq(self, fr):
        self.nb.add(fr, text="Comprobantes (NCF)")
        top = ttk.Frame(fr); top.pack(fill="x", pady=4)
        ttk.Button(top, text="Agregar secuencia nueva", command=lambda: self.edit_seq(None)).pack(side="left", padx=3)
        ttk.Button(top, text="Editar", command=lambda: self.edit_seq(self.sel_s(), True)).pack(side="left", padx=3)
        ttk.Button(top, text="Activar / desactivar", command=self.toggle_seq).pack(side="left", padx=3)
        ttk.Label(top, text="Avisar cuando queden").pack(side="left", padx=(20, 3))
        self.av = tk.StringVar(value=self.db.cfg("aviso_pocos"))
        ttk.Entry(top, textvariable=self.av, width=5).pack(side="left")
        ttk.Button(top, text="Guardar aviso", command=lambda: (self.db.set_cfg("aviso_pocos", int(num(self.av.get(), 10))), self.refresh_all())).pack(side="left", padx=3)
        cols = ("Id", "Tipo", "Prefijo (como en Monica)", "Siguiente NCF", "Siguiente nro.", "Último autorizado", "Quedan", "Estado", "Autorización")
        self.tv_s = ttk.Treeview(fr, columns=cols, show="headings")
        for c, w in zip(cols, (40, 200, 160, 190, 100, 120, 80, 90, 100)):
            self.tv_s.heading(c, text=c); self.tv_s.column(c, width=w)
        self.tv_s.tag_configure("low", background="#fff3cd"); self.tv_s.tag_configure("off", foreground="#888")
        self.tv_s.pack(fill="both", expand=True)
        menu_derecho(self.tv_s, self.root, (("Editar", lambda: self.edit_seq(self.sel_s(), True)),
                                            ("Activar / desactivar", self.toggle_seq)))
        ttk.Label(fr, text="Para el e-CF el prefijo es como Monica lo guarda, por ejemplo  ......E3100  (crédito fiscal) o  ......E3200  "
                           "(consumidor final). El NCF queda: prefijo + número de 8 dígitos.").pack(anchor="w", padx=6, pady=4)

    def sel_s(self):
        s = self.tv_s.selection(); return int(s[0]) if s else None

    def load_seq(self):
        self.tv_s.delete(*self.tv_s.get_children())
        lim = int(self.db.cfg("aviso_pocos") or 10)
        for s in self.db.q("SELECT * FROM sequences ORDER BY active DESC, id DESC"):
            q = self.db.seq_remaining(s)
            tag = "off" if not s["active"] else ("low" if q <= lim else "")
            self.tv_s.insert("", "end", iid=str(s["id"]), tags=(tag,), values=(
                s["id"], tipo_nombre(s["tipo"]), s["fixed"], self.db.ncf_text(s["fixed"], s["next_num"]),
                s["next_num"], s["limit_num"], q, "Activa" if s["active"] else "Inactiva", dmy(s["auth_date"])))

    def edit_seq(self, sid, need=False):
        if need and not sid:
            messagebox.showinfo("Comprobantes", "Seleccione una secuencia."); return
        tipos = [tipo_nombre(t) for t in (1, 2, 14, 15, 16, 3, 4)]
        vals = dict(self.db.one("SELECT * FROM sequences WHERE id=?", (sid,))) if sid else {"fixed": "......E3100", "next_num": 1, "tipo": 1}
        vals["tipo_n"] = tipo_nombre(vals["tipo"]); vals["auth"] = dmy(vals.get("auth_date"))
        r = form_dialog(self.root, "Secuencia de comprobantes", [
            ("tipo_n", "Tipo", "combo:" + "|".join(tipos)), ("fixed", "Prefijo", "text"),
            ("next_num", "Primer número a usar", "num"), ("limit_num", "Último número autorizado", "num"),
            ("auth", "Fecha autorización (DD/MM/AAAA)", "date")], vals)
        if not r: return
        try:
            tipo = next(t for t in (1, 2, 14, 15, 16, 3, 4) if tipo_nombre(t) == r["tipo_n"])
            nx = int(num(r["next_num"])); lm = int(num(r["limit_num"]))
            au = fmt_date(read_dmy(r["auth"])) if r["auth"] else ""
        except (ValueError, StopIteration) as e:
            messagebox.showwarning("Comprobantes", f"Dato no válido. {e}"); return
        if not r["fixed"] or lm < nx:
            messagebox.showwarning("Comprobantes", "Revise el prefijo y que el último número sea mayor o igual al primero."); return
        try:
            if sid:
                self.db.con.execute("UPDATE sequences SET tipo=?,name=?,fixed=?,next_num=?,limit_num=?,auth_date=? WHERE id=?",
                                    (tipo, tipo_nombre(tipo), r["fixed"], nx, lm, au, sid))
            else:
                if messagebox.askyesno("Comprobantes", "¿Desactivar las otras secuencias de este mismo tipo?"):
                    self.db.con.execute("UPDATE sequences SET active=0 WHERE tipo=?", (tipo,))
                self.db.con.execute("INSERT INTO sequences(tipo,name,fixed,next_num,limit_num,active,auth_date) VALUES(?,?,?,?,?,1,?)",
                                    (tipo, tipo_nombre(tipo), r["fixed"], nx, lm, au))
            self.db.con.commit()
        except Exception as e:
            messagebox.showwarning("Comprobantes", f"No se pudo guardar: {e}"); return
        self.refresh_all()
        pend = self.db.one("SELECT COUNT(*) FROM invoices WHERE deleted=0 AND (ncf IS NULL OR ncf='') AND tipo=?", (tipo,))[0]
        if pend:
            messagebox.showinfo("Comprobantes", f"Hay {pend} factura(s) de este tipo sin NCF. En 'Ventas', filtre "
                                                "'Sin NCF (pendientes)' y use 'Asignar NCF'.")

    def toggle_seq(self):
        sid = self.sel_s()
        if not sid: return
        self.db.con.execute("UPDATE sequences SET active=1-active WHERE id=?", (sid,)); self.db.con.commit()
        self.refresh_all()

    # ----- Respaldo -----
    def tab_respaldo(self, fr):
        self.nb.add(fr, text="Respaldo")
        box = ttk.Frame(fr); box.pack(anchor="nw", padx=20, pady=20)
        ttk.Button(box, text="Importar respaldo de Monica (.zip)", command=lambda: self.importar(True), width=45).pack(anchor="w", pady=4)
        ttk.Button(box, text="Importar respaldo de Monica (carpeta)", command=lambda: self.importar(False), width=45).pack(anchor="w", pady=4)
        ttk.Button(box, text="Hacer respaldo ahora", command=self.respaldar, width=45).pack(anchor="w", pady=4)
        ttk.Button(box, text="Restaurar un respaldo de este programa", command=self.restaurar, width=45).pack(anchor="w", pady=4)
        ttk.Button(box, text="Abrir carpeta del programa", command=lambda: open_file(self.db.loc), width=45).pack(anchor="w", pady=4)
        uf = ttk.LabelFrame(box, text="Carpeta del programa (datos, documentos y respaldos)"); uf.pack(anchor="w", fill="x", pady=(14, 4))
        self.vbk = tk.StringVar(value=self.db.loc)
        ttk.Entry(uf, textvariable=self.vbk, width=70).pack(side="left", padx=6, pady=6)
        ttk.Button(uf, text="Elegir carpeta...", command=self.elegir_carpeta_bk).pack(side="left", padx=3)
        ttk.Button(uf, text="Guardar ubicación", command=self.guardar_carpeta_bk).pack(side="left", padx=3)
        ttk.Label(box, text=f"(se usa una carpeta llamada '{APP_NAME}' en el lugar que elija; si no existe, se crea y todo se mueve ahí)").pack(anchor="w")
        self.lbl_r = ttk.Label(box, text="", justify="left"); self.lbl_r.pack(anchor="w", pady=12)
        self.lbl_r.config(text=self.texto_respaldo())

    def elegir_carpeta_bk(self):
        d = filedialog.askdirectory(title=f"Dónde crear la carpeta {APP_NAME}", mustexist=False)
        if d:
            self.vbk.set(os.path.normpath(d)); self.guardar_carpeta_bk()

    def guardar_carpeta_bk(self):
        carpeta = self.vbk.get().strip()
        if not carpeta:
            messagebox.showwarning("Carpeta", "Escriba o elija una carpeta."); self.vbk.set(self.db.loc); return
        if carpeta:
            try:
                os.makedirs(carpeta, exist_ok=True)   # si no existe, se crea
                prueba = os.path.join(carpeta, ".prueba_escritura")
                open(prueba, "w").close(); os.remove(prueba)
            except OSError as e:
                messagebox.showwarning("Respaldos", f"No se puede usar esa carpeta:\n{carpeta}\n\n{e}"); return
            carpeta = os.path.normpath(carpeta)
            if os.path.basename(carpeta).lower() != APP_NAME.lower():
                carpeta = os.path.join(carpeta, APP_NAME)
            self.vbk.set(carpeta)
        try:
            nueva = self.db.cambiar_ubicacion(carpeta)
        except OSError as e:
            messagebox.showwarning("Respaldos", f"No se pudo mover a esa carpeta:\n{e}"); return
        self.vbk.set(nueva)
        self.lbl_r.config(text=self.texto_respaldo())
        messagebox.showinfo("Carpeta", f"Todo se guarda ahora en:\n{nueva}")

    def texto_respaldo(self):
        return (f"Carpeta: {self.db.loc}\n"
                "Dentro: datos.db y las carpetas " + ", ".join(SUB.values()) + ".\n"
                "Al cerrar se hace un respaldo en Respaldos\\Cierre, solo si hubo cambios desde el último respaldo.\n"
                "Los manuales y los de antes de importar o restaurar van a Respaldos\\Antes de cerrar.\n"
                "Al importar un respaldo de Monica se actualizan sus datos; lo que hizo en este programa se conserva.")

    def importar(self, zip_):
        path = filedialog.askopenfilename(title="Respaldo de Monica", filetypes=[("Zip", "*.zip")]) if zip_ else \
            filedialog.askdirectory(title="Carpeta del respaldo de Monica (ej. JUEVES)")
        if not path: return
        self.db.backup("antes_de_importar")
        self.root.config(cursor="watch"); self.root.update()
        try:
            rep = import_backup(self.db, path, lambda m: (self.banner.config(text=m), self.root.update()))
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror("Importar", f"No se pudo importar:\n{e}"); return
        self.root.config(cursor="")
        msg = (f"Importado:\n  Clientes: {rep['clientes']}\n  Productos: {rep['productos']}\n  Secuencias: {rep['secuencias']}\n"
               f"  Facturas: {rep['facturas']}\n  Facturas borradas en Monica: {rep['facturas_borradas']}\n"
               f"  Cotizaciones: {rep.get('Q', 0)}\n  Conduces: {rep.get('G', 0)}\n  Órdenes de compra: {rep.get('O', 0)}\n"
               f"  Notas de crédito: {rep.get('NC', 0)}")
        if rep["conflictos"]:
            msg += "\n\nAvisos:\n" + "\n".join(rep["conflictos"][:15])
            if len(rep["conflictos"]) > 15: msg += f"\n... y {len(rep['conflictos'])-15} más"
        self.rango_total()
        self.refresh_all(); messagebox.showinfo("Importar", msg)

    def respaldar(self):
        p = self.db.backup("manual"); messagebox.showinfo("Respaldo", f"Respaldo guardado:\n{p}")

    def restaurar(self):
        p = filedialog.askopenfilename(title="Respaldo a restaurar", initialdir=self.db.backup_dir(),
                                       filetypes=[("Respaldo", "*.db")])
        if not p: return
        if not messagebox.askyesno("Restaurar", "Se reemplazarán los datos actuales por ese respaldo\n"
                                                "(antes se guarda un respaldo de lo actual). ¿Seguir?"):
            return
        import sqlite3
        self.db.backup("antes_de_restaurar")
        src = sqlite3.connect(p)
        with self.db.con:
            src.backup(self.db.con)
        src.close()
        self.refresh_all(); messagebox.showinfo("Restaurar", "Listo.")

    # ----- Configuracion -----
    def tab_config(self, fr):
        self.nb.add(fr, text="Configuración")
        box = ttk.Frame(fr); box.pack(anchor="nw", padx=20, pady=20)
        items = [("emp_nombre", "Nombre de la empresa"), ("emp_l1", "Línea 1"), ("emp_l2", "Línea 2"), ("emp_l3", "Línea 3"),
                 ("emp_l4", "Línea 4"), ("emp_l5", "Línea 5"), ("lugar", "Lugar de expedición"), ("envio", "Envío (por defecto)"),
                 ("coment2", "Comentario 2 (por defecto)"), ("coment3", "Comentario 3 (por defecto)"),
                 ("max_respaldos", "Respaldos automáticos a conservar"),
                 ("msg_fact1", "Mensaje de factura 1"), ("msg_fact2", "Mensaje de factura 2"),
                 ("msg_fact3", "Mensaje de factura 3")]
        self.cv = {}
        for i, (k, lab) in enumerate(items):
            ttk.Label(box, text=lab).grid(row=i, column=0, sticky="e", padx=6, pady=3)
            v = tk.StringVar(value=self.db.cfg(k)); self.cv[k] = v
            ttk.Entry(box, textvariable=v, width=50).grid(row=i, column=1, sticky="w")
        ttk.Button(box, text="Guardar", command=self.save_cfg).grid(row=len(items) + 1, column=1, sticky="w", pady=10)

    def save_cfg(self):
        for k, v in self.cv.items(): self.db.set_cfg(k, v.get())
        messagebox.showinfo("Configuración", "Guardado.")

    def on_close(self):
        try:
            self.db.backup("cierre")
        except Exception as e:
            if not messagebox.askyesno("Respaldo", f"No se pudo hacer el respaldo al cerrar:\n{e}\n\n¿Cerrar igual?"):
                return
        self.db.close(); self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        App().run()
    except Exception:
        err = traceback.format_exc()
        try:
            with open(os.path.join(leer_ubicacion() or os.environ.get("TEMP", os.path.expanduser("~")), "error.log"), "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.datetime.now()} ---\n{err}")
        except Exception:
            pass
        try:
            messagebox.showerror("Error", err)
        except Exception:
            print(err)


if __name__ == "__main__":
    main()
