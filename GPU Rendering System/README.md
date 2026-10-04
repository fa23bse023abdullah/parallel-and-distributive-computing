⚡ Distributed Task Offloading & Remote GPU Rendering System

<!-- Screenshot styling: professional centered layout for Markdown renderers that support CSS.
.screenshot { text-align:center; margin:24px 0; }
.screenshot img { display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px; }
.screenshot p { margin-bottom:10px; }
-->

CSC-334: Parallel and Distributed Computing
A custom distributed system for offloading compute-heavy rendering tasks from a resource-constrained client to a remote GPU-equipped worker node over LAN.

📖 Table of Contents

Overview

System Architecture

Features

Repository Structure

Prerequisites

Network Configuration Guide

Installation

Usage Guide

Starting the Server Daemon

Launching the Client GUI

Running a Benchmark

Protocol Specification

Performance Benchmarking

Screenshots & Demo

Troubleshooting

Technologies Used

Overview

This project implements a Distributed Task Offloading System that allows a resource-constrained client laptop (e.g., with only integrated graphics or low-end GPU) to offload heavy computational tasks—specifically video transcoding and CUDA tensor operations—to a remote worker node equipped with a dedicated NVIDIA GPU.

Problem

Client machines with limited GPU resources suffer from extreme latency, thermal throttling, or OOM failures during heavy rendering workloads.

Upgrading local hardware is expensive and not always feasible.

Solution

Establish a high-speed LAN connection between client and worker node.

Serialize, transmit, and execute workloads using GPU hardware acceleration (NVENC/CUDA).

Stream real-time progress back to the client and deliver the rendered output.

System Architecture

+─────────────────────────────────────────────────────────────────+
│                    CLIENT LAPTOP (Client App)                    │
│  [CustomTkinter GUI] → [Job Config] → [Socket Connection]      │
+─────────────────────────────────────────────────────────────────+
                              │
                              │ TCP Socket (Direct LAN / Wi-Fi)
                              │ Length-Prefixed JSON Protocol
                              ▼
+─────────────────────────────────────────────────────────────────+
│                  REMOTE WORKER NODE (Server Daemon)             │
│  [Socket Listener] → [Task Queue] → [FFmpeg NVENC / CUDA]      │
+─────────────────────────────────────────────────────────────────+
                              │
                              │ Real-time Progress + File Download
                              ▼
+─────────────────────────────────────────────────────────────────+
│                    CLIENT LAPTOP (Output Render)                │
│  [Live Terminal] → [Progress Bar] → [Rendered Output File]     │
+─────────────────────────────────────────────────────────────────+

Workflow

Handshake — Client connects and exchanges capabilities with server.

Job Submission — Client sends render configuration and uploads input file.

File Transfer — Input file transferred in 64KB chunks with SHA-256 checksum validation.

GPU Execution — Server processes the job using NVENC hardware encoding (or CPU fallback).

Progress Streaming — Real-time progress updates streamed back to client over the socket.

Output Delivery — Rendered file downloaded back to client with integrity verification.

Features

Feature

Description

🔗 Handshake Protocol

Initial capability negotiation, version checking, and latency ping

🎮 GPU Acceleration

FFmpeg NVENC (h264_nvenc) hardware encoding with CPU fallback

🧮 CUDA Compute

PyTorch CUDA matrix multiplication and convolution benchmarks

🖥️ Studio GUI

Luxury White & Dark Mode toggleable CustomTkinter interface with animated harmonic wave

📊 Real-time Progress

Asynchronous progress bar with percentage, speed, and ETA

🌡️ Hardware Telemetry

Live server GPU/CPU monitoring (VRAM used/total, load %, temp °C, power draw)

🚀 Active Speed Test

Integrated network throughput (MB/s & Mbps) and latency benchmark

🖼️ Video Thumbnails

Automatic video thumbnail extraction and preview in asset dropzone

📜 Job History Panel

Persistent execution history with status, elapsed times, compression ratios, and 1-click file launch

📋 Batch Processing

Multi-file queue support for sequential offloaded rendering

🔔 Audio-Visual Chimes

System audio notifications and visual completion toasts

🔒 File Integrity

Cryptographic SHA-256 checksum validation on both upload and download

⏱️ Benchmarking

Local vs. remote performance comparison with speedup factor analysis

🛡️ Robustness

Timeout handling, graceful disconnection, and error recovery

📝 Logging

Obsidian developer console with color-coded tags and persistent file logs

Repository Structure

PAD/
├── common/                     # Shared modules
│   ├── __init__.py
│   ├── protocol.py             # Message protocol, serialization, file transfer
│   └── utils.py                # System detection, live GPU stats, thumbnails, logging
│
├── server/                     # Remote Worker Node
│   ├── __init__.py
│   ├── server_daemon.py        # Main server daemon (entry point & telemetry dispatcher)
│   ├── task_queue.py           # Thread-safe job queue manager
│   ├── task_executor.py        # GPU execution engine (NVENC + CUDA)
│   └── requirements.txt
│
├── client/                     # Client Laptop Application
│   ├── __init__.py
│   ├── client_app.py           # CustomTkinter GUI application (Luxury theme & telemetry)
│   ├── network_handler.py      # Socket communication & speed test manager
│   ├── benchmark.py            # Comparative performance benchmarking tool
│   ├── job_history.json        # Persistent local execution log
│   └── requirements.txt
│
├── scripts/                    # Convenience Launchers & Diagnostics
│   ├── run_server.bat          # 1-Click Worker Daemon Launcher
│   ├── run_client.bat          # 1-Click Client Desktop GUI Launcher
│   ├── run_benchmark.bat       # 1-Click Automated Benchmark Launcher
│   ├── setup_environment.bat   # 1-Click Dependency Installer
│   └── verify_system.py        # System hardware & protocol diagnostic audit
│
├── screenshots/                # Execution screenshots
├── requirements.txt            # Project dependencies (customtkinter, Pillow)
├── .gitignore
└── README.md                   # Comprehensive documentation

Prerequisites

Both Machines

Python 3.8+

FFmpeg (with ffprobe) installed and available in system PATH

Client Laptop

Python packages: customtkinter, Pillow

Any operating system (Windows/Linux/macOS)

Server / Worker Node

NVIDIA GPU with up-to-date drivers (for NVENC hardware encoding)

FFmpeg compiled with NVENC support (h264_nvenc encoder)

(Optional) PyTorch with CUDA support for tensor compute tasks

Network

Direct Ethernet (CAT5e/CAT6) cable OR same Wi-Fi subnet

Both machines must be able to reach each other via TCP

Network Configuration Guide

Option A: Direct Ethernet Cable (Recommended)

Connect both machines with a CAT6 Ethernet cable.

Configure static IPs on both machines:

Server (Worker Node):

IP Address:  192.168.1.1
Subnet Mask: 255.255.255.0
Gateway:     (leave empty)

Client (Laptop):

IP Address:  192.168.1.2
Subnet Mask: 255.255.255.0
Gateway:     (leave empty)

Verify connectivity:

# From client:
ping 192.168.1.1

# From server:
ping 192.168.1.2

Windows Static IP Setup

Open Settings → Network & Internet → Ethernet

Click Edit next to IP assignment

Set to Manual, enable IPv4

Enter the IP address and subnet mask as shown above

Linux Static IP Setup

# Temporary (until reboot):
sudo ip addr add 192.168.1.1/24 dev eth0
sudo ip link set eth0 up

# Permanent (edit /etc/netplan/ or /etc/network/interfaces)

Option B: Wi-Fi (Same Network)

Connect both machines to the same Wi-Fi network.

Find the server's IP address:

# Windows:
ipconfig

# Linux/macOS:
ip addr show

Use the server's Wi-Fi IP address in the client GUI.

Installation

1. Clone the Repository

git clone https://github.com/<your-username>/distributed-gpu-renderer.git
cd distributed-gpu-renderer

2. Install Dependencies

On the Client machine:

pip install -r requirements.txt

On the Server machine:

# Base (no extra Python packages needed for FFmpeg transcoding)
# Python standard library handles everything

# Optional: For CUDA compute tasks
pip install torch --index-url https://download.pytorch.org/whl/cu121

3. Verify FFmpeg Installation

ffmpeg -version
ffmpeg -encoders | findstr nvenc    # Windows
ffmpeg -encoders | grep nvenc       # Linux/macOS

Expected output should show h264_nvenc in the encoder list.

4. Run System Diagnostics (Recommended)

Verify your node's hardware, FFmpeg binaries, and network readiness with one command:

python scripts/verify_system.py

(Or double-click scripts\setup_environment.bat on Windows)

Usage Guide

1. Starting the Server Daemon (Worker Node)

On the GPU-equipped machine:

# 1-Click Launch (Windows):
scripts\run_server.bat

# Or via Command Line:
python -m server.server_daemon --host 0.0.0.0 --port 9850

# Custom workspace directory:
python -m server.server_daemon --work-dir /data/render_workspace

You should see output like:

════════════════════════════════════════════════════════════════════
  DISTRIBUTED TASK OFFLOADING — REMOTE WORKER NODE
════════════════════════════════════════════════════════════════════
  Server listening on 0.0.0.0:9850
  Work directory: C:\workspace
  GPU: NVIDIA GeForce RTX 3060 (12288MB VRAM)
  FFmpeg: Available
  NVENC: Supported
════════════════════════════════════════════════════════════════════
  Waiting for client connections...

2. Launching the Client GUI (Client Laptop)

On the client machine:

# 1-Click Launch (Windows):
scripts\run_client.bat

# Or via Command Line:
python -m client.client_app

Step-by-step workflow:

Enter Server IP — Type the worker node's IP address (e.g., 192.168.1.1 or 127.0.0.1).

Click "Connect Worker Node" — Performs protocol handshake and starts streaming live hardware telemetry.

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">start the connection:</p>
  <img src="https://github.com/user-attachments/assets/f902dea7-790d-4d7a-8205-2f62eac23a30" alt="image" width="1366" height="727" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

Click "Ping" / "🚀 Speed Test" — Measures round-trip latency and active link throughput (MB/s & Mbps).

Browse Video Asset(s) — Select one or multiple videos for batch queuing. The GUI automatically extracts a video thumbnail preview in the dropzone!

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">upload vedio:</p>
  <img src="https://github.com/user-attachments/assets/c1cc8d56-e1b2-4a72-82a2-b895d0b037f4" alt="image" width="1361" height="720" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

Configure Render Settings — Choose resolution (480p to 4K), bitrate (2M to 50M), and encoder preset (Ultrafast to Quality).

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">hardware render config:</p>
  <img src="https://github.com/user-attachments/assets/ab0a23ba-3d13-4605-9c98-819d6394db16" alt="image" width="1366" height="718" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

Click "Launch Remote GPU Render" — Streams progress in real-time, displays live VRAM/GPU load, downloads rendered output with SHA-256 integrity verification, plays an audio chime, and records to the persistent Job History panel!

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">launch remote gpu render:</p>
  <img src="https://github.com/user-attachments/assets/8212fe5e-5c58-4490-b51c-a0426e70886e" alt="image" width="1358" height="716" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">complete gpu render :</p>
  <img src="https://github.com/user-attachments/assets/e2dd9b4d-8358-4bde-a611-74a492de8e5e" alt="image" width="1365" height="718" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">gpu render result</p>
  <img src="https://github.com/user-attachments/assets/b3ccfd36-93b6-4363-9227-c9a93abd2660" alt="image" width="529" height="301" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

Toggle Light/Dark Mode — Click 🌙 Dark / ☀️ Light in the header navbar at any time.

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">dark theme:</p>
  <img src="https://github.com/user-attachments/assets/43dfea3b-e600-499c-89cc-c07147742fa2" alt="image" width="1366" height="726" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>



3. Running a Performance Benchmark

# Local-only benchmark (CPU transcoding):
python -m client.benchmark --input video.mp4

# Local + Remote comparison:
python -m client.benchmark --input video.mp4 --server 192.168.1.1

# Full options:
python -m client.benchmark --input video.mp4 --server 192.168.1.1 --port 9850 --output-dir ./results

The benchmark generates:

<div align="center" style="text-align:center; margin:24px 0;">
  <p style="margin-bottom:10px;">LOCAL CPU BENCHMARK :</p>
  <img src="https://github.com/user-attachments/assets/a387633b-f905-4735-8504-15d1a63019c3" alt="image" width="853" height="267" style="display:block; margin:0 auto; max-width:100%; height:auto; border-radius:10px;" />
</div>

benchmark_results.json — Raw data

benchmark_report.md — Formatted technical report with speedup analysis

Protocol Specification

Message Format

All messages use length-prefixed JSON framing:

[4-byte big-endian length header] + [JSON payload bytes]

Message Structure

{
    "type": "MESSAGE_TYPE",
    "version": "1.0.0",
    "timestamp": 1696348800.0,
    "payload": { ... }
}

Message Types

Type

Direction

Purpose

HANDSHAKE_REQUEST

Client → Server

Initial capability exchange

HANDSHAKE_RESPONSE

Server → Client

Accept with server capabilities

PING / PONG

Bidirectional

Latency measurement

JOB_SUBMIT

Client → Server

Submit job with config

JOB_ACCEPTED

Server → Client

Job queued successfully

JOB_PROGRESS

Server → Client

Real-time progress update

JOB_COMPLETE

Server → Client

Job finished with result info

JOB_FAILED

Server → Client

Job error details

FILE_TRANSFER_START

Sender → Receiver

File metadata + checksum

FILE_CHUNK

Sender → Receiver

Base64-encoded 64KB chunks

FILE_TRANSFER_END

Sender → Receiver

Transfer complete + verification

File Integrity

Files are transferred in 64KB chunks with Base64 encoding.

SHA-256 checksums are computed before transfer and verified after reception.

Mismatched checksums trigger automatic error handling and the corrupted file is deleted.

Performance Benchmarking

Methodology

Benchmarks compare:

Local CPU transcoding using libx264 software encoder

Remote GPU transcoding using h264_nvenc hardware encoder (+ network overhead)

Test Configurations

#

Resolution

Bitrate

Preset

1

720p

5 Mbps

Fast

2

1080p

5 Mbps

Medium

3

1080p

10 Mbps

Medium

4

1080p

5 Mbps

Slow

Metrics Measured

Encoding time (seconds)

Network transfer overhead (upload + download time)

Total end-to-end time (local vs. remote)

Speedup factor = Local Time / Remote Total Time

Throughput (MB/s)

Compression ratio = Input Size / Output Size

Sample Results

Configuration

Local CPU

Remote GPU (Total)

Render Only

Speedup

1080p/5M/medium

45.2s

12.8s

8.3s

3.53x

1080p/10M/medium

48.7s

14.1s

9.7s

3.45x

1080p/5M/slow

128.4s

18.6s

14.2s

6.90x

720p/5M/fast

18.3s

7.2s

3.1s

2.54x

Note: Actual results vary by hardware. NVENC provides the greatest speedup on slower presets.

Screenshots & Demo

Client GUI — Connected & Ready

Launch the client and connect to the server. The handshake shows server capabilities including GPU info.

Live Progress Tracking

Real-time progress bar and terminal showing encoding progress with speed indicator.

Benchmark Comparison

Side-by-side comparison of local CPU vs. remote GPU transcoding times.

📸 Add your own screenshots to the screenshots/ directory.

Troubleshooting

Issue

Solution

Connection refused

Ensure the server daemon is running and the firewall allows port 9850

Connection timeout

Verify network connectivity with ping. Check static IP configuration

NVENC not available

Install latest NVIDIA drivers. Verify with ffmpeg -encoders | grep nvenc

FFmpeg not found

Install FFmpeg and add to system PATH

Checksum mismatch

Network corruption detected — retry the transfer

Job stuck at 0%

Check server logs in workspace/logs/ for errors

Port already in use

Change port with --port 9851 or kill the existing process

Firewall Configuration

Windows:

New-NetFirewallRule -DisplayName "GPU Render Server" -Direction Inbound -Protocol TCP -LocalPort 9850 -Action Allow

Linux:

sudo ufw allow 9850/tcp

Technologies Used

Technology

Purpose

Python 3

Core language for both client and server

Socket (TCP)

Low-level network communication

Threading

Concurrent job processing and async I/O

CustomTkinter

Modern dark-themed desktop GUI framework

FFmpeg + NVENC

Hardware-accelerated video transcoding

PyTorch CUDA

GPU tensor operations (optional)

SHA-256

File integrity validation via checksums

JSON

Structured message serialization

License

This project was developed for CSC-334: Parallel and Distributed Computing.

Built with ⚡ for high-performance distributed computing.
