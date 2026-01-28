@echo off
setlocal
echo ========================================================
echo   SmartHarvest - Continuous Delivery Reproduction Script
echo ========================================================

echo [1/3] Building Docker Image (Clean Build)...
FOR /F "tokens=*" %%g IN ('git rev-parse HEAD') do (SET GIT_COMMIT=%%g)
echo       Git Commit: %GIT_COMMIT%

docker compose build --no-cache --build-arg GIT_COMMIT=%GIT_COMMIT%
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker build failed.
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Executing Pipeline Container...
echo       Artifacts will be saved to .\output_docker
docker compose up
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker execution failed.
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Verifying Output Artifacts...
if exist "output_docker\gate_a_output\runs" (
    echo [SUCCESS] Run artifacts detected in .\output_docker\gate_a_output\runs
    echo           Reproducibility Check PASSED.
) else (
    echo [FAIL] output_docker\runs directory NOT found.
    echo        The pipeline might have failed or verify volume mounting.
    exit /b 1
)

echo.
echo Done.
