#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_fast_diagnostics.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for p in (t, r):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")

def read(p):
    return p.read_text(encoding="latin-1")

def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")

# ----------------------------------------------------------------------
# telegacy.cpp: don't force a physical disk flush for every diagnostic line.
# WriteFile + CloseHandle is enough for this diagnostic build and is vastly
# faster while Telegram is processing hundreds/thousands of startup objects.
# ----------------------------------------------------------------------
s = read(t)

old = """        WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
        FlushFileBuffers(file);
        CloseHandle(file);"""

new = """        WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
        // Do not FlushFileBuffers() here. Startup can emit thousands of
        // diagnostic records; a forced disk flush per line makes the
        // "Updating data..." phase extremely slow.
        CloseHandle(file);"""

if old in s:
    s = s.replace(old, new, 1)
elif "FlushFileBuffers(file);" in s:
    s = s.replace(
        "        FlushFileBuffers(file);\n",
        "",
        1
    )
elif "Do not FlushFileBuffers()" not in s:
    raise SystemExit("Could not locate diagnostic FlushFileBuffers in telegacy.cpp")

write(t, s)

# ----------------------------------------------------------------------
# response.cpp: remove the ultra-hot generic log written for EVERY TL object.
# Keep the targeted logs for dialogs, folders, history, upload.file, exceptions,
# etc. Those are enough to diagnose state without turning startup into a disk
# benchmark.
# ----------------------------------------------------------------------
s = read(r)

generic = (
    '\tdiag_log("response_handler ctor=0x%08X length=%d ack=%d peers=%d '
    'total=%d folders=%d ptr=%p", constructor, length, '
    'acknowledgement ? 1 : 0, peers_count, total_peers_count, '
    'folders_count, unenc_response);\n'
)

if generic in s:
    s = s.replace(generic, "", 1)
elif "response_handler ctor=0x%08X" in s:
    # Conservative fallback for formatting changes: remove only that one line.
    lines = s.splitlines(keepends=True)
    lines = [
        line for line in lines
        if "response_handler ctor=0x%08X" not in line
    ]
    s = "".join(lines)

write(r, s)

print("Optimized Telegacy diagnostic logging for fast startup.")
