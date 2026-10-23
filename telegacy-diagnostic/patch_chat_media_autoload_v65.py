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
# v6.4 -> v6.6 -> v7.0 -> v7.1 -> v7.2 -> v7.3 -> v7.4 -> v7.5 -> v7.6 -> v7.7 -> v7.8 -> v7.9 -> v8.0 -> v8.1 -> v8.2 -> v8.3 -> v8.4 -> v8.5 -> v8.6 -> v8.7 -> v8.8 -> v8.9 -> v9.0 -> v9.1 -> v9.2 -> v9.3 -> v9.4 -> v9.5 -> v9.6 -> v9.7 -> v9.8 -> v9.9 -> v10.0 -> v10.1 -> v10.2 -> v10.3 -> v10.4.
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
v86 = Path(__file__).resolve().with_name("patch_chat_viewport_media_stability_v86.py")
v87 = Path(__file__).resolve().with_name("patch_chat_media_identity_stability_v87.py")
v88 = Path(__file__).resolve().with_name("patch_chat_runtime_sticker_stability_v88.py")
v89 = Path(__file__).resolve().with_name("patch_safe_jpeg_decode_v89.py")
v90 = Path(__file__).resolve().with_name("patch_concept98_shell_v90.py")
v91 = Path(__file__).resolve().with_name("patch_concept98_polish_v91.py")
v92 = Path(__file__).resolve().with_name("patch_concept98_interactions_v92.py")
v93 = Path(__file__).resolve().with_name("patch_concept98_avatars_notifications_v93.py")
v94 = Path(__file__).resolve().with_name("patch_concept98_sticker_anchors_v94.py")
v95 = Path(__file__).resolve().with_name("patch_concept98_pixel_icons_v95.py")
v96 = Path(__file__).resolve().with_name("patch_concept98_integrity_v96.py")
v97 = Path(__file__).resolve().with_name("patch_concept98_notification_integrity_v97.py")
v98 = Path(__file__).resolve().with_name("patch_concept98_avatar_thread_safety_v98.py")
v99 = Path(__file__).resolve().with_name("patch_concept98_fast_avatars_v99.py")
v100 = Path(__file__).resolve().with_name("patch_concept98_viewport_v100.py")
v101 = Path(__file__).resolve().with_name("patch_concept98_full_photo_cache_v101.py")
v102 = Path(__file__).resolve().with_name("patch_concept98_visual_finish_v102.py")
v103 = Path(__file__).resolve().with_name("patch_concept98_photo_hit_v103.py")
v104 = Path(__file__).resolve().with_name("patch_concept98_static_webp_identity_v104.py")
v105 = Path(__file__).resolve().with_name("patch_concept98_clean_media_v105.py")
v106 = Path(__file__).resolve().with_name("patch_concept98_media_recovery_v106.py")
v107 = Path(__file__).resolve().with_name("patch_concept98_borrowed_icons_v107.py")
v108 = Path(__file__).resolve().with_name("patch_concept98_cache_first_v108.py")
v109 = Path(__file__).resolve().with_name("patch_concept98_sticker_first_frame_v109.py")
v110 = Path(__file__).resolve().with_name("patch_concept98_shell_polish_v110.py")
v111 = Path(__file__).resolve().with_name("patch_concept98_photo_ole_identity_v111.py")
v112 = Path(__file__).resolve().with_name("patch_concept98_skip_hidden_thumbs_v112.py")
v113 = Path(__file__).resolve().with_name("patch_concept98_palette_stability_v113.py")
v114 = Path(__file__).resolve().with_name("patch_concept98_avatar_dc_v114.py")
v115 = Path(__file__).resolve().with_name("patch_concept98_webm_fallback_v115.py")
v116 = Path(__file__).resolve().with_name("patch_concept98_no_phantom_media_v116.py")
v117 = Path(__file__).resolve().with_name("patch_concept98_sticker_size_alpha_v117.py")
v118 = Path(__file__).resolve().with_name("patch_concept98_typography_v118.py")
v119 = Path(__file__).resolve().with_name("patch_concept98_forum_topics_v119.py")
v120 = Path(__file__).resolve().with_name("patch_concept98_forum_media_v120.py")
v121 = Path(__file__).resolve().with_name("patch_concept98_forum_search_cached_photo_v121.py")
v122 = Path(__file__).resolve().with_name("patch_concept98_ui_finish_v122.py")
v123 = Path(__file__).resolve().with_name("patch_concept98_photo_reply_v123.py")
v124 = Path(__file__).resolve().with_name("patch_concept98_page_stage_v124.py")
v125 = Path(__file__).resolve().with_name("patch_concept98_seamless_paging_v125.py")
v126 = Path(__file__).resolve().with_name("patch_concept98_photo_visibility_v126.py")
v127 = Path(__file__).resolve().with_name("patch_concept98_readable_ui_v127.py")
v128 = Path(__file__).resolve().with_name("patch_concept98_chat_polish_v128.py")
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
    ("v8.6", v86),
    ("v8.7", v87),
    ("v8.8", v88),
    ("v8.9", v89),
    ("v9.0", v90),
    ("v9.1", v91),
    ("v9.2", v92),
    ("v9.3", v93),
    ("v9.4", v94),
    ("v9.5", v95),
    ("v9.6", v96),
    ("v9.7", v97),
    ("v9.8", v98),
    ("v9.9", v99),
    ("v10.0", v100),
    ("v10.1", v101),
    ("v10.2", v102),
    ("v10.3", v103),
    ("v10.4", v104),
    ("v10.5", v105),
    ("v10.6", v106),
    ("v10.7", v107),
    ("v10.8", v108),
    ("v10.9", v109),
    ("v11.0", v110),
    ("v11.1", v111),
    ("v11.2", v112),
    ("v11.3", v113),
    ("v11.4", v114),
    ("v11.5", v115),
    ("v11.6", v116),
    ("v11.7", v117),
    ("v11.8", v118),
    ("v11.9", v119),
    ("v12.0", v120),
    ("v12.1", v121),
    ("v12.2", v122),
    ("v12.3", v123),
    ("v12.4", v124),
    ("v12.5", v125),
    ("v12.6", v126),
    ("v12.7", v127),
    ("v12.8", v128),
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
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_viewport_media_stability_v86.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_media_identity_stability_v87.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_chat_runtime_sticker_stability_v88.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_safe_jpeg_decode_v89.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_shell_v90.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_polish_v91.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_interactions_v92.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_avatars_notifications_v93.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_sticker_anchors_v94.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_pixel_icons_v95.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_integrity_v96.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_notification_integrity_v97.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_avatar_thread_safety_v98.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_fast_avatars_v99.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_viewport_v100.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_full_photo_cache_v101.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_visual_finish_v102.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_photo_hit_v103.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_static_webp_identity_v104.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_clean_media_v105.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_media_recovery_v106.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_borrowed_icons_v107.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_cache_first_v108.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_sticker_first_frame_v109.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_shell_polish_v110.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_photo_ole_identity_v111.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_skip_hidden_thumbs_v112.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_palette_stability_v113.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_avatar_dc_v114.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_webm_fallback_v115.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_no_phantom_media_v116.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_sticker_size_alpha_v117.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_typography_v118.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_forum_topics_v119.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_forum_media_v120.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_forum_search_cached_photo_v121.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_ui_finish_v122.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_photo_reply_v123.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_page_stage_v124.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_seamless_paging_v125.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_photo_visibility_v126.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_readable_ui_v127.py")),
        str(root),
    ]
)
_chat_media_v66_subprocess.check_call(
    [
        sys.executable,
        str(Path(__file__).resolve().with_name("patch_concept98_chat_polish_v128.py")),
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
    "v8.5 bounded square sticker layout plus safer MFPlay lifetime handling, and "
    "v8.6 stable scrolling, exact clicked-photo replacement, and OLE-backed static stickers, "
    "plus v8.7 exact clicked-OLE photo replacement and persistent WebM players across scrolling, "
    "and v8.8 cached scroll geometry plus staged async RichEdit replacement crash containment, "
    "plus v8.9 non-fatal JPEG thumbnail decoding for upload.file responses, "
    "and v9.0 native Concept 98 two-pane shell and notifications, "
    "followed by v9.1 compact layout, real global search and popup refinements, "
    "and v9.2 adjustable sidebar plus keyboard/context-menu interactions, "
    "v9.3 lazy real avatars/notification DND, v9.4 strict OLE sticker anchoring, "
    "and v9.5 classic pixel-action icon controls, v9.6 avatar lifetime and chat-header fixes, "
    "v9.7 notification/DND unread semantics hardening, v9.8 thread-safe avatars, "
    "v9.9 disk thumbnails/parallel requests, v10 verified media geometry/bootstrap, "
    "v10.1 full photo disk cache, v10.2 original pixel art, v10.3 clicked OLE "
    "correction, v10.4 transaction-checked static WebP replacement, "
    "v10.5 clean photo loading and strict sticker geometry, "
    "v10.6 full photos/avatars/WebM posters and v10.7 archived Win98 icon assets."
)
