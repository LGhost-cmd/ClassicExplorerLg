#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_viewport_media_stability_v86.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
hp = root / "src" / "helpers.cpp"
r = root / "src" / "response.cpp"
p = root / "src" / "procs.cpp"

for path in (h, t, hp, r, p):
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
if "chat_viewport_media_stability_v86" in s:
    print("Chat viewport/media stability v8.6 already applied.")
    raise SystemExit(0)

for token in (
    "chat_sticker_layout_stability_v85",
    "chat_media_stickers_forward_links_v84",
    "media_inplace_upgrade_v73",
    "chat_photo_click_download_v78",
):
    if token not in s:
        raise SystemExit(f"Required predecessor marker missing in telegacy.cpp: {token}")

# ---------------------------------------------------------------------------
# Shared declarations.
# ---------------------------------------------------------------------------
s = read(h)
decl_anchor = "void media_chat_animated_sticker_clear(); // chat_animated_stickers_v82"
if decl_anchor not in s:
    raise SystemExit("Could not locate animated sticker declarations in header.")

extra = r'''
void media_chat_sticker_scroll_event_v86(); // chat_viewport_media_stability_v86
void history_v86_capture_viewport(); // chat_viewport_media_stability_v86
void history_v86_restore_viewport(); // chat_viewport_media_stability_v86
'''
if "media_chat_sticker_scroll_event_v86" not in s:
    s = s.replace(decl_anchor, decl_anchor + extra, 1)
write(h, s)

# ---------------------------------------------------------------------------
# A) Full-photo click: keep the exact clicked Document through the async
# download. Matching only Telegram document id/access_hash is not enough because
# the same media can appear more than once in one chat.
# ---------------------------------------------------------------------------
s = read(t)

state_anchor = "static std::vector<BYTE> media_chat_full_photo_bytes;"
if state_anchor not in s:
    raise SystemExit("Could not locate full-photo state vector.")

s = s.replace(
    state_anchor,
    state_anchor +
    "\nstatic Document* media_chat_full_photo_target_v86 = NULL; "
    "// chat_viewport_media_stability_v86",
    1,
)

rs, re = function_range(s, "static void media_chat_full_photo_reset(")
reset_func = s[rs:re]
brace = reset_func.find("{")
if brace < 0:
    raise SystemExit("Could not locate full-photo reset brace.")
if "media_chat_full_photo_target_v86 = NULL;" not in reset_func:
    reset_func = (
        reset_func[:brace + 1] +
        "\n    media_chat_full_photo_target_v86 = NULL;\n" +
        reset_func[brace + 1:]
    )
s = s[:rs] + reset_func + s[re:]

bs, be = function_range(s, "bool media_chat_full_photo_begin(")
begin_func = s[bs:be]
target_init_anchor = "    int file_ref_len = tlstr_len("
if target_init_anchor not in begin_func:
    raise SystemExit("Could not locate full-photo file_reference initialization.")
begin_func = begin_func.replace(
    target_init_anchor,
    "    media_chat_full_photo_target_v86 = document;\n\n" +
    target_init_anchor,
    1,
)
s = s[:bs] + begin_func + s[be:]

us, ue = function_range(s, "bool media_chat_full_photo_handle_upload(")
upload_func = s[us:ue]
target_start = upload_func.find("    int target = -1;")
if target_start < 0:
    raise SystemExit("Could not locate full-photo target selection.")
target_log = upload_func.find("    diag_log(", target_start)
if target_log < 0:
    raise SystemExit("Could not locate full-photo target diagnostic.")

new_target = r'''    int target = -1;

    // Prefer the exact deque element that started this user action. deque
    // references survive push_front/push_back, and peer switches already cancel
    // the transfer. Never dereference the stored pointer until we have found the
    // same address in the current deque.
    if (media_chat_full_photo_target_v86) {
        for (int i = 0; i < (int)documents.size(); i++) {
            if (
                &documents[i] ==
                    media_chat_full_photo_target_v86 &&
                documents[i].visible &&
                memcmp(
                    documents[i].id,
                    media_chat_full_photo_id,
                    8
                ) == 0 &&
                memcmp(
                    documents[i].access_hash,
                    media_chat_full_photo_access_hash,
                    8
                ) == 0
            ) {
                target = i;
                break;
            }
        }
    }

    // A legacy/background request may not have an exact pointer. Fall back only
    // when the Telegram id identifies exactly one visible Document.
    if (target < 0) {
        int unique = -1;
        int matches = 0;

        for (int i = 0; i < (int)documents.size(); i++) {
            if (
                documents[i].visible &&
                memcmp(
                    documents[i].id,
                    media_chat_full_photo_id,
                    8
                ) == 0 &&
                memcmp(
                    documents[i].access_hash,
                    media_chat_full_photo_access_hash,
                    8
                ) == 0
            ) {
                unique = i;
                matches++;
            }
        }

        if (matches == 1)
            target = unique;

        if (matches > 1) {
            diag_log(
                "chat v86 full photo ambiguous duplicate media matches=%d",
                matches
            );
        }
    }

'''
upload_func = upload_func[:target_start] + new_target + upload_func[target_log:]
s = s[:us] + upload_func + s[ue:]

# ---------------------------------------------------------------------------
# B) Exact full-photo OLE replacement. Never use SB_BOTTOM while an async photo
# finishes: preserve the pixel scroll position instead.
# ---------------------------------------------------------------------------
ps, pe = function_range(s, "static bool media_chat_upgrade_photo_in_place(")

photo_replace = r'''static bool media_chat_upgrade_photo_in_place(
    Document* document,
    HBITMAP decoded
) {
    if (!document || !decoded || !chat)
        return false;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (!ole)
        return false;

    int expected = document->min;
    int lower = expected > 16 ? expected - 16 : 0;
    int upper = expected + 16;
    bool have_message_range = false;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            expected >= messages[i].start_char - 2 &&
            expected <= messages[i].end_footer + 2
        ) {
            lower = messages[i].start_char;
            upper = messages[i].end_footer;
            have_message_range = true;
            break;
        }
    }

    int exact_cp = -1;
    int unique_cp = -1;
    int bitmap_candidates = 0;
    int nearest_cp = -1;
    int nearest_distance = INT_MAX;

    LONG count = ole->GetObjectCount();

    for (LONG i = 0; i < count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (
            FAILED(
                ole->GetObject(
                    i,
                    &reo,
                    REO_GETOBJ_POLEOBJ
                )
            ) ||
            !reo.poleobj
        ) {
            continue;
        }

        IDataObject* data = NULL;
        bool bitmap = false;

        if (
            SUCCEEDED(
                reo.poleobj->QueryInterface(
                    IID_IDataObject,
                    (void**)&data
                )
            ) &&
            data
        ) {
            FORMATETC format = {
                CF_BITMAP,
                NULL,
                DVASPECT_CONTENT,
                -1,
                TYMED_GDI
            };

            bitmap =
                SUCCEEDED(
                    data->QueryGetData(
                        &format
                    )
                );

            data->Release();
        }

        reo.poleobj->Release();

        if (!bitmap)
            continue;

        int cp = (int)reo.cp;

        if (cp < lower || cp > upper)
            continue;

        bitmap_candidates++;
        unique_cp = cp;

        int distance =
            cp >= expected
                ? cp - expected
                : expected - cp;

        if (distance < nearest_distance) {
            nearest_distance = distance;
            nearest_cp = cp;
        }

        if (cp == expected)
            exact_cp = cp;
    }

    ole->Release();

    int target_cp = exact_cp;

    if (
        target_cp < 0 &&
        have_message_range &&
        bitmap_candidates == 1
    ) {
        target_cp = unique_cp;
    }

    if (
        target_cp < 0 &&
        nearest_cp >= 0 &&
        nearest_distance <= 1
    ) {
        target_cp = nearest_cp;
    }

    if (target_cp < 0) {
        diag_log(
            "chat v86 full photo OLE unresolved expected=%d candidates=%d nearest=%d distance=%d",
            expected,
            bitmap_candidates,
            nearest_cp,
            nearest_distance
        );
        return false;
    }

    HBITMAP card =
        media_chat_make_photo_card(
            decoded
        );

    HBITMAP display =
        card
            ? card
            : decoded;

    CHARRANGE selection = {0};

    SendMessageW(
        chat,
        EM_EXGETSEL,
        0,
        (LPARAM)&selection
    );

    POINT scroll = {0, 0};

    BOOL have_scroll =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&scroll
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

    SendMessageW(
        chat,
        EM_SETSEL,
        target_cp,
        target_cp + 1
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
        display
    );

    if (card)
        DeleteObject(card);

    document->min = target_cp;
    document->max = target_cp + 1;

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

    if (have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    if (was_drawchat) {
        SendMessageW(
            chat,
            WM_SETREDRAW,
            TRUE,
            0
        );

        RedrawWindow(
            chat,
            NULL,
            NULL,
            RDW_INVALIDATE |
                RDW_ERASE |
                RDW_ALLCHILDREN
        );
    }

    if (have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    diag_log(
        "chat v86 full photo OLE replaced expected=%d actual=%d candidates=%d",
        expected,
        target_cp,
        bitmap_candidates
    );

    return true;
}'''

s = s[:ps] + photo_replace + s[pe:]

# Rebind a click to the actual bitmap OLE under the pointer before beginning the
# async transfer. This handles stale Document::min after forwarded/grouped rows.
photo_handler_pos = s.find("bool media_chat_photo_handle_chat_mouse(")
if photo_handler_pos < 0:
    raise SystemExit("Could not locate photo mouse handler.")

click_helper = r'''
static bool media_chat_rebind_clicked_photo_v86(
    Document* document,
    POINT point
) {
    if (!document || !chat)
        return false;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (!ole)
        return false;

    int expected = document->min;
    int lower = expected > 64 ? expected - 64 : 0;
    int upper = expected + 64;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            expected >= messages[i].start_char - 4 &&
            expected <= messages[i].end_footer + 4
        ) {
            lower = messages[i].start_char;
            upper = messages[i].end_footer;
            break;
        }
    }

    int best_cp = -1;
    int best_distance = INT_MAX;
    int effective_dpi =
        dpi > 0
            ? dpi
            : 96;

    int width =
        MulDiv(
            288,
            effective_dpi,
            96
        );

    int height =
        MulDiv(
            216,
            effective_dpi,
            96
        );

    LONG count = ole->GetObjectCount();

    for (LONG i = 0; i < count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (
            FAILED(
                ole->GetObject(
                    i,
                    &reo,
                    REO_GETOBJ_POLEOBJ
                )
            ) ||
            !reo.poleobj
        ) {
            continue;
        }

        IDataObject* data = NULL;
        bool bitmap = false;

        if (
            SUCCEEDED(
                reo.poleobj->QueryInterface(
                    IID_IDataObject,
                    (void**)&data
                )
            ) &&
            data
        ) {
            FORMATETC format = {
                CF_BITMAP,
                NULL,
                DVASPECT_CONTENT,
                -1,
                TYMED_GDI
            };

            bitmap =
                SUCCEEDED(
                    data->QueryGetData(
                        &format
                    )
                );

            data->Release();
        }

        reo.poleobj->Release();

        if (!bitmap)
            continue;

        int cp = (int)reo.cp;

        if (cp < lower || cp > upper)
            continue;

        POINTL origin = {0, 0};

        if (
            SendMessageW(
                chat,
                EM_POSFROMCHAR,
                (WPARAM)&origin,
                (LPARAM)cp
            ) == -1
        ) {
            continue;
        }

        RECT card = {
            origin.x,
            origin.y,
            origin.x + width,
            origin.y + height
        };

        if (!PtInRect(&card, point))
            continue;

        int distance =
            cp >= expected
                ? cp - expected
                : expected - cp;

        if (distance < best_distance) {
            best_distance = distance;
            best_cp = cp;
        }
    }

    ole->Release();

    if (best_cp < 0)
        return false;

    document->min = best_cp;
    document->max = best_cp + 1;

    diag_log(
        "chat v86 photo click rebound expected=%d actual=%d distance=%d",
        expected,
        best_cp,
        best_distance
    );

    return true;
}

'''
s = s[:photo_handler_pos] + click_helper + s[photo_handler_pos:]

photo_handler_pos = s.find(
    "bool media_chat_photo_handle_chat_mouse("
)

if photo_handler_pos < 0:
    raise SystemExit("Could not locate final photo mouse handler.")

action_call = s.find(
    "media_chat_full_photo_user_action(",
    photo_handler_pos
)

if action_call < 0:
    raise SystemExit("Could not locate final photo user-action call.")

action_line = s.rfind(
    "\n",
    photo_handler_pos,
    action_call
) + 1

photo_rebind_call = r'''        media_chat_rebind_clicked_photo_v86(
            document,
            point
        );

'''

s = (
    s[:action_line] +
    photo_rebind_call +
    s[action_line:]
)

# ---------------------------------------------------------------------------
# C) Static WebP stickers are committed into the RichEdit OLE itself. They no
# longer use a child overlay, eliminating ordinary-sticker scroll trails.
# ---------------------------------------------------------------------------
loader_s, loader_e = function_range(s, "static bool media_chat_sticker_load_webp_v84(")
commit_pos = loader_e

static_commit = r'''

static bool media_chat_sticker_commit_webp_v86(
    Document* document,
    const wchar_t* path
) {
    if (!document || !path || !path[0] || !chat)
        return false;

    ChatAnimatedSticker temp;

    temp.anchor_min = document->min;
    temp.kind = 3;
    temp.path[0] = 0;
    temp.window = NULL;
    temp.lottie = NULL;
    temp.video = NULL;
    temp.frame = 0;
    temp.total_frames = 0;
    temp.fps = 0.0;
    temp.next_frame_tick = 0;
    temp.visible = false;
    temp.video_paused_for_visibility = false;

    wcsncpy(
        temp.path,
        path,
        ARRAYSIZE(temp.path) - 1
    );

    temp.path[
        ARRAYSIZE(temp.path) - 1
    ] = 0;

    if (
        !media_chat_sticker_load_webp_v84(
            &temp
        ) ||
        temp.pixels.empty()
    ) {
        return false;
    }

    int width =
        media_chat_sticker_card_width();

    int height =
        media_chat_sticker_card_height();

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

    HDC dc = GetDC(chat);

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

    if (!bitmap || !bits) {
        if (bitmap)
            DeleteObject(bitmap);
        return false;
    }

    memcpy(
        bits,
        &temp.pixels[0],
        width * height * sizeof(unsigned int)
    );

    int cp =
        media_chat_sticker_find_ole_cp(
            document
        );

    if (cp < 0) {
        DeleteObject(bitmap);
        return false;
    }

    CHARRANGE selection = {0};

    SendMessageW(
        chat,
        EM_EXGETSEL,
        0,
        (LPARAM)&selection
    );

    POINT scroll = {0, 0};

    BOOL have_scroll =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&scroll
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
        bitmap
    );

    DeleteObject(bitmap);

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

    if (have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    if (was_drawchat) {
        SendMessageW(
            chat,
            WM_SETREDRAW,
            TRUE,
            0
        );

        RedrawWindow(
            chat,
            NULL,
            NULL,
            RDW_INVALIDATE |
                RDW_ERASE |
                RDW_ALLCHILDREN
        );
    }

    if (have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    diag_log(
        "chat v86 static WebP committed OLE cp=%d path=%ls",
        cp,
        path
    );

    return true;
}
'''
s = s[:commit_pos] + static_commit + s[commit_pos:]

as_, ae = function_range(s, "static void media_chat_sticker_activate(")
activate = s[as_:ae]
new_obj_anchor = "    ChatAnimatedSticker* sticker =\n        new ChatAnimatedSticker();"
if new_obj_anchor not in activate:
    raise SystemExit("Could not locate animated sticker allocation.")

activate = activate.replace(
    new_obj_anchor,
    r'''    if (kind == 3) {
        if (
            !media_chat_sticker_commit_webp_v86(
                document,
                path
            )
        ) {
            diag_log(
                "chat v86 static WebP commit failed min=%d path=%ls",
                document->min,
                path
            );
        }

        return;
    }

    ChatAnimatedSticker* sticker =
        new ChatAnimatedSticker();''',
    1,
)
s = s[:as_] + activate + s[ae:]

# ---------------------------------------------------------------------------
# D) Animated overlays enter an 80ms quiet period during any user scroll. Hide
# immediately and repaint their old parent rectangles before the timer moves
# them. This prevents the repeated date/text fragments visible in the screenshot.
# ---------------------------------------------------------------------------
timer_state_anchor = "static UINT_PTR media_chat_sticker_timer = 0;"
if timer_state_anchor not in s:
    raise SystemExit("Could not locate sticker timer state.")
s = s.replace(
    timer_state_anchor,
    timer_state_anchor +
    "\nstatic DWORD media_chat_sticker_scroll_quiet_until_v86 = 0; "
    "// chat_viewport_media_stability_v86",
    1,
)

release_s, release_e = function_range(
    s,
    "static void media_chat_sticker_release_video_v85("
)

overlay_helpers = r'''

static void media_chat_sticker_hide_overlay_v86(
    ChatAnimatedSticker* sticker
) {
    if (!sticker || !sticker->window)
        return;

    RECT old_rect = {0};

    bool had_rect =
        GetWindowRect(
            sticker->window,
            &old_rect
        ) != FALSE;

    if (had_rect) {
        MapWindowPoints(
            HWND_DESKTOP,
            chat,
            (POINT*)&old_rect,
            2
        );
    }

    ShowWindow(
        sticker->window,
        SW_HIDE
    );

    if (had_rect) {
        InvalidateRect(
            chat,
            &old_rect,
            TRUE
        );
    }

    sticker->visible = false;
}

void media_chat_sticker_scroll_event_v86() {
    if (!chat)
        return;

    media_chat_sticker_scroll_quiet_until_v86 =
        GetTickCount() + 80;

    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {
        ChatAnimatedSticker* sticker =
            media_chat_animated_stickers[i];

        if (!sticker)
            continue;

        media_chat_sticker_hide_overlay_v86(
            sticker
        );

        if (
            sticker->video &&
            !sticker->video_paused_for_visibility
        ) {
            sticker->video->Pause();
            sticker->video_paused_for_visibility = true;
        }
    }

    InvalidateRect(
        chat,
        NULL,
        TRUE
    );
}
'''
s = s[:release_e] + overlay_helpers + s[release_e:]

ts, te = function_range(
    s,
    "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe("
)
timer_func = s[ts:te]

now_anchor = "    DWORD now =\n        GetTickCount();\n"
if now_anchor not in timer_func:
    raise SystemExit("Could not locate v8.5 sticker timer clock.")
timer_func = timer_func.replace(
    now_anchor,
    now_anchor +
    r'''
    if (
        media_chat_sticker_scroll_quiet_until_v86 &&
        (LONG)(
            now -
            media_chat_sticker_scroll_quiet_until_v86
        ) < 0
    ) {
        return;
    }

''',
    1,
)

setpos_anchor = r'''        SetWindowPos(
            sticker->window,
            HWND_TOP,
            origin.x,
            origin.y,
            width,
            height,
            SWP_NOACTIVATE |
                SWP_SHOWWINDOW
        );'''
if setpos_anchor not in timer_func:
    raise SystemExit("Could not locate sticker SetWindowPos.")

setpos_new = r'''        RECT old_overlay_rect = {0};

        bool old_overlay_visible =
            IsWindowVisible(
                sticker->window
            ) != FALSE &&
            GetWindowRect(
                sticker->window,
                &old_overlay_rect
            ) != FALSE;

        if (old_overlay_visible) {
            MapWindowPoints(
                HWND_DESKTOP,
                chat,
                (POINT*)&old_overlay_rect,
                2
            );
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

        if (
            old_overlay_visible &&
            (
                old_overlay_rect.left != origin.x ||
                old_overlay_rect.top != origin.y
            )
        ) {
            InvalidateRect(
                chat,
                &old_overlay_rect,
                TRUE
            );
        }'''
timer_func = timer_func.replace(
    setpos_anchor,
    setpos_new,
    1,
)

s = s[:ts] + timer_func + s[te:]
write(t, s)

# WndProcChat tells overlay runtime about all user-driven scrolling before the
# RichEdit performs it.
s = read(p)
wnd_sig = "LRESULT CALLBACK WndProcChat(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {"
wnd_pos = s.find(wnd_sig)
if wnd_pos < 0:
    raise SystemExit("Could not locate WndProcChat.")
wnd_insert = wnd_pos + len(wnd_sig)

scroll_hook = r'''

    // chat_viewport_media_stability_v86
    if (
        hWnd == chat &&
        (
            msg == WM_VSCROLL ||
            msg == WM_HSCROLL ||
            msg == WM_MOUSEWHEEL ||
            (
                msg == WM_KEYDOWN &&
                (
                    wParam == VK_UP ||
                    wParam == VK_DOWN ||
                    wParam == VK_PRIOR ||
                    wParam == VK_NEXT ||
                    wParam == VK_HOME ||
                    wParam == VK_END
                )
            )
        )
    ) {
        media_chat_sticker_scroll_event_v86();
    }
'''
s = s[:wnd_insert] + scroll_hook + s[wnd_insert:]
write(p, s)

# ---------------------------------------------------------------------------
# E) Preserve a message/pixel anchor across getHistory prepend. Scrollbar nPos
# alone is not stable because prepending messages changes the range.
# ---------------------------------------------------------------------------
s = read(hp)
get_pos = s.find("void get_history()")
if get_pos < 0:
    raise SystemExit("Could not locate get_history for viewport preservation.")

history_helpers = r'''
// chat_viewport_media_stability_v86
static bool history_v86_anchor_valid = false;
static int history_v86_anchor_message_id = 0;
static int history_v86_anchor_y = 0;
static BYTE history_v86_anchor_peer_id[8] = {0};

void history_v86_capture_viewport() {
    history_v86_anchor_valid = false;

    if (
        !chat ||
        !current_peer ||
        messages.empty()
    ) {
        return;
    }

    RECT rect = {0};

    SendMessageW(
        chat,
        EM_GETRECT,
        0,
        (LPARAM)&rect
    );

    POINT top = {
        rect.left + 2,
        rect.top + 2
    };

    int cp =
        (int)SendMessageW(
            chat,
            EM_CHARFROMPOS,
            0,
            (LPARAM)&top
        );

    int selected = -1;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            cp >= messages[i].start_char &&
            cp <= messages[i].end_footer
        ) {
            selected = i;
            break;
        }
    }

    if (selected < 0) {
        int best_distance = INT_MAX;

        for (int i = 0; i < (int)messages.size(); i++) {
            int distance =
                messages[i].start_char >= cp
                    ? messages[i].start_char - cp
                    : cp - messages[i].start_char;

            if (distance < best_distance) {
                best_distance = distance;
                selected = i;
            }
        }
    }

    if (selected < 0)
        return;

    POINTL pos = {0, 0};

    if (
        SendMessageW(
            chat,
            EM_POSFROMCHAR,
            (WPARAM)&pos,
            (LPARAM)messages[selected].start_char
        ) == -1
    ) {
        return;
    }

    history_v86_anchor_message_id =
        messages[selected].id;

    history_v86_anchor_y =
        pos.y;

    memcpy(
        history_v86_anchor_peer_id,
        current_peer->id,
        8
    );

    history_v86_anchor_valid = true;

    diag_log(
        "history v86 captured anchor id=%d cp=%d y=%d",
        history_v86_anchor_message_id,
        messages[selected].start_char,
        history_v86_anchor_y
    );
}

void history_v86_restore_viewport() {
    if (
        !history_v86_anchor_valid ||
        !chat ||
        !current_peer ||
        memcmp(
            history_v86_anchor_peer_id,
            current_peer->id,
            8
        ) != 0
    ) {
        history_v86_anchor_valid = false;
        return;
    }

    int selected = -1;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            messages[i].id ==
                history_v86_anchor_message_id
        ) {
            selected = i;
            break;
        }
    }

    if (selected < 0) {
        history_v86_anchor_valid = false;
        return;
    }

    POINTL pos = {0, 0};

    if (
        SendMessageW(
            chat,
            EM_POSFROMCHAR,
            (WPARAM)&pos,
            (LPARAM)messages[selected].start_char
        ) == -1
    ) {
        history_v86_anchor_valid = false;
        return;
    }

    POINT scroll = {0, 0};

    if (
        !SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&scroll
        )
    ) {
        history_v86_anchor_valid = false;
        return;
    }

    int delta =
        pos.y -
        history_v86_anchor_y;

    if (delta != 0) {
        LONGLONG adjusted =
            (LONGLONG)scroll.y +
            (LONGLONG)delta;

        if (adjusted < 0)
            adjusted = 0;

        if (adjusted > INT_MAX)
            adjusted = INT_MAX;

        scroll.y =
            (LONG)adjusted;

        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    diag_log(
        "history v86 restored anchor id=%d delta=%d scroll_y=%ld",
        history_v86_anchor_message_id,
        delta,
        scroll.y
    );

    history_v86_anchor_valid = false;
}

'''
s = s[:get_pos] + history_helpers + s[get_pos:]

gs, ge = function_range(s, "void get_history()")
get_func = s[gs:ge]
query_anchor = "    BYTE unenc_query[112];"
if query_anchor not in get_func:
    raise SystemExit("Could not locate get_history request buffer.")
get_func = get_func.replace(
    query_anchor,
    "    history_v86_capture_viewport();\n\n" + query_anchor,
    1,
)
s = s[:gs] + get_func + s[ge:]
write(hp, s)

# Restore after the history page has finished layout, before any automatic
# request for another page is considered.
s = read(r)
history_case = s.find("case 0x3a54685e:")
if history_case < 0:
    raise SystemExit("Could not locate messages history response case.")
update_pos = s.find("UpdateWindow(chat);", history_case)
if update_pos < 0:
    raise SystemExit("Could not locate history UpdateWindow(chat).")
update_end = s.find("\n", update_pos)
if update_end < 0:
    raise SystemExit("Could not isolate history UpdateWindow line.")
update_end += 1
s = (
    s[:update_end] +
    "\t\thistory_v86_restore_viewport(); // chat_viewport_media_stability_v86\n" +
    s[update_end:]
)
write(r, s)

# ---------------------------------------------------------------------------
# Verification.
# ---------------------------------------------------------------------------
checks = {
    h: [
        "media_chat_sticker_scroll_event_v86",
        "history_v86_capture_viewport",
        "history_v86_restore_viewport",
    ],
    t: [
        "chat_viewport_media_stability_v86",
        "media_chat_full_photo_target_v86",
        "chat v86 full photo OLE replaced",
        "chat v86 photo click rebound",
        "media_chat_sticker_commit_webp_v86",
        "chat v86 static WebP committed OLE",
        "media_chat_sticker_scroll_quiet_until_v86",
        "media_chat_sticker_hide_overlay_v86",
    ],
    hp: [
        "history v86 captured anchor",
        "history v86 restored anchor",
        "history_v86_capture_viewport();",
    ],
    r: [
        "history_v86_restore_viewport();",
    ],
    p: [
        "chat_viewport_media_stability_v86",
        "media_chat_sticker_scroll_event_v86();",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"v8.6 verification failed in {path.name}: {token}"
            )

print(
    "Applied chat viewport/media stability v8.6: full-photo clicks keep their "
    "exact Document and replace only its bitmap OLE without SB_BOTTOM snapping; "
    "static WebP stickers are committed into RichEdit instead of child overlays; "
    "animated overlays hide/repaint during scrolling; and history prepends "
    "restore a stable message/pixel viewport anchor."
)
