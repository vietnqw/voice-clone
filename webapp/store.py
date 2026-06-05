import io
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from pydub import AudioSegment


def _to_wav_bytes(raw: bytes) -> bytes:
    """Convert any audio format to WAV bytes via pydub/ffmpeg."""
    seg = AudioSegment.from_file(io.BytesIO(raw))
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


class VoiceStore:
    def __init__(self, data_dir: str = "webapp/data"):
        self._dir = Path(data_dir)
        self._audio_dir = self._dir / "audio"
        self._json_path = self._dir / "voices.json"
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        if not self._json_path.exists():
            self._write({"samples": []})
        self._migrate_to_wav()

    def _migrate_to_wav(self) -> None:
        """Convert any pre-existing non-WAV audio files to WAV in-place."""
        data = self._read()
        changed = False
        for s in data["samples"]:
            old_path = Path(s["audio_path"])
            if old_path.suffix.lower() == ".wav" or not old_path.exists():
                continue
            print(f"[store] Migrating {old_path.name} → WAV…")
            try:
                wav_bytes = _to_wav_bytes(old_path.read_bytes())
                new_path = old_path.with_suffix(".wav")
                new_path.write_bytes(wav_bytes)
                old_path.unlink()
                s["audio_path"] = str(new_path)
                changed = True
                print(f"[store] Migrated {old_path.name} → {new_path.name}")
            except Exception as e:
                print(f"[store] Migration failed for {old_path.name}: {e}")
        if changed:
            self._write(data)

    def _read(self) -> dict:
        return json.loads(self._json_path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self._json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def list_samples(self) -> list[dict]:
        with self._lock:
            return self._read()["samples"]

    def get_sample(self, sample_id: str) -> dict | None:
        return next((s for s in self.list_samples() if s["id"] == sample_id), None)

    def get_default_sample(self) -> dict | None:
        samples = self.list_samples()
        return next((s for s in samples if s.get("is_default")), samples[0] if samples else None)

    def add_sample(self, name: str, audio_bytes: bytes, transcript: str) -> dict:
        sample_id = str(uuid.uuid4())
        wav_bytes = _to_wav_bytes(audio_bytes)
        audio_path = self._audio_dir / f"{sample_id}.wav"
        audio_path.write_bytes(wav_bytes)
        sample = {
            "id": sample_id,
            "name": name,
            "audio_path": str(audio_path),
            "transcript": transcript,
            "is_default": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        with self._lock:
            data = self._read()
            if not data["samples"]:
                sample["is_default"] = True
            data["samples"].append(sample)
            self._write(data)
        return sample

    def update_sample(
        self,
        sample_id: str,
        name: str | None = None,
        transcript: str | None = None,
    ) -> dict | None:
        with self._lock:
            data = self._read()
            for s in data["samples"]:
                if s["id"] == sample_id:
                    if name is not None:
                        s["name"] = name
                    if transcript is not None:
                        s["transcript"] = transcript
                    self._write(data)
                    return s
        return None

    def replace_audio(self, sample_id: str, audio_bytes: bytes) -> dict | None:
        wav_bytes = _to_wav_bytes(audio_bytes)
        with self._lock:
            data = self._read()
            for s in data["samples"]:
                if s["id"] == sample_id:
                    old = Path(s["audio_path"])
                    if old.exists():
                        old.unlink()
                    new_path = self._audio_dir / f"{sample_id}.wav"
                    new_path.write_bytes(wav_bytes)
                    s["audio_path"] = str(new_path)
                    self._write(data)
                    return s
        return None

    def delete_sample(self, sample_id: str) -> bool:
        with self._lock:
            data = self._read()
            for i, s in enumerate(data["samples"]):
                if s["id"] == sample_id:
                    was_default = s.get("is_default", False)
                    audio = Path(s["audio_path"])
                    if audio.exists():
                        audio.unlink()
                    data["samples"].pop(i)
                    if was_default and data["samples"]:
                        data["samples"][0]["is_default"] = True
                    self._write(data)
                    return True
        return False

    def set_default(self, sample_id: str) -> bool:
        with self._lock:
            data = self._read()
            found = False
            for s in data["samples"]:
                s["is_default"] = s["id"] == sample_id
                if s["is_default"]:
                    found = True
            if found:
                self._write(data)
            return found
