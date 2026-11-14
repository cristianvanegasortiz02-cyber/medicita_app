@echo off
cd /d "%~dp0"
echo === Instalando MediCita ===
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations usuarios citas
python manage.py migrate
python manage.py cargar_datos_demo
echo.
echo Instalacion terminada. Para encender la aplicacion usa iniciar.bat
pause
