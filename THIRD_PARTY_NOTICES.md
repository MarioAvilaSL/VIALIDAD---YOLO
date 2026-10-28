# Avisos de terceros

El código propio de este repositorio (carpetas `app/`, `android/`, `scripts/`, `tests/`, `sql/`, `calibracion/`) se publica bajo licencia **MIT** (ver `LICENSE`): se puede usar, copiar, modificar y distribuir libremente, **conservando el aviso de copyright y el nombre del autor**.

Esa licencia **no cambia** las licencias de los componentes de terceros que se indican a continuación, que siguen sus propios términos.

| Componente | Licencia | Notas |
|---|---|---|
| [Ultralytics YOLO](https://github.com/ultralytics/ultralytics) (biblioteca y pesos base `yolo26s.pt`) | AGPL-3.0 | La aplicación importa esta biblioteca. Si distribuyes la aplicación junto con ella, o la ofreces como servicio en red a terceros, debes cumplir también la AGPL-3.0 (o adquirir la licencia Enterprise de Ultralytics). |
| Modelo entrenado `models/best.pt` | Derivado de pesos de Ultralytics | Se entrenó a partir de `yolo26s.pt`; Ultralytics distribuye sus modelos bajo AGPL-3.0. Verifica las condiciones antes de redistribuirlo. |
| Conjunto de datos [RDD2022](https://arxiv.org/abs/2209.08538) | Ver su registro (Figshare) | Usado para entrenar. Cita a sus autores. No se incluye en este repositorio. |
| Leaflet | BSD-2-Clause | `app/static/vendor/leaflet/` |
| Chart.js | MIT | `app/static/vendor/chart.umd.js` |
| JSZip | MIT o GPL-3.0 (a elección) | `app/static/vendor/jszip.min.js` |
| jsPDF | MIT | `app/static/vendor/jspdf.umd.min.js` |
| FastAPI, SQLAlchemy, Pillow, OpenCV, PyTorch, etc. | Sus respectivas licencias | Se instalan con `pip`; no se incluyen aquí. |

Esto es información práctica, no asesoría legal. Si vas a redistribuir el sistema comercialmente, consulta a un abogado.
