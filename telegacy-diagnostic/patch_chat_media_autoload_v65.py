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
# chat-media patches provide a server preview while retaining a stripped-image
# fallback so a failed/migrated preview can never leave a featureless blank card.
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
# The history-specific guard remains useful even with the wider v7.1 response
# boundary because it can reject an unsupported message before any partial UI
# mutation occurs.
v69 = Path(__file__).resolve().with_name("patch_history_parser_guard_v69.py")
if not v69.exists():
    raise SystemExit(f"Missing guarded history parser patch: {v69}")
subprocess.check_call([sys.executable, str(v69), str(root)])

# The workflow invokes v6.4 later. Make that final layout step run the complete
# transport/UI chain in a deterministic order:
#   v6.4 -> v6.6 (DC retry -> v7.0 native preview) -> v7.1 resilience.
# v7.1 is deliberately last because it restores the stripped-photo fallback,
# enforces RichEdit block boundaries for photo/video cards, and adds the broad
# response parser exception boundary.
v64 = Path(__file__).resolve().with_name("patch_chat_media_layout_v64.py")
v66 = Path(__file__).resolve().with_name("patch_chat_media_dc_retry_v66.py")
v71 = Path(__file__).resolve().with_name("patch_chat_media_resilience_v71.py")
if not v64.exists():
    raise SystemExit(f"Missing future v6.4 chat media patch: {v64}")
if not v66.exists():
    raise SystemExit(f"Missing v6.6 media-DC retry patch: {v66}")
if not v71.exists():
    raise SystemExit(f"Missing v7.1 chat/media resilience patch: {v71}")

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
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_media_resilience_v71.py")),
        str(root),
    ]
)
'''
    v64.write_text(v64_text, encoding="utf-8", newline="\n")

print(
    "Applied chat media autoload v6.5: all enabled image modes request server "
    "previews; history uses the v6.9 guard; the final v6.4 step is chained through "
    "v6.6/v7.0 and then v7.1 resilience."
)
