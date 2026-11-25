@echo off
cd /d "%~dp0"
python -c "import aiohttp, webview, qrcode" 2>nul || python -m pip install -r requirements.txt
start "" pythonw app\pydrop.py
