import io
import os
import threading

import numpy as np
import soundfile as sf
import torch

# Reduces fragmentation so the second+ generation can reuse reserved pages
# instead of failing with OOM when only contiguous blocks are needed.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from omnivoice import OmniVoice, OmniVoiceGenerationConfig
from omnivoice.models.omnivoice import VoiceClonePrompt


class TTSEngine:
    def __init__(self, model_name: str = "k2-fsa/OmniVoice"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        print(f"[TTS] Loading model '{model_name}' on {device} ({dtype})...")
        self.model = OmniVoice.from_pretrained(
            model_name,
            device_map=device,
            dtype=dtype,
        )
        # Move audio tokenizer to CPU to save ~1 GB VRAM on the 4 GB card.
        # The encode/decode paths already use self.audio_tokenizer.device
        # to move tensors, so this is safe.
        if device == "cuda" and self.model.audio_tokenizer is not None:
            self.model.audio_tokenizer = self.model.audio_tokenizer.to("cpu")
            print("[TTS] Audio tokenizer moved to CPU (VRAM optimisation).")
        print("[TTS] Model loaded.")
        self._prompt_cache: dict[str, VoiceClonePrompt] = {}
        self._gen_lock = threading.Lock()
        self._base_gen_config = OmniVoiceGenerationConfig(
            num_step=32,
            guidance_scale=2.0,
            class_temperature=0.1,   # small non-zero → natural variation instead of robotic greedy
            postprocess_output=True,
            audio_chunk_threshold=30.0,
            audio_chunk_duration=15.0,
        )

    def build_prompt(self, sample_id: str, audio_path: str, transcript: str) -> None:
        print(f"[TTS] Building prompt for sample {sample_id}...")
        prompt = self.model.create_voice_clone_prompt(audio_path, ref_text=transcript)
        self._prompt_cache[sample_id] = prompt
        print(f"[TTS] Prompt cached for sample {sample_id}.")

    def has_prompt(self, sample_id: str) -> bool:
        return sample_id in self._prompt_cache

    def invalidate_prompt(self, sample_id: str) -> None:
        self._prompt_cache.pop(sample_id, None)

    @staticmethod
    def _free_cuda_cache() -> None:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate_wav_bytes(self, text: str, sample_id: str, speed: float = 0.9) -> bytes:
        if sample_id not in self._prompt_cache:
            raise ValueError(
                "Giọng mẫu chưa được tải. Vui lòng chờ hoặc thử thêm lại giọng mẫu."
            )
        prompt = self._prompt_cache[sample_id]
        with self._gen_lock:
            self._free_cuda_cache()
            try:
                results = self.model.generate(
                    text=text,
                    language="vi",
                    voice_clone_prompt=prompt,
                    speed=speed,
                    generation_config=self._base_gen_config,
                )
            finally:
                self._free_cuda_cache()
        audio: np.ndarray = results[0]
        buf = io.BytesIO()
        sf.write(buf, audio, self.model.sampling_rate, format="WAV")
        return buf.getvalue()
