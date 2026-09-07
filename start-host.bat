@echo off
REM Host web xem phim tren may nay (1 click) - tu mo cho may khac cung wifi
cd /d %~dp0
where python >nul 2>nul || (echo Cai Python 3.10+ truoc: https://www.python.org/downloads/ && pause && exit /b 1)
where ffmpeg >nul 2>nul || echo [WARN] Chua co ffmpeg (cat frame vision can) - tai: https://www.gyan.dev/ffmpeg/builds/
python -m pip install -q yt-dlp edge-tts 2>nul
set PYTHONIOENCODING=utf-8
set HOST=0.0.0.0
set PORT=7378
echo.
echo  Mo web: http://localhost:7378  (may khac cung wifi xem IP in ben duoi)
echo  Bam cho phep khi Windows Firewall hoi nhe!
echo.
start "" "http://localhost:7378"
python -u server.py
pause
