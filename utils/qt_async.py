"""Ejecutar funciones en segundo plano y devolver el resultado al hilo de la interfaz."""
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from .logger import get_logger

log = get_logger("async")


class _Dispatcher(QObject):
    """Vive en el hilo principal; ejecuta callbacks que llegan desde otros hilos."""
    invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self.invoke.connect(self._run)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("Error en callback del hilo principal")


_dispatcher: Optional[_Dispatcher] = None


def init_async() -> None:
    """Debe llamarse una vez desde el hilo principal (tras crear QApplication)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _Dispatcher()


def call_in_main(fn: Callable) -> None:
    if _dispatcher is None:
        raise RuntimeError("init_async() no se ha llamado")
    _dispatcher.invoke.emit(fn)


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs, on_done, on_error):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.on_done, self.on_error = on_done, on_error

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("Tarea en segundo plano fallida: %s", exc)
            if self.on_error:
                call_in_main(lambda e=exc: self.on_error(e))
            return
        if self.on_done:
            call_in_main(lambda r=result: self.on_done(r))


def run_async(fn: Callable, on_done: Optional[Callable] = None,
              on_error: Optional[Callable] = None, *args, **kwargs) -> None:
    QThreadPool.globalInstance().start(_Task(fn, args, kwargs, on_done, on_error))
