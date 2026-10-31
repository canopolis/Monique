UN = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ",
      "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISEIS", "DIECISIETE", "DIECIOCHO",
      "DIECINUEVE", "VEINTE", "VEINTIUN", "VEINTIDOS", "VEINTITRES", "VEINTICUATRO",
      "VEINTICINCO", "VEINTISEIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
DEC = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
CEN = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS",
       "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]

def _cientos(n):
    if n == 0: return ""
    if n == 100: return "CIEN"
    c, r = divmod(n, 100)
    out = CEN[c]
    if r:
        if r < 30: t = UN[r]
        else:
            d, u = divmod(r, 10)
            t = DEC[d] + (" Y " + UN[u] if u else "")
        out = (out + " " + t).strip()
    return out

def entero(n):
    if n == 0: return "CERO"
    partes = []
    mill, resto = divmod(n, 1000000)
    if mill:
        partes.append("UN MILLON" if mill == 1 else entero(mill) + " MILLONES")
    miles, cien = divmod(resto, 1000)
    if miles:
        partes.append("MIL" if miles == 1 else _cientos(miles) + " MIL")
    if cien:
        partes.append(_cientos(cien))
    return " ".join(partes)

def monto_letras(v, moneda="PESOS"):
    v = round(abs(v) + 1e-9, 2)
    e = int(v); c = int(round((v - e) * 100))
    return f"{entero(e)} {moneda} {c:02d}/100"
