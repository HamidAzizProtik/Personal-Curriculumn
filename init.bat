@echo off
setlocal
cd /d "%~dp0"
set "VENV=%~dp0.venv\Scripts"

REM Create the virtualenv on a fresh checkout so `init.bat` just works.
if not exist "%VENV%\python.exe" (
    echo [init] Creating virtual environment...
    python -m venv "%~dp0.venv"
)

REM Ensure dependencies are present (idempotent; safe to re-run).
"%VENV%\python.exe" -c "import google.genai, matplotlib, numpy" >nul 2>&1
if errorlevel 1 (
    if exist "%~dp0requirements.txt" (
        "%VENV%\Scripts\pip.exe" install -r "%~dp0requirements.txt"
    ) else (
        echo [init] Dependencies missing and no requirements.txt found.
        echo [init] Install google-genai, matplotlib and numpy into the venv.
    )
)

"%VENV%\python.exe" "main.py" %*

REM Keep the window open in interactive use so errors / the finished session
REM are visible. In headless runs (TUTOR_HEADLESS set) we must NOT pause, or
REM the process hangs forever waiting for a keystroke.
if errorlevel 1 (
    echo [init] The tutor stopped with an error. See output above.
    if not defined TUTOR_HEADLESS ( pause )
) else (
    if not defined TUTOR_HEADLESS ( pause )
)
