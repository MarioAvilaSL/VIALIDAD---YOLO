"""Trabajos en segundo plano (análisis de video). Se guardan en memoria: si el servidor se reinicia, se pierden."""
import threading
import time
from pathlib import Path
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video")  # un video a la vez (CPU)
_lock = threading.Lock()
_jobs: dict[str, "Job"] = {}
MAX_JOBS = 30
TTL_S = 2 * 3600


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    estado: str = "en_cola"      # en_cola | procesando | listo | error | cancelado
    hechos: int = 0
    total: int = 0
    mensaje: str = ""
    resultado: dict | None = None
    error: str | None = None
    creado: float = field(default_factory=time.time)
    cancelar: threading.Event = field(default_factory=threading.Event)
    salida: Path | None = None   # archivo temporal de salida (video anotado) mientras el trabajo existe
    iniciado: float = 0.0
    adjuntos: dict[str, bytes] = field(default_factory=dict)  # recortes de hallazgos (modo solo analizar)

    def publico(self) -> dict:
        prog = (self.hechos / self.total) if self.total else None
        return {
            "id": self.id, "estado": self.estado, "hechos": self.hechos, "total": self.total,
            "progreso": None if prog is None else round(min(1.0, prog), 3),
            "mensaje": self.mensaje, "error": self.error,
            "transcurrido_s": round(time.time() - self.iniciado, 1) if self.iniciado else 0,
            "resultado": self.resultado if self.estado == "listo" else None,
        }


def _soltar(job: "Job") -> None:
    if job.salida:
        job.salida.unlink(missing_ok=True)
        job.salida = None
    job.adjuntos = {}


def _purge() -> None:
    ahora = time.time()
    for jid in [j for j, job in _jobs.items() if job.estado in ("listo", "error", "cancelado") and ahora - job.creado > TTL_S]:
        _soltar(_jobs.pop(jid))
    while len(_jobs) > MAX_JOBS:
        viejo = min((j for j in _jobs.values() if j.estado in ("listo", "error", "cancelado")),
                    key=lambda j: j.creado, default=None)
        if viejo is None:
            break
        _soltar(_jobs.pop(viejo.id))


def lanzar(fn) -> Job:
    """fn(job) hace el trabajo y devuelve el resultado (dict); las excepciones marcan el job como error."""
    job = Job()

    def run():
        if job.cancelar.is_set():
            job.estado = "cancelado"
            return
        job.estado = "procesando"
        job.iniciado = time.time()
        try:
            job.resultado = fn(job)
            job.estado = "listo"
        except Exception as e:  # noqa: BLE001 - se informa al usuario
            from .video import Cancelado
            if isinstance(e, Cancelado):
                job.estado, job.mensaje = "cancelado", "Análisis cancelado."
            else:
                job.estado = "error"
                job.error = str(e) if str(e) else e.__class__.__name__
            _soltar(job)

    with _lock:
        _purge()
        _jobs[job.id] = job
    _executor.submit(run)
    return job


def descartar(job: "Job") -> None:
    """Libera los archivos temporales de un trabajo ya terminado (o pendiente de cancelar)."""
    if job.estado in ("listo", "error", "cancelado"):
        _soltar(job)


def obtener(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)
