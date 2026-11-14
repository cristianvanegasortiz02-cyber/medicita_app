@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
set DJANGO_ALLOWED_HOSTS=*
echo.
echo Desde el otro dispositivo abre: http://TU-IP:8000/  (TU-IP = direccion IPv4 de abajo)
ipconfig | findstr /i "IPv4"
echo.
python manage.py runserver 0.0.0.0:8000
