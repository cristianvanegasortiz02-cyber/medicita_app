@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
python manage.py test -v 2
pause
