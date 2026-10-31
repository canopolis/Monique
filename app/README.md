# Facturación Canopolis (reemplazo de Monica 8.5)

Un solo programa de Windows: **FacturacionCanopolis.exe**. Se compila solo en GitHub Actions y en
Releases queda siempre una sola descarga, la más nueva.

## Qué hace
- Importa el respaldo de Monica (.zip o carpeta) cuantas veces quiera: clientes, proveedores, productos,
  existencias, secuencias NCF, facturas, pagos, cotizaciones, conduces y órdenes de compra.
- Facturas: crédito fiscal, consumidor final, regímenes especiales, gubernamental y sin comprobante.
  Si se agota una secuencia no bloquea; el NCF se asigna después. ITBIS por línea (0, 16, 18).
- PDF igual al de Monica: facturas, cotizaciones, conduces y órdenes de compra.
- Cuentas por cobrar: pagos, estado de cuenta y saldos vencidos.
- Cuentas por pagar: pagos a proveedores, estado de cuenta de proveedor y saldos por pagar.
- Notas de crédito (E34, con o sin devolución al inventario) y de débito (E33), con NCF modificado.
- Reportes: relación de facturas, por clase, por NCF, ITBIS cobrado, por producto, valor del inventario,
  órdenes de compra.
- Respaldo automático al cerrar.

## Datos
`Documentos\FacturacionCanopolis\` → `datos.db`, `respaldos\`, `facturas_pdf\`, `reportes\`.
