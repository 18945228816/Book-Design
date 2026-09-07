@echo off
chcp 65001 >nul
echo ========================================
echo   重启后端服务
echo ========================================
echo.

:: 查找并关闭正在运行的 uvicorn 进程（book_design 相关）
echo [1/3] 检查正在运行的后端服务...
set "found=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    set "found=1"
    set "pid=%%a"
)

if "%found%"=="1" (
    echo     发现正在运行的后端服务，PID: %pid%
    echo     正在关闭...
    taskkill /F /PID %pid% >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo     已关闭
) else (
    echo     未发现正在运行的后端服务
)

echo.
echo [2/3] 启动后端服务...
cd /d "%~dp0backend"
start "BookDesign-Backend" cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo     后端服务启动中...
timeout /t 3 /nobreak >nul

echo.
echo [3/3] 检查服务状态...
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel%==0 (
    echo     ✓ 后端服务启动成功！
    echo     访问地址: http://localhost:8000
) else (
    echo     ✗ 后端服务启动失败，请检查日志
)

echo.
echo ========================================
echo 按任意键退出...
pause >nul
