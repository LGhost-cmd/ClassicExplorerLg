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
    m: ["IMAGELOADPOLICY != 0) get_photo(NULL, &document, &dcInfoMain); // chat_media_autoload_v65"],
    r: ["IMAGELOADPOLICY != 0 &&"],
    t: ["chat_media_autoload_v65"],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat media autoload v6.5 verification failed in {path.name}: {token}")

# Protect history before the later layout patches mutate the same parser.
v69 = Path(__file__).resolve().with_name("patch_history_parser_guard_v69.py")
if not v69.exists():
    raise SystemExit(f"Missing guarded history parser patch: {v69}")
subprocess.check_call([sys.executable, str(v69), str(root)])

# The normal workflow calls v6.4 last. Extend that runner-local script so the
# complete final chain is deterministic:
# v6.4 -> v6.6 -> v7.0 -> v7.1 -> v7.2 -> v7.3 -> v7.4 -> v7.5 -> v7.6 -> v7.7 -> v7.8 -> v7.9 -> v8.0 -> v8.1 -> v8.2 -> v8.3 -> v8.4 -> v8.5.
v64 = Path(__file__).resolve().with_name("patch_chat_media_layout_v64.py")
v66 = Path(__file__).resolve().with_name("patch_chat_media_dc_retry_v66.py")
v71 = Path(__file__).resolve().with_name("patch_chat_media_resilience_v71.py")
v72 = Path(__file__).resolve().with_name("patch_dialog_rows_v72.py")
v73 = Path(__file__).resolve().with_name("patch_media_inplace_upgrade_v73.py")
v74 = Path(__file__).resolve().with_name("patch_chat_scope_sync_v74_runner.py")
v75 = Path(__file__).resolve().with_name("patch_chat_interaction_paging_v75_runner.py")
v76 = Path(__file__).resolve().with_name("patch_chat_runtime_recovery_v76.py")
v77 = Path(__file__).resolve().with_name("patch_chat_channel_media_layout_v77.py")
v78 = Path(__file__).resolve().with_name("patch_chat_photo_click_download_v78.py")
v79 = Path(__file__).resolve().with_name("patch_chat_global_peer_photo_hit_v79.py")
v80 = Path(__file__).resolve().with_name("patch_chat_media_ole_rebind_v80.py")
v81 = Path(__file__).resolve().with_name("patch_chat_photo_open_sticker_viewport_v81.py")
v82 = Path(__file__).resolve().with_name("patch_chat_animated_stickers_v82.py")
v83 = Path(__file__).resolve().with_name("patch_chat_animated_sticker_stability_v83.py")
v84 = Path(__file__).resolve().with_name("patch_chat_media_stickers_forward_links_v84.py")
v85 = Path(__file__).resolve().with_name("patch_chat_sticker_layout_stability_v85.py")
for label, path in (
    ("v6.4", v64),
    ("v6.6", v66),
    ("v7.1", v71),
    ("v7.2", v72),
    ("v7.3", v73),
    ("v7.4", v74),
    ("v7.5", v75),
    ("v7.6", v76),
    ("v7.7", v77),
    ("v7.8", v78),
    ("v7.9", v79),
    ("v8.0", v80),
    ("v8.1", v81),
    ("v8.2", v82),
    ("v8.3", v83),
    ("v8.4", v84),
    ("v8.5", v85),
):
    if not path.exists():
        raise SystemExit(f"Missing {label} patch: {path}")

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
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_dialog_rows_v72.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_media_inplace_upgrade_v73.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_scope_sync_v74_runner.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_interaction_paging_v75_runner.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_runtime_recovery_v76.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_channel_media_layout_v77.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_photo_click_download_v78.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_global_peer_photo_hit_v79.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_media_ole_rebind_v80.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_photo_open_sticker_viewport_v81.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_animated_stickers_v82.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_animated_sticker_stability_v83.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_media_stickers_forward_links_v84.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_sticker_layout_stability_v85.py")),
        str(root),
    ]
)
'''
    v64.write_text(v64_text, encoding="utf-8", newline="\n")

print(
    "Applied chat media autoload v6.5: image autoload is enabled, history uses "
    "v6.9, and the final v6.4 runner is chained through v6.6/v7.0, v7.1 "
    "media/parser resilience, v7.2 dialog cleanup, v7.3 in-place media upgrade, "
    "v7.4 My Chats/global search plus periodic update reconciliation, v7.5 "
    "photo retry/top-bar spacing/history pagination hardening, and v7.6 "
    "orphan-date/media-queue runtime recovery, and v7.7 search-channel photo "
    "transport plus OLE-safe media placement, and v7.8 single-click full-photo "
    "upgrade plus double-click persistent download/open, and v7.9 exact global-peer "
    "identity parsing plus OLE-based photo hit testing, v8.0 CF_BITMAP "
    "OLE-to-Document rebinding for stale media ranges, and v8.1 deterministic "
    "double-click open, pixel-stable OLE replacement, sticker thumbnails, "
    "v8.2 inline looping TGS/WebM sticker animation, v8.3 safe cache paths "
    "plus animation crash containment, and v8.4 strict media replacement, "
    "static/animated sticker fallback rendering, plus forwarded-origin links, "
    "and v8.5 bounded square sticker layout plus safer MFPlay lifetime handling."
)
