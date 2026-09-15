#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_autoload_v65.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
m = root / "src" / "message.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"

for path in (m, r, t):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


# Keep chat image autoload enabled for every non-zero image policy. The later
# v6.4 interceptor handles these requests with the custom serial full-photo
# loader; we deliberately do NOT restore Telegacy 1.0.4's native get_photo
# request path here because runs #70/#72 showed a repeatable memcpy crash while
# opening history-heavy chats.
if "chat_media_autoload_v65" in read(t):
    print("Chat media autoload v6.5 already applied.")
    raise SystemExit(0)

s = read(m)
old = "if (!to_front && IMAGELOADPOLICY == 2) get_photo(NULL, &document, &dcInfoMain);"
new = "if (!to_front && IMAGELOADPOLICY != 0) get_photo(NULL, &document, &dcInfoMain); // chat_media_autoload_v65"
count = s.count(old)
if count != 1:
    raise SystemExit(
        f"Expected exactly one ordinary-photo autoload gate in message.cpp, found {count}."
    )
s = s.replace(old, new, 1)
write(m, s)

s = read(r)
pattern = re.compile(r"IMAGELOADPOLICY == 2(?=\s*&&\s*documents_count_old)")
s, count = pattern.subn("IMAGELOADPOLICY != 0", s)
if count != 3:
    raise SystemExit(
        f"Expected three history/context photo autoload gates in response.cpp, found {count}."
    )
write(r, s)

s = read(t)
anchor = "// chat_video_direct_mouse_v59"
if anchor not in s:
    raise SystemExit("Could not locate direct-mouse marker for v6.5 audit marker.")
s = s.replace(anchor, anchor + "\n// chat_media_autoload_v65", 1)
write(t, s)

checks = {
    m: [
        "IMAGELOADPOLICY != 0) get_photo(NULL, &document, &dcInfoMain); // chat_media_autoload_v65",
    ],
    r: [
        "IMAGELOADPOLICY != 0 &&",
    ],
    t: [
        "chat_media_autoload_v65",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"Chat media autoload v6.5 verification failed in {path.name}: {token}"
            )

# Guard the normal getHistory parser before later chat-media layout patches run.
# The crash reproduced in runs #70/#72/#74 occurs while parsing the decompressed
# history page, before the image downloader is reached. v6.9 reuses the already
# installed length-aware Media message envelope and SEH wrapper so an unsupported
# modern Telegram message aborts that page safely instead of reading past the RPC
# buffer in read_le()/memcpy.
v69 = Path(__file__).resolve().with_name("patch_history_parser_guard_v69.py")
if not v69.exists():
    raise SystemExit(f"Missing guarded history parser patch: {v69}")
subprocess.check_call([sys.executable, str(v69), str(root)])

# The workflow invokes v6.4 later. Append only v6.6 to that runner-local helper
# file. v6.7/v6.8 are intentionally NOT chained: switching chat photos back to
# the legacy native get_photo implementation caused a repeatable memcpy access
# violation on chat open. v6.4 + v6.6 remains the active photo-loading path.
v64 = Path(__file__).resolve().with_name("patch_chat_media_layout_v64.py")
v66 = Path(__file__).resolve().with_name("patch_chat_media_dc_retry_v66.py")
if not v64.exists():
    raise SystemExit(f"Missing future v6.4 chat media patch: {v64}")
if not v66.exists():
    raise SystemExit(f"Missing v6.6 media-DC retry patch: {v66}")

chain_marker = "# chat_media_dc_retry_v66_chain"
v64_text = v64.read_text(encoding="utf-8")
if chain_marker not in v64_text:
    v64_text += r'''

# chat_media_dc_retry_v66_chain
import subprocess as _chat_media_v66_subprocess
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_media_dc_retry_v66.py")),
        str(root),
    ]
)
'''
    v64.write_text(v64_text, encoding="utf-8", newline="\n")

print(
    "Applied chat media autoload v6.5 in stable mode: ordinary chat photos request "
    "server images whenever image loading is enabled; normal history is protected "
    "by v6.9; v6.4 is chained only through v6.6. The crashing native v6.7/v6.8 "
    "path remains disabled."
)
