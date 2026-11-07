@echo off
cd /d "%~dp0"
python -c "import main; ok, msg = main.save_everything_to_git(); print(msg)"
pause
