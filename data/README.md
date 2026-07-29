# Datos del proyecto

Esta carpeta contiene únicamente documentación, muestras pequeñas y catálogos de referencia necesarios para comprender o reproducir el proyecto.

## Estructura

```text
data/
  reference/    Catálogos pequeños y datos auxiliares versionables
```

## Política

- No versionar datasets completos, respaldos de SQL Server ni archivos comprimidos.
- No incluir credenciales, cadenas de conexión personales ni datos sensibles.
- Los archivos `*.rar` y `*.bak` están excluidos para nuevas incorporaciones.
- Mantener una muestra mínima anonimizada solo cuando el equipo confirme su esquema y licencia.
- Registrar el origen, fecha, cantidad de registros, columnas y hash de cualquier fuente utilizada.

Los archivos pesados que ya formen parte del historial requieren una limpieza separada y aprobada; esta reorganización no los elimina ni modifica.

## Pendiente

El equipo debe documentar el medio externo autorizado para obtener los datos completos y publicar una muestra pequeña que permita ejecutar una prueba de humo.
