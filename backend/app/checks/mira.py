"""MIRA v1 (SAGEA AI, Apache-2.0) decision model: "which of these answers fits this text best?"

How it works (from the model card): every option is paired with the state as
"state [SEP] option", the encoder reads each pair, and the `scorer` head gives one number per
option; dividing by a temperature and applying softmax gives calibrated probabilities.
Temperatures per question type come from the model's own calibrators.json.

- MiraModel   : the loaded model; choice() and batch() (several questions in ONE forward pass).
- MiraService : loads the model in the background at server start, runs every call in one worker
                thread with a time limit, and raises MiraUnavailable on timeout/error so the
                check can continue without MIRA (checks_skipped=["mira"]).
The message text is only ever used as the state, never as an option (prompt-injection safety)."""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

from .model_lock import LOAD_LOCK

log = logging.getLogger("checkscam.mira")

# Backend flow B5: the owner's prompt is ~900-1,500 tokens (full WHOIS + two examples), so pairs may be long.
# A pair longer than this keeps the start and the end of the state (the question) and the whole option; only the
# middle of the state is dropped (see _fit), so an answer option is never cut off.
MAX_TOKENS = 4096
KEEP_END_TOKENS = 200  # the end of a too-long state that is always kept (the question asked)


class MiraUnavailable(Exception):
    """reason: disabled | loading | failed | timeout | error"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Question:
    state: str
    options: list[str]
    kind: str = "plain"  # calibration type: plain | hard-synonym | negation | score | noul | not-answerable


@dataclass
class MiraAnswer:
    probabilities: dict[str, float]
    top: str
    top_probability: float
    not_sure: bool
    abstain_probability: float | None = None  # model's own abstain head (information only for now)
    ms: float = 0.0
    extra: dict = field(default_factory=dict)


class MiraModel:
    """The loaded model. Build with MiraModel.load(...) or pass parts directly (tests)."""

    def __init__(self, tokenizer, encoder, heads: dict, temperatures: dict[str, float], version: str,
                 not_sure_below: float = 0.5, chunk_size: int = 8):
        import torch  # imported here so the rest of the backend never needs torch

        self._torch = torch
        self.tokenizer = tokenizer
        self.encoder = encoder
        self.scorer_w = heads["scorer"]["weight"]
        self.scorer_b = heads["scorer"].get("bias")
        self.abstain = heads.get("abstain")
        self.temperatures = temperatures
        self.version = version
        self.not_sure_below = not_sure_below
        self.chunk_size = chunk_size  # pairs per forward pass, grouped by length (0 = one big batch)

    @classmethod
    def load(cls, model_id: str, revision: str, cache_dir: str | None = None, local_only: bool = True,
             not_sure_below: float = 0.5) -> "MiraModel":
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModel, AutoTokenizer

        kw = {"revision": revision, "cache_dir": cache_dir or None, "local_files_only": local_only}
        tokenizer = AutoTokenizer.from_pretrained(model_id, **kw)
        encoder = AutoModel.from_pretrained(model_id, **kw).eval()
        heads = torch.load(hf_hub_download(model_id, "heads.pt", **kw), map_location="cpu", weights_only=True)
        try:
            with open(hf_hub_download(model_id, "calibrators.json", **kw), encoding="utf-8") as f:
                temperatures = json.load(f).get("temperatures", {})
        except Exception:  # calibration file is optional
            temperatures = {}
        return cls(tokenizer, encoder, heads, temperatures, f"{model_id.split('/')[-1]}@{revision[:7]}", not_sure_below)

    def _encode(self, texts: list[str]):
        """Encodes all pairs. Pairs are sorted by length and run in small chunks, so short pairs are not
        padded up to the longest one (padding made a batch ~2x slower on the laptop CPU).
        The result rows are in the original order; the numbers are the same as one big batch."""
        torch = self._torch
        if self.chunk_size <= 0 or len(texts) <= self.chunk_size:
            inputs = self.tokenizer(texts, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            return self.encoder(**inputs).last_hidden_state[:, 0]
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        parts = []
        for start in range(0, len(order), self.chunk_size):
            idx = order[start:start + self.chunk_size]
            inputs = self.tokenizer([texts[i] for i in idx], padding=True, truncation=True,
                                    max_length=MAX_TOKENS, return_tensors="pt")
            parts.append(self.encoder(**inputs).last_hidden_state[:, 0])
        sorted_hidden = torch.cat(parts)
        hidden = torch.empty_like(sorted_hidden)
        hidden[torch.tensor(order)] = sorted_hidden
        return hidden

    def _fit(self, state: str, option: str) -> str:
        """The state, shortened in the middle if state + option would be longer than MAX_TOKENS."""
        encode = getattr(self.tokenizer, "encode", None)
        if encode is None:  # simple test tokenizers
            return state
        ids = encode(state, add_special_tokens=False)
        room = MAX_TOKENS - len(encode(option, add_special_tokens=False)) - 8  # [CLS], [SEP]s, " ... "
        if len(ids) <= room:
            return state
        keep_end = min(KEEP_END_TOKENS, room // 2)
        head, tail = ids[:room - keep_end], ids[-keep_end:]
        log.info("MIRA state cut in the middle: %d -> %d tokens", len(ids), room)
        return f"{self.tokenizer.decode(head)} ... {self.tokenizer.decode(tail)}"

    def temperature(self, kind: str) -> float:
        return float(self.temperatures.get(kind, self.temperatures.get("plain", 1.0)))

    def batch(self, questions: list[Question]) -> list[MiraAnswer]:
        """All questions in one forward pass: every (state, option) pair becomes one row."""
        torch = self._torch
        texts, spans = [], []
        for q in questions:
            if not q.options:
                raise ValueError("a question needs at least one option")
            start = len(texts)
            texts += [f"{self._fit(q.state, opt)} [SEP] {opt}" for opt in q.options]
            spans.append((start, len(texts)))
        t0 = time.perf_counter()
        with torch.inference_mode():
            hidden = self._encode(texts)  # first-token vector per pair
            scores = (hidden @ self.scorer_w.T).squeeze(-1)
            abstain = None
            if self.abstain is not None:
                abstain = torch.sigmoid((hidden @ self.abstain["weight"].T).squeeze(-1) + self.abstain["bias"])
        ms = (time.perf_counter() - t0) * 1000

        answers = []
        for q, (a, b) in zip(questions, spans):
            probs = (scores[a:b] / self.temperature(q.kind)).softmax(-1).tolist()
            pmap = {opt: round(float(p), 4) for opt, p in zip(q.options, probs)}
            top = max(pmap, key=pmap.get)
            answers.append(MiraAnswer(
                probabilities=pmap,
                top=top,
                top_probability=pmap[top],
                not_sure=pmap[top] < self.not_sure_below,
                abstain_probability=round(float(abstain[a:b].mean()), 4) if abstain is not None else None,
                ms=ms,
            ))
        return answers

    def choice(self, state: str, options: list[str], kind: str = "plain") -> MiraAnswer:
        return self.batch([Question(state, options, kind)])[0]


class MiraService:
    """Owns the model for the running server: background loading, one worker thread, time limit."""

    def __init__(self, loader, timeout: float = 3.0, enabled: bool = True, warmup=None):
        self._loader = loader  # callable returning a MiraModel
        self.warmup = warmup  # optional callable(model): one practice call before "ready" (first calls are slow)
        self.timeout = timeout
        self.enabled = enabled
        self.model: MiraModel | None = None
        self.status = "disabled" if not enabled else "not_started"  # not_started | loading | ready | failed
        self.error: str | None = None
        self.load_seconds: float | None = None
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mira")  # one model call at a time
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def version(self) -> str | None:
        return self.model.version if self.model else None

    def start_loading(self, background: bool = True) -> None:
        with self._lock:
            if not self.enabled or self.status in ("loading", "ready"):
                return
            self.status = "loading"
        if background:
            threading.Thread(target=self._load, name="mira-load", daemon=True).start()
        else:
            self._load()

    def _load(self) -> None:
        t0 = time.perf_counter()
        try:
            with LOAD_LOCK:  # never at the same time as the trained model (see model_lock.py)
                self.model = self._loader()
            if self.warmup is not None:
                try:
                    t1 = time.perf_counter()
                    self.warmup(self.model)
                    log.info("MIRA warm-up done in %.1f s", time.perf_counter() - t1)
                except Exception as exc:  # a failed warm-up never blocks MIRA
                    log.warning("MIRA warm-up failed: %s", type(exc).__name__)
            self.load_seconds = round(time.perf_counter() - t0, 1)
            self.status = "ready"
            log.info("MIRA loaded (%s) in %.1f s", self.model.version, self.load_seconds)
        except Exception as exc:
            self.error = type(exc).__name__
            self.status = "failed"
            log.exception("MIRA failed to load: %s", self.error)

    def batch(self, questions: list[Question]) -> list[MiraAnswer]:
        if not self.enabled:
            raise MiraUnavailable("disabled")
        if self.status != "ready" or self.model is None:
            raise MiraUnavailable("loading" if self.status in ("loading", "not_started") else "failed")
        future = self._worker.submit(self.model.batch, questions)
        try:
            return future.result(timeout=self.timeout)
        except FutureTimeout:
            log.warning("MIRA took longer than %.1f s", self.timeout)
            raise MiraUnavailable("timeout") from None
        except Exception as exc:
            log.error("MIRA call failed: %s", type(exc).__name__)
            raise MiraUnavailable("error") from None

    def choice(self, state: str, options: list[str], kind: str = "plain") -> MiraAnswer:
        return self.batch([Question(state, options, kind)])[0]
