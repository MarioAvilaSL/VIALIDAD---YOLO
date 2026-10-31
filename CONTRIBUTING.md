# Cómo contribuir

¡Gracias por el interés! Este es un proyecto académico; las mejoras, correcciones y reportes de errores son bienvenidos.

## Reportar un error o proponer una mejora
Abre un *issue* con la plantilla que corresponda. Para un error, incluye:
- qué hiciste, qué esperabas y qué pasó;
- sistema operativo, versión de Python y, si aplica, modelo de teléfono;
- el mensaje de error de la consola (sin claves ni datos personales).

## Preparar el entorno
Sigue la sección *Instalación* del [README](README.md). Para las pruebas necesitas una base PostgreSQL **aparte** (las pruebas vacían sus tablas):

```powershell
psql -U postgres -c "CREATE DATABASE vialidad_test;"
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:TU_PASSWORD@localhost:5432/vialidad_test"
pytest -q
```

Las pruebas usan un detector simulado, así que no hace falta `models/best.pt`.

## Enviar cambios
1. Haz un *fork* y crea una rama (`git checkout -b mi-mejora`).
2. Mantén los cambios pequeños y con un propósito claro.
3. Añade o actualiza pruebas si cambias la lógica.
4. Comprueba que `pytest -q` pasa.
5. Abre un *pull request* describiendo qué cambia y por qué.

## Reglas del proyecto
- **No inventar cifras:** toda métrica o afirmación del README o del informe debe poder verificarse (medida, citada o marcada como hipótesis).
- **Datos personales:** no subas fotos con rostros, placas o direcciones exactas, ni archivos `.env`, bases de datos o la carpeta `storage/`.
- **Licencias:** el código propio es MIT; revisa `THIRD_PARTY_NOTICES.md` antes de añadir dependencias o incluir modelos y datos de terceros (Ultralytics es AGPL-3.0).
