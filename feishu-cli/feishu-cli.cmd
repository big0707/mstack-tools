@echo off
REM Windows launcher: feishu-cli.cmd <command> [options]
set "NODE_CMD="
if not "%FEISHU_NODE_PATH%"=="" if exist "%FEISHU_NODE_PATH%" set "NODE_CMD=%FEISHU_NODE_PATH%"
if "%NODE_CMD%"=="" if exist "%~dp0node\node.exe" set "NODE_CMD=%~dp0node\node.exe"
if "%NODE_CMD%"=="" if exist "%~dp0nodejs\node.exe" set "NODE_CMD=%~dp0nodejs\node.exe"
if "%NODE_CMD%"=="" (
  where node >nul 2>nul
  if not errorlevel 1 set "NODE_CMD=node"
)
if "%NODE_CMD%"=="" (
  echo Node.js 18+ is required. Install Node.js, set FEISHU_NODE_PATH, or put node.exe under tools\feishu-cli\node\.
  exit /b 9009
)
"%NODE_CMD%" "%~dp0src\cli.js" %*
