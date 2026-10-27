import os

# Ultralytics parchea PIL.Image.open y, ante un archivo no reconocible, intenta instalar
# paquetes con pip en pleno servidor. En una app web eso no debe ocurrir nunca.
os.environ.setdefault("YOLO_AUTOINSTALL", "False")
