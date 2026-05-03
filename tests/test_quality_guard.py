import ast

from tools.quality_guard import _check_bare_except, _check_hardcoded_sys_path_insert


def test_detects_bare_except():
    tree = ast.parse("""
try:
    x = 1
except:
    x = 2
""")
    findings = _check_bare_except(tree, "x.py")
    assert len(findings) == 1
    assert findings[0].rule == "bare_except"


def test_detects_hardcoded_sys_path_insert():
    tree = ast.parse("""
import sys
sys.path.insert(0, r'C:\\Users\\Administrator\\clawd')
""")
    findings = _check_hardcoded_sys_path_insert(tree, "x.py")
    assert len(findings) == 1
    assert findings[0].rule == "hardcoded_sys_path"


def test_detects_exception_without_alias():
    tree = ast.parse("""
try:
    x = 1
except Exception:
    x = 2
""")
    findings = _check_bare_except(tree, "x.py")
    assert len(findings) == 1
    assert findings[0].rule == "exception_without_alias"
