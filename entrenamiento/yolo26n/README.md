# Experimento: YOLO26n (opción «rápida») frente a YOLO26s y YOLO26m

> Experimento con resultados medidos (abajo). La aplicación ofrece YOLO26n como opción «rápida»; el modelo predeterminado sigue siendo YOLO26s.

## Qué responde

¿Cuánta precisión pierde un modelo más pequeño (YOLO26n) y cuánta velocidad gana? La respuesta decide si la aplicación puede ofrecer una opción «rápida» además de la normal (YOLO26s). El experimento anterior con YOLO26m está en `../yolo26m/`.

## Qué hay aquí

| Archivo | Para qué sirve |
|---|---|
| `entrenar_y_comparar_yolo26n.ipynb` | Cuaderno de Google Colab (GPU T4). Reconstruye las mismas particiones de la Fase 4, entrena YOLO26n, compara los **tres** modelos y calcula los umbrales del perfil sensible de YOLO26m y de YOLO26n. |
| `../yolo26m/medir_velocidad_cpu.py` | Se ejecuta en **tu computador**: mide los ms por imagen de cada modelo en tu CPU (acepta dos o más modelos). |

## Cómo se garantiza una comparación justa

- **Mismos datos:** el cuaderno se detiene si las imágenes de train, val o test no coinciden con `manifest_full.csv` de la Fase 4.
- **Mismos hiperparámetros** que `full_yolo26s-2` (`args.yaml`); solo cambia el modelo.
- **Mismo presupuesto de tiempo (4 h).** YOLO26n es más rápido por época, así que hará **más épocas** que YOLO26s (47) o terminará antes por parada anticipada (`patience=20`). Es una comparación «a igual tiempo de entrenamiento», no «a igual número de épocas»; el cuaderno informa cuántas épocas hizo y por qué terminó.
- **Mismo evaluador** para los tres modelos, con verificación cruzada contra `model.val()` y contra lo medido antes para YOLO26s y YOLO26m.
- **Umbrales elegidos solo con validación; test se mira una sola vez** (la celda de test está desactivada hasta que pongas `EJECUTAR_TEST = True`).
- Se verifica el **SHA-256** de YOLO26s y de YOLO26m para asegurar que se compara contra los modelos correctos.
- El criterio de comparación (`MAX_PERDIDA_MAP`, `MAX_PERDIDA_RECALL`) es una sugerencia de partida, no un estándar: cámbialo **antes** de ver los resultados.

## Pasos

1. En la cuenta de Drive donde está el entrenamiento original debe existir:
   - `MyDrive/rdd2022_yolo26/final_full/best.pt` (YOLO26s)
   - `MyDrive/rdd2022_yolo26/manifest_full.csv`
   - `MyDrive/rdd2022_yolo26/runs/full_yolo26m/weights/best.pt` (YOLO26m del experimento anterior)
2. Abre el cuaderno en Colab con GPU T4 y ejecuta las celdas **en orden** (el dataset se vuelve a descargar al disco de Colab; tarda).
3. El entrenamiento puede tardar hasta unas 4 h. Si Colab se corta, usa la celda de reanudar.
4. Lee la comparación de validación (apartados 16 a 20). En el apartado 18, los umbrales de YOLO26m deben coincidir con los del experimento anterior (0,15 / 0,19 / 0,11 / 0,15).
5. Cuando ya no vayas a tocar parámetros, pon `EJECUTAR_TEST = True` y ejecuta esa celda **una sola vez**.
6. Copia los `best.pt` a `models/` de tu PC y mide la velocidad real:

   ```powershell
   python entrenamiento/yolo26m/medir_velocidad_cpu.py --modelos models/best.pt models/best_yolo26m.pt models/best_yolo26n.pt --imagenes C:\ruta\a\fotos --n 60
   ```

## Más de un modelo en la aplicación

Cada modelo necesita su propio `PERFIL_SENSIBLE` (el cuaderno imprime el de YOLO26m y el de YOLO26n): los umbrales de un modelo **no** sirven para otro. Las descripciones que vea el usuario deben usar solo cifras medidas (validación de RDD2022 y velocidad en CPU).

## Resultados medidos

Todo en RDD2022. Validación y prueba: 2100 imágenes cada una; la prueba se evaluó una sola vez, con umbrales elegidos en validación.

| | YOLO26s | YOLO26n | YOLO26m |
|---|---|---|---|
| Épocas en 4 h (mejor época) | 47 (36) | 55 (51) | 24 (24) |
| mAP50-95, validación / prueba | 0,337 / 0,353 | 0,322 / 0,346 | 0,341 / 0,362 |
| Recall medio sensible, validación / prueba | 0,684 / 0,695 | 0,657 / 0,666 | 0,698 / 0,714 |
| Precisión media sensible, prueba | 0,500 | 0,498 | 0,506 |
| CPU del autor, ms por imagen (rango de 3 corridas) | 108–120 | 58–71 | 239–281 |
| `best.pt` | 20,3 MB | 5,5 MB | 44,0 MB |

Umbrales del perfil sensible de YOLO26n (grieta longitudinal, transversal, piel de cocodrilo, bache): 0,17 / 0,18 / 0,12 / 0,15.

**Lectura:** YOLO26n es 1,7 a 2,0 veces más rápido en CPU y pierde recall de forma consistente en validación (−0,026) y prueba (−0,029), sobre todo en baches (recall sensible en prueba 0,542 frente a 0,584 de YOLO26s). La pérdida de mAP50-95 (−0,016 en validación, −0,006 en prueba) es de tamaño parecido a la diferencia entre validación y prueba de un mismo modelo.

**Evidencia en esta carpeta:** `entrenar_y_comparar_yolo26n_ejecutado.ipynb` (cuaderno con todas sus salidas), `curva_validacion.csv` y `curva_validacion.png` (mAP, precisión y recall por época, reconstruidos del registro de salida del cuaderno). Curvas precisión–recall de los tres modelos: `../comparacion/curvas_precision_recall_tres_modelos.png`.

## Límites

- Todo se mide sobre RDD2022 (Japón, India, Chequia, EE. UU., China-moto), **no sobre carreteras de Ecuador**.
- Los ms del cuaderno son de la GPU de Colab; la velocidad que importa es la de `medir_velocidad_cpu.py` en tu equipo.
- Los modelos de Ultralytics se distribuyen bajo AGPL-3.0; revisa las implicaciones si ofreces el sistema como servicio.
