@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Consulta CNPJ - montar banco de dados
echo ============================================
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Rode primeiro o "instalar.bat".
    pause
    exit /b 1
)
echo Feche outros programas pesados antes de continuar (Chrome, AutoCAD...).
echo O processo leva cerca de 40 minutos.
echo.
set /p DADOS=Cole o caminho da pasta com os .zip da Receita e tecle Enter:
set DADOS=%DADOS:"=%
".venv\Scripts\python.exe" build.py "%DADOS%"
echo.
if exist "cnpj.duckdb" (echo Pronto! Abra "Abrir Consulta CNPJ.bat".) else (echo [ERRO] O banco nao foi criado. Veja a mensagem acima.)
pause
