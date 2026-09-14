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
# It only changes the policy gates that decide whether ordinary chat photos are
# requested from Telegram. v6.4 later redirects those requests to the full-photo
# loader. IMAGELOADPOLICY==0 remains the explicit no-network-image mode.
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

print(
    "Applied chat media autoload v6.5: ordinary chat photos now request server/full "
    "images whenever image loading is enabled (IMAGELOADPOLICY != 0), including "
    "normal dialogs, history, search context, and media jumps."
)
