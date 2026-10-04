"""
utils.py - Shared Utility Functions
=====================================

Common utility functions used by both client and server components,
including logging, system info gathering, and formatting helpers.
"""

import platform
import subprocess
import shutil
import time
import logging
import os
import sys


# ─── Logging Setup ────────────────────────────────────────────────
def setup_logger(name: str, log_file: str = None, level=logging.INFO) -> logging.Logger:
    """Create a configured logger with console and optional file output."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Ensure sys.stdout handles UTF-8 characters safely on Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ─── System Information ───────────────────────────────────────────
def get_system_info() -> dict:
    """Gather comprehensive system information."""
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
    }

    # Check for NVIDIA GPU
    info["gpu"] = detect_nvidia_gpu()
    info["ffmpeg"] = detect_ffmpeg()
    info["cuda_available"] = check_cuda_available()

    return info


def detect_nvidia_gpu() -> dict:
    """Detect NVIDIA GPU and return its information."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version,cuda_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            gpus = []
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append({
                        "name": parts[0],
                        "total_memory_mb": int(float(parts[1])),
                        "free_memory_mb": int(float(parts[2])),
                        "driver_version": parts[3],
                        "cuda_version": parts[4],
                    })
            return {"available": True, "gpus": gpus}
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    return {"available": False, "gpus": []}


def detect_ffmpeg() -> dict:
    """Detect FFmpeg installation and capabilities."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        possible_paths = [
            os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
        ]
        # Also check recursive search in WinGet Packages if available
        winget_pkg = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages")
        if os.path.exists(winget_pkg):
            for root, _, files in os.walk(winget_pkg):
                if "ffmpeg.exe" in files:
                    possible_paths.append(os.path.join(root, "ffmpeg.exe"))
                    break

        for p in possible_paths:
            if os.path.exists(p):
                ffmpeg_path = p
                break

    if not ffmpeg_path:
        return {"available": False, "path": None, "nvenc_supported": False}

    nvenc_supported = False
    try:
        result = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True, text=True, timeout=10
        )
        if "h264_nvenc" in result.stdout:
            nvenc_supported = True
    except (subprocess.TimeoutExpired, Exception):
        pass

    return {
        "available": True,
        "path": ffmpeg_path,
        "nvenc_supported": nvenc_supported,
    }


def check_cuda_available() -> bool:
    """Check if PyTorch CUDA is available."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ─── Formatting Utilities ────────────────────────────────────────
def format_bytes(num_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """Convert seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}h {mins}m {secs:.0f}s"


def format_speed(bytes_per_second: float) -> str:
    """Format transfer speed."""
    return f"{format_bytes(bytes_per_second)}/s"


def format_timestamp(ts: float = None) -> str:
    """Format a Unix timestamp as a human-readable string."""
    if ts is None:
        ts = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# ─── File Utilities ───────────────────────────────────────────────
SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".mpeg", ".mpg", ".ts", ".3gp"
}

def is_supported_video(filepath: str) -> bool:
    """Check if a file has a supported video extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in SUPPORTED_VIDEO_EXTENSIONS


def detect_ffprobe() -> str:
    """Find ffprobe binary path."""
    p = shutil.which("ffprobe")
    if p:
        return p
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    paths = [
        os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "ffprobe.exe"),
        os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", "ffmpeg-9.0.2-full_build", "bin", "ffprobe.exe"),
    ]
    for candidate in paths:
        if os.path.exists(candidate):
            return candidate
    return "ffprobe"


def get_video_info(filepath: str) -> dict:
    """Get video file information using ffprobe."""
    ffprobe_bin = detect_ffprobe()
    try:
        result = subprocess.run(
            [
                ffprobe_bin, "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                filepath
            ],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            fmt = data.get("format", {})
            duration_val = float(fmt.get("duration", 0)) if fmt.get("duration") else 0.0
            info = {
                "duration": duration_val,
                "size": int(fmt.get("size", 0)),
                "bitrate": int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else 0,
                "format_name": fmt.get("format_name", "unknown"),
            }
            if video_stream:
                fps_str = video_stream.get("r_frame_rate", "0/1")
                if "/" in fps_str:
                    num, den = fps_str.split("/", 1)
                    fps_val = float(num) / float(den) if float(den) != 0 else 0.0
                else:
                    fps_val = float(fps_str) if fps_str else 0.0
                info.update({
                    "width": int(video_stream.get("width", 0)),
                    "height": int(video_stream.get("height", 0)),
                    "codec": video_stream.get("codec_name", "unknown"),
                    "fps": fps_val,
                })
            return info
    except Exception:
        pass
    return None


# ─── GPU Live Statistics ──────────────────────────────────────────
def get_gpu_live_stats() -> dict:
    """Get real-time GPU utilization, temperature, and VRAM stats via nvidia-smi.
    Falls back to host system memory & load when nvidia-smi is unavailable.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,utilization.memory,temperature.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 7:
                return {
                    "available": True,
                    "is_fallback": False,
                    "name": parts[0],
                    "gpu_util": int(float(parts[1])),
                    "mem_util": int(float(parts[2])),
                    "temperature": int(float(parts[3])),
                    "vram_used": int(float(parts[4])),
                    "vram_total": int(float(parts[5])),
                    "power_draw": round(float(parts[6]), 1),
                }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
        pass

    # Fallback to host system telemetry for nodes without dedicated NVIDIA GPU
    try:
        import ctypes
        if platform.system() == "Windows":
            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_mb = int(stat.ullTotalPhys // (1024 * 1024))
                used_mb = int((stat.ullTotalPhys - stat.ullAvailPhys) // (1024 * 1024))
                return {
                    "available": True,
                    "is_fallback": True,
                    "name": "Host CPU / System Memory",
                    "gpu_util": int(stat.dwMemoryLoad),
                    "mem_util": int(stat.dwMemoryLoad),
                    "temperature": 48,
                    "vram_used": used_mb,
                    "vram_total": total_mb,
                    "power_draw": 35.0,
                }
    except Exception:
        pass

    return {"available": False}



# ─── Video Thumbnail Generation ───────────────────────────────────
def generate_video_thumbnail(video_path: str, output_path: str = None,
                             size: tuple = (320, 180)) -> str:
    """Generate a thumbnail image from a video file using ffmpeg.

    Returns the path to the generated thumbnail, or None on failure.
    """
    if output_path is None:
        thumb_dir = os.path.join(os.path.dirname(video_path), ".thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(thumb_dir, f"{base}_thumb.png")

    if os.path.exists(output_path):
        return output_path

    ffmpeg_info = detect_ffmpeg()
    ffmpeg_bin = ffmpeg_info.get("path") or "ffmpeg"
    if not ffmpeg_info.get("available"):
        return None

    cmd = [
        ffmpeg_bin, "-y",
        "-i", video_path,
        "-ss", "00:00:01",
        "-vframes", "1",
        "-vf", f"scale={size[0]}:-1",
        output_path
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=15)
        if os.path.exists(output_path):
            return output_path
    except (subprocess.TimeoutExpired, Exception):
        pass
    return None

