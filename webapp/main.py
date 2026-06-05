import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webapp.engine import TTSEngine
from webapp.store import VoiceStore

DATA_DIR = os.environ.get("DATA_DIR", "webapp/data")
MODEL_NAME = os.environ.get("MODEL_NAME", "k2-fsa/OmniVoice")

engine: Optional[TTSEngine] = None
store: Optional[VoiceStore] = None
_model_error: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _rebuild_prompt(sample: dict) -> None:
    """Build (or rebuild) the cached VoiceClonePrompt for a sample."""
    if engine is None:
        return
    try:
        await asyncio.to_thread(
            engine.build_prompt,
            sample["id"],
            sample["audio_path"],
            sample["transcript"],
        )
    except Exception as e:
        print(f"[prompt] build failed for '{sample['name']}': {e}")


async def _ensure_prompt(sample_id: str) -> dict:
    """Return the sample and guarantee its prompt is cached; raise 404/500 on failure."""
    sample = store.get_sample(sample_id)
    if sample is None:
        raise HTTPException(404, "Không tìm thấy giọng mẫu")
    if not engine.has_prompt(sample_id):
        try:
            await asyncio.to_thread(
                engine.build_prompt,
                sample["id"],
                sample["audio_path"],
                sample["transcript"],
            )
        except Exception as e:
            raise HTTPException(500, f"Không thể tải giọng mẫu: {e}")
    return sample


# ── Startup ───────────────────────────────────────────────────────────────────


async def _load_model() -> None:
    global engine, _model_error
    try:
        engine = await asyncio.to_thread(TTSEngine, MODEL_NAME)
        for sample in store.list_samples():
            await _rebuild_prompt(sample)
    except Exception as e:
        _model_error = str(e)
        print(f"[startup] Model load failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    store = VoiceStore(DATA_DIR)
    asyncio.create_task(_load_model())
    yield


# ── App ───────────────────────────────────────────────────────────────────────


app = FastAPI(title="OmniVoice TTS", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse("webapp/static/index.html")


@app.get("/api/health")
def health():
    if _model_error:
        return {"status": "error", "detail": _model_error}
    return {"status": "ready" if engine is not None else "loading"}


# ── Voice samples ─────────────────────────────────────────────────────────────


@app.get("/api/samples")
def list_samples():
    return store.list_samples()


@app.post("/api/samples", status_code=201)
async def add_sample(
    name: str = Form(...),
    transcript: str = Form(...),
    audio: UploadFile = File(...),
):
    audio_bytes = await audio.read()
    sample = store.add_sample(name, audio_bytes, transcript)
    await _rebuild_prompt(sample)
    return sample


class UpdateBody(BaseModel):
    name: Optional[str] = None
    transcript: Optional[str] = None


@app.put("/api/samples/{sample_id}")
async def update_sample(sample_id: str, body: UpdateBody):
    sample = store.update_sample(sample_id, name=body.name, transcript=body.transcript)
    if sample is None:
        raise HTTPException(404, "Không tìm thấy giọng mẫu")
    if engine and body.transcript is not None:
        engine.invalidate_prompt(sample_id)
        await _rebuild_prompt(sample)
    return sample


@app.put("/api/samples/{sample_id}/audio")
async def replace_audio(sample_id: str, audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    sample = store.replace_audio(sample_id, audio_bytes)
    if sample is None:
        raise HTTPException(404, "Không tìm thấy giọng mẫu")
    if engine:
        engine.invalidate_prompt(sample_id)
    await _rebuild_prompt(sample)
    return sample


@app.delete("/api/samples/{sample_id}")
def delete_sample(sample_id: str):
    if not store.delete_sample(sample_id):
        raise HTTPException(404, "Không tìm thấy giọng mẫu")
    if engine:
        engine.invalidate_prompt(sample_id)
    return {"ok": True}


@app.post("/api/samples/{sample_id}/default")
def set_default(sample_id: str):
    if not store.set_default(sample_id):
        raise HTTPException(404, "Không tìm thấy giọng mẫu")
    return {"ok": True}


@app.get("/api/samples/{sample_id}/audio")
def get_sample_audio(sample_id: str):
    sample = store.get_sample(sample_id)
    if sample is None:
        raise HTTPException(404, "Không tìm thấy giọng mẫu")
    path = Path(sample["audio_path"])
    if not path.exists():
        raise HTTPException(404, "File âm thanh không tồn tại")
    return FileResponse(str(path))


# ── TTS generation ────────────────────────────────────────────────────────────


class GenerateBody(BaseModel):
    text: str
    sample_id: Optional[str] = None
    speed: float = 0.9


@app.post("/api/generate")
async def generate(body: GenerateBody):
    if engine is None:
        raise HTTPException(503, "Mô hình chưa sẵn sàng, vui lòng đợi")
    if not body.text.strip():
        raise HTTPException(400, "Văn bản không được để trống")

    sample_id = body.sample_id
    if not sample_id:
        default = store.get_default_sample()
        if default is None:
            raise HTTPException(400, "Chưa có giọng mẫu nào. Vui lòng thêm giọng mẫu trước.")
        sample_id = default["id"]

    await _ensure_prompt(sample_id)

    try:
        wav_bytes = await asyncio.to_thread(
            engine.generate_wav_bytes, body.text.strip(), sample_id, body.speed
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Lỗi tạo âm thanh: {e}")

    return Response(content=wav_bytes, media_type="audio/wav")
