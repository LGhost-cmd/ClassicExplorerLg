#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_chat_video_reactions.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
repo_root = Path(__file__).resolve().parent.parent

# Keep the already-tested v5.8 patch immutable, then layer v5.9 on top.
# The workflow checks out full helper history (fetch-depth: 0), so this blob is
# available locally and does not depend on GitHub API rate limits.
V58_BLOB_SHA = "4f1d7380b5fe0fcd56ecd1225147d2a457a0f101"

try:
    source = subprocess.check_output(
        ["git", "cat-file", "blob", V58_BLOB_SHA],
        cwd=str(repo_root),
        stderr=subprocess.STDOUT,
    ).decode("utf-8")
except Exception as exc:
    raise SystemExit(
        "Could not obtain the pinned chat video/reactions v5.8 patch "
        f"({V58_BLOB_SHA}) from local git history: {exc}"
    )

old_argv = sys.argv[:]
namespace = {
    "__name__": "__main__",
    "__file__": "patch_chat_video_reactions_v58_pinned.py",
}

try:
    sys.argv = [
        "patch_chat_video_reactions_v58_pinned.py",
        str(root),
    ]

    try:
        exec(
            compile(
                source,
                "patch_chat_video_reactions_v58_pinned.py",
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

telegacy_cpp = root / "src" / "telegacy.cpp"
if (
    not telegacy_cpp.exists() or
    "chat_video_full_download_reactions_v58" not in
        telegacy_cpp.read_text(encoding="latin-1")
):
    raise SystemExit(
        "Pinned chat video/reactions v5.8 patch finished, but its marker "
        "was not found in telegacy.cpp."
    )

v59 = Path(__file__).resolve().with_name(
    "patch_chat_video_direct_mouse.py"
)

if not v59.exists():
    raise SystemExit(
        f"Missing direct chat video mouse patch: {v59}"
    )

subprocess.check_call(
    [
        sys.executable,
        str(v59),
        str(root),
    ],
    cwd=str(repo_root),
)

if "chat_video_direct_mouse_v59" not in telegacy_cpp.read_text(
    encoding="latin-1"
):
    raise SystemExit(
        "Chat video direct-mouse v5.9 patch finished, but its marker "
        "was not found in telegacy.cpp."
    )

# Apply the small v6.5 policy-gate fix before v6.0/v6.4. This makes ordinary
# photos request server data in every enabled image mode; v6.4 later redirects
# those requests to the full-photo loader used for crisp chat cards.
v65 = Path(__file__).resolve().with_name(
    "patch_chat_media_autoload_v65.py"
)

if not v65.exists():
    raise SystemExit(
        f"Missing chat media autoload patch: {v65}"
    )

subprocess.check_call(
    [
        sys.executable,
        str(v65),
        str(root),
    ],
    cwd=str(repo_root),
)

if "chat_media_autoload_v65" not in telegacy_cpp.read_text(
    encoding="latin-1"
):
    raise SystemExit(
        "Chat media autoload v6.5 patch finished, but its marker "
        "was not found in telegacy.cpp."
    )

print(
    "Applied chat video/reactions v5.8, direct RichEdit mouse v5.9, and "
    "full-photo autoload policy v6.5."
)
