from pathlib import Path


LAUNCHER = Path("run_lowcost_analysis.bat")


def test_lowcost_launcher_anchors_project_root_without_hardcoded_path():
    content = LAUNCHER.read_text()

    assert 'set "PROJECT_ROOT=%~dp0"' in content
    assert 'cd /d "%PROJECT_ROOT%"' in content
    assert 'set "PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%"' in content
    assert "C:\\Users\\Administrator\\clawd" not in content


def test_lowcost_launcher_requires_external_api_key_and_runs_existing_entrypoint():
    content = LAUNCHER.read_text()

    assert 'if "%SILICON_API_KEY%"==""' in content
    assert 'REM set "SILICON_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxx"' in content
    assert "python runsectoranalysis.py -sector kcb50" in content
    assert "SILICON_MODEL=Qwen/Qwen2.5-14B-Instruct" in content
