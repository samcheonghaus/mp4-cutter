@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "import imageio_ffmpeg" 2>nul || pip install -r requirements.txt
start "" pythonw mp4cutter.py %*
