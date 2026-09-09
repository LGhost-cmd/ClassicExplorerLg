#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_search_id_fix.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing Telegacy source file: {t}")

s = t.read_text(encoding="latin-1")

if "hChatSearch" not in s:
    print("No custom hChatSearch found; nothing to change.")
    raise SystemExit(0)

changed = False

# Change only the control ID inside the hChatSearch CreateWindow block.
start = s.find("hChatSearch = CreateWindow")
if start >= 0:
    end = s.find(");", start)
    if end >= 0:
        block = s[start:end + 2]
        if "(HMENU)30" in block:
            block2 = block.replace("(HMENU)30", "(HMENU)3000", 1)
            s = s[:start] + block2 + s[end + 2:]
            changed = True

# Change only the case 30 handler which actually references hChatSearch.
search_from = 0
while True:
    pos = s.find("case 30:", search_from)
    if pos < 0:
        break

    window = s[pos:pos + 1800]

    if "hChatSearch" in window or "rebuild_chat_combo_by_name" in window:
        s = s[:pos] + s[pos:].replace("case 30:", "case 3000:", 1)
        changed = True
        break

    search_from = pos + 1

if not changed:
    raise SystemExit(
        "hChatSearch exists, but its old command ID 30 could not be located"
    )

t.write_text(s, encoding="latin-1", newline="\r\n")
print("Changed custom chat-search WM_COMMAND ID 30 -> 3000.")
