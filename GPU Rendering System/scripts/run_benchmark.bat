@echo off
title GPU Offloading - Benchmark Suite
cd /d "%~dp0\.."
echo =======================================================
echo   RUNNING GPU OFFLOADING BENCHMARK SUITE
echo =======================================================
if "%~1"=="" (
    echo Usage: run_benchmark.bat [path_to_video.mp4] [server_ip]
    echo Running with default local CPU verification...
    python -m client.benchmark --help
) else (
    python -m client.benchmark --input "%~1" --server "%~2"
)
pause
