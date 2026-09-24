"""Search the local Markdown knowledge base without external services."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

MAX_QUERY_CHARS = 300
DEFAULT_RESULT_LIMIT = 4
MAX_RESULT_LIMIT = 8
_MAX_EXCERPT_CHARS = 260

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]+")
_ASCII_TERM_RE = re.compile(r"[a-z][a-z0-9_]{1,31}")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_LATEX_COMMAND_RE = re.compile(r"\\[a-zA-Z]+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_COMPACT_DROP_RE = re.compile(
    r"[\s`~!@#$%^&*()+=\[\]{}\\|;:',.<>/?\""
    r"\u3000-\u303f\uff01-\uff65]+"
)

_QUERY_STOP_PHRASES = (
    "请问",
    "帮我",
    "怎么",
    "如何",
    "什么",
    "是否",
    "一下",
    "这个",
    "这道",
    "题目",
    "问题",
    "the",
    "how",
    "what",
)

_TOPIC_EXPANSIONS = (
    (("derivative",), ("导数", "求导", "微分")),
    (("integral",), ("积分", "原函数")),
    (("limit",), ("极限", "洛必达")),
    (("series",), ("级数", "收敛")),
    (("differential equation",), ("微分方程", "通解", "特解")),
    (("gradient",), ("梯度", "方向导数")),
    (("partial derivative",), ("偏导数", "多元函数")),
    (("curl", "divergence", "flux"), ("旋度", "散度", "通量")),
)


@dataclass(frozen=True)
class KnowledgeSection:
    id: str
    source: str
    chapter: str
    title: str
    heading_path: tuple[str, ...]
    body: str
    normalized_title: str
    normalized_path: str
    normalized_body: str
    compact_title: str
    compact_path: str
    compact_body: str


@dataclass(frozen=True)
class KnowledgeSearchResult:
    id: str
    title: str
    chapter: str
    source: str
    heading_path: tuple[str, ...]
    excerpt: str
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "chapter": self.chapter,
            "source": self.source,
            "heading_path": list(self.heading_path),
            "excerpt": self.excerpt,
            "points": [self.excerpt],
            "score": self.score,
        }


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    for source, target in (
        ("\u2212", "-"),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2032", "'"),
    ):
        text = text.replace(source, target)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _compact_text(value: object) -> str:
    return _COMPACT_DROP_RE.sub("", normalize_text(value))


def _clean_markdown(value: str) -> str:
    text = _MARKDOWN_IMAGE_RE.sub(" ", value)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _LATEX_COMMAND_RE.sub(lambda match: f"{match.group(0)[1:]} ", text)
    text = text.replace("\\(", " ").replace("\\)", " ")
    text = text.replace("\\[", " ").replace("\\]", " ")
    text = text.replace("$$", " ").replace("$", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _iter_markdown_files(root: Path) -> Iterable[Path]:
    for directory_name in ("knowledge", "knowledge_tongji"):
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name.startswith("00_"):
                continue
            yield path


def _parse_markdown_file(
    path: Path,
    root: Path,
) -> list[KnowledgeSection]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []

    relative_source = path.relative_to(root).as_posix()
    sections: list[KnowledgeSection] = []
    heading_stack: list[tuple[int, str]] = []
    chapter = ""
    current_title = ""
    current_line = 0
    current_body: list[str] = []

    def flush_section() -> None:
        if not current_title:
            return
        body = _clean_markdown("\n".join(current_body))
        if not body:
            return
        heading_path = tuple(title for _, title in heading_stack)
        normalized_title = normalize_text(current_title)
        normalized_path = normalize_text(" ".join(heading_path))
        normalized_body = normalize_text(body)
        sections.append(
            KnowledgeSection(
                id=f"{path.stem}:{current_line}",
                source=relative_source,
                chapter=chapter or heading_path[0],
                title=current_title,
                heading_path=heading_path,
                body=body,
                normalized_title=normalized_title,
                normalized_path=normalized_path,
                normalized_body=normalized_body,
                compact_title=_compact_text(current_title),
                compact_path=_compact_text(" ".join(heading_path)),
                compact_body=_compact_text(body),
            )
        )

    for line_number, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match is None:
            if current_title:
                current_body.append(line)
            continue

        flush_section()
        level = len(match.group(1))
        title = _clean_markdown(match.group(2))
        heading_stack = [
            (item_level, item_title)
            for item_level, item_title in heading_stack
            if item_level < level
        ]
        heading_stack.append((level, title))
        if level == 1 and not chapter:
            chapter = title
        current_title = title
        current_line = line_number
        current_body = []

    flush_section()
    return sections


class KnowledgeBase:
    def __init__(self, root: str | Path | None = None):
        if root is None:
            root = Path(__file__).resolve().parents[1]
        self.root = Path(root).resolve()
        self.sections = tuple(
            section
            for path in _iter_markdown_files(self.root)
            for section in _parse_markdown_file(path, self.root)
        )

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def search(
        self,
        query: str,
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list[KnowledgeSearchResult]:
        normalized_query = normalize_text(query)
        if not normalized_query or not self.sections:
            return []

        safe_limit = max(1, min(int(limit), MAX_RESULT_LIMIT))
        units, exact_query = self._query_units(normalized_query)
        if not units and not exact_query:
            return []

        unit_weights = {
            unit: self._unit_weight(unit) * self._inverse_document_frequency(unit)
            for unit in units
        }
        total_weight = max(sum(unit_weights.values()), 1.0)
        scored: list[tuple[float, KnowledgeSection, tuple[str, ...]]] = []

        for section in self.sections:
            raw_score = 0.0
            matched_terms: list[str] = []

            if exact_query and len(exact_query) >= 3:
                if exact_query in section.compact_title:
                    raw_score += 34.0
                    matched_terms.append(exact_query)
                elif exact_query in section.compact_path:
                    raw_score += 17.0
                    matched_terms.append(exact_query)
                elif exact_query in section.compact_body:
                    raw_score += 8.0
                    matched_terms.append(exact_query)

            for unit in units:
                weight = unit_weights[unit]
                body_frequency = section.normalized_body.count(unit)
                in_title = unit in section.normalized_title
                in_path = unit in section.normalized_path
                if not in_title and not in_path and not body_frequency:
                    continue
                matched_terms.append(unit)
                if in_title:
                    raw_score += weight * 5.0
                elif in_path:
                    raw_score += weight * 2.5
                if body_frequency:
                    raw_score += weight * min(body_frequency, 3) * 0.8

            if not matched_terms:
                continue
            threshold = max(2.4, total_weight * 0.08)
            if raw_score < threshold:
                continue
            score = round(raw_score / total_weight * 100.0, 2)
            scored.append((raw_score, section, tuple(dict.fromkeys(matched_terms))))

        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].source,
                item[1].title,
            )
        )
        return [
            KnowledgeSearchResult(
                id=section.id,
                title=section.title,
                chapter=section.chapter,
                source=section.source,
                heading_path=section.heading_path,
                excerpt=self._select_excerpt(section.body, matched_terms),
                score=round(raw_score / total_weight * 100.0, 2),
            )
            for raw_score, section, matched_terms in scored[:safe_limit]
        ]

    def _query_units(self, normalized_query: str) -> tuple[set[str], str]:
        content_query = normalized_query
        for phrase in _QUERY_STOP_PHRASES:
            content_query = content_query.replace(phrase, " ")
        content_query = _WHITESPACE_RE.sub(" ", content_query).strip()
        expanded_query = f"{content_query} {normalized_query}"
        for triggers, expansions in _TOPIC_EXPANSIONS:
            if any(trigger in normalized_query for trigger in triggers):
                expanded_query += " " + " ".join(expansions)

        units: set[str] = set()
        for run in _CJK_RUN_RE.findall(expanded_query):
            if len(run) < 2:
                continue
            max_size = min(6, len(run))
            for size in range(2, max_size + 1):
                for start in range(0, len(run) - size + 1):
                    units.add(run[start:start + size])

        for term in _ASCII_TERM_RE.findall(expanded_query):
            if term not in _QUERY_STOP_PHRASES:
                units.add(term)

        exact_query = _compact_text(content_query)
        return units, exact_query

    def _unit_weight(self, unit: str) -> float:
        if _CJK_RUN_RE.fullmatch(unit):
            return float(len(unit) ** 1.55)
        return max(2.0, min(6.0, float(len(unit))))

    def _inverse_document_frequency(self, unit: str) -> float:
        document_frequency = sum(
            1
            for section in self.sections
            if unit in section.normalized_title
            or unit in section.normalized_path
            or unit in section.normalized_body
        )
        return 1.0 + math.log(
            (self.section_count + 1) / (document_frequency + 1)
        )

    @staticmethod
    def _select_excerpt(body: str, matched_terms: tuple[str, ...]) -> str:
        candidates = [
            candidate.strip()
            for candidate in re.split(r"(?<=[。！？!?；;])\s*", body)
            if candidate.strip()
        ]
        if not candidates:
            return ""

        def candidate_score(candidate: str) -> int:
            normalized = normalize_text(candidate)
            return sum(
                min(normalized.count(term), 2) * len(term)
                for term in matched_terms
            )

        excerpt = max(candidates, key=candidate_score)
        if len(excerpt) <= _MAX_EXCERPT_CHARS:
            return excerpt
        return excerpt[: _MAX_EXCERPT_CHARS - 1].rstrip() + "\u2026"


@lru_cache(maxsize=1)
def _default_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()


def search_knowledge(
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> list[KnowledgeSearchResult]:
    return _default_knowledge_base().search(query, limit=limit)
