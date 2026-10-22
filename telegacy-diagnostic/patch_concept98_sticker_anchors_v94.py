#!/usr/bin/env python3
"""v9.4: Keep sticker overlays anchored to exactly the matching RichEdit OLE."""
from pathlib import Path
import sys

if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_sticker_anchors_v94.py <Telegacy src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_sticker_anchors_v94" in s:
    print("Sticker anchors v9.4 already applied");raise SystemExit(0)
if "chat_runtime_sticker_stability_v88" not in s:
    raise SystemExit("Expected v8.8 sticker runtime missing")
if "concept98_interactions_v92" not in s:
    raise SystemExit("Expected Concept 98 missing")

# v8.2 used the nearest OLE within 16 RichEdit characters and was allowed to
# bind to an adjacent photo. On loaded albums/media-heavy chats this shows an
# animation over the wrong photo, creating the sliced duplicate visible in the
# reported screenshot. Do not bind to an unrelated OLE by proximity.
old=r'''        if (
            distance > 1 &&
            (
                distance > 16 ||
                !large_object
            )
        ) {
            continue;
        }'''
new=r'''        // concept98_sticker_anchors_v94
        // Never borrow an adjacent PHOTO OLE just because its cp happens
        // to be within 16 characters of the sticker document.
        if (distance > 1 || !large_object)
            continue;'''
if old not in s:raise SystemExit("Exact OLE selection anchor missing")
s=s.replace(old,new,1)

# The v8.8 timer silently generated new sticker placeholder OLEs when no
# matching image could be found. On albums this can append another bitmap and
# shift document cp values, corrupting other media. Preserve the cached
# thumbnail and never mutate RichEdit from the animation timer.
old_timer=r'''        if (sticker_cp < 0) {
            media_chat_sticker_ensure_anchor_ole_v85(
                document
            );

            sticker_cp =
                media_chat_sticker_find_ole_cp(
                    document
                );
        }'''
new_timer=r'''        // concept98_sticker_anchors_v94: fail closed on missing anchor;
        // no OLE insertion is permitted from a 33ms animation timer.
        if (sticker_cp < 0) {
            if (sticker->window)
                ShowWindow(sticker->window, SW_HIDE);
            if (sticker->video && !sticker->video_paused_for_visibility) {
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;
            }
            sticker->have_geometry_v88 = false;
            sticker->visible = false;
            continue;
        }'''
if old_timer not in s:raise SystemExit("v88 auto-OLE regeneration missing")
s=s.replace(old_timer,new_timer,1)

# Reuse geometries ONLY for the very same cp. If new history/messages shifted
# the OLE, RichEdit must return a fresh location before any animation resumes.
old_geom=r'''            sticker->have_geometry_v88 &&
            (
                now -
                sticker->last_geometry_tick_v88
            ) <= 1500'''
new_geom=r'''            sticker->have_geometry_v88 &&
            sticker_cp == sticker->last_cp_v88 &&
            (
                now -
                sticker->last_geometry_tick_v88
            ) <= 350'''
if old_geom not in s:raise SystemExit("v88 cached geometry path missing")
s=s.replace(old_geom,new_geom,1)

# A truly wrong/empty image window should never cover a user's real chat photo.
# Record the refusal once per inactive transition, not 30 times a second.
s=s.replace(
'''        if (sticker_cp < 0) {
            if (sticker->window)''',
'''        if (sticker_cp < 0) {
            if (sticker->visible)
                diag_log("concept98 v94 sticker missing exact OLE; overlay hidden");
            if (sticker->window)''',1)

p.write_text(s,encoding="latin-1",newline="\r\n")
for marker in (
    "concept98_sticker_anchors_v94",
    "distance > 1 || !large_object",
    "sticker_cp == sticker->last_cp_v88",
    "concept98 v94 sticker missing exact OLE; overlay hidden"
):
    if marker not in s:raise SystemExit("v9.4 verification missing "+marker)
print("Applied Concept 98 v9.4: animated sticker overlays cannot hijack "
      "neighboring photo OLEs, cannot insert duplicates from timer and never "
      "reuse geometry from a different anchor.")
