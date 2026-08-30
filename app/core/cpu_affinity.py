"""CPU affinity helpers for parallel workers/threads on Linux.

Pinning long-running ffmpeg/render workers to stable CPU sets avoids the
“all processes migrate across all logical CPUs” pattern that causes high
context-switch overhead and uneven core utilization on many-core servers.
"""
from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional, Tuple


def parse_cpu_list(text: str) -> set[int]:
    """Parse a Linux sysfs CPU list such as '0,36' or '0-3' into a set of ints."""
    cpus: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            cpus.update(range(int(start), int(end) + 1))
        else:
            cpus.add(int(part))
    return cpus


def cpu_core_groups() -> List[List[int]]:
    """Return logical CPUs grouped by physical core on Linux.

    Example on a 2-socket/HT host: [[0, 36], [1, 37], ...].  Falls back to one
    logical CPU per group when sysfs topology is unavailable.
    """
    try:
        allowed = set(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        allowed = set(range(os.cpu_count() or 1))

    groups: Dict[Tuple[int, ...], set[int]] = {}
    for cpu in sorted(allowed):
        try:
            with open(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list", encoding="utf-8") as f:
                siblings = tuple(sorted(parse_cpu_list(f.read().strip())))
        except OSError:
            continue
        groups.setdefault(siblings, set()).add(cpu)

    if groups:
        return [sorted(cpus) for cpus in groups.values()]
    return [[cpu] for cpu in sorted(allowed)]


def worker_cpu_affinity(worker_index: int, worker_count: int) -> Optional[List[int]]:
    """Pick a stable CPU set for a parallel worker.

    When there are no more workers than physical cores, pin each worker to one
    physical core (both hyperthreads).  If more workers than cores are
    requested, fall back to a round-robin single logical CPU per worker.
    """
    groups = cpu_core_groups()
    if not groups:
        return None

    if worker_count <= len(groups):
        core = groups[worker_index % len(groups)]
        return core

    all_cpus = sorted(cpu for core in groups for cpu in core)
    return [all_cpus[worker_index % len(all_cpus)]]


def set_process_cpu_affinity(worker_index: int, worker_count: int) -> None:
    """Pin the current process (and its children) to the chosen CPU set."""
    cpus = worker_cpu_affinity(worker_index, worker_count)
    if not cpus or not hasattr(os, "sched_setaffinity"):
        return
    try:
        os.sched_setaffinity(0, cpus)
    except OSError:
        # Non-fatal: some sandboxes/containers restrict affinity changes.
        pass


# Per-thread affinity state used by ThreadPoolExecutor workers.
_thread_lock = threading.Lock()
_thread_core_map: Dict[int, int] = {}
_next_core = 0


def pin_current_thread_to_core() -> None:
    """Pin the calling thread to a stable, distinct physical core.

    Each OS thread receives one core the first time it calls this helper.
    Subsequent calls from the same thread keep the same core, giving analysis
    threads stable CPU locality without pinning the whole process.
    """
    if not hasattr(os, "sched_setaffinity"):
        return

    global _next_core
    ident = threading.get_ident()
    with _thread_lock:
        if ident not in _thread_core_map:
            groups = cpu_core_groups()
            if groups:
                core = groups[_next_core % len(groups)]
            else:
                core = [_next_core % max(1, (os.cpu_count() or 1))]
            _thread_core_map[ident] = core[0]
            _next_core += 1
        cpu = _thread_core_map[ident]

    try:
        os.sched_setaffinity(0, [cpu])
    except OSError:
        pass
