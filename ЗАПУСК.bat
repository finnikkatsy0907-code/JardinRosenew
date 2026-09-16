@echo off
chcp 65001 >nul
REM Кодировка UTF-8 и для окна, и для вывода Python:
REM без этой строки русский текст в консоли превращается в кракозябры
set PYTHONIOENCODING=utf-8
title Jardin Rose - салон флористики

echo.
echo   ============================================
echo    JARDIN ROSE - запуск сайта салона
echo   ============================================
echo.

cd /d "%~dp0"

REM Проверяем, установлен ли Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   ОШИБКА: Python не найден.
    echo   Установите Python 3.10 или новее с python.org
    echo   и обязательно отметьте "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

REM Доустанавливаем библиотеки, если их нет
python -c "import flask, PIL" >nul 2>&1
if errorlevel 1 (
    echo   Устанавливаю библиотеки, это займёт минуту...
    python -m pip install -r requirements.txt
    echo.
)

echo   Сайт:            http://127.0.0.1:5000
echo   Заказы салона:   http://127.0.0.1:5000/admin
echo.
echo   Адрес для телефона появится ниже — откройте его в браузере
echo   телефона, подключённого к тому же Wi-Fi.
echo   Если Windows спросит про брандмауэр, нажмите "Разрешить доступ".
echo.
echo   Чтобы остановить сервер, закройте это окно
echo   или нажмите Ctrl+C.
echo.

python app.py

pause
