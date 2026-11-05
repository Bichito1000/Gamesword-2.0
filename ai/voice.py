"""Voz: lectura de respuestas (pyttsx3 / SAPI5 de Windows) y reconocimiento (SpeechRecognition)."""
import queue
import re
import threading
from difflib import SequenceMatcher
from typing import Callable, Optional

from utils.helpers import normalize
from utils.logger import get_logger

log = get_logger("voice")

try:
    import pyttsx3
except Exception:  # noqa: BLE001
    pyttsx3 = None

try:
    import speech_recognition as sr
except Exception:  # noqa: BLE001
    sr = None


try:
    from faster_whisper import WhisperModel
except Exception:  # noqa: BLE001
    WhisperModel = None

WAKE = "gamesword"


class VoiceError(Exception):
    pass


def extract_after_wake(text: str) -> Optional[str]:
    """Si `text` empieza con «(oye/hey) Gamesword», devuelve lo que sigue ('' si no hay nada); si no, None."""
    words = normalize(text).split()
    for i in range(min(len(words), 4)):
        for span in (1, 2):
            cand = "".join(words[i:i + span])
            if cand and SequenceMatcher(None, cand, WAKE).ratio() >= 0.75:
                if all(w in ("oye", "hey", "ey", "ok", "okay", "hola", "buenas") for w in words[:i]):
                    return " ".join(words[i + span:])
    return None


def clean_for_speech(text: str, limit: int = 600) -> str:
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"^[\s•\-\*]+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


class VoiceEngine:
    def __init__(self, settings):
        self.settings = settings
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._mic_ok: Optional[bool] = None
        self._whisper = None
        self._whisper_size = None
        self._wake_thread: Optional[threading.Thread] = None
        self._wake_stop = threading.Event()

    # ----------------------------------------------------------- capacidades
    @property
    def tts_available(self) -> bool:
        return pyttsx3 is not None

    @property
    def stt_available(self) -> bool:
        if sr is None:
            return False
        if self._mic_ok is None:
            try:
                import pyaudio  # noqa: F401
                self._mic_ok = True
            except Exception:  # noqa: BLE001
                self._mic_ok = False
        return bool(self._mic_ok)

    @property
    def local_stt_available(self) -> bool:
        return WhisperModel is not None

    @property
    def engine(self) -> str:
        eng = self.settings.get("voice.stt_engine", "google")
        return "local" if eng == "local" and self.local_stt_available else "google"

    def missing_hint(self, which: str) -> str:
        if which == "local":
            return "Para el reconocimiento local instala: pip install faster-whisper"
        if which == "tts":
            return "Para la lectura de voz instala: pip install pyttsx3"
        return "Para el reconocimiento de voz instala: pip install SpeechRecognition PyAudio"

    # ------------------------------------------------------------------ TTS
    def speak(self, text: str) -> None:
        if not self.tts_available:
            return
        text = clean_for_speech(text)
        if not text:
            return
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._tts_loop, daemon=True, name="tts")
            self._worker.start()
        self._queue.put(text)

    def stop(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _tts_loop(self) -> None:
        # COM debe inicializarse en cada hilo que use SAPI5
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001
            try:
                import comtypes  # type: ignore
                comtypes.CoInitialize()
            except Exception:  # noqa: BLE001
                pass
        while True:
            text = self._queue.get()
            if text is None:
                return
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", int(self.settings.get("voice.rate", 185)))
                engine.setProperty("volume", float(self.settings.get("voice.volume", 0.9)))
                self._pick_voice(engine)
                engine.say(text)
                engine.runAndWait()
                engine.stop()
            except Exception:  # noqa: BLE001
                log.exception("Error al leer en voz alta")

    def _pick_voice(self, engine) -> None:
        lang = (self.settings.get("voice.language", "es-ES") or "es-ES").split("-")[0].lower()
        hints = {"es": ("spanish", "español", "espanol", "helena", "sabina", "pablo", "es-"),
                 "en": ("english", "zira", "david", "en-"), "ca": ("catal",), "fr": ("french", "fr-"),
                 "de": ("german", "de-"), "it": ("italian", "it-"), "pt": ("portug", "pt-")}.get(lang, (lang,))
        try:
            for v in engine.getProperty("voices"):
                blob = f"{v.name} {v.id} {getattr(v, 'languages', '')}".lower()
                if any(h in blob for h in hints):
                    engine.setProperty("voice", v.id)
                    return
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ STT
    def _load_whisper(self):
        size = self.settings.get("voice.whisper_model", "base")
        if self._whisper is None or self._whisper_size != size:
            log.info("Cargando modelo de voz local '%s' (la primera vez se descarga)", size)
            self._whisper = WhisperModel(size, device="cpu", compute_type="int8")
            self._whisper_size = size
        return self._whisper

    def _transcribe(self, recognizer, audio) -> str:
        """Convierte audio a texto con el motor elegido. Lanza VoiceError si no se entiende."""
        lang = self.settings.get("voice.language", "es-ES")
        if self.engine == "local":
            import numpy as np
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
            segments, _ = self._load_whisper().transcribe(
                samples, language=lang.split("-")[0], beam_size=1, vad_filter=True,
                initial_prompt="Oye Gamesword, ábreme Fortnite. ¿Cuántas horas he jugado?")
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if not text:
                raise VoiceError("No te he entendido. Prueba a hablar más cerca del micrófono.")
            return text
        try:
            return recognizer.recognize_google(audio, language=lang)
        except sr.UnknownValueError:
            raise VoiceError("No te he entendido. Prueba a hablar más cerca del micrófono.")
        except sr.RequestError:
            raise VoiceError("No se pudo contactar con el servicio de reconocimiento (¿sin conexión?).")

    def listen(self, timeout: int = 6, phrase_limit: int = 12) -> str:
        """Bloqueante: llamar desde un hilo. Motor «google» (en la nube) o «local» (faster-whisper)."""
        if not self.stt_available:
            raise VoiceError(self.missing_hint("stt"))
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        except sr.WaitTimeoutError:
            raise VoiceError("No he oído nada. Inténtalo de nuevo.")
        except OSError:
            raise VoiceError("No se encontró ningún micrófono disponible.")
        return self._transcribe(recognizer, audio)

    # ------------------------------------------------------- palabra de activación
    @property
    def wake_running(self) -> bool:
        return self._wake_thread is not None and self._wake_thread.is_alive()

    def start_wake(self, on_command: Callable[[str], None]) -> None:
        """Escucha «Oye Gamesword» de forma continua. Solo con el motor local: nada sale de tu PC."""
        if self.wake_running:
            return
        if self.engine != "local":
            raise VoiceError("La palabra de activación solo está disponible con el reconocimiento local "
                             "(así tu audio no se envía a ningún servidor). " + self.missing_hint("local"))
        if not self.stt_available:
            raise VoiceError(self.missing_hint("stt"))
        self._wake_stop.clear()
        self._wake_thread = threading.Thread(target=self._wake_loop, args=(on_command,), daemon=True, name="wake")
        self._wake_thread.start()

    def stop_wake(self) -> None:
        self._wake_stop.set()

    def _wake_loop(self, on_command: Callable[[str], None]) -> None:
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1.0)
                while not self._wake_stop.is_set():
                    try:
                        audio = recognizer.listen(source, timeout=2, phrase_time_limit=5)
                        heard = self._transcribe(recognizer, audio)
                    except (sr.WaitTimeoutError, VoiceError):
                        continue
                    rest = extract_after_wake(heard)
                    if rest is None:
                        continue
                    if not rest:      # solo dijo «Oye Gamesword»: escuchar la orden
                        try:
                            rest = self._transcribe(recognizer, recognizer.listen(source, timeout=5, phrase_time_limit=10))
                        except (sr.WaitTimeoutError, VoiceError):
                            continue
                    on_command(rest)
        except Exception:  # noqa: BLE001
            log.exception("La escucha de la palabra de activación se detuvo")
