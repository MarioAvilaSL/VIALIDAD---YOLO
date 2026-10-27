from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Perfil(BaseModel):
    """Parámetros de inferencia de un perfil de sensibilidad."""

    conf: float = Field(0.25, gt=0, lt=1)                 # umbral de confianza global
    conf_clase: dict[str, float] = Field(default_factory=dict)  # umbrales propios por clase (opcional)
    imgsz: int = Field(640, ge=320, le=1920)
    augment: bool = False                                  # TTA: más lento (~2-3x), puede ayudar o no

    def conf_para(self, clase: str) -> float:
        return self.conf_clase.get(clase, self.conf)

    def conf_minimo(self) -> float:
        return min([self.conf, *self.conf_clase.values()])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/vialidad"
    model_path: Path = Path("models/best.pt")
    storage_dir: Path = Path("storage")
    device: str = "cpu"
    max_upload_mb: int = 15
    max_pixels: int = 100_000_000
    timezone: str = "America/Guayaquil"
    preload_model: bool = True
    app_token: str = ""            # si no está vacío, /api y /media exigen la cookie de /acceso?t=TOKEN (ver security.py)

    # Perfiles de sensibilidad.
    # "normal": 0.25 (valor por defecto de Ultralytics).
    # "sensible": umbrales por clase MEDIDOS con el notebook de calibración sobre la validación de RDD2022
    # (exigiendo precisión >= 0.50 por clase) y confirmados en test. Se pueden sustituir con PERFIL_SENSIBLE en .env.
    perfil_normal: Perfil = Perfil(conf=0.25)
    perfil_sensible: Perfil = Perfil(
        conf=0.11,
        conf_clase={"longitudinal_crack": 0.16, "transverse_crack": 0.17, "alligator_crack": 0.11, "pothole": 0.14},
    )

    # Video
    max_video_mb: int = 500
    video_max_frames: int = 300       # límite por defecto de fotogramas analizados por video
    video_max_frames_cap: int = 6000  # máximo que el usuario puede pedir
    video_max_side: int = 1280        # los fotogramas se reducen a este lado máximo antes de analizar (y del video anotado)
    video_crf: int = 23               # calidad del video anotado (H.264): menor = mejor calidad y más peso
    video_top_frames: int = 8         # fotogramas "peores" que se conservan como imagen

    def resolved(self, p: Path) -> Path:
        return p if p.is_absolute() else BASE_DIR / p

    def perfil(self, nombre: str) -> Perfil:
        return self.perfil_sensible if nombre == "sensible" else self.perfil_normal


settings = Settings()
MODEL_FILE = settings.resolved(settings.model_path)
STORAGE = settings.resolved(settings.storage_dir)
