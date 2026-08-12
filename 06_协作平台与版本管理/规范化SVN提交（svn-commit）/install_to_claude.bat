@echo off
setlocal enabledelayedexpansion

set "SOURCE_DIR=%~dp0"
for %%I in ("%SOURCE_DIR:~0,-1%") do set "SKILL_CATEGORY=%%~nxI"

echo ========================================
echo   Install Skills to Claude: %SKILL_CATEGORY%
echo ========================================
echo.

set "SKILL_DIR="
set "CURRENT_DIR=%~dp0"
:find_skill_dir
if exist "%CURRENT_DIR%.skill" (
    set "SKILL_DIR=%CURRENT_DIR%.skill"
    goto :found_skill_dir
)
if "%CURRENT_DIR:~1,1%"=="" (
    echo ERROR: .skill directory not found
    exit /b 1
)
for %%I in ("%CURRENT_DIR:~0,-1%") do set "CURRENT_DIR=%%~dpI"
goto :find_skill_dir
:found_skill_dir

for %%I in ("%SKILL_DIR%") do set "PROJECT_ROOT=%%~dpI"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

for /f "tokens=1,2 delims==" %%A in ('findstr "CLAUDE_SKILLS_PATH" "%SKILL_DIR%\paths.md"') do (
    set "TARGET_DIR=%PROJECT_ROOT%\%%B"
)

if not defined TARGET_DIR (
    echo ERROR: CLAUDE_SKILLS_PATH not found in paths.md
    exit /b 1
)

if not exist "%TARGET_DIR%" (
    echo Create target dir: %TARGET_DIR%
    mkdir "%TARGET_DIR%"
)

echo Source: %SOURCE_DIR%
echo Target: %TARGET_DIR%
echo.

set COUNT=0
for /d %%D in ("%SOURCE_DIR%*") do (
    if exist "%%D\SKILL.md" (
        set /a COUNT+=1
        echo Copy skill: %%~nxD
        xcopy "%%D" "%TARGET_DIR%\%%~nxD\" /E /I /Y >nul
        if !errorlevel! equ 0 (
            echo   [OK] %%~nxD copied
        ) else (
            echo   [FAIL] %%~nxD failed
        )
    )
)

echo.
echo ========================================
if !COUNT! equ 0 (
    echo   No skills found
) else (
    echo   Installed !COUNT! skill(s^)
)
echo   Target: %TARGET_DIR%
echo ========================================
echo.
