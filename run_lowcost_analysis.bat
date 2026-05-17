@echo off
setlocal EnableExtensions

REM ==================================================
REM  1. Anchor execution to this repository root.
REM     Double-clicking from any folder still runs runsectoranalysis.py here.
REM ==================================================
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%"

REM ==================================================
REM  2. Inject the low-cost SiliconFlow channel without changing OpenClaw code.
REM     Prefer setting SILICON_API_KEY in Windows System/User Environment
REM     Variables.  You can also uncomment the next line for a local-only test.
REM ==================================================
REM set "SILICON_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxx"

if "%SILICON_API_KEY%"=="" (
    echo [ERROR] SILICON_API_KEY is not set.
    echo Set it in Windows Environment Variables or edit this launcher locally.
    echo This file intentionally does not commit any real API key.
    pause
    exit /b 1
)

REM ==================================================
REM  3. Optional cheap model hint.  This does not alter code routing; it only
REM     supplies an environment value for frameworks that already read it.
REM ==================================================
if "%SILICON_MODEL%"=="" set "SILICON_MODEL=Qwen/Qwen2.5-14B-Instruct"

REM Keep Python import/runtime behavior deterministic.
set "PYTHONUTF8=1"

echo ===============================================
echo     Low-cost analysis environment is ready
echo     Project root: %CD%
echo     SiliconFlow model hint: %SILICON_MODEL%
echo ===============================================

python runsectoranalysis.py -sector kcb50
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] runsectoranalysis.py failed with exit code %EXIT_CODE%.
    echo Check that this launcher is located in the same folder as runsectoranalysis.py.
)

pause
exit /b %EXIT_CODE%
