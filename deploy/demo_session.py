"""In-memory conversation state for the public demo."""

from __future__ import annotations

from dataclasses import dataclass
import re
import threading
import time


WAITING_IMAGE = "waiting_image"
AWAITING_OCR_CONFIRMATION = "awaiting_ocr_confirmation"
SOLVING = "solving"

OCR_FAILURE_MESSAGE = (
    "识别请求失败/未识别到有效题目，请重新上传清晰完整题目图片"
)
NO_PENDING_QUESTION_MESSAGE = (
    "我还没识别出具体要计算的内容。请把题目、条件和要求写清楚；"
    "图片题可以先识别，再回复“确认”继续。"
)

_SESSION_TTL_SECONDS = 30 * 60
_MAX_SESSIONS = 500
_FAILURE_TEXT_PATTERN = re.compile(
    r"(?:ocr\s*(?:error|failed|failure)|识别失败|识别错误|无法识别|"
    r"未识别|没有识别|无有效内容|内容为空|空结果|请求失败|超时|"
    r"识别可能不准确|可能不准确|重新上传|请上传清晰|清晰完整|"
    r"看不清|不清晰|无法辨认|未检测到题目|图中没有题目)",
    re.IGNORECASE,
)
_USEFUL_TEXT_PATTERN = re.compile(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(frozen=True)
class DemoSessionSnapshot:
    state: str
    pending_question: str
    updated_at: float


class DemoSessionStore:
    """Small thread-safe state store suitable for one PythonAnywhere worker."""

    def __init__(self, ttl_seconds: float, max_sessions: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._lock = threading.RLock()
        self._sessions: dict[str, DemoSessionSnapshot] = {}

    def get(self, session_id: str) -> DemoSessionSnapshot:
        with self._lock:
            self._prune_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return DemoSessionSnapshot(WAITING_IMAGE, "", time.time())
            return session

    def remember_ocr_question(self, session_id: str, question: str) -> None:
        cleaned = str(question).strip()
        if not is_valid_ocr_question(cleaned):
            raise ValueError("OCR question is not valid")
        with self._lock:
            self._prune_locked()
            self._set_locked(session_id, AWAITING_OCR_CONFIRMATION, cleaned)

    def mark_ocr_failure(self, session_id: str) -> None:
        with self._lock:
            self._prune_locked()
            self._set_locked(session_id, WAITING_IMAGE, "")

    def begin_solving(self, session_id: str) -> str:
        with self._lock:
            self._prune_locked()
            session = self._sessions.get(session_id)
            if (
                session is None
                or session.state != AWAITING_OCR_CONFIRMATION
                or not is_valid_ocr_question(session.pending_question)
            ):
                return ""
            self._set_locked(session_id, SOLVING, session.pending_question)
            return session.pending_question

    def finish_solving(self, session_id: str) -> None:
        with self._lock:
            self._set_locked(session_id, WAITING_IMAGE, "")

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _set_locked(self, session_id: str, state: str, question: str) -> None:
        self._sessions.pop(session_id, None)
        self._sessions[session_id] = DemoSessionSnapshot(
            state=state,
            pending_question=question,
            updated_at=time.time(),
        )
        while len(self._sessions) > self._max_sessions:
            oldest_session_id = min(
                self._sessions,
                key=lambda key: self._sessions[key].updated_at,
            )
            self._sessions.pop(oldest_session_id, None)

    def _prune_locked(self) -> None:
        now = time.time()
        for session_id, session in list(self._sessions.items()):
            if now - session.updated_at > self._ttl_seconds:
                self._sessions.pop(session_id, None)


def is_valid_ocr_question(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 3 or len(text) > 600:
        return False
    if _FAILURE_TEXT_PATTERN.search(text):
        return False
    if not _USEFUL_TEXT_PATTERN.search(text):
        return False
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        return False
    replacement_count = text.count("\ufffd")
    if replacement_count and replacement_count / len(text) > 0.15:
        return False
    return True


demo_sessions = DemoSessionStore(
    ttl_seconds=_SESSION_TTL_SECONDS,
    max_sessions=_MAX_SESSIONS,
)
