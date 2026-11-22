"""The owner's trained MIRA (fine-tuned in Google Colab on the owner's data set): message text -> chance of scam.

It is MIRA's encoder with a scam / not-scam head (ModernBertForSequenceClassification), saved with save_pretrained
into D:/checkscam/models/<name>/ (the folder holding config.json may sit one level deeper - it is found). It reads
the original message text, as in training, and answers in ~0.1-0.3 s on the laptop CPU (MIRA's long prompt: 30-70 s).

temperature T makes the score more graded: softmax(logits / T). T = 1 gives mostly 0% / 100%; T = 3 gives e.g. 92%
for a clear scam and 2-5% for a normal message. The decision (above / below 50%) never changes with T.

Like MiraService: loads in the background at server start (plus one warm-up call), runs in one worker thread with a
time limit, and raises ClassifierUnavailable instead of crashing - the check then falls back to the MIRA prompt."""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from .model_lock import LOAD_LOCK

log = logging.getLogger("checkscam.classifier")
MAX_TOKENS = 256  # as in training


class ClassifierUnavailable(Exception):
    """reason: not_found | loading | failed | timeout | error"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def find_model_dir(path: Path | str) -> Path | None:
    """The folder with config.json: `path` itself or one folder below it (a zip unpacked into its own folder)."""
    p = Path(path)
    if (p / "config.json").is_file():
        return p
    if p.is_dir():
        for sub in sorted(p.iterdir()):
            if sub.is_dir() and (sub / "config.json").is_file():
                return sub
    return None


class ScamClassifier:
    def __init__(self, path: Path | str, timeout: float = 15.0, loader=None):
        self.path = Path(path)
        self.model_dir = find_model_dir(self.path)
        self.timeout = timeout
        self._loader = loader or self._load_from_disk  # tests pass a fake
        self.model = None
        self.tokenizer = None
        self.status = "not_found" if self.model_dir is None else "not_started"  # loading | ready | failed
        self.error: str | None = None
        self.load_seconds: float | None = None
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="classifier")
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def version(self) -> str | None:
        """e.g. "checkscam-mira-ft" (the model folder's name)."""
        return self.model_dir.name if self.model_dir else None

    @property
    def labels(self) -> dict:
        try:
            return json.loads((self.model_dir / "config.json").read_text(encoding="utf-8")).get("id2label", {})
        except (OSError, ValueError, AttributeError):
            return {}

    def start_loading(self, background: bool = True) -> None:
        with self._lock:
            if self.status not in ("not_started", "failed"):
                return
            self.status = "loading"
        if background:
            threading.Thread(target=self._load, name="classifier-load", daemon=True).start()
        else:
            self._load()

    def _load_from_disk(self):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # heavy: only when loading

        tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(self.model_dir).eval()
        return tokenizer, model

    def _load(self) -> None:
        t0 = time.perf_counter()
        try:
            with LOAD_LOCK:  # never at the same time as MIRA (see model_lock.py)
                self.tokenizer, self.model = self._loader()
            self._scam_logits("Hello, how are you?")  # warm-up: the first call is several seconds slower
            self.load_seconds = round(time.perf_counter() - t0, 1)
            self.status = "ready"
            log.info("Trained model loaded (%s) in %.1f s", self.version, self.load_seconds)
        except Exception as exc:  # noqa: BLE001 - a missing / broken model must never stop the server
            self.error = type(exc).__name__
            self.status = "failed"
            log.exception("Trained model failed to load: %s", self.error)

    def _scam_logits(self, text: str):
        import torch

        with torch.inference_mode():
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=MAX_TOKENS)
            return self.model(**inputs).logits[0]

    def probability(self, text: str, temperature: float = 3.0) -> float:
        """Chance (0-1) that `text` is a scam."""
        if self.status != "ready":
            raise ClassifierUnavailable({"loading": "loading", "failed": "failed"}.get(self.status, self.status))
        future = self._worker.submit(self._probability, text, max(0.1, float(temperature)))
        try:
            return future.result(timeout=self.timeout)
        except FutureTimeout:
            log.warning("Trained model took longer than %.1f s", self.timeout)
            raise ClassifierUnavailable("timeout") from None
        except Exception as exc:  # noqa: BLE001
            log.warning("Trained model failed: %s", type(exc).__name__)
            raise ClassifierUnavailable("error") from None

    def _probability(self, text: str, temperature: float) -> float:
        import torch

        logits = self._scam_logits(text)
        return float(torch.softmax(logits / temperature, -1)[1])
