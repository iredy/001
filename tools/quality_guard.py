"""Static guardrails for common reliability anti-patterns."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class Finding:
    path: str
    lineno: int
    rule: str
    detail: str


def _is_python_file(path: Path) -> bool:
    return path.suffix == ".py" and ".git" not in path.parts and "__pycache__" not in path.parts


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if _is_python_file(path):
            yield path


def _check_bare_except(tree: ast.AST, rel_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            findings.append(
                Finding(rel_path, node.lineno, "bare_except", "Use `except Exception as exc` with logging/context")
            )
            continue
        if isinstance(node.type, ast.Name) and node.type.id == "Exception" and node.name is None:
            findings.append(
                Finding(rel_path, node.lineno, "exception_without_alias", "Use `except Exception as exc` for traceability")
            )
    return findings


def _check_hardcoded_sys_path_insert(tree: ast.AST, rel_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "insert":
            continue
        base = node.func.value
        if not isinstance(base, ast.Attribute) or base.attr != "path":
            continue
        if not isinstance(base.value, ast.Name) or base.value.id != "sys":
            continue
        if len(node.args) < 2:
            continue
        arg = node.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            value = arg.value.lower()
            if ":\\" in value or value.startswith("/"):
                findings.append(
                    Finding(rel_path, node.lineno, "hardcoded_sys_path", "Use project-relative imports or PYTHONPATH")
                )
    return findings


def run_checks(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_python_files(root):
        rel_path = str(path.relative_to(root))
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as exc:
            findings.append(Finding(rel_path, 1, "parse_error", str(exc)))
            continue

        findings.extend(_check_bare_except(tree, rel_path))
        findings.extend(_check_hardcoded_sys_path_insert(tree, rel_path))
    return findings


def main() -> int:
    root = Path.cwd()
    findings = run_checks(root)
    if findings:
        for f in findings:
            print(f"{f.path}:{f.lineno} [{f.rule}] {f.detail}")
        return 1
    print("quality_guard: no findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
