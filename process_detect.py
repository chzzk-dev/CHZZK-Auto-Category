"""Conservative process-name detection for game auto-detection.

On Windows this module uses Toolhelp32Snapshot and reads only executable names
from the OS process snapshot. It does not open game processes, read memory,
enumerate modules, inject code, or request debug privileges.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess


TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', wintypes.WCHAR * MAX_PATH),
    ]


def _windows_process_names():
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    create_snapshot.restype = wintypes.HANDLE

    process_first = kernel32.Process32FirstW
    process_first.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    process_first.restype = wintypes.BOOL

    process_next = kernel32.Process32NextW
    process_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    process_next.restype = wintypes.BOOL

    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    snapshot = create_snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, 0, INVALID_HANDLE_VALUE):
        error = ctypes.get_last_error()
        raise OSError(error, 'CreateToolhelp32Snapshot failed')

    names = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not process_first(snapshot, ctypes.byref(entry)):
            error = ctypes.get_last_error()
            # ERROR_NO_MORE_FILES (18) is equivalent to an empty snapshot.
            if error == 18:
                return []
            raise OSError(error, 'Process32FirstW failed')

        while True:
            name = str(entry.szExeFile or '').strip()
            if name:
                names.add(name)
            if not process_next(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error in (0, 18):
                    break
                raise OSError(error, 'Process32NextW failed')
    finally:
        close_handle(snapshot)

    return sorted(names, key=str.casefold)


def _portable_process_names():
    """Development-only fallback for non-Windows hosts."""
    try:
        result = subprocess.run(
            ['ps', '-A', '-o', 'comm='],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return []
    names = {line.strip().rsplit('/', 1)[-1] for line in result.stdout.splitlines() if line.strip()}
    return sorted(names, key=str.casefold)


def process_names():
    if os.name == 'nt':
        return _windows_process_names()
    return _portable_process_names()
