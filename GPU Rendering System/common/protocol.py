"""
protocol.py - Shared Communication Protocol Definitions
========================================================

Defines the message format, command types, and serialization/deserialization
logic used by both client and server for structured network communication.

Protocol Format:
    [4-byte header (message length)] + [JSON payload]

Message Structure:
    {
        "type": "<MESSAGE_TYPE>",
        "timestamp": <unix_timestamp>,
        "payload": { ... }
    }
"""

import json
import struct
import hashlib
import time
import os

# ─── Protocol Version ─────────────────────────────────────────────
PROTOCOL_VERSION = "1.0.0"

# ─── Message Types ────────────────────────────────────────────────
class MessageType:
    """Enumeration of all supported message types in the protocol."""
    # Handshake & Connection
    HANDSHAKE_REQUEST   = "HANDSHAKE_REQUEST"
    HANDSHAKE_RESPONSE  = "HANDSHAKE_RESPONSE"
    PING                = "PING"
    PONG                = "PONG"

    # Job Lifecycle
    JOB_SUBMIT          = "JOB_SUBMIT"
    JOB_ACCEPTED        = "JOB_ACCEPTED"
    JOB_REJECTED        = "JOB_REJECTED"
    JOB_PROGRESS        = "JOB_PROGRESS"
    JOB_COMPLETE        = "JOB_COMPLETE"
    JOB_FAILED          = "JOB_FAILED"
    JOB_CANCEL          = "JOB_CANCEL"

    # File Transfer
    FILE_TRANSFER_START = "FILE_TRANSFER_START"
    FILE_CHUNK          = "FILE_CHUNK"
    FILE_TRANSFER_END   = "FILE_TRANSFER_END"
    FILE_DOWNLOAD_REQ   = "FILE_DOWNLOAD_REQ"
    FILE_DOWNLOAD_START = "FILE_DOWNLOAD_START"
    FILE_DOWNLOAD_CHUNK = "FILE_DOWNLOAD_CHUNK"
    FILE_DOWNLOAD_END   = "FILE_DOWNLOAD_END"

    # System
    SERVER_STATUS       = "SERVER_STATUS"
    ERROR               = "ERROR"
    DISCONNECT          = "DISCONNECT"
    LOG_MESSAGE         = "LOG_MESSAGE"

    # GPU Monitoring & Speed Test
    GPU_STATS_REQUEST   = "GPU_STATS_REQUEST"
    GPU_STATS           = "GPU_STATS"
    SPEED_TEST_REQ      = "SPEED_TEST_REQ"
    SPEED_TEST_RES      = "SPEED_TEST_RES"


# ─── Default Configuration ────────────────────────────────────────
DEFAULT_SERVER_PORT     = 9850
CHUNK_SIZE              = 65536  # 64KB chunks for file transfer
HEADER_SIZE             = 4      # 4 bytes for message length header
SOCKET_TIMEOUT          = 300    # 5 minutes for heavy render jobs
HANDSHAKE_TIMEOUT       = 15     # seconds
MAX_MESSAGE_SIZE        = 50 * 1024 * 1024  # 50MB max message size


# ─── Render Presets ───────────────────────────────────────────────
RENDER_PRESETS = {
    "ultrafast": {"description": "Fastest encoding, lowest quality", "nvenc_preset": "p1"},
    "fast":      {"description": "Fast encoding, good quality",      "nvenc_preset": "p4"},
    "medium":    {"description": "Balanced speed and quality",       "nvenc_preset": "p5"},
    "slow":      {"description": "Slow encoding, high quality",     "nvenc_preset": "p6"},
    "quality":   {"description": "Highest quality, slowest",        "nvenc_preset": "p7"},
}

RESOLUTIONS = {
    "480p":  {"width": 854,  "height": 480},
    "720p":  {"width": 1280, "height": 720},
    "1080p": {"width": 1920, "height": 1080},
    "1440p": {"width": 2560, "height": 1440},
    "4K":    {"width": 3840, "height": 2160},
}

BITRATES = {
    "Low (2 Mbps)":       "2M",
    "Medium (5 Mbps)":    "5M",
    "High (10 Mbps)":     "10M",
    "Very High (20 Mbps)":"20M",
    "Ultra (50 Mbps)":    "50M",
}


# ─── Message Construction ────────────────────────────────────────
def create_message(msg_type: str, payload: dict = None) -> dict:
    """Create a protocol-compliant message dictionary."""
    return {
        "type": msg_type,
        "version": PROTOCOL_VERSION,
        "timestamp": time.time(),
        "payload": payload or {}
    }


def serialize_message(message: dict) -> bytes:
    """Serialize a message dict into bytes with a 4-byte length header."""
    json_bytes = json.dumps(message).encode("utf-8")
    header = struct.pack("!I", len(json_bytes))
    return header + json_bytes


def deserialize_header(header_bytes: bytes) -> int:
    """Extract message length from 4-byte header."""
    if len(header_bytes) != HEADER_SIZE:
        raise ValueError(f"Invalid header size: expected {HEADER_SIZE}, got {len(header_bytes)}")
    return struct.unpack("!I", header_bytes)[0]


def deserialize_message(json_bytes: bytes) -> dict:
    """Deserialize JSON bytes into a message dictionary."""
    return json.loads(json_bytes.decode("utf-8"))


# ─── File Utilities ───────────────────────────────────────────────
def compute_file_checksum(filepath: str, algorithm: str = "sha256") -> str:
    """Compute the SHA-256 checksum of a file for integrity validation."""
    hasher = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_bytes_checksum(data: bytes, algorithm: str = "sha256") -> str:
    """Compute the SHA-256 checksum of a bytes object."""
    hasher = hashlib.new(algorithm)
    hasher.update(data)
    return hasher.hexdigest()


def get_file_info(filepath: str) -> dict:
    """Get metadata about a file."""
    stat = os.stat(filepath)
    return {
        "filename": os.path.basename(filepath),
        "size": stat.st_size,
        "checksum": compute_file_checksum(filepath),
        "extension": os.path.splitext(filepath)[1].lower(),
    }


# ─── Network I/O Helpers ─────────────────────────────────────────
def send_message(sock, message: dict):
    """Send a protocol message over a socket with length-prefixed framing."""
    data = serialize_message(message)
    sock.sendall(data)


def receive_message(sock) -> dict:
    """Receive a protocol message from a socket with length-prefixed framing."""
    # Read the 4-byte header
    header = _recv_exact(sock, HEADER_SIZE)
    if not header:
        raise ConnectionError("Connection closed while reading header")

    msg_length = deserialize_header(header)

    if msg_length > MAX_MESSAGE_SIZE:
        raise ValueError(f"Message too large: {msg_length} bytes (max {MAX_MESSAGE_SIZE})")

    # Read the message body
    body = _recv_exact(sock, msg_length)
    if not body:
        raise ConnectionError("Connection closed while reading message body")

    return deserialize_message(body)


def send_file_chunked(sock, filepath: str, job_id: str, progress_callback=None):
    """Send a file in chunks over the socket with progress reporting."""
    file_info = get_file_info(filepath)
    total_size = file_info["size"]

    # Send FILE_TRANSFER_START
    start_msg = create_message(MessageType.FILE_TRANSFER_START, {
        "job_id": job_id,
        "filename": file_info["filename"],
        "size": total_size,
        "checksum": file_info["checksum"],
    })
    send_message(sock, start_msg)

    # Send file chunks
    bytes_sent = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            import base64
            chunk_msg = create_message(MessageType.FILE_CHUNK, {
                "job_id": job_id,
                "data": base64.b64encode(chunk).decode("ascii"),
                "offset": bytes_sent,
            })
            send_message(sock, chunk_msg)
            bytes_sent += len(chunk)

            if progress_callback:
                progress_callback(bytes_sent, total_size)

    # Send FILE_TRANSFER_END
    end_msg = create_message(MessageType.FILE_TRANSFER_END, {
        "job_id": job_id,
        "total_bytes": bytes_sent,
        "checksum": file_info["checksum"],
    })
    send_message(sock, end_msg)


def receive_file_chunked(sock, output_dir: str, expected_info: dict = None) -> str:
    """Receive a file in chunks from the socket and save to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, expected_info.get("filename", "received_file"))
    total_size = expected_info.get("size", 0)
    expected_checksum = expected_info.get("checksum", "")

    bytes_received = 0
    import base64

    with open(filepath, "wb") as f:
        while True:
            msg = receive_message(sock)

            if msg["type"] == MessageType.FILE_CHUNK:
                chunk_data = base64.b64decode(msg["payload"]["data"])
                f.write(chunk_data)
                bytes_received += len(chunk_data)

            elif msg["type"] == MessageType.FILE_TRANSFER_END:
                break

            elif msg["type"] == MessageType.ERROR:
                raise RuntimeError(f"File transfer error: {msg['payload'].get('message', 'Unknown')}")

    # Verify checksum
    if expected_checksum:
        actual_checksum = compute_file_checksum(filepath)
        if actual_checksum != expected_checksum:
            os.remove(filepath)
            raise ValueError(
                f"Checksum mismatch! Expected: {expected_checksum[:16]}..., "
                f"Got: {actual_checksum[:16]}..."
            )

    return filepath


def _recv_exact(sock, num_bytes: int) -> bytes:
    """Receive exactly num_bytes from the socket."""
    import socket
    data = bytearray()
    while len(data) < num_bytes:
        remaining = num_bytes - len(data)
        try:
            chunk = sock.recv(min(remaining, 65536))
        except (socket.timeout, TimeoutError):
            if len(data) == 0:
                raise  # Re-raise timeout if no header bytes read yet
            continue
        except (ConnectionResetError, OSError):
            return None
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)
