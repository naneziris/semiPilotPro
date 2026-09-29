@echo off
rem Run semipilot straight from this download on Windows - no pip, no pipx.
rem Needs Python 3.9+ (the py launcher or python on PATH). Add this bin\ folder to PATH.
set "SEMIPILOT_SRC=%~dp0..\src"
if defined PYTHONPATH (set "PYTHONPATH=%SEMIPILOT_SRC%;%PYTHONPATH%") else (set "PYTHONPATH=%SEMIPILOT_SRC%")
where py >nul 2>&1
if %errorlevel%==0 (py -3 -m semipilot %*) else (python -m semipilot %*)
