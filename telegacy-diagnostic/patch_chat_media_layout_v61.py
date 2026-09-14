#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_layout_v61.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
repo_root = Path(__file__).resolve().parent.parent

# Preserve the already-tested v6.1 layout patch, then layer the thumbnail
# quality fix on top. Full helper history is checked out by the workflow.
V61_BLOB_SHA = "f192905540f4cdd0e9fef5b6f4c593d91b543647"

try:
    source = subprocess.check_output(
        ["git", "cat-file", "blob", V61_BLOB_SHA],
        cwd=str(repo_root),
        stderr=subprocess.STDOUT,
    ).decode("utf-8")
except Exception as exc:
    raise SystemExit(
        "Could not obtain the pinned chat media v6.1 patch "
        f"({V61_BLOB_SHA}) from local git history: {exc}"
    )

old_argv = sys.argv[:]
namespace = {
    "__name__": "__main__",
    "__file__": "patch_chat_media_layout_v61_pinned.py",
}

try:
    sys.argv = [
        "patch_chat_media_layout_v61_pinned.py",
        str(root),
    ]
    try:
        exec(
            compile(
                source,
                "patch_chat_media_layout_v61_pinned.py",
                "exec",
            ),
            namespace,
            namespace,
        )
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise
finally:
    sys.argv = old_argv

hp = root / "src" / "helpers.cpp"
m = root / "src" / "message.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"

for path in (hp, m, r, t):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


if "chat_media_layout_v61" not in read(t):
    raise SystemExit(
        "Pinned chat media v6.1 patch finished, but its marker was not found."
    )

# ---------------------------------------------------------------------------
# High-quality previews.
#
# Telegacy's original get_photo() always asks Telegram for thumb type "m".
# More importantly, IMAGELOADPOLICY==1 never asks the server at all: it keeps
# the tiny stripped JPEG embedded in the message and our large 288x216 card
# merely magnifies those few pixels. That is the pixelation visible in chat.
#
# For normal photos request Telegram's "x" preview when the message advertises
# x/y/w sizes (x is normally around the 800px class and comfortably fits the
# fixed chat card). Keep m for smaller photos and for document/video thumbs.
# ---------------------------------------------------------------------------
s = read(hp)
old = "\tunenc_query[offset_query] = 1;\n\tunenc_query[offset_query + 1] = 'm';"
new = r'''\tunenc_query[offset_query] = 1;

\t// chat_media_hq_preview_v62
\tchar chat_preview_type = 'm';
\tif (
\t\t!rce &&
\t\tdocument &&
\t\tdocument->photo_size != 1 &&
\t\tdocument->photo_size != 3
\t) {
\t\t// Normal Telegram photos commonly expose s/m/x/y/w.  x gives a crisp
\t\t// preview for a 288x216 logical-pixel card without fetching the original.
\t\tif (
\t\t\tdocument->photo_size == 'x' ||
\t\t\tdocument->photo_size == 'y' ||
\t\t\tdocument->photo_size == 'w'
\t\t) {
\t\t\tchat_preview_type = 'x';
\t\t} else if (
\t\t\tdocument->photo_size == 'm' ||
\t\t\tdocument->photo_size == 's'
\t\t) {
\t\t\tchat_preview_type = document->photo_size;
\t\t}
\t}

\tunenc_query[offset_query + 1] = chat_preview_type;'''.replace('\\t', '\t')
if old not in s:
    raise SystemExit("Could not locate Telegram thumbnail type selection in get_photo().")
s = s.replace(old, new, 1)
write(hp, s)

# If images are enabled at all, replace the embedded stripped thumbnail with a
# real Telegram preview. Mode 0 still means no network image loading.
s = read(m)
count = s.count("IMAGELOADPOLICY == 2")
if count < 2:
    raise SystemExit(
        f"Expected chat image auto-load checks in message.cpp, found {count}."
    )
s = s.replace("IMAGELOADPOLICY == 2", "IMAGELOADPOLICY != 0")
write(m, s)

# History/search/context loading has separate one-at-a-time queues. Apply the
# same rule there so older messages also upgrade from stripped to clean thumbs.
s = read(r)
count = s.count("IMAGELOADPOLICY == 2")
if count < 3:
    raise SystemExit(
        f"Expected history image auto-load checks in response.cpp, found {count}."
    )
s = s.replace("IMAGELOADPOLICY == 2", "IMAGELOADPOLICY != 0")
write(r, s)

# Marker lives in telegacy.cpp so the final generated artifact is easy to audit.
s = read(t)
marker = "// chat_media_layout_v61"
if marker not in s:
    raise SystemExit("Could not locate chat media v6.1 marker.")
s = s.replace(
    marker,
    marker + "\n// chat_media_hq_preview_v62",
    1,
)
write(t, s)

checks = {
    hp: [
        "chat_media_hq_preview_v62",
        "char chat_preview_type = 'm';",
        "chat_preview_type = 'x';",
        "unenc_query[offset_query + 1] = chat_preview_type;",
    ],
    m: ["IMAGELOADPOLICY != 0"],
    r: ["IMAGELOADPOLICY != 0"],
    t: ["chat_media_hq_preview_v62"],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"Chat media HQ preview v6.2 verification failed in "
                f"{path.name}: {token}"
            )

print(
    "Applied chat media v6.1 plus v6.2 HQ previews: displayed photos now "
    "upgrade from stripped JPEGs to real Telegram x/m thumbnails while the "
    "288x216 framed block layout remains unchanged."
)
