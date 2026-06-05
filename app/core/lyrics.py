"""
Lyrics parsing and cue lookup for synchronized LRC files.
"""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")
_META_RE = re.compile(r"^\[([A-Za-z]+):(.*)\]$")
_TOKEN_RE = re.compile(r"[\w\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+", re.UNICODE)
_LYRIC_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "cp932",
    "shift_jis",
    "gb18030",
)


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


@dataclass(frozen=True)
class LyricCue:
    """A single synchronized lyric cue, optionally with multiple stacked lines."""

    start_time: float
    lines: Tuple[str, ...]


@dataclass
class TrackLyrics:
    """Parsed lyrics plus lightweight cue navigation helpers."""

    source_path: str
    cues: List[LyricCue]
    metadata: Dict[str, str] = field(default_factory=dict)
    _cue_times: List[float] = field(init=False, repr=False)

    def __post_init__(self):
        self._cue_times = [cue.start_time for cue in self.cues]

    def active_index_at(self, position: float) -> int:
        """Return the active cue index for a playback position, or -1 if not started."""
        if not self._cue_times:
            return -1
        return bisect_right(self._cue_times, position) - 1


def _decode_lrc(raw: bytes) -> str:
    """Decode lyrics bytes with a small set of common encodings."""
    last_error: Optional[Exception] = None
    for encoding in _LYRIC_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return raw.decode("utf-8", errors="replace")


def _stem_tokens(stem: str) -> Tuple[str, ...]:
    normalized = stem.casefold().replace("_", " ").replace("-", " ")
    tokens = [token for token in _TOKEN_RE.findall(normalized) if token]
    return tuple(sorted(tokens))


def find_lyrics_file(audio_path: str) -> Optional[Path]:
    """Find the best matching .lrc file in the same folder as the audio file."""
    audio = Path(audio_path)
    if not audio.exists():
        return None

    exact_match = audio.with_suffix(".lrc")
    if exact_match.exists():
        return exact_match

    candidates = sorted(audio.parent.glob("*.lrc"))
    if not candidates:
        return None

    audio_tokens = set(_stem_tokens(audio.stem))
    if not audio_tokens:
        return candidates[0] if len(candidates) == 1 else None

    best_path: Optional[Path] = None
    best_score = 0.0
    for candidate in candidates:
        lyric_tokens = set(_stem_tokens(candidate.stem))
        if not lyric_tokens:
            continue
        if lyric_tokens == audio_tokens:
            return candidate
        overlap = len(audio_tokens & lyric_tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(audio_tokens), len(lyric_tokens))
        if score > best_score:
            best_score = score
            best_path = candidate

    if best_path and best_score >= 0.5:
        return best_path
    return best_path if len(candidates) == 1 and best_score > 0 else None


def parse_lrc_file(path: str) -> Optional[TrackLyrics]:
    """Parse an LRC file into grouped synchronized cues."""
    lyric_path = Path(path)
    if not lyric_path.exists():
        return None

    text = _decode_lrc(lyric_path.read_bytes())
    entries: List[Tuple[int, str]] = []
    metadata: Dict[str, str] = {}
    offset_ms = 0

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue

        meta_match = _META_RE.fullmatch(line)
        if meta_match and not _TIMESTAMP_RE.search(line):
            key = meta_match.group(1).strip().lower()
            value = _normalize_text(meta_match.group(2))
            metadata[key] = value
            if key == "offset":
                try:
                    offset_ms = int(value)
                except ValueError:
                    offset_ms = 0
            continue

        time_matches = list(_TIMESTAMP_RE.finditer(line))
        if not time_matches:
            continue

        content = _normalize_text(_TIMESTAMP_RE.sub("", line))
        if not content:
            continue

        for match in time_matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = (match.group(3) or "0").ljust(3, "0")[:3]
            timestamp_ms = minutes * 60_000 + seconds * 1_000 + int(fraction) + offset_ms
            entries.append((max(0, timestamp_ms), content))

    if not entries:
        return None

    entries.sort(key=lambda item: (item[0], item[1]))
    cues: List[LyricCue] = []
    current_time: Optional[int] = None
    current_lines: List[str] = []
    seen_lines = set()

    for timestamp_ms, content in entries:
        if current_time != timestamp_ms:
            if current_lines:
                cues.append(LyricCue(start_time=current_time / 1000.0, lines=tuple(current_lines)))
            current_time = timestamp_ms
            current_lines = []
            seen_lines = set()
        if content and content not in seen_lines:
            current_lines.append(content)
            seen_lines.add(content)

    if current_lines and current_time is not None:
        cues.append(LyricCue(start_time=current_time / 1000.0, lines=tuple(current_lines)))

    return TrackLyrics(source_path=str(lyric_path), cues=cues, metadata=metadata)
