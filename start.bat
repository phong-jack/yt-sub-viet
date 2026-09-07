@echo off
REM Xem phim tren chinh may nay (localhost only - khong mo mang)
cd /d %~dp0
where python >nul 2>nul || (echo Cai Python 3.10+ truoc: https://www.python.org/downloads/ && pause && exit /b 1)
python -m pip install -q yt-dlp edge-tts 2>nul
set PYTHONIOENCODING=utf-8
echo.
echo  Mo web: http://127.0.0.1:7378  (chi may nay xem duoc)
echo.
start "" "http://127.0.0.1:7378"
python -u server.py
pause
