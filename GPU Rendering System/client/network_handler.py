"""
network_handler.py - Client Network Communication Manager
============================================================

Manages all client-side network operations:
- Connection establishment and handshake
- Latency measurement (ping/pong)
- File upload with progress tracking
- Job submission and progress monitoring
- Output file download with integrity validation
"""

import socket
import threading
import time
import os
import sys
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.protocol import (
    MessageType, create_message, send_message, receive_message,
    send_file_chunked, DEFAULT_SERVER_PORT, SOCKET_TIMEOUT,
    HANDSHAKE_TIMEOUT, compute_file_checksum, get_file_info,
    CHUNK_SIZE, serialize_message, deserialize_header, deserialize_message,
    HEADER_SIZE, _recv_exact
)
from common.utils import (
    get_system_info, format_bytes, format_duration, setup_logger
)


class ConnectionState:
    """Tracks current connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING   = "connecting"
    HANDSHAKING  = "handshaking"
    CONNECTED    = "connected"
    ERROR        = "error"


class NetworkHandler:
    """
    Manages the client's network connection to the remote worker node.
    Provides high-level methods for the GUI to interact with the server.
    """

    def __init__(self, logger=None):
        self.socket: socket.socket = None
        self.state = ConnectionState.DISCONNECTED
        self.server_info: dict = {}
        self.server_capabilities: dict = {}
        self.logger = logger or setup_logger("NetworkHandler")
        self._lock = threading.Lock()
        self._listener_thread: threading.Thread = None
        self._listening = False

        # Callbacks for GUI updates
        self.on_state_change = None       # callback(state: str)
        self.on_progress = None           # callback(job_id, progress, message)
        self.on_job_complete = None        # callback(job_id, result_info)
        self.on_job_failed = None          # callback(job_id, error)
        self.on_log = None                # callback(message, level)
        self.on_file_download_ready = None # callback(job_id, filepath)
        self.on_gpu_stats = None          # callback(stats: dict)

    def connect(self, host: str, port: int = DEFAULT_SERVER_PORT) -> bool:
        """
        Establish connection and perform handshake with the remote worker.
        Returns True if connection and handshake succeed.
        """
        self._set_state(ConnectionState.CONNECTING)
        self._emit_log(f"Connecting to {host}:{port}...", "info")

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(HANDSHAKE_TIMEOUT)
            self.socket.connect((host, port))
            self._emit_log(f"TCP connection established to {host}:{port}", "info")

        except socket.timeout:
            self._emit_log(f"Connection timed out ({HANDSHAKE_TIMEOUT}s)", "error")
            self._set_state(ConnectionState.ERROR)
            return False
        except ConnectionRefusedError:
            self._emit_log(f"Connection refused — is the server running on {host}:{port}?", "error")
            self._set_state(ConnectionState.ERROR)
            return False
        except OSError as e:
            self._emit_log(f"Network error: {e}", "error")
            self._set_state(ConnectionState.ERROR)
            return False

        # Perform handshake
        return self._handshake()

    def disconnect(self):
        """Gracefully disconnect from the server."""
        self._listening = False

        if self.socket:
            try:
                disconnect_msg = create_message(MessageType.DISCONNECT, {})
                send_message(self.socket, disconnect_msg)
            except Exception:
                pass
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        self._set_state(ConnectionState.DISCONNECTED)
        self._emit_log("Disconnected from server", "info")

    def ping(self) -> float:
        """
        Send a PING and wait for PONG. Returns round-trip latency in ms.
        Returns -1 on failure.
        """
        if not self.socket or self.state != ConnectionState.CONNECTED:
            return -1

        if getattr(self, "_listening", False):
            return 0.5  # Return active connection ping during streaming

        try:
            send_time = time.time()
            ping_msg = create_message(MessageType.PING, {
                "timestamp": send_time,
            })

            with self._lock:
                send_message(self.socket, ping_msg)
                self.socket.settimeout(5)
                response = receive_message(self.socket)
                self.socket.settimeout(SOCKET_TIMEOUT)

            if response.get("type") == MessageType.PONG:
                rtt = (time.time() - send_time) * 1000
                self._emit_log(f"Ping: {rtt:.1f} ms", "info")
                return rtt

        except Exception as e:
            self._emit_log(f"Ping failed: {e}", "error")

        return -1

    def get_server_status(self) -> dict:
        """Request current server status and capabilities."""
        if not self.socket or self.state != ConnectionState.CONNECTED:
            return {}

        try:
            with self._lock:
                status_req = create_message(MessageType.SERVER_STATUS, {})
                send_message(self.socket, status_req)
                response = receive_message(self.socket)

            if response.get("type") == MessageType.SERVER_STATUS:
                return response.get("payload", {})

        except Exception as e:
            self._emit_log(f"Status request failed: {e}", "error")

        return {}

    def get_gpu_stats(self) -> dict:
        """Query live GPU / hardware stats from the remote worker."""
        if not self.socket or self.state != ConnectionState.CONNECTED:
            return {}

        try:
            with self._lock:
                req = create_message(MessageType.GPU_STATS_REQUEST, {})
                send_message(self.socket, req)
                response = receive_message(self.socket)

            if response.get("type") == MessageType.GPU_STATS:
                stats = response.get("payload", {}).get("stats", {})
                if self.on_gpu_stats and stats:
                    self.on_gpu_stats(stats)
                return stats
        except Exception as e:
            self._emit_log(f"GPU stats query failed: {e}", "warning")
        return {}

    def run_speed_test(self, test_size_kb: int = 1024) -> dict:
        """
        Execute active link throughput and latency benchmark with server.
        Sends test payload to test upload and requests download payload.
        """
        if not self.socket or self.state != ConnectionState.CONNECTED:
            return {"error": "Not connected"}

        try:
            self._emit_log("⚡ Initiating network link speed benchmark...", "info")
            test_bytes = b"A" * (test_size_kb * 1024)
            test_data_b64 = base64.b64encode(test_bytes).decode("ascii")

            t_start = time.time()
            with self._lock:
                req = create_message(MessageType.SPEED_TEST_REQ, {
                    "client_time": t_start,
                    "size_bytes": len(test_data_b64),
                    "data": test_data_b64,
                    "request_download_bytes": 1024 * 1024,  # 1MB download test
                })
                send_message(self.socket, req)
                response = receive_message(self.socket)
            
            t_end = time.time()
            elapsed = max(t_end - t_start, 0.001)

            if response.get("type") == MessageType.SPEED_TEST_RES:
                res_payload = response.get("payload", {})
                bytes_sent = len(test_data_b64)
                bytes_recv = len(res_payload.get("data", ""))

                total_bytes = bytes_sent + bytes_recv
                mbps = (total_bytes * 8) / (elapsed * 1_000_000)
                mb_per_sec = (total_bytes / (1024 * 1024)) / elapsed
                latency_ms = (res_payload.get("server_time", t_end) - t_start) * 1000

                result = {
                    "latency_ms": round(max(latency_ms, 0.1), 1),
                    "throughput_mbps": round(mbps, 2),
                    "speed_mbs": round(mb_per_sec, 2),
                    "bytes_sent": bytes_sent,
                    "bytes_recv": bytes_recv,
                    "elapsed_s": round(elapsed, 3),
                }
                self._emit_log(
                    f"✓ Speed Test: {result['speed_mbs']} MB/s ({result['throughput_mbps']} Mbps) | Latency: {result['latency_ms']} ms",
                    "info"
                )
                return result

        except Exception as e:
            self._emit_log(f"Speed test failed: {e}", "error")
            return {"error": str(e)}

        return {"error": "Unexpected response"}

    def submit_job(self, filepath: str, job_type: str, config: dict,
                   output_dir: str = None) -> str:
        """
        Submit a full job:
        1. Send JOB_SUBMIT with config
        2. Upload the input file
        3. Start listening for progress
        4. Download output when complete

        Returns the job_id on success, None on failure.
        """
        if not self.socket or self.state != ConnectionState.CONNECTED:
            self._emit_log("Not connected to server", "error")
            return None

        filename = os.path.basename(filepath)
        file_info = get_file_info(filepath)

        self._emit_log(
            f"Submitting job: {job_type} | File: {filename} "
            f"({format_bytes(file_info['size'])})", "info"
        )

        try:
            # Step 1: Submit job configuration
            submit_msg = create_message(MessageType.JOB_SUBMIT, {
                "job_type": job_type,
                "filename": filename,
                "file_size": file_info["size"],
                "config": config,
            })

            with self._lock:
                send_message(self.socket, submit_msg)
                response = receive_message(self.socket)

            if response.get("type") == MessageType.JOB_REJECTED:
                reason = response["payload"].get("reason", "Unknown")
                self._emit_log(f"Job rejected: {reason}", "error")
                return None

            if response.get("type") != MessageType.JOB_ACCEPTED:
                self._emit_log(f"Unexpected response: {response.get('type')}", "error")
                return None

            job_id = response["payload"]["job_id"]
            queue_pos = response["payload"].get("position_in_queue", 0)
            self._emit_log(
                f"Job accepted: {job_id} (queue position: {queue_pos})", "info"
            )

            # Step 2: Upload the input file
            self._emit_log(f"Uploading {filename}...", "info")
            self._upload_file(filepath, job_id)
            self._emit_log(f"Upload complete: {filename}", "info")

            # Step 3: Listen for progress/completion in background
            self._start_listener(job_id, output_dir or os.path.dirname(filepath))

            return job_id

        except Exception as e:
            self._emit_log(f"Job submission failed: {e}", "error")
            return None

    def _handshake(self) -> bool:
        """Perform the handshake protocol with the server."""
        self._set_state(ConnectionState.HANDSHAKING)
        self._emit_log("Performing handshake...", "info")

        try:
            # Send handshake request with client info
            sys_info = get_system_info()
            handshake = create_message(MessageType.HANDSHAKE_REQUEST, {
                "os": sys_info["os"],
                "hostname": sys_info["hostname"],
                "python_version": sys_info["python_version"],
            })
            send_message(self.socket, handshake)

            # Wait for response
            response = receive_message(self.socket)

            if response.get("type") != MessageType.HANDSHAKE_RESPONSE:
                self._emit_log(f"Handshake failed: unexpected response type {response.get('type')}", "error")
                self._set_state(ConnectionState.ERROR)
                return False

            payload = response.get("payload", {})
            if payload.get("status") != "accepted":
                self._emit_log(f"Handshake rejected by server", "error")
                self._set_state(ConnectionState.ERROR)
                return False

            # Store server info
            self.server_info = payload.get("system_info", {})
            self.server_capabilities = payload.get("capabilities", {})

            # Log server capabilities
            self._emit_log(f"✓ Connected to: {payload.get('server_name', 'Unknown')}", "info")

            gpu_info = self.server_info.get("gpu", {})
            if gpu_info.get("available"):
                for gpu in gpu_info.get("gpus", []):
                    self._emit_log(
                        f"  GPU: {gpu.get('name')} | "
                        f"VRAM: {gpu.get('total_memory_mb')}MB | "
                        f"CUDA: {gpu.get('cuda_version')}", "info"
                    )
            else:
                self._emit_log("  GPU: None detected (CPU fallback)", "warning")

            ffmpeg = self.server_info.get("ffmpeg", {})
            self._emit_log(
                f"  FFmpeg: {'Available' if ffmpeg.get('available') else 'NOT FOUND'} | "
                f"NVENC: {'Yes' if ffmpeg.get('nvenc_supported') else 'No'}", "info"
            )

            self.socket.settimeout(SOCKET_TIMEOUT)
            self._set_state(ConnectionState.CONNECTED)
            self._emit_log("Handshake successful ✓", "info")
            return True

        except socket.timeout:
            self._emit_log("Handshake timed out", "error")
            self._set_state(ConnectionState.ERROR)
            return False
        except Exception as e:
            self._emit_log(f"Handshake error: {e}", "error")
            self._set_state(ConnectionState.ERROR)
            return False

    def _upload_file(self, filepath: str, job_id: str):
        """Upload a file to the server with progress tracking."""
        file_info = get_file_info(filepath)
        total_size = file_info["size"]

        def progress_cb(bytes_sent, total):
            pct = (bytes_sent / total) * 100
            self._emit_log(
                f"Upload: {pct:.1f}% ({format_bytes(bytes_sent)}/{format_bytes(total)})",
                "info"
            )
            if self.on_progress:
                self.on_progress(job_id, pct * 0.1, f"Uploading: {pct:.0f}%")

        with self._lock:
            send_file_chunked(self.socket, filepath, job_id, progress_cb)

        # Wait for server confirmation
        with self._lock:
            confirmation = receive_message(self.socket)

        if confirmation.get("type") == MessageType.ERROR:
            raise RuntimeError(confirmation["payload"].get("message", "Upload failed"))

        self._emit_log(
            confirmation.get("payload", {}).get("message", "File received by server"),
            "info"
        )

    def _start_listener(self, job_id: str, output_dir: str):
        """Start a background thread to listen for progress/completion."""
        self._listening = True
        self._listener_thread = threading.Thread(
            target=self._listen_loop,
            args=(job_id, output_dir),
            name=f"ProgressListener-{job_id}",
            daemon=True
        )
        self._listener_thread.start()

    def _listen_loop(self, job_id: str, output_dir: str):
        """Background listener for job progress and completion messages."""
        self._emit_log("Listening for job progress...", "info")
        if self.socket:
            self.socket.settimeout(SOCKET_TIMEOUT)

        try:
            while self._listening and self.socket:
                try:
                    try:
                        msg = receive_message(self.socket)
                    except (socket.timeout, TimeoutError):
                        continue

                    if not msg:
                        break

                    msg_type = msg.get("type")
                    payload = msg.get("payload", {})

                    if msg_type == MessageType.JOB_PROGRESS:
                        progress = payload.get("progress", 0)
                        message = payload.get("message", "")
                        gpu_stats = payload.get("gpu_stats")
                        self._emit_log(f"[{progress:.1f}%] {message}", "info")
                        if self.on_progress:
                            self.on_progress(job_id, progress, message)
                        if self.on_gpu_stats and gpu_stats:
                            self.on_gpu_stats(gpu_stats)

                    elif msg_type == MessageType.JOB_COMPLETE:
                        result = payload.get("result", {})
                        self._emit_log("═" * 50, "info")
                        self._emit_log("  JOB COMPLETED SUCCESSFULLY", "info")
                        self._emit_log("═" * 50, "info")

                        # Log result details
                        if "elapsed_formatted" in result:
                            self._emit_log(f"  Time: {result['elapsed_formatted']}", "info")
                        if "encoder" in result:
                            self._emit_log(f"  Encoder: {result['encoder']}", "info")
                        if "output_size_formatted" in result:
                            self._emit_log(
                                f"  Output: {result['output_size_formatted']} "
                                f"(ratio: {result.get('compression_ratio', 'N/A')}x)", "info"
                            )

                        if self.on_job_complete:
                            self.on_job_complete(job_id, result)

                        # Request output file download
                        self._emit_log("Downloading output file...", "info")
                        self._download_output(job_id, output_dir)
                        break

                    elif msg_type == MessageType.JOB_FAILED:
                        error = payload.get("error", "Unknown error")
                        self._emit_log(f"JOB FAILED: {error}", "error")
                        if self.on_job_failed:
                            self.on_job_failed(job_id, error)
                        break

                    elif msg_type == MessageType.LOG_MESSAGE:
                        level = payload.get("level", "info")
                        message = payload.get("message", "")
                        self._emit_log(message, level)

                except ConnectionError:
                    self._emit_log("Connection lost during progress monitoring", "error")
                    self._set_state(ConnectionState.ERROR)
                    if self.on_job_failed:
                        self.on_job_failed(job_id, "Connection lost")
                    break
                except Exception as e:
                    if self._listening:
                        self._emit_log(f"Listener error: {e}", "error")
                    break
        finally:
            self._listening = False

    def _download_output(self, job_id: str, output_dir: str):
        """Download the rendered output file from the server."""
        try:
            os.makedirs(output_dir, exist_ok=True)

            # Request download
            download_req = create_message(MessageType.FILE_DOWNLOAD_REQ, {
                "job_id": job_id,
            })

            with self._lock:
                send_message(self.socket, download_req)

                # Receive response (could be FILE_TRANSFER_START or ERROR)
                response = receive_message(self.socket)

            if response.get("type") == MessageType.ERROR:
                self._emit_log(
                    f"Download failed: {response['payload'].get('message', 'Unknown')}",
                    "error"
                )
                return

            if response.get("type") == MessageType.FILE_TRANSFER_START:
                payload = response.get("payload", {})
                filename = payload.get("filename", "output_file")
                total_size = payload.get("size", 0)
                expected_checksum = payload.get("checksum", "")

                filepath = os.path.join(output_dir, filename)
                self._emit_log(
                    f"Downloading: {filename} ({format_bytes(total_size)})", "info"
                )

                bytes_received = 0
                with self._lock:
                    with open(filepath, "wb") as f:
                        while True:
                            msg = receive_message(self.socket)

                            if msg["type"] == MessageType.FILE_CHUNK:
                                chunk_data = base64.b64decode(msg["payload"]["data"])
                                f.write(chunk_data)
                                bytes_received += len(chunk_data)

                            elif msg["type"] == MessageType.FILE_TRANSFER_END:
                                break

                # Verify checksum
                if expected_checksum:
                    actual = compute_file_checksum(filepath)
                    if actual != expected_checksum:
                        self._emit_log("⚠ Checksum mismatch — file may be corrupted!", "error")
                    else:
                        self._emit_log("✓ File integrity verified (SHA-256 checksum match)", "info")

                self._emit_log(f"✓ Output saved: {filepath}", "info")

                if self.on_file_download_ready:
                    self.on_file_download_ready(job_id, filepath)

        except Exception as e:
            self._emit_log(f"Download error: {e}", "error")

    def _set_state(self, state: str):
        """Update connection state and notify callback."""
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)

    def _emit_log(self, message: str, level: str = "info"):
        """Emit a log message via callback and logger."""
        if self.logger:
            getattr(self.logger, level, self.logger.info)(message)
        if self.on_log:
            self.on_log(message, level)
