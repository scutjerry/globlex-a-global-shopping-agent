@echo off
setlocal EnableExtensions DisableDelayedExpansion

title Globex MVP - Docker Startup
set "PROJECT_ROOT=%~dp0"
set "COMPOSE_FILE=%PROJECT_ROOT%docker\docker-compose.yaml"
set "ENV_FILE=%PROJECT_ROOT%.env"
rem Keep the compose project name explicit: it determines the container and named-volume
rem prefix (globex-app-1, globex-app-data, ...). The compose file also declares name: globex.
set "COMPOSE_PROJECT=globex"

cd /d "%PROJECT_ROOT%"

echo.
echo ============================================================
echo   Globex MVP - Docker Startup
echo ============================================================
echo.

if not exist "%COMPOSE_FILE%" (
  echo [ERROR] Compose file not found:
  echo %COMPOSE_FILE%
  goto :failed
)

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker command was not found.
  echo Install Docker Desktop and run this script again.
  goto :failed
)

rem Start Docker Desktop automatically when its engine is not ready.
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready

echo [INFO] Docker engine is not ready. Starting Docker Desktop...
set "DOCKER_DESKTOP_EXE="
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DOCKER_DESKTOP_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not defined DOCKER_DESKTOP_EXE if exist "%LocalAppData%\Docker\Docker Desktop.exe" set "DOCKER_DESKTOP_EXE=%LocalAppData%\Docker\Docker Desktop.exe"

if not defined DOCKER_DESKTOP_EXE (
  echo [ERROR] Docker Desktop executable was not found.
  echo Install Docker Desktop, or start its Linux engine manually.
  goto :failed
)

start "Docker Desktop" "%DOCKER_DESKTOP_EXE%"
set /a DOCKER_WAIT_SECONDS=0

:wait_for_docker
timeout /t 2 /nobreak >nul
set /a DOCKER_WAIT_SECONDS+=2
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready
if %DOCKER_WAIT_SECONDS% GEQ 180 (
  echo [ERROR] Docker Desktop did not become ready within 180 seconds.
  echo Check Docker Desktop for startup errors, then run this script again.
  goto :failed
)
echo [INFO] Waiting for Docker engine... %DOCKER_WAIT_SECONDS%s / 180s
goto :wait_for_docker

:docker_ready
echo [INFO] Docker engine is ready.

rem Priority: project .env is authoritative, above anything inherited from the machine.
rem app/worker read .env through compose env_file, which a machine-level variable such as
rem LLM_MODEL cannot override. The values are parsed by Docker Compose, not by cmd: cmd's
rem for /f does not trim the spaces in "KEY = value" lines, so parsing them here used to
rem silently leave a machine-level LLM_MODEL in effect.
if not exist "%ENV_FILE%" (
  echo [ERROR] No .env file found.
  echo Create .env from .env.example and fill in LLM_BASE_URL and LLM_API_KEY.
  goto :failed
)

echo [INFO] Using .env as the authoritative configuration source.
rem Detect key presence with findstr, which tolerates the "KEY = value" spacing that cmd's
rem for /f parser does not trim (a trailing space in the parsed name made an equality test
rem fail silently). The values themselves are parsed by Docker Compose, never here.
findstr /r /c:"^ *LLM_BASE_URL *=" "%ENV_FILE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] LLM_BASE_URL is not defined in .env
  goto :failed
)
findstr /r /c:"^ *LLM_API_KEY *=" "%ENV_FILE%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] LLM_API_KEY is not defined in .env
  goto :failed
)

rem Reject the .env.example placeholder and an empty value before wasting a build.
findstr /r /c:"^ *LLM_API_KEY *= *$" "%ENV_FILE%" >nul 2>&1
if not errorlevel 1 (
  echo [ERROR] LLM_API_KEY in .env is empty.
  goto :failed
)
findstr /r /c:"^ *LLM_API_KEY *= *sk-xxx *$" "%ENV_FILE%" >nul 2>&1
if not errorlevel 1 (
  echo [ERROR] .env still contains the placeholder LLM_API_KEY=sk-xxx
  goto :failed
)

echo.
echo [INFO] Building and starting app, worker, Redis, Qdrant, and frontend...
echo [INFO] The first launch may take several minutes while images and dependencies download.
echo.

if exist "%ENV_FILE%" (
  docker compose --project-name "%COMPOSE_PROJECT%" --env-file "%ENV_FILE%" -f "%COMPOSE_FILE%" up -d --build
) else (
  docker compose --project-name "%COMPOSE_PROJECT%" -f "%COMPOSE_FILE%" up -d --build
)
if errorlevel 1 (
  echo.
  echo [ERROR] Globex failed to start. Show logs with:
  echo docker compose --project-name globex -f docker\docker-compose.yaml logs --tail=200 app frontend worker
  goto :failed
)

echo.
echo [OK] Globex startup request completed.
echo [INFO] Project:         globex
echo [INFO] Containers:      globex-app-1 / globex-worker-1 / globex-redis-1 / globex-qdrant-1 / globex-frontend-1
echo [INFO] Named volumes:   globex_app-data / globex_qdrant-data / globex_redis-data
echo [INFO] Frontend:       http://localhost:8080
echo [INFO] Frontend health: http://localhost:8080/healthz
echo [INFO] Backend health:  http://localhost:8080/api/health
echo.
echo [INFO] Current service status:
if exist "%ENV_FILE%" (
  docker compose --project-name "%COMPOSE_PROJECT%" --env-file "%ENV_FILE%" -f "%COMPOSE_FILE%" ps
) else (
  docker compose --project-name "%COMPOSE_PROJECT%" -f "%COMPOSE_FILE%" ps
)

echo.
echo [INFO] Opening browser. Refresh the page after a moment if services are still initializing.
start "Globex MVP" "http://localhost:8080"
goto :done

:failed
echo.
echo [HINT] Verify Docker Desktop with: docker version

:done
echo.
pause
endlocal
