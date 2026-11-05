# Experimento: YOLO26m frente a YOLO26s

> Experimento con resultados medidos (abajo). La aplicación ofrece YOLO26m como opción «más precisa»; el modelo predeterminado sigue siendo YOLO26s.

## Qué responde

¿Un modelo más grande (YOLO26m) detecta mejor los daños que el YOLO26s actual, y a qué costo de velocidad?

## Qué hay aquí

| Archivo | Para qué sirve |
|---|---|
| `entrenar_y_comparar_yolo26m.ipynb` | Cuaderno de Google Colab (GPU T4). Reconstruye los mismos train/val/test de la Fase 4, entrena YOLO26m y compara con YOLO26s. |
| `medir_velocidad_cpu.py` | Se ejecuta en **tu computador**: mide los ms por imagen de cada modelo en tu CPU. |

## Cómo se garantiza una comparación justa

- **Mismos datos.** El cuaderno reconstruye el dataset con el mismo código de la Fase 4 y se detiene si las imágenes de train, val o test no coinciden con `manifest_full.csv`.
- **Mismos hiperparámetros.** Se toman del `args.yaml` de `full_yolo26s-2`; solo cambia el modelo (`yolo26m.pt`).
- **Mismo presupuesto de tiempo (4 h).** Esto significa que YOLO26m hará **menos épocas** que las 47 de YOLO26s y puede quedar sub-entrenado. El cuaderno lo avisa si la mejor época está entre las últimas. Si ocurre, la comparación favorece a YOLO26s y debe decirse en el informe.
- **Mismo evaluador** para ambos modelos, con verificación cruzada contra `model.val()` de Ultralytics y contra lo medido en el entrenamiento de YOLO26s.
- **Umbrales elegidos solo con validación; test se mira una sola vez** (la celda de test está desactivada hasta que pongas `EJECUTAR_TEST = True`).
- Se verifica el **SHA-256** del `best.pt` de YOLO26s para asegurar que se compara contra el modelo correcto.

## Pasos

1. Abre el cuaderno en Colab, activa GPU T4 y ejecuta las celdas **en orden**. Necesita en tu Drive `MyDrive/rdd2022_yolo26/final_full/best.pt` y `manifest_full.csv`.
2. El entrenamiento tarda unas 4 h. Si Colab se corta, usa la celda de reanudar.
3. Lee la tabla de validación y la celda de **decisión** (los criterios `MIN_GANANCIA_*` son una sugerencia: cámbialos *antes* de ver resultados).
4. Cuando ya no vayas a tocar nada, pon `EJECUTAR_TEST = True` y ejecuta esa celda **una sola vez**.
5. Copia `best.pt` de YOLO26m a `models/best_yolo26m.pt` en tu PC y mide la velocidad:

   ```powershell
   python entrenamiento/yolo26m/medir_velocidad_cpu.py --modelos models/best.pt models/best_yolo26m.pt --imagenes C:\ruta\a\fotos --n 60
   ```

6. Decide con las dos cosas juntas: precisión (cuaderno) y velocidad (tu CPU).

## Si decides adoptar YOLO26m

En el `.env`:

```
MODEL_PATH=models/best_yolo26m.pt
PERFIL_SENSIBLE=<la línea que imprime el cuaderno para YOLO26m>
```

**Los umbrales del perfil sensible de YOLO26s no sirven para YOLO26m**: cada modelo necesita los suyos. Reinicia el servidor después de cambiar el `.env`. El análisis en vivo envía ~1 fotograma por segundo: si YOLO26m tarda cerca de 1 s por imagen en tu CPU, no podrá seguir el ritmo.

## Resultados medidos

Todo en RDD2022. Validación y prueba: 2100 imágenes cada una; la prueba se evaluó una sola vez, con umbrales elegidos en validación.

| | YOLO26s | YOLO26m |
|---|---|---|
| Épocas en 4 h (mejor época) | 47 (36) | 24 (24) |
| mAP50-95, validación / prueba | 0,337 / 0,353 | 0,341 / 0,362 |
| Recall medio sensible, validación / prueba | 0,684 / 0,695 | 0,698 / 0,714 |
| Precisión media sensible, prueba | 0,500 | 0,506 |
| CPU del autor, ms por imagen (rango de 3 corridas) | 108–120 | 239–281 |
| `best.pt` | 20,3 MB | 44,0 MB |

Umbrales del perfil sensible de YOLO26m (grieta longitudinal, transversal, piel de cocodrilo, bache): 0,15 / 0,19 / 0,11 / 0,15.

**Lectura:** YOLO26m mejora poco (+0,004 de mAP50-95 en validación, +0,009 en prueba) y es 2,1 a 2,3 veces más lento en CPU. La diferencia es menor que la que hay entre validación y prueba de un mismo modelo y no se midió la variación entre semillas, así que no es concluyente. Terminó en su mejor época (la 24): con más tiempo podría haber mejorado, pero no se puede afirmar.

**Evidencia en esta carpeta:** `entrenar_y_comparar_yolo26m_ejecutado.ipynb` (cuaderno con todas sus salidas), `curva_validacion.csv` y `curva_validacion.png` (reconstruidos del registro de salida del cuaderno), y `velocidad_cpu.csv` si lo añadiste. Comparación de los tres modelos: `../yolo26n/README.md`.

## Límites

- Todo se mide sobre RDD2022 (Japón, India, Chequia, EE. UU., China-moto), **no sobre carreteras de Ecuador**.
- Los ms del cuaderno son de la GPU de Colab; la velocidad que importa es la que da `medir_velocidad_cpu.py` en tu equipo.
- Los modelos de Ultralytics se distribuyen bajo AGPL-3.0; revisa las implicaciones si ofreces el sistema como servicio.
