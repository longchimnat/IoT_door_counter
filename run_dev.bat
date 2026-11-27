@echo off
REM Chay server dev tren Windows: bam dup file nay hoac go run_dev.bat
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "VPY=%~dp0.venv\Scripts\python.exe"

if exist "%VPY%" goto :venv_ok
echo [1/4] Tao moi truong ao .venv ...
where py >nul 2>nul
if errorlevel 1 goto :use_python
py -3 -m venv .venv
goto :venv_check
:use_python
python -m venv .venv
:venv_check
if not exist "%VPY%" (
  echo Khong tao duoc .venv - kiem tra da cai Python 3.10+ va tick "Add python.exe to PATH"
  goto :error
)
:venv_ok

echo [2/4] Cai thu vien ...
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -r requirements-dev.txt
if errorlevel 1 goto :error

if not exist .env (
  copy .env.example .env >nul
  echo      Da tao file .env tu .env.example
)

echo [3/4] Tao/cap nhat bang CSDL (alembic upgrade head) ...
"%VPY%" -m alembic upgrade head
if errorlevel 1 goto :error

echo [4/4] Khoi dong server: http://localhost:8000  (Swagger: /docs)  - Ctrl+C de dung
"%VPY%" -m server --reload
goto :eof

:error
echo.
echo *** Co loi, xem thong bao phia tren ***
pause
exit /b 1
