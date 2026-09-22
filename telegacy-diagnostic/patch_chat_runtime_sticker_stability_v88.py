#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_runtime_sticker_stability_v88.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"

for path in (h, t):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


def function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")

    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")

    depth = 0
    in_string = False
    in_char = False
    in_line = False
    in_block = False
    escaped = False
    i = brace

    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""

        if in_line:
            if c == "\n":
                in_line = False
            i += 1
            continue

        if in_block:
            if c == "*" and n == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "'":
                in_char = False
            i += 1
            continue

        if c == "/" and n == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and n == "*":
            in_block = True
            i += 2
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "'":
            in_char = True
            i += 1
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

        i += 1

    raise SystemExit(f"Could not locate closing brace: {signature}")


s = read(t)

if "chat_runtime_sticker_stability_v88" in s:
    print("Chat runtime/sticker stability v8.8 already applied.")
    raise SystemExit(0)

for token in (
    "chat_media_identity_stability_v87",
    "chat v87 WebM paused without release",
    "media_chat_sticker_after_scroll_v87",
    "chat_media_stickers_forward_links_v84",
):
    if token not in s:
        raise SystemExit(f"Required predecessor marker missing: {token}")


# ---------------------------------------------------------------------------
# A) Keep sticker geometry stable even when RichEdit briefly refuses to map an
# off-edge OLE cp through EM_POSFROMCHAR. The last known origin is adjusted by
# the exact EM_GETSCROLLPOS delta. This is specifically for the v8.7 trace where
# the same WebM stayed alive but repeatedly toggled to paused while scrolling.
# ---------------------------------------------------------------------------
struct_anchor = "    bool video_paused_for_visibility;\n};"
if struct_anchor not in s:
    raise SystemExit("Could not locate ChatAnimatedSticker tail.")

struct_extra = r'''    bool video_paused_for_visibility;

    // chat_runtime_sticker_stability_v88
    POINT last_origin_v88;
    POINT last_scroll_v88;
    DWORD last_geometry_tick_v88;
    int last_cp_v88;
    bool have_geometry_v88;
};'''

s = s.replace(struct_anchor, struct_extra, 1)

init_anchor = "    sticker->video_paused_for_visibility = false;"
if init_anchor not in s:
    raise SystemExit("Could not locate animated sticker initialization.")

s = s.replace(
    init_anchor,
    init_anchor + r'''
    sticker->last_origin_v88.x = 0;
    sticker->last_origin_v88.y = 0;
    sticker->last_scroll_v88.x = 0;
    sticker->last_scroll_v88.y = 0;
    sticker->last_geometry_tick_v88 = 0;
    sticker->last_cp_v88 = -1;
    sticker->have_geometry_v88 = false;''',
    1,
)

ts, te = function_range(
    s,
    "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe("
)

new_timer = r'''static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(
    HWND,
    UINT,
    UINT_PTR,
    DWORD
) {
    if (
        !chat ||
        media_chat_animated_stickers.empty()
    ) {
        return;
    }

    RECT viewport = {0};

    SendMessageW(
        chat,
        EM_GETRECT,
        0,
        (LPARAM)&viewport
    );

    if (
        viewport.right <= viewport.left ||
        viewport.bottom <= viewport.top
    ) {
        GetClientRect(
            chat,
            &viewport
        );
    }

    POINT scroll = {0, 0};
    BOOL have_scroll =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );

    DWORD now = GetTickCount();
    bool webm_claimed = false;

    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {
        ChatAnimatedSticker* sticker =
            media_chat_animated_stickers[i];

        if (!sticker)
            continue;

        Document* document =
            media_chat_sticker_find_document(
                sticker
            );

        if (
            !document ||
            document->max <= document->min
        ) {
            if (sticker->window)
                ShowWindow(sticker->window, SW_HIDE);

            if (
                sticker->video &&
                !sticker->video_paused_for_visibility
            ) {
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;
            }

            sticker->visible = false;
            sticker->have_geometry_v88 = false;
            continue;
        }

        int sticker_cp =
            media_chat_sticker_find_ole_cp(
                document
            );

        if (sticker_cp < 0) {
            media_chat_sticker_ensure_anchor_ole_v85(
                document
            );

            sticker_cp =
                media_chat_sticker_find_ole_cp(
                    document
                );
        }

        POINTL origin = {0, 0};
        bool direct_geometry = false;

        if (sticker_cp >= 0) {
            LRESULT pos_result =
                SendMessageW(
                    chat,
                    EM_POSFROMCHAR,
                    (WPARAM)&origin,
                    (LPARAM)sticker_cp
                );

            if (pos_result != -1) {
                direct_geometry = true;

                sticker->last_origin_v88.x =
                    (LONG)origin.x;
                sticker->last_origin_v88.y =
                    (LONG)origin.y;

                if (have_scroll) {
                    sticker->last_scroll_v88 =
                        scroll;
                }

                sticker->last_geometry_tick_v88 =
                    now;
                sticker->last_cp_v88 =
                    sticker_cp;
                sticker->have_geometry_v88 =
                    true;
            }
        }

        bool inferred_geometry = false;

        if (
            !direct_geometry &&
            sticker->have_geometry_v88 &&
            (
                now -
                sticker->last_geometry_tick_v88
            ) <= 1500
        ) {
            origin.x =
                sticker->last_origin_v88.x;
            origin.y =
                sticker->last_origin_v88.y;

            if (have_scroll) {
                origin.x -=
                    scroll.x -
                    sticker->last_scroll_v88.x;
                origin.y -=
                    scroll.y -
                    sticker->last_scroll_v88.y;

                sticker->last_origin_v88.x =
                    (LONG)origin.x;
                sticker->last_origin_v88.y =
                    (LONG)origin.y;
                sticker->last_scroll_v88 =
                    scroll;
                sticker->last_geometry_tick_v88 =
                    now;
            }

            inferred_geometry = true;
        }

        if (
            !direct_geometry &&
            !inferred_geometry
        ) {
            if (sticker->window)
                ShowWindow(sticker->window, SW_HIDE);

            if (
                sticker->video &&
                !sticker->video_paused_for_visibility
            ) {
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;

                diag_log(
                    "chat v88 WebM paused no geometry cp=%d path=%ls",
                    sticker_cp,
                    sticker->path
                );
            }

            sticker->visible = false;
            continue;
        }

        int width =
            media_chat_sticker_card_width();

        int height =
            media_chat_sticker_card_height();

        RECT card = {
            (LONG)origin.x,
            (LONG)origin.y,
            (LONG)origin.x + width,
            (LONG)origin.y + height
        };

        RECT visible = {0};

        bool in_view =
            IntersectRect(
                &visible,
                &card,
                &viewport
            ) != FALSE;

        if (!in_view) {
            if (sticker->window)
                ShowWindow(sticker->window, SW_HIDE);

            if (
                sticker->video &&
                !sticker->video_paused_for_visibility
            ) {
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;

                diag_log(
                    "chat v88 WebM paused truly offscreen y=%ld scroll=%ld path=%ls",
                    (LONG)origin.y,
                    have_scroll ? scroll.y : 0,
                    sticker->path
                );
            }

            sticker->visible = false;
            continue;
        }

        if (
            !media_chat_sticker_create_window(
                sticker
            )
        ) {
            continue;
        }

        int clip_left =
            visible.left - card.left;
        int clip_top =
            visible.top - card.top;
        int clip_right =
            visible.right - card.left;
        int clip_bottom =
            visible.bottom - card.top;

        bool full_visible =
            clip_left == 0 &&
            clip_top == 0 &&
            clip_right == width &&
            clip_bottom == height;

        if (full_visible) {
            SetWindowRgn(
                sticker->window,
                NULL,
                FALSE
            );
        } else {
            HRGN clip =
                CreateRectRgn(
                    clip_left,
                    clip_top,
                    clip_right,
                    clip_bottom
                );

            if (clip) {
                if (
                    !SetWindowRgn(
                        sticker->window,
                        clip,
                        FALSE
                    )
                ) {
                    DeleteObject(clip);
                }
            }
        }

        SetWindowPos(
            sticker->window,
            HWND_TOP,
            origin.x,
            origin.y,
            width,
            height,
            SWP_NOACTIVATE |
                SWP_SHOWWINDOW
        );

        sticker->visible = true;

        if (sticker->kind == 1) {
            if (
                media_chat_sticker_load_lottie(
                    sticker
                )
            ) {
                media_chat_sticker_render_lottie(
                    sticker,
                    now
                );
            }
        } else if (sticker->kind == 3) {
            if (
                media_chat_sticker_load_webp_v84(
                    sticker
                )
            ) {
                InvalidateRect(
                    sticker->window,
                    NULL,
                    FALSE
                );
            }
        } else if (sticker->kind == 2) {
            if (!webm_claimed) {
                webm_claimed = true;

                if (
                    media_chat_sticker_load_video(
                        sticker
                    )
                ) {
                    if (
                        sticker->video_paused_for_visibility
                    ) {
                        sticker->video->Play();
                        sticker->video_paused_for_visibility =
                            false;

                        diag_log(
                            "chat v88 WebM resumed inferred=%d cp=%d path=%ls",
                            inferred_geometry ? 1 : 0,
                            sticker_cp,
                            sticker->path
                        );
                    }

                    if (
                        sticker->next_frame_tick == 0 ||
                        (LONG)(
                            now -
                            sticker->next_frame_tick
                        ) >= 0
                    ) {
                        media_chat_sticker_loop_video(
                            sticker
                        );

                        sticker->next_frame_tick =
                            now + 250;
                    }
                }
            } else if (
                sticker->video &&
                !sticker->video_paused_for_visibility
            ) {
                // Keep the MFPlay object and the overlay itself alive. Only
                // serialize playback if two WebM stickers are simultaneously
                // visible.
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;
            }
        }
    }
}'''

s = s[:ts] + new_timer + s[te:]


# ---------------------------------------------------------------------------
# B) Local crash boundary around asynchronous RichEdit OLE replacement.
# The new trace ended after "upload.file state" and before the normal v84
# replacement diagnostic, so contain exactly this mutation path and record the
# phase if RichEdit/COM raises an SEH exception.
# ---------------------------------------------------------------------------
fs, fe = function_range(
    s,
    "bool media_chat_replace_loaded_bitmap("
)

replace_func = s[fs:fe]

old_sig = "bool media_chat_replace_loaded_bitmap("
if old_sig not in replace_func:
    raise SystemExit("Could not locate async media replace signature.")

replace_func = replace_func.replace(
    old_sig,
    "static bool media_chat_replace_loaded_bitmap_unsafe_v88(",
    1,
)

validation_anchor = r'''    if (!document || !decoded || !chat)
        return false;
'''
if validation_anchor not in replace_func:
    raise SystemExit("Could not locate async media validation.")

replace_func = replace_func.replace(
    validation_anchor,
    validation_anchor +
    "\n    media_chat_replace_stage_v88 = 1;\n",
    1,
)

for old, new, label in (
    (
        "    HBITMAP decorated =\n",
        "    media_chat_replace_stage_v88 = 2;\n\n    HBITMAP decorated =\n",
        "decorate",
    ),
    (
        "    if (was_drawchat)\n        SendMessageW(\n",
        "    media_chat_replace_stage_v88 = 3;\n\n    if (was_drawchat)\n        SendMessageW(\n",
        "redraw",
    ),
    (
        "    SendMessageW(\n        chat,\n        EM_REPLACESEL,\n",
        "    media_chat_replace_stage_v88 = 4;\n\n    SendMessageW(\n        chat,\n        EM_REPLACESEL,\n",
        "delete",
    ),
    (
        "    insert_image(\n        chat,\n        NULL,\n        display\n    );",
        "    media_chat_replace_stage_v88 = 5;\n\n    insert_image(\n        chat,\n        NULL,\n        display\n    );\n\n    media_chat_replace_stage_v88 = 6;",
        "insert",
    ),
):
    if old not in replace_func:
        raise SystemExit(
            f"Could not locate async media {label} phase."
        )
    replace_func = replace_func.replace(old, new, 1)

stage_decl = r'''// chat_runtime_sticker_stability_v88
static volatile LONG media_chat_replace_stage_v88 = 0;

'''

wrapper = r'''

bool media_chat_replace_loaded_bitmap(
    Document* document,
    HBITMAP decoded
) {
    if (!document || !decoded || !chat)
        return false;

    BITMAP bitmap = {0};

    if (
        GetObjectW(
            decoded,
            sizeof(bitmap),
            &bitmap
        ) != sizeof(bitmap) ||
        bitmap.bmWidth <= 0 ||
        bitmap.bmHeight <= 0 ||
        bitmap.bmWidth > 16384 ||
        bitmap.bmHeight > 16384
    ) {
        diag_log(
            "chat v88 async media rejected invalid bitmap min=%d size=%ldx%ld",
            document->min,
            (LONG)bitmap.bmWidth,
            (LONG)bitmap.bmHeight
        );
        return false;
    }

    media_chat_replace_stage_v88 = 0;

    __try {
        bool result =
            media_chat_replace_loaded_bitmap_unsafe_v88(
                document,
                decoded
            );

        media_chat_replace_stage_v88 = 0;
        return result;
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        DWORD code = GetExceptionCode();
        LONG stage =
            media_chat_replace_stage_v88;

        media_chat_replace_stage_v88 = 0;

        diag_log(
            "chat v88 recovered async media replace exception=0x%08lX stage=%ld min=%d type=%d",
            code,
            stage,
            document ? document->min : -1,
            document ? (int)document->photo_size : -1
        );

        if (chat) {
            SendMessageW(
                chat,
                WM_SETREDRAW,
                TRUE,
                0
            );

            InvalidateRect(
                chat,
                NULL,
                FALSE
            );
        }

        return false;
    }
}'''

s = (
    s[:fs] +
    stage_decl +
    replace_func +
    wrapper +
    s[fe:]
)

write(t, s)

checks = [
    "chat_runtime_sticker_stability_v88",
    "last_origin_v88",
    "last_scroll_v88",
    "last_geometry_tick_v88",
    "chat v88 WebM paused no geometry",
    "chat v88 WebM paused truly offscreen",
    "chat v88 WebM resumed inferred=",
    "media_chat_replace_loaded_bitmap_unsafe_v88",
    "media_chat_replace_stage_v88 = 5",
    "chat v88 recovered async media replace exception",
    "chat v88 async media rejected invalid bitmap",
]

data = read(t)
for token in checks:
    if token not in data:
        raise SystemExit(
            f"v8.8 verification failed in telegacy.cpp: {token}"
        )

print(
    "Applied chat runtime/sticker stability v8.8: animated sticker overlays "
    "retain scroll-delta geometry when EM_POSFROMCHAR transiently fails at a "
    "viewport edge, preventing false visibility pauses; asynchronous RichEdit "
    "bitmap replacement now validates decoded HBITMAPs and has a local staged "
    "SEH crash boundary that restores redraw instead of dropping the dialog."
)
