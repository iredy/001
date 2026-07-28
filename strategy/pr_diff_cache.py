"""PR diff summary cache keyed by repository, PR number and head SHA."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiffFileSummary:
    path: str
    additions: int
    deletions: int
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class DiffSummary:
    repo: str
    pr_number: int
    head_sha: str
    digest: str
    files: tuple[DiffFileSummary, ...]

    @property
    def changed_files(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.files)


class PRDiffSummaryCache:
    """Persist concise PR diff summaries and invalidate them on head SHA change."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, dict[str, object]] = {}
        if self.path.exists():
            self._items = json.loads(self.path.read_text(encoding="utf-8"))

    def key(self, repo: str, pr_number: int, head_sha: str) -> str:
        return f"pr:{repo}:{pr_number}:{head_sha}:diff_summary"

    def get(self, repo: str, pr_number: int, head_sha: str) -> DiffSummary | None:
        item = self._items.get(self.key(repo, pr_number, head_sha))
        if item is None:
            return None
        return _decode_summary(item)

    def set(self, summary: DiffSummary) -> None:
        self._items[self.key(summary.repo, summary.pr_number, summary.head_sha)] = _encode_summary(summary)
        self.path.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_or_create(self, repo: str, pr_number: int, head_sha: str, diff_text: str) -> DiffSummary:
        cached = self.get(repo, pr_number, head_sha)
        if cached is not None:
            return cached
        summary = summarize_unified_diff(repo, pr_number, head_sha, diff_text)
        self.set(summary)
        return summary


def summarize_unified_diff(repo: str, pr_number: int, head_sha: str, diff_text: str) -> DiffSummary:
    files: list[DiffFileSummary] = []
    current_path: str | None = None
    additions = 0
    deletions = 0
    bullets: list[str] = []

    def flush() -> None:
        nonlocal additions, deletions, bullets, current_path
        if current_path is None:
            return
        files.append(
            DiffFileSummary(
                path=current_path,
                additions=additions,
                deletions=deletions,
                bullets=tuple(bullets[:5]),
            )
        )
        additions = 0
        deletions = 0
        bullets = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            parts = line.split()
            current_path = parts[-1][2:] if len(parts) >= 4 and parts[-1].startswith("b/") else parts[-1]
            continue
        if current_path is None:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
            _append_bullet(bullets, "adds", line[1:])
        elif line.startswith("-"):
            deletions += 1
            _append_bullet(bullets, "removes", line[1:])

    flush()
    digest = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    return DiffSummary(repo=repo, pr_number=pr_number, head_sha=head_sha, digest=digest, files=tuple(files))


def _append_bullet(bullets: list[str], action: str, content: str) -> None:
    normalized = " ".join(content.strip().split())
    if normalized and len(bullets) < 5:
        bullets.append(f"{action}: {normalized[:120]}")


def _encode_summary(summary: DiffSummary) -> dict[str, object]:
    return {
        "repo": summary.repo,
        "pr_number": summary.pr_number,
        "head_sha": summary.head_sha,
        "digest": summary.digest,
        "files": [file.__dict__ | {"bullets": list(file.bullets)} for file in summary.files],
    }


def _decode_summary(data: dict[str, object]) -> DiffSummary:
    files = tuple(
        DiffFileSummary(
            path=str(item["path"]),
            additions=int(item["additions"]),
            deletions=int(item["deletions"]),
            bullets=tuple(str(bullet) for bullet in item.get("bullets", [])),
        )
        for item in data.get("files", [])  # type: ignore[union-attr]
    )
    return DiffSummary(
        repo=str(data["repo"]),
        pr_number=int(data["pr_number"]),
        head_sha=str(data["head_sha"]),
        digest=str(data["digest"]),
        files=files,
    )
