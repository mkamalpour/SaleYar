@echo off
setlocal
cd /d "%~dp0"
set "PROJECT_PYTHON=G:\AnaConda\install\envs\ml\python.exe"
if exist "G:\AnaConda\install\condabin\conda.bat" (
 call "G:\AnaConda\install\condabin\conda.bat" activate "G:\AnaConda\install\envs\ml"
 if errorlevel 1 (
  echo Could not activate the assigned ml environment. Nothing was installed.
  exit /b 2
 )
)
if not exist "%PROJECT_PYTHON%" set "PROJECT_PYTHON=python"
set "GRADIO_ANALYTICS_ENABLED=False"
"%PROJECT_PYTHON%" -c "import runtime_setup; runtime_setup.configure_runtime(); import importlib.util, sys; names='numpy pandas sklearn fastapi gradio lightgbm'.split(); missing=[m for m in names if importlib.util.find_spec(m) is None]; loaded=[] if missing else [importlib.import_module(m) for m in names]; print('Missing packages: ' + ', '.join(missing) if missing else 'Required startup modules imported.'); sys.exit(bool(missing))"
if errorlevel 1 (
 echo SaleYar startup check failed. Assigned environment: ml.
 echo Activate conda ml and review README.md for dependencies. Nothing was installed.
 exit /b 2
)
if "%~1"=="--check" (
 "%PROJECT_PYTHON%" -c "import sys; print('Interpreter: ' + sys.executable); print('Python: ' + sys.version.split()[0])"
 echo Startup imports were checked; model assets and optional workflows need separate verification.
 exit /b 0
)
"%PROJECT_PYTHON%" run.py --mode owner %*
exit /b %errorlevel%
