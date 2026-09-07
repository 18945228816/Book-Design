@echo off
chcp 65001 >nul
echo ========================================
echo   重启前端服务
echo ========================================
echo.

:: 查找并关闭正在运行的 Vite 开发服务器
echo [1/3] 检查正在运行的前端服务...
set "found=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do (
    set "found=1"
    set "pid=%%a"
)

if "%found%"=="1" (
    echo     发现正在运行的前端服务，PID: %pid%
    echo     正在关闭...
    taskkill /F /PID %pid% >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo     已关闭
) else (
    echo     未发现正在运行的前端服务
)

echo.
echo [2/3] 启动前端服务...
cd /d "%~dp0frontend"
start "BookDesign-Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo     前端服务启动中...
timeout /t 5 /nobreak >nul

echo.
echo [3/3] 检查服务状态...
netstat -ano | findstr :5173 | findstr LISTENING >nul
if %errorlevel%==0 (
    echo     ✓ 前端服务启动成功！
    echo     访问地址: http://localhost:5173
) else (
    echo     ✗ 前端服务启动失败，请检查日志
)

echo.
echo ========================================
echo 按任意键退出...
pause >nul
