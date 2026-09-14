#!/usr/bin/env python3
from pathlib import Path
import re
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


# This patch deliberately runs before the v6.0/v6.4 chat-media layout patches.
# It changes the policy gates that decide whether ordinary chat photos are
# requested from Telegram. IMAGELOADPOLICY==0 remains the explicit
# no-network-image mode.
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

# The workflow invokes v6.4 later. Append v6.6 and then v6.7 to that runner-local
# helper file. v6.6 leaves the experimental full-photo code buildable; v6.7 then
# deliberately disables its get_photo interception so normal chat photos use the
# same native Telegram server-preview queue as Media.
v64 = Path(__file__).resolve().with_name("patch_chat_media_layout_v64.py")
v66 = Path(__file__).resolve().with_name("patch_chat_media_dc_retry_v66.py")
v67 = Path(__file__).resolve().with_name("patch_chat_media_use_native_preview_v67.py")
if not v64.exists():
    raise SystemExit(f"Missing future v6.4 chat media patch: {v64}")
if not v66.exists():
    raise SystemExit(f"Missing v6.6 media-DC retry patch: {v66}")
if not v67.exists():
    raise SystemExit(f"Missing v6.7 native Media preview patch: {v67}")

chain_marker = "# chat_media_native_preview_v67_chain"
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

# chat_media_native_preview_v67_chain
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_media_use_native_preview_v67.py")),
        str(root),
    ]
)
'''
    v64.write_text(v64_text, encoding="utf-8", newline="\n")

print(
    "Applied chat media autoload v6.5: ordinary chat photos request server images "
    "whenever image loading is enabled; v6.4 is chained through v6.6 and finally "
    "v6.7, which restores Telegacy's native Media/get_photo preview queue."
)
