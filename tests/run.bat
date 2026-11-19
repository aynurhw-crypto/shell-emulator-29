@echo off
python -m unittest discover -s tests -p "test_*.py"
if %errorlevel% neq 0 exit /b %errorlevel%
python src/emulator.py %*
