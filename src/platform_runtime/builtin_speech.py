"""Offline operator speech backed by the packaged eSpeak NG runtime."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QSoundEffect


MAX_SPEECH_CHARACTERS = 256
ESPEAK_TIMEOUT_SECONDS = 10
DIGIT_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}
PHONETIC_WORDS = {
    "A": "Alpha", "B": "Bravo", "C": "Charlie", "D": "Delta",
    "E": "Echo", "F": "Foxtrot", "G": "Golf", "H": "Hotel",
    "I": "India", "J": "Juliett", "K": "Kilo", "L": "Lima",
    "M": "Mike", "N": "November", "O": "Oscar", "P": "Papa",
    "Q": "Quebec", "R": "Romeo", "S": "Sierra", "T": "Tango",
    "U": "Uniform", "V": "Victor", "W": "Whiskey", "X": "X ray",
    "Y": "Yankee", "Z": "Zulu",
}


def callsign_for_speech(callsign: str) -> str:
    """Expand a normalized amateur callsign with ITU phonetic words."""
    spoken: list[str] = []
    for character in callsign.strip().upper():
        if character.isalpha():
            spoken.append(PHONETIC_WORDS[character])
        elif character in DIGIT_WORDS:
            spoken.append(DIGIT_WORDS[character])
        elif character == "/":
            spoken.append("stroke")
        elif character == "-":
            spoken.append("dash")
    return " ".join(spoken)


def _runtime_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(Path(sys.executable).resolve().parent)
    return tuple(dict.fromkeys(roots))


def locate_espeak_runtime() -> tuple[Path, Path | None]:
    """Return the packaged executable and optional parent of espeak-ng-data."""
    executable_names = ("espeak-ng.exe",) if sys.platform == "win32" else ("espeak-ng",)
    for root in _runtime_roots():
        runtime = root / "espeak"
        for name in executable_names:
            executable = runtime / name
            if executable.is_file():
                data = runtime / "espeak-ng-data"
                return executable, runtime if data.is_dir() else None
    system_executable = shutil.which("espeak-ng")
    if system_executable:
        return Path(system_executable), None
    raise FileNotFoundError("packaged eSpeak NG runtime was not found")


class EspeakSynthesizer:
    """Render bounded text to WAV without invoking a shell or audio device."""

    def __init__(self, executable: Path | None = None,
                 data_parent: Path | None = None) -> None:
        self.executable = Path(executable) if executable else None
        self.data_parent = Path(data_parent) if data_parent else None

    def synthesize_to(self, text: str, destination: Path) -> None:
        phrase = " ".join(text.split())
        if not phrase:
            raise ValueError("speech text contains no speakable characters")
        if len(phrase) > MAX_SPEECH_CHARACTERS:
            raise ValueError(
                f"speech text exceeds {MAX_SPEECH_CHARACTERS} characters"
            )
        executable, discovered_data = (
            (self.executable, self.data_parent)
            if self.executable else locate_espeak_runtime()
        )
        if executable is None or not executable.is_file():
            raise FileNotFoundError("eSpeak NG executable was not found")
        data_parent = self.data_parent or discovered_data
        command = [
            str(executable), "-v", "en-us", "-s", "155", "-p", "45",
            "-a", "175", "-w", str(destination),
        ]
        if data_parent is not None:
            command.append(f"--path={data_parent}")
        command.append(phrase)
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=ESPEAK_TIMEOUT_SECONDS,
            text=True,
        )
        if completed.returncode != 0 or not destination.is_file():
            detail = completed.stderr.strip()[:240] or "rendering failed"
            raise RuntimeError(f"eSpeak NG {detail}")


class BuiltinSpeechEngine(QObject):
    """Cache eSpeak output and play it through Qt's default output device."""

    error_received = Signal(str)

    def __init__(self, cache_directory: Path, parent=None,
                 synthesizer: EspeakSynthesizer | None = None) -> None:
        super().__init__(parent)
        self.cache_directory = Path(cache_directory)
        self.synthesizer = synthesizer or EspeakSynthesizer()
        self.effect = QSoundEffect(self)
        self.effect.setVolume(0.75)

    def speak(self, text: str) -> bool:
        try:
            phrase = " ".join(text.split())
            self.cache_directory.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:16]
            path = self.cache_directory / f"espeak-{key}.wav"
            if not path.exists():
                temporary = path.with_suffix(".wav.part")
                self.synthesizer.synthesize_to(phrase, temporary)
                temporary.replace(path)
            self.effect.setSource(QUrl.fromLocalFile(str(path)))
            self.effect.play()
            return True
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            self.error_received.emit(f"Speech announcement unavailable: {error}")
            return False
