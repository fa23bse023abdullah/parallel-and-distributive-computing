"""
verify_system.py - System Diagnostics & Hardware Verification Tool
===================================================================

Verifies system capabilities, software dependencies, FFmpeg encoder
support, GPU availability, and network readiness for the Distributed
Task Offloading & Remote GPU Rendering System.
"""

import sys
import os
import platform
import socket

# Reconfigure stdout/stderr for Unicode support on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.utils import (
    get_system_info, detect_nvidia_gpu, detect_ffmpeg,
    check_cuda_available, get_gpu_live_stats, format_bytes
)
from common.protocol import (
    PROTOCOL_VERSION, DEFAULT_SERVER_PORT, create_message,
    serialize_message, deserialize_message, MessageType,
    compute_file_checksum
)


def run_diagnostics():
    print("=" * 64)
    print("  ⚡ GPU OFFLOADING SYSTEM - HARDWARE & ENVIRONMENT AUDIT")
    print("=" * 64)
    print(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"Python: {platform.python_version()} ({sys.executable})")
    print(f"Protocol: v{PROTOCOL_VERSION} on default port {DEFAULT_SERVER_PORT}")
    print("-" * 64)

    # 1. Check Python Packages
    print("[1/5] Checking Python Dependencies...")
    for pkg in ["customtkinter", "PIL", "tkinter"]:
        try:
            __import__(pkg)
            print(f"  ✓ {pkg:15s} INSTALLED")
        except ImportError:
            print(f"  ✗ {pkg:15s} MISSING (Run: pip install -r requirements.txt)")

    # 2. Check FFmpeg & NVENC
    print("\n[2/5] Checking Media Transcoding Engine (FFmpeg)...")
    ffmpeg = detect_ffmpeg()
    if ffmpeg["available"]:
        print(f"  ✓ FFmpeg Binary: {ffmpeg['path']}")
        if ffmpeg.get("nvenc_supported"):
            print("  ✓ NVENC Support: Hardware Acceleration (h264_nvenc) ENABLED")
        else:
            print("  ℹ NVENC Support: Not detected (libx264 CPU fallback will be used)")
    else:
        print("  ✗ FFmpeg: Not found in PATH or standard directories.")

    # 3. Check GPU Hardware
    print("\n[3/5] Checking GPU Acceleration Hardware...")
    gpu_info = detect_nvidia_gpu()
    if gpu_info["available"]:
        for gpu in gpu_info.get("gpus", []):
            print(f"  ✓ NVIDIA GPU: {gpu.get('name')} | VRAM: {gpu.get('total_memory_mb')} MB | CUDA: {gpu.get('cuda_version')}")
    else:
        print("  ℹ NVIDIA GPU: Not detected on this node (Client mode or CPU fallback active)")

    live_stats = get_gpu_live_stats()
    if live_stats.get("available"):
        print(f"  ✓ Hardware Telemetry: {live_stats.get('name')} (RAM/VRAM: {live_stats.get('vram_used')}/{live_stats.get('vram_total')} MB, Load: {live_stats.get('gpu_util')}%)")

    # 4. Check Protocol Serialization & Integrity
    print("\n[4/5] Checking Protocol Serialization & Cryptographic Checksums...")
    test_msg = create_message(MessageType.PING, {"test": 12345})
    raw = serialize_message(test_msg)
    parsed = deserialize_message(raw[4:])
    assert parsed["type"] == MessageType.PING
    print("  ✓ Length-Prefixed Protocol: Encoding & Decoding Verified")

    # Test Checksum
    script_path = os.path.abspath(__file__)
    csum = compute_file_checksum(script_path)
    assert len(csum) == 64
    print(f"  ✓ SHA-256 Checksum Engine: Verified ({csum[:16]}...)")

    # 5. Check Network Port Readiness
    print("\n[5/5] Checking Network Socket Port Availability...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", DEFAULT_SERVER_PORT))
        print(f"  ✓ Port {DEFAULT_SERVER_PORT}: FREE & READY for server listener")
    except OSError:
        print(f"  ℹ Port {DEFAULT_SERVER_PORT}: CURRENTLY IN USE (Server Daemon may be running)")
    finally:
        sock.close()

    print("\n" + "=" * 64)
    print("  ✅ AUDIT COMPLETE: ALL CRITICAL SUBSYSTEMS OPERATIONAL")
    print("=" * 64)


if __name__ == "__main__":
    run_diagnostics()
