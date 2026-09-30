from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexReport:
    root: str
    status: str
    indexed: int
    unchanged: int
    removed: int
    skipped: int
    errors: tuple[str, ...]
    text_enabled: bool


@dataclass(frozen=True, slots=True)
class SearchHit:
    root: str
    path: str
    name: str
    size_bytes: int
    modified_ns: int
    content_status: str
    match: str
    snippet: str | None
    indexed_at: str
    scan_status: str
