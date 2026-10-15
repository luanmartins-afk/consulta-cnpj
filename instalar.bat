@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Consulta CNPJ - instalacao
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado.
    echo Instale o Python 3.12 em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" na instalacao.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente Python...
    py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar o ambiente Python.
        pause
        exit /b 1
    )
)

echo Instalando bibliotecas (pode levar alguns minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERRO] Falha ao instalar as bibliotecas. Verifique a internet.
    pause
    exit /b 1
)

rem Evita a pergunta de e-mail do Streamlit na primeira execucao
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo Instalacao concluida!
if exist "cnpj.duckdb" (
    echo O banco ja existe. Abra "Abrir Consulta CNPJ.bat".
) else (
    echo Proximo passo: baixe os dados da Receita e rode "montar_banco.bat".
)
pause
