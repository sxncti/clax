@echo off
setlocal
where py.exe >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%~dp0clax.py" %*
exit /b %errorlevel%
:try_python
where python.exe >nul 2>nul
if errorlevel 1 goto missing_python
python.exe "%~dp0clax.py" %*
exit /b %errorlevel%
:missing_python
echo Erro: Python 3 nao foi encontrado. Instale Python 3.10 ou mais recente. 1>&2
exit /b 127
