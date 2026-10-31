"""Importa un respaldo de Monica 8.5 (carpeta o .zip) a la base local."""
import os, zipfile, tempfile, shutil
from dbfreader import read_dbf
from db import fmt_date

def find_backup_dir(path):
    tmp = None
    if os.path.isfile(path) and path.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="monica_")
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
        path = tmp
    for root, dirs, files in os.walk(path):
        low = {f.lower(): f for f in files}
        if "comefac.dbf" in low and "facturas.dbf" in low and "empresas.dbf" in low:
            return root, low, tmp
    raise FileNotFoundError("No encontré un respaldo de Monica (faltan comefac.dbf / facturas.dbf / empresas.dbf).")

def _t(root, low, name):
    f = low.get(name.lower() + ".dbf")
    if not f:
        return []
    _, rows = read_dbf(os.path.join(root, f))
    return [r for r in rows if not r["_deleted"]]

def import_backup(db, path, progress=lambda m: None):
    root, low, tmp = find_backup_dir(path)
    rep = {"clientes": 0, "productos": 0, "secuencias": 0, "facturas": 0,
           "facturas_borradas": 0, "conflictos": []}
    con = db.con
    try:
        progress("Leyendo clientes...")
        for r in _t(root, low, "empresas"):
            if r["tipo_empre"] not in ("C", "S") or not r["cod_empre"]:
                continue
            code = r["cod_empre"].strip()
            old = db.one("SELECT origin FROM clients WHERE code=?", (code,))
            if old and old["origin"] == "app":
                rep["conflictos"].append(f"Cliente {code}: existe en Monica y en este programa; se dejó el de este programa.")
                continue
            if old and old["origin"] == "app-mod":
                continue
            con.execute("INSERT OR REPLACE INTO clients(code,name,addr1,addr2,addr3,city,phone,fax,rnc,email,contact,terms,ctype,origin)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?, 'monica')",
                        (code, r["name_empre"], r["direcc1"], r["direcc2"], r["direcc3"], r["ciudad"],
                         r["nro_telefo"], (r["nro_fax"] or "").strip(), (r["nro_tribut"] or "").strip(),
                         r["e_mail"], r["contacto"], r["terminos"], r["tipo_empre"]))
            rep["clientes"] += 1

        progress("Leyendo productos...")
        all_items = {}
        _, raw_items = read_dbf(os.path.join(root, low["items.dbf"])) if "items.dbf" in low else (None, [])
        for r in raw_items:
            if r["cod_item"]:
                all_items[r["cod_item"].strip()] = r
        for r in raw_items:
            if r["_deleted"] or not r["cod_item"] or r["cod_item"].strip() == "XXXX":
                continue
            code = r["cod_item"].strip()
            old = db.one("SELECT origin FROM products WHERE code=?", (code,))
            if old and old["origin"] in ("app", "app-mod"):
                con.execute("UPDATE products SET stock_base=? WHERE code=?", (r["cant_stock"], code))
                if old["origin"] == "app":
                    rep["conflictos"].append(f"Producto {code}: existe en Monica y en este programa; se dejó el de este programa.")
                continue
            con.execute("INSERT OR REPLACE INTO products(code,descr,price,price2,cost,stock_base,itbis,category,active,origin)"
                        " VALUES(?,?,?,?,?,?,?,?,1,'monica')",
                        (code, r["des_item"], r["precio"], r["precio2"], r["costo_pro"] or r["costo"],
                         r["cant_stock"], r["impuesto"] or 0, r["cod_cate"]))
            rep["productos"] += 1

        progress("Leyendo secuencias de comprobantes...")
        for r in _t(root, low, "ncf"):
            fixed = r["sec_fija"]
            if not fixed:
                continue
            mid = int(r["codigo_ncf"] or 0)
            old = db.one("SELECT * FROM sequences WHERE monica_id=?", (mid,))
            if old:
                con.execute("UPDATE sequences SET next_num=MAX(next_num,?), limit_num=MAX(limit_num,?) WHERE id=?",
                            (int(r["contador"]), int(r["limite"]), old["id"]))
            else:
                con.execute("INSERT INTO sequences(monica_id,tipo,name,fixed,next_num,limit_num,active,auth_date,origin)"
                            " VALUES(?,?,?,?,?,?,?,?,'monica')",
                            (mid, int(r["tipo_cf"]), r["tipo_comp"], fixed, int(r["contador"]), int(r["limite"]),
                             1 if (r["situacion"] or "").lower().startswith("activ") else 0, fmt_date(r["aut_fecha"])))
            rep["secuencias"] += 1

        progress("Leyendo facturas...")
        heads = {}
        for r in _t(root, low, "comefac"):
            heads[int(r["nro_fact"])] = r
        lines = {}
        for r in _t(root, low, "facturas"):
            lines.setdefault(int(r["nro_fact"]), []).append(r)
        comments = {}
        for r in _t(root, low, "cofact"):
            comments.setdefault(int(r["nro_fact"]), []).append(r)
        saldos = {}
        con.execute("DELETE FROM ledger")
        for r in _t(root, low, "docs"):
            if r["tipo_doc"] in ("F", "P", "D", "C") and (r["cod_empre"] or "").strip():
                con.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",
                            (r["cod_empre"].strip(), r["tipo_doc"], fmt_date(r["fecha_e"]), fmt_date(r["fecha_ve"]),
                             int(r["nro_fact"] or 0), r["descri_doc"], r["monto"] or 0, r["saldo"] or 0))
            if r["tipo_doc"] == "F":
                n = int(r["nro_fact"])
                saldos[n] = saldos.get(n, 0) + (r["saldo"] or 0)
        names = {c["code"]: c["name"] for c in db.q("SELECT code,name FROM clients")}

        existing = {r["nro"]: r for r in db.q("SELECT nro,origin,modified FROM invoices")}
        for nro, h in heads.items():
            ex = existing.get(nro)
            if ex and ex["origin"] == "app":
                rep["conflictos"].append(f"Factura {nro}: existe en Monica y en este programa con el mismo número; se dejó la de este programa.")
                continue
            if ex and ex["modified"]:
                continue
            ncf = (h["ncf"] or "").strip()
            tipo = db.tipo_from_ncf(ncf)
            client = (h["sold_to"] or "").strip()
            # Monica imprime el nombre comercial del cliente (ficha), no el contacto que guarda en ship_to
            name = names.get(client) or (h["ship_to"] or "").strip() or client
            ls = lines.get(nro, [])[::-1]  # Monica muestra las lineas en orden inverso al de grabacion
            subtotal = round(sum(l["cantidad"] * l["prec_unit"] for l in ls), 2)
            total = h["total"] or subtotal
            con.execute("DELETE FROM lines WHERE nro=?", (nro,))
            con.execute("DELETE FROM orig_lines WHERE nro=? AND kind='F'", (nro,))
            con.execute("DELETE FROM comments WHERE nro=?", (nro,))
            con.execute("DELETE FROM stock_moves WHERE nro=? AND kind='F'", (nro,))
            con.execute("INSERT OR REPLACE INTO invoices(nro,date,due,client,name,dir1,dir2,dir3,rnc,terms,ship_via,seller,ref,"
                        "comment1,comment2,comment3,ncf,tipo,subtotal,itbis,discount,total,saldo_base,deleted,origin,modified)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'monica',0)",
                        (nro, fmt_date(h["fecha_fact"]), fmt_date(h["vence_en"]), client, name,
                         h["direc1"], h["direc_spa"], h["direc3"], (h["reg_tribut"] or "").strip(),
                         h["terms"], h["ship_via"], h["slsperson"], h["su_refe"],
                         h["comentario"], h["comenta2"], h["comenta3"], ncf, tipo,
                         subtotal, h["impto"] or 0, h["dscto_cant"] or 0, total, round(saldos.get(nro, 0), 2)))
            for i, l in enumerate(ls, 1):
                code = (l["item"] or "").strip()
                it = all_items.get(code)
                descr = it["des_item"] if it else ""
                q = l["cantidad"] or 0
                cost = (l["costo_item"] / q) if q else 0
                con.execute("INSERT INTO lines(nro,pos,code,descr,qty,price,cost,itbis) VALUES(?,?,?,?,?,?,?,?)",
                            (nro, i, code, descr, q, l["prec_unit"], cost, l["porce"] or 0))
                con.execute("INSERT INTO orig_lines(nro,code,qty,kind) VALUES(?,?,?,'F')", (nro, code, q))
            for k, c in enumerate(comments.get(nro, [])):
                con.execute("INSERT INTO comments VALUES(?,?,?,?)", (nro, int(c["posicion"]), k, c["comentario"]))
            rep["facturas"] += 1

        progress("Leyendo cuentas por pagar...")
        con.execute("DELETE FROM ap_ledger")
        for r in _t(root, low, "cpdocs"):
            if r["tipo_doc"] in ("F", "P", "D", "C") and (r["cod_empre"] or "").strip():
                con.execute("INSERT INTO ap_ledger VALUES(?,?,?,?,?,?,?,?)",
                            (r["cod_empre"].strip(), r["tipo_doc"], fmt_date(r["fecha_e"]), fmt_date(r["fecha_ve"]),
                             int(r["nro_fact"] or 0), r["descri_doc"], r["monto"] or 0, r["saldo"] or 0))

        progress("Leyendo notas de crédito...")
        rep["NC"] = 0
        if "comedev.dbf" in low:
            dl = {}
            for r in _t(root, low, "devoluci"):
                dl.setdefault(int(r["nro_fact"]), []).append(r)
            exn = {r["nro"]: r for r in db.q("SELECT nro,origin,modified FROM odocs WHERE kind='NC'")}
            for h in _t(root, low, "comedev"):
                nro = int(h["nro_fact"]); e = exn.get(nro)
                if e and (e["origin"] == "app" or e["modified"]):
                    continue
                for t in ("odocs", "olines", "ocomments"):
                    con.execute(f"DELETE FROM {t} WHERE kind='NC' AND nro=?", (nro,))
                client = (h["sold_to"] or "").strip()
                ls = dl.get(nro, [])
                sub = round(sum((l["cantidad"] or 0) * (l["prec_unit"] or 0) for l in ls), 2)
                con.execute("INSERT INTO odocs(kind,nro,date,due,client,name,dir1,dir2,dir3,ship_to,sdir1,sdir2,sdir3,rnc,terms,"
                            "ship_via,seller,ref,comment1,comment2,comment3,subtotal,itbis,discount,total,paid,status,factura,"
                            "deleted,origin,modified,ncf) VALUES('NC',?,?,?,?,?,?,?,?,'','','','',?,?,?,'','',?,?,?,?,0,0,?,?,"
                            "'Con devolución',0,0,'monica',0,?)",
                            (nro, fmt_date(h["fecha_fact"]), fmt_date(h["vence_en"]), client, names.get(client, client),
                             h["direc1"], h["direc_spa"], h["direc2a"], (h["reg_tribut"] or "").strip(), h["terms"],
                             h["ship_via"], h["comentario"], h["comenta2"], h["comenta3"], sub, h["total"] or sub,
                             h["pago"] or 0, (h["ncf"] or "").strip()))
                for i, l in enumerate(ls, 1):
                    code = (l["item"] or "").strip(); it = all_items.get(code); q = l["cantidad"] or 0
                    con.execute("INSERT INTO olines(kind,nro,pos,code,descr,qty,price,cost,itbis,received) VALUES('NC',?,?,?,?,?,?,?,0,0)",
                                (nro, i, code, it["des_item"] if it else "", q, l["prec_unit"] or 0,
                                 ((l["costo_item"] or 0) / q) if q else 0))
                    con.execute("INSERT INTO orig_lines(nro,code,qty,kind) VALUES(?,?,?,'NC')", (nro, code, q))
                rep["NC"] += 1

        progress("Leyendo cotizaciones, conduces y órdenes de compra...")
        for kind, hn, ln, cn, kno, kdate, kdue in (
                ("Q", "comeest", "estimado", "coesti", "nro_esti", "fecha_fact", None),
                ("G", "comeguia", "guia", "coguia", "nro_guia", "fecha_guia", "fecha_ven"),
                ("O", "comeord", "ordenes", "coorden", "nro_orden", "fecha_fact", "vence_en")):
            rep[kind] = 0
            if hn + ".dbf" not in low:
                continue
            hh = {int(r[kno]): r for r in _t(root, low, hn)}
            ll = {}
            for r in _t(root, low, ln):
                ll.setdefault(int(r[kno]), []).append(r)
            cc = {}
            ckey = "nro_fact" if kind == "Q" else kno
            for r in _t(root, low, cn):
                cc.setdefault(int(r[ckey]), []).append(r)
            ex = {r["nro"]: r for r in db.q("SELECT nro,origin,modified FROM odocs WHERE kind=?", (kind,))}
            for nro, h in hh.items():
                e = ex.get(nro)
                if e and (e["origin"] == "app" or e["modified"]):
                    if e["origin"] == "app":
                        rep["conflictos"].append(f"{ {'Q':'Cotización','G':'Conduce','O':'Orden de compra'}[kind]} {nro}: "
                                                 "existe en Monica y en este programa; se dejó la de este programa.")
                    continue
                ls = ll.get(nro, [])[::-1]
                sub = round(sum((l["cantidad"] or 0) * (l["prec_unit"] or 0) for l in ls), 2)
                if kind == "O":
                    status = "Recibida" if ls and all((l["recibido"] or 0) >= (l["cantidad"] or 0) for l in ls) else "Pendiente"
                    status = "Recibida" if h["status"] == "P" and status == "Recibida" else status
                else:
                    status = ""
                for t in ("odocs", "olines", "ocomments"):
                    con.execute(f"DELETE FROM {t} WHERE kind=? AND nro=?", (kind, nro))
                con.execute("DELETE FROM orig_lines WHERE kind=? AND nro=?", (kind, nro))
                con.execute("DELETE FROM stock_moves WHERE kind=? AND nro=?", (kind, nro))
                g = lambda k: h[k] if k in h else ""
                client = (h["sold_to"] or "").strip()
                con.execute("INSERT INTO odocs(kind,nro,date,due,client,name,dir1,dir2,dir3,ship_to,sdir1,sdir2,sdir3,rnc,"
                            "terms,ship_via,seller,ref,comment1,comment2,comment3,subtotal,itbis,discount,total,paid,status,"
                            "factura,deleted,origin,modified) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'monica',0)",
                            (kind, nro, fmt_date(h[kdate]), fmt_date(h[kdue]) if kdue else "", client,
                             names.get(client, client), g("direc1"), g("direc_spa"), g("direc3"),
                             (g("ship_to") or "").strip() if kind == "O" else "", g("direc2"), g("direc2a"), g("direc3a"),
                             (g("reg_tribut") or "").strip(), g("terms"), g("ship_via"), g("slsperson"), g("su_refe"),
                             g("comentario"), g("comenta2"), g("comenta3"), sub, g("impto") or 0,
                             g("dscto_cant") or g("descuento") or 0, h["total"] or sub, g("pago") or 0, status,
                             int(g("nro_factu") or 0)))
                for i, l in enumerate(ls, 1):
                    code = (l["item"] or "").strip()
                    it = all_items.get(code)
                    q = l["cantidad"] or 0
                    con.execute("INSERT INTO olines(kind,nro,pos,code,descr,qty,price,cost,itbis,received) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (kind, nro, i, code, it["des_item"] if it else "", q, l["prec_unit"] or 0,
                                 ((l["costo_item"] or 0) / q) if q else 0, l["porce"] or 0,
                                 l["recibido"] if "recibido" in l else 0))
                    if kind == "G" or (kind == "O" and status == "Recibida"):
                        con.execute("INSERT INTO orig_lines(nro,code,qty,kind) VALUES(?,?,?,?)", (nro, code, q, kind))
                for k, c in enumerate(cc.get(nro, [])):
                    con.execute("INSERT INTO ocomments VALUES(?,?,?,?,?)", (kind, nro, int(c["posicion"]), k, c["comentario"]))
                rep[kind] += 1

        # facturas que Monica ya no tiene (borradas en Monica) y no se tocaron aqui
        for nro, ex in existing.items():
            if ex["origin"] == "monica" and not ex["modified"] and nro not in heads:
                for t in ("invoices", "lines", "comments", "payments"):
                    con.execute(f"DELETE FROM {t} WHERE nro=?", (nro,))
                for t in ("orig_lines", "stock_moves"):
                    con.execute(f"DELETE FROM {t} WHERE nro=? AND kind='F'", (nro,))
                rep["facturas_borradas"] += 1
        db.fix_contact_names()
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    db.set_cfg("ultima_importacion", path)
    return rep
