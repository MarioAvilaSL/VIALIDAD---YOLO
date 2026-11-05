# Experimento: YOLO26m frente a YOLO26s

> Rama `experimental`. Es un experimento: **no cambia el modelo de la aplicación** hasta que los resultados lo justifiquen.

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

## Límites

- Todo se mide sobre RDD2022 (Japón, India, Chequia, EE. UU., China-moto), **no sobre carreteras de Ecuador**.
- Los ms del cuaderno son de la GPU de Colab; la velocidad que importa es la que da `medir_velocidad_cpu.py` en tu equipo.
- Los resultados de este experimento aún no existen: este README describe el método, no una conclusión.
- Los modelos de Ultralytics se distribuyen bajo AGPL-3.0; revisa las implicaciones si ofreces el sistema como servicio.
