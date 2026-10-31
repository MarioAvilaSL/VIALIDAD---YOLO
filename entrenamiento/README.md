# Entrenamiento del modelo

Evidencia del entrenamiento de **YOLO26s** sobre **RDD2022** (4 clases: `longitudinal_crack`, `transverse_crack`, `alligator_crack`, `pothole`). Todo lo que aparece aquí proviene de los archivos de esta carpeta (salida real del entrenamiento en Google Colab).

## Contenido

| Carpeta | Archivo | Qué es |
|---|---|---|
| `configuracion/` | `args.yaml` | Hiperparámetros exactos que usó Ultralytics (corrida `full_yolo26s-2`). |
| `configuracion/` | `run_info.json` | Metadatos de la corrida: versiones, GPU, reparto del dataset, cajas por clase, métricas val/test y SHA-256 de `best.pt`. |
| `resultados/` | `results.csv` | Métricas y pérdidas por época (47 épocas). |
| `graficas/` | `results.png` | Curvas de entrenamiento y validación. |
| `graficas/` | `confusion_matrix.png`, `confusion_matrix_normalized.png` | Matriz de confusión (conteos y normalizada). |
| `graficas/` | `BoxP_curve.png`, `BoxR_curve.png`, `BoxF1_curve.png` | Precisión, recall y F1 frente a la confianza. |
| `graficas/` | `labels.jpg` | Distribución de las etiquetas del dataset. |
| `notebooks/` | `rdd2022_yolo26_colab_full2.ipynb` | Notebook de entrenamiento y evaluación (Colab). |
| `notebooks/` | `calibracion_sensibilidad_3.ipynb` | Notebook de calibración del perfil "sensible". |

Los pesos (`best.pt`, 20,3 MB) están en `models/`.

## Configuración del entrenamiento

| Parámetro | Valor |
|---|---|
| Modelo base | `yolo26s.pt` (preentrenado) |
| Tamaño de imagen | 640 |
| Batch | -1 (automático) |
| Épocas solicitadas | 100, pero `time: 4.0` (horas) tiene prioridad y detuvo el entrenamiento en la época 47 |
| Paciencia | 20 |
| `close_mosaic` | 3 |
| Optimizador | `auto` · `lr0` 0.01 · `lrf` 0.01 · momentum 0.937 · weight decay 0.0005 |
| Aumentos | mosaic 1.0 · fliplr 0.5 · HSV 0.015/0.7/0.4 · translate 0.1 · scale 0.5 · randaugment · erasing 0.4 |
| `cls_pw` | 0.0 |
| Semilla | 0 (determinista) |
| AMP | sí |
| GPU | Tesla T4 (Colab) |
| Versiones | Ultralytics 8.4.184 · torch 2.11.0+cu130 |

## Datos

- 20 826 imágenes: 16 626 train, 2 100 val, 2 100 test.
- Países usados: Japan, India, Czech, United_States, China_MotorBike.
- Cajas de entrenamiento por clase: longitudinal 12 823, transversal 7 021, piel de cocodrilo 7 884, bache 4 870.

## Resultados

Métricas oficiales de Ultralytics sobre el mejor modelo (`best.pt`):

| Conjunto | Precisión | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Validación | 0.672 | 0.602 | 0.660 | 0.337 |
| Prueba (test) | 0.692 | 0.597 | 0.665 | 0.353 |

Lo que muestra `results.csv`:

- Se completaron **47 épocas** en 4.006 h (`time` del CSV: 240.4 min a la última época; `run_info.json` registra 241.45 min en total).
- El **mejor modelo corresponde a la época 36** (mayor fitness `0.1·mAP50 + 0.9·mAP50-95`): mAP50 0.660 y mAP50-95 0.337.
- La suma de las pérdidas de validación (box + cls + l1) es mínima en la época 35.
- Entre la época 36 y la 47, mAP50 baja de 0.660 a 0.645 y mAP50-95 de 0.337 a 0.330: el modelo dejó de mejorar al final del entrenamiento, por lo que se conservó el de la época 36.

## Verificar que los pesos son los mismos

```bash
sha256sum models/best.pt
# esperado: 59e030a042fa97d8e1da8de5dd989e94e1c47227de795a89f827def471ba8d88
```

## Reproducir

1. Abre `notebooks/rdd2022_yolo26_colab_full2.ipynb` en Google Colab con GPU.
2. Verifica que la celda 3 tenga `MODE = "full"` y ejecuta las celdas en orden (descarga de RDD2022, conversión a YOLO, división sin fuga de datos, entrenamiento, evaluación en val y test).
3. El tiempo límite de 4 h puede dar un número de épocas distinto según la GPU asignada.

## Limitaciones

- RDD2022 no incluye vías de Ecuador; el desempeño en campo local no está medido.
- El mAP50-95 (0.35 en test) indica que la localización fina de las cajas es moderada; por eso el sistema usa un índice de severidad propio como ayuda de priorización, no como diagnóstico normativo.
