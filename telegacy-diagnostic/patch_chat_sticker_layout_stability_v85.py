#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_sticker_layout_stability_v85.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing expected Telegacy file: {t}")


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

if "chat_sticker_layout_stability_v85" in s:
    print("Chat sticker layout/stability v8.5 already applied.")
    raise SystemExit(0)

for token in (
    "chat_media_stickers_forward_links_v84",
    "chat_animated_sticker_stability_v83",
    "media_chat_sticker_timer_proc_unsafe",
    "media_chat_sticker_create_window",
):
    if token not in s:
        raise SystemExit(f"Required predecessor marker missing: {token}")


# ---------------------------------------------------------------------------
# 1) Stickers are square content. 288x216 was inherited from photo cards and
# made WebM/TGS stickers oversized and distorted. Use a compact square card.
# ---------------------------------------------------------------------------
ws, we = function_range(s, "static int media_chat_sticker_card_width()")
new_width = r'''// chat_sticker_layout_stability_v85
static int media_chat_sticker_card_width() {
    int effective_dpi =
        dpi > 0
            ? dpi
            : 96;

    return MulDiv(
        180,
        effective_dpi,
        96
    );
}'''
s = s[:ws] + new_width + s[we:]

hs, he = function_range(s, "static int media_chat_sticker_card_height()")
new_height = r'''static int media_chat_sticker_card_height() {
    int effective_dpi =
        dpi > 0
            ? dpi
            : 96;

    return MulDiv(
        180,
        effective_dpi,
        96
    );
}'''
s = s[:hs] + new_height + s[he:]


# ---------------------------------------------------------------------------
# 2) If Telegram supplied no sticker thumbnail OLE, reserve real RichEdit
# vertical space before placing the animated overlay. v8.4 could anchor directly
# to the one-character placeholder, but that line is only font-height, so the
# 180px overlay floated over neighbouring messages.
# ---------------------------------------------------------------------------
insert_at = s.find("static bool media_chat_sticker_load_lottie(")
if insert_at < 0:
    raise SystemExit("Could not locate sticker loader insertion point.")

anchor_helpers = r'''
static int media_chat_sticker_find_ole_cp(
    Document* document
);

static HBITMAP media_chat_sticker_make_anchor_bitmap_v85() {
    int width =
        media_chat_sticker_card_width();

    int height =
        media_chat_sticker_card_height();

    if (width <= 0 || height <= 0)
        return NULL;

    BITMAPINFO info;
    memset(
        &info,
        0,
        sizeof(info)
    );

    info.bmiHeader.biSize =
        sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth =
        width;
    info.bmiHeader.biHeight =
        -height;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;

    void* bits = NULL;

    HDC dc =
        GetDC(chat);

    HBITMAP bitmap =
        CreateDIBSection(
            dc,
            &info,
            DIB_RGB_COLORS,
            &bits,
            NULL,
            0
        );

    if (dc)
        ReleaseDC(chat, dc);

    if (!bitmap || !bits)
        return bitmap;

    COLORREF background =
        GetSysColor(COLOR_WINDOW);

    unsigned int pixel =
        (GetRValue(background) << 16) |
        (GetGValue(background) << 8) |
        GetBValue(background);

    unsigned int* out =
        (unsigned int*)bits;

    for (int i = 0; i < width * height; i++)
        out[i] = pixel;

    return bitmap;
}

static bool media_chat_sticker_ensure_anchor_ole_v85(
    Document* document
) {
    if (
        !chat ||
        !document ||
        document->photo_size != 1 ||
        document->min < 0
    ) {
        return false;
    }

    int existing =
        media_chat_sticker_find_ole_cp(
            document
        );

    if (existing >= 0) {
        document->min = existing;
        document->max = existing + 1;
        return true;
    }

    HBITMAP anchor =
        media_chat_sticker_make_anchor_bitmap_v85();

    if (!anchor)
        return false;

    CHARRANGE selection = {0};

    SendMessageW(
        chat,
        EM_EXGETSEL,
        0,
        (LPARAM)&selection
    );

    POINT viewport = {0, 0};

    BOOL have_viewport =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&viewport
        );

    bool was_drawchat = drawchat;

    if (was_drawchat) {
        SendMessageW(
            chat,
            WM_SETREDRAW,
            FALSE,
            0
        );
    }

    int cp = document->min;

    SendMessageW(
        chat,
        EM_SETSEL,
        cp,
        cp + 1
    );

    SendMessageW(
        chat,
        EM_REPLACESEL,
        FALSE,
        (LPARAM)L""
    );

    insert_image(
        chat,
        NULL,
        anchor
    );

    DeleteObject(anchor);

    document->min = cp;
    document->max = cp + 1;

    if (
        selection.cpMin >= 0 &&
        selection.cpMax >= 0
    ) {
        SendMessageW(
            chat,
            EM_EXSETSEL,
            0,
            (LPARAM)&selection
        );
    }

    if (have_viewport) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&viewport
        );
    }

    if (was_drawchat) {
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

    if (have_viewport) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&viewport
        );
    }

    int anchored =
        media_chat_sticker_find_ole_cp(
            document
        );

    bool ok =
        anchored >= 0;

    if (ok) {
        document->min = anchored;
        document->max = anchored + 1;
    }

    diag_log(
        "chat v85 sticker anchor OLE inserted cp=%d resolved=%d ok=%d",
        cp,
        anchored,
        ok ? 1 : 0
    );

    return ok;
}

'''
s = s[:insert_at] + anchor_helpers + s[insert_at:]


# Ensure layout reservation before activation.
as_, ae = function_range(s, "static void media_chat_sticker_activate(")
activate = s[as_:ae]

kind_anchor = r'''    if (!kind)
        return;

    ChatAnimatedSticker* sticker ='''
if kind_anchor not in activate:
    raise SystemExit("Could not locate sticker activate kind guard.")

activate = activate.replace(
    kind_anchor,
    r'''    if (!kind)
        return;

    if (
        !media_chat_sticker_ensure_anchor_ole_v85(
            document
        )
    ) {
        diag_log(
            "chat v85 sticker activation skipped: no stable layout anchor min=%d",
            document->min
        );
        return;
    }

    ChatAnimatedSticker* sticker =''',
    1
)

s = s[:as_] + activate + s[ae:]


# ---------------------------------------------------------------------------
# 3) Child overlay is clipped to RichEdit's formatting rectangle, not merely the
# full window client. This keeps partially visible stickers from painting across
# margins/scrollbar-adjacent areas while scrolling.
# Also animate only one WebM player at a time and probe its playback position at
# 250ms instead of hammering MFPlay every 33ms.
# ---------------------------------------------------------------------------
timer_helper_pos = s.find(
    "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe("
)

if timer_helper_pos < 0:
    raise SystemExit("Could not locate v8.3 sticker timer for v8.5.")

video_release_helper = r'''
static void media_chat_sticker_release_video_v85(
    ChatAnimatedSticker* sticker
) {
    if (!sticker || !sticker->video)
        return;

    sticker->video->Pause();
    sticker->video->Stop();
    sticker->video->Shutdown();
    sticker->video->Release();
    sticker->video = NULL;
    sticker->video_paused_for_visibility = true;
    sticker->next_frame_tick = 0;

    diag_log(
        "chat v85 released inactive WebM player path=%ls",
        sticker->path
    );
}

'''

s = (
    s[:timer_helper_pos] +
    video_release_helper +
    s[timer_helper_pos:]
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

    DWORD now =
        GetTickCount();

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
            if (sticker->window) {
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );
            }

            if (sticker->kind == 2) {
                media_chat_sticker_release_video_v85(
                    sticker
                );
            } else {
                media_chat_sticker_release_video_v85(
                    sticker
                );
            }

            sticker->visible = false;
            continue;
        }

        int sticker_cp =
            media_chat_sticker_find_ole_cp(
                document
            );

        if (sticker_cp < 0) {
            if (
                !media_chat_sticker_ensure_anchor_ole_v85(
                    document
                )
            ) {
                if (sticker->window)
                    ShowWindow(sticker->window, SW_HIDE);

                sticker->visible = false;
                continue;
            }

            sticker_cp =
                media_chat_sticker_find_ole_cp(
                    document
                );
        }

        if (sticker_cp < 0)
            continue;

        POINTL origin = {0, 0};

        LRESULT result =
            SendMessageW(
                chat,
                EM_POSFROMCHAR,
                (WPARAM)&origin,
                (LPARAM)sticker_cp
            );

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
            result != -1 &&
            IntersectRect(
                &visible,
                &card,
                &viewport
            );

        if (!in_view) {
            if (sticker->window)
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );

            if (sticker->kind == 2) {
                media_chat_sticker_release_video_v85(
                    sticker
                );
            } else if (
                sticker->video &&
                !sticker->video_paused_for_visibility
            ) {
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;
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
                    DeleteObject(
                        clip
                    );
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
                        sticker->video_paused_for_visibility = false;
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
                sticker->video->Pause();
                sticker->video_paused_for_visibility = true;
            }
        }
    }
}'''

s = s[:ts] + new_timer + s[te:]


# ---------------------------------------------------------------------------
# 4) Window-proc crash boundary and safer teardown. MFPlay can deliver paint/
# window messages while a player is being shut down. Detach user data and hide
# the child before releasing the player; stop the timer before destroying the
# runtime list.
# ---------------------------------------------------------------------------
wps, wpe = function_range(
    s,
    "static LRESULT CALLBACK media_chat_sticker_window_proc("
)
window_func = s[wps:wpe]

window_func = window_func.replace(
    "static LRESULT CALLBACK media_chat_sticker_window_proc(",
    "static LRESULT CALLBACK media_chat_sticker_window_proc_unsafe(",
    1
)

window_wrapper = r'''

static LRESULT CALLBACK media_chat_sticker_window_proc(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    __try {
        return media_chat_sticker_window_proc_unsafe(
            hwnd,
            msg,
            wParam,
            lParam
        );
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        diag_log(
            "chat v85 recovered sticker window exception msg=0x%04X",
            (unsigned int)msg
        );

        return DefWindowProcW(
            hwnd,
            msg,
            wParam,
            lParam
        );
    }
}'''

s = s[:wps] + window_func + window_wrapper + s[wpe:]


ds, de = function_range(
    s,
    "static void media_chat_sticker_destroy("
)

new_destroy = r'''static void media_chat_sticker_destroy(
    ChatAnimatedSticker* sticker
) {
    if (!sticker)
        return;

    if (sticker->window) {
        ShowWindow(
            sticker->window,
            SW_HIDE
        );

        SetWindowLongPtrW(
            sticker->window,
            GWLP_USERDATA,
            0
        );

        SetWindowRgn(
            sticker->window,
            NULL,
            FALSE
        );
    }

    media_chat_sticker_release_video_v85(
        sticker
    );

    if (sticker->window) {
        DestroyWindow(
            sticker->window
        );
        sticker->window = NULL;
    }

    if (sticker->lottie) {
        delete sticker->lottie;
        sticker->lottie = NULL;
    }

    delete sticker;
}'''

s = s[:ds] + new_destroy + s[de:]


cs, ce = function_range(
    s,
    "void media_chat_animated_sticker_clear()"
)

clear_func = s[cs:ce]

old_clear_timer = r'''    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {'''

if old_clear_timer not in clear_func:
    raise SystemExit("Could not locate sticker clear loop.")

clear_func = clear_func.replace(
    old_clear_timer,
    r'''    // Stop callbacks before COM/video/window teardown. Shutdown may pump
    // messages, so leaving WM_TIMER armed here is unnecessarily risky.
    if (media_chat_sticker_timer) {
        KillTimer(
            NULL,
            media_chat_sticker_timer
        );
        media_chat_sticker_timer = 0;
    }

    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {''',
    1
)

old_late_kill = r'''
    if (media_chat_sticker_timer) {
        KillTimer(
            NULL,
            media_chat_sticker_timer
        );
        media_chat_sticker_timer = 0;
    }
'''
clear_func = clear_func.replace(
    old_late_kill,
    "",
    1
)

s = s[:cs] + clear_func + s[ce:]


# Improve the v8.3 timer exception fallback: hide/pause all runtime windows if
# the timer is disabled due to a recovered exception.
wrapper_start = s.find(
    'diag_log(\n            "chat v83 recovered animated-sticker timer exception"'
)
if wrapper_start < 0:
    raise SystemExit("Could not locate v8.3 timer exception wrapper.")

kill_pos = s.find(
    "        if (media_chat_sticker_timer) {",
    wrapper_start
)
if kill_pos < 0:
    raise SystemExit("Could not locate timer kill in v8.3 wrapper.")

fallback = r'''        for (
            int i = 0;
            i < (int)media_chat_animated_stickers.size();
            i++
        ) {
            ChatAnimatedSticker* sticker =
                media_chat_animated_stickers[i];

            if (!sticker)
                continue;

            if (sticker->window)
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );

            if (sticker->video)
                sticker->video->Pause();

            sticker->visible = false;
            sticker->video_paused_for_visibility = true;
        }

'''

s = s[:kill_pos] + fallback + s[kill_pos:]


write(t, s)

checks = [
    "chat_sticker_layout_stability_v85",
    "media_chat_sticker_ensure_anchor_ole_v85",
    "chat v85 sticker anchor OLE inserted",
    "MulDiv(\n        180,",
    "EM_GETRECT",
    "IntersectRect(",
    "SetWindowRgn(",
    "bool webm_claimed = false",
    "media_chat_sticker_release_video_v85",
    "chat v85 released inactive WebM player",
    "now + 250",
    "media_chat_sticker_window_proc_unsafe",
    "chat v85 recovered sticker window exception",
    "Stop callbacks before COM/video/window teardown",
]

data = read(t)

for token in checks:
    if token not in data:
        raise SystemExit(
            f"v8.5 verification failed in telegacy.cpp: {token}"
        )

print(
    "Applied sticker layout/stability v8.5: animated/static sticker overlays now "
    "reserve a real square RichEdit OLE row, render at a compact 180x180 logical "
    "size, clip to the RichEdit formatting viewport, serialize visible WebM "
    "playback with lower-frequency MFPlay probing, and use safer timer/window/"
    "COM teardown plus an additional sticker-window crash boundary."
)
