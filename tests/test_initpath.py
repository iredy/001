import sys

import initpath


def test_project_root_inserted_once():
    root = str(initpath.PROJECT_ROOT)
    assert root in sys.path
    assert sys.path.count(root) == 1
