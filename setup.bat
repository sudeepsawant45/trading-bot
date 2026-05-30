@echo off
echo ================================================
echo   NSE Trading Bot v2.0 - Windows Setup
echo ================================================
echo.

echo [1/4] Checking Python...
python --version
if errorlevel 1 (echo ERROR: Python not found & pause & exit /b 1)

echo.
echo [2/4] Installing libraries...
pip install -r requirements.txt
if errorlevel 1 (echo ERROR: Install failed & pause & exit /b 1)

echo.
echo [3/4] Creating config...
if not exist .env (
    copy .env.example .env
    echo Created .env — edit it with your capital amount
) else (
    echo .env already exists
)

echo.
echo [4/4] Running tests...
python main.py test

echo.
echo ================================================
echo   Setup Complete!
echo ================================================
echo.
echo Next: python main.py backtest
echo.
pause
