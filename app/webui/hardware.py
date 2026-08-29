"""
Hardware and FFmpeg encoder detection for headless servers and local machines.

Listing an encoder in ``ffmpeg -encoders`` only means it was compiled in; GPU
encoders still fail at runtime without the actual hardware. We therefore probe
each GPU encoder with a tiny real encode before offering it.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Dict, List, Any, Optional

# (codec, human label, category). Category "cpu_software" encoders are assumed
# to work whenever they are listed; GPU encoders are runtime-probed.
_KNOWN_ENCODERS = [
    # NVIDIA NVENC
    ("h264_nvenc", "NVIDIA NVENC H.264 硬件加速", "gpu_nvidia"),
    ("hevc_nvenc", "NVIDIA NVENC HEVC/H.265 硬件加速", "gpu_nvidia"),
    ("av1_nvenc", "NVIDIA NVENC AV1 硬件加速", "gpu_nvidia"),
    # Intel QSV
    ("h264_qsv", "Intel QSV H.264 硬件加速", "gpu_intel"),
    ("hevc_qsv", "Intel QSV HEVC/H.265 硬件加速", "gpu_intel"),
    ("av1_qsv", "Intel QSV AV1 硬件加速", "gpu_intel"),
    # AMD AMF (Windows / d3d11va)
    ("h264_amf", "AMD AMF H.264 硬件加速", "gpu_amd"),
    ("hevc_amf", "AMD AMF HEVC/H.265 硬件加速", "gpu_amd"),
    ("av1_amf", "AMD AMF AV1 硬件加速", "gpu_amd"),
    # Apple VideoToolbox
    ("h264_videotoolbox", "Apple VideoToolbox H.264 硬件加速", "gpu_apple"),
    ("hevc_videotoolbox", "Apple VideoToolbox HEVC 硬件加速", "gpu_apple"),
    # CPU software encoders
    ("libx264", "H.264 / AVC (CPU 极高兼容性 libx264)", "cpu_software"),
    ("libx265", "H.265 / HEVC (CPU 高效压缩 libx265)", "cpu_software"),
    ("libsvtav1", "AV1 (CPU SVT-AV1 高画质)", "cpu_software"),
]

_GPU_CATEGORIES = ("gpu_nvidia", "gpu_intel", "gpu_amd", "gpu_apple")

_probe_results: Dict[str, bool] = {}


def get_system_info() -> Dict[str, Any]:
    """Retrieve basic system resource and platform info."""
    info: Dict[str, Any] = {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor() or "Unknown",
        "cpu_cores": os_cpu_count(),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "ram_total_gb": _detect_ram_gb(),
    }
    return info


def os_cpu_count() -> int:
    import os

    return os.cpu_count() or 1


def _detect_ram_gb() -> Any:
    try:
        system = platform.system()
        if system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
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

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        if system == "Linux":
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 1)
        if system == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=3,
            )
            return round(int(out.stdout.strip()) / (1024 ** 3), 1)
    except Exception:
        pass
    return "Unknown"


def _listed_encoders() -> List[str]:
    """Codec names compiled into the local ffmpeg build."""
    if not shutil.which("ffmpeg"):
        return []
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []

    listed: List[str] = []
    for line in proc.stdout.splitlines():
        # Format: " V....D libx264   libx264 H.264 / AVC ..." — the first token is
        # the capability flag column, the second token is the codec name.
        tokens = line.split()
        if len(tokens) >= 2 and tokens[0] and set(tokens[0]) <= set("VASFX.BDL"):
            listed.append(tokens[1])
    return listed


def probe_encoder(codec: str, timeout: float = 8.0, force: bool = False) -> bool:
    """Run a tiny real encode to verify an encoder actually works on this machine."""
    if not force and codec in _probe_results:
        return _probe_results[codec]

    ok = False
    if shutil.which("ffmpeg"):
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=black:s=128x128:d=0.1",
                    "-frames:v", "1",
                    "-c:v", codec,
                    "-f", "null", "-",
                ],
                capture_output=True,
                timeout=timeout,
            )
            ok = proc.returncode == 0
        except Exception:
            ok = False

    _probe_results[codec] = ok
    return ok


def detect_available_encoders() -> Dict[str, List[Dict[str, str]]]:
    """
    Detect all available FFmpeg video encoders grouped by hardware vendor / CPU.
    GPU encoders are additionally runtime-probed; failed probes are reported
    with status "unavailable" and excluded from the recommended list.
    """
    results: Dict[str, List[Dict[str, str]]] = {
        "recommended": [],
        "gpu_nvidia": [],
        "gpu_intel": [],
        "gpu_amd": [],
        "gpu_apple": [],
        "cpu_software": [],
    }

    listed = set(_listed_encoders())

    for codec_name, desc, category in _KNOWN_ENCODERS:
        if codec_name not in listed:
            continue
        if category in _GPU_CATEGORIES:
            works = probe_encoder(codec_name)
            entry = {
                "codec": codec_name,
                "name": desc,
                "category": category,
                "status": "available" if works else "unavailable (无可用硬件)",
            }
            results[category].append(entry)
            if works:
                results["recommended"].append(entry)
        else:
            entry = {"codec": codec_name, "name": desc, "category": category, "status": "available"}
            results[category].append(entry)
            results["recommended"].append(entry)

    return results


def get_encoder_dropdown_choices() -> List[tuple[str, str]]:
    """Return a flat list of (Display Label, Codec ID) for UI dropdowns.

    Working GPU encoders come first (fastest), CPU fallbacks last.
    """
    encoders = detect_available_encoders()
    choices: List[tuple[str, str]] = []

    for item in encoders.get("recommended", []):
        if item["category"] in _GPU_CATEGORIES:
            choices.append((f"{item['name']} ({item['codec']}) ⚡", item["codec"]))
        else:
            choices.append((f"{item['name']} ({item['codec']})", item["codec"]))

    if not choices:
        # ffmpeg missing or nothing listed — assume the most common CPU codecs.
        choices = [
            ("H.264 (CPU libx264 - 通用兼容)", "libx264"),
            ("H.265 (CPU libx265 - 高压缩)", "libx265"),
        ]

    return choices


def get_default_encoder(choices: Optional[List[tuple[str, str]]] = None) -> str:
    """Default export codec: prefer libx264 for compatibility, else first choice."""
    choices = choices if choices is not None else get_encoder_dropdown_choices()
    codecs = [c for _, c in choices]
    if "libx264" in codecs:
        return "libx264"
    return codecs[0] if codecs else "libx264"
