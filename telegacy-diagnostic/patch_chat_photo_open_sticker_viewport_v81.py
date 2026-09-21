#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_photo_open_sticker_viewport_v81.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
m = root / "src" / "message.cpp"
h = root / "src" / "helpers.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"

for path in (m, h, r, t):
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


def block_range(source, start):
    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit("Could not locate block opening brace")

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

    raise SystemExit("Could not locate block closing brace")


if "chat_photo_open_sticker_viewport_v81" in read(t):
    print("Chat photo/sticker/viewport v8.1 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_media_ole_rebind_v80", t),
    ("chat_photo_click_download_v78", t),
    ("media_inplace_upgrade_v73", t),
    ("chat_channel_media_layout_v77", t),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

# ---------------------------------------------------------------------------
# 1) Normal automatic image loading should fetch Telegram's medium thumbnail.
# Full PhotoSize is now reserved for the explicit single/double click path.
# This removes the background cascade of full-resolution replacements that made
# the chat visibly jump while the user was reading.
# ---------------------------------------------------------------------------
s = read(h)
start, end = function_range(
    s,
    "void get_photo(RequestedCustomEmoji* rce, Document* document, DCInfo* dcInfo)"
)
func = s[start:end]

needle_start = func.find(
    "    // chat_media_resilience_v71: normal visible chat photos use the proven"
)
if needle_start < 0:
    raise SystemExit("Could not locate v7.1 normal-photo full-loader interceptor.")

needle_end = func.find(
    "\n\n",
    func.find("    }", needle_start) + 5
)
if needle_end < 0:
    raise SystemExit("Could not isolate v7.1 normal-photo interceptor.")

replacement = r'''    // chat_photo_open_sticker_viewport_v81:
    // Automatic chat media uses the native Telegram thumb request below.
    // Explicit clicks still call media_chat_full_photo_begin() directly through
    // v7.8, so a single click upgrades to full quality and a double click can
    // persist/open the exact full JPEG without background full-size churn.
'''

func = func[:needle_start] + replacement + func[needle_end:]
s = s[:start] + func + s[end:]
write(h, s)

# ---------------------------------------------------------------------------
# 2) Load sticker thumbnails for every enabled image policy, not only policy 2.
# This path is also used by animated/video stickers to obtain their Telegram
# poster thumbnail, so they no longer remain an empty object in the chat.
# ---------------------------------------------------------------------------
s = read(m)
old_sticker_gate = "if (!to_front && IMAGELOADPOLICY == 2) get_photo(NULL, &document, &dcInfoMain);"
if old_sticker_gate not in s:
    raise SystemExit("Could not locate sticker thumbnail autoload gate.")
s = s.replace(
    old_sticker_gate,
    "if (!to_front && IMAGELOADPOLICY != 0) get_photo(NULL, &document, &dcInfoMain); // chat_photo_open_sticker_viewport_v81",
    1,
)
write(m, s)

# ---------------------------------------------------------------------------
# 3) The legacy sticker completion assumed every sticker thumbnail was WebP and
# also hardcoded the 4-byte TL-string prefix. Modern animated/video stickers may
# return another image thumbnail format. Decode the correct TL payload and try
# WebP first, JPEG second; replace through the v7.7 OLE-safe helper.
# ---------------------------------------------------------------------------
s = read(r)
case_pos = s.find("case 0x96a18d5: { // upload.file")
if case_pos < 0:
    raise SystemExit("Could not locate upload.file response case.")

sticker_pos = s.find("if (documents[i].photo_size == 1)", case_pos)
if sticker_pos < 0:
    raise SystemExit("Could not locate sticker thumbnail decode branch.")

else_pos = s.find("else hClone = jpg_to_bmp", sticker_pos)
if else_pos < 0:
    raise SystemExit("Could not locate ordinary JPEG decode tail after sticker branch.")
else_end = s.find(";", else_pos)
if else_end < 0:
    raise SystemExit("Could not isolate ordinary JPEG decode tail.")
else_end += 1

old_decode = s[sticker_pos:else_end]
new_decode = r'''int media_payload_size =
                    tlstr_len(
                        unenc_response + 12,
                        false
                    );

                int media_payload_offset =
                    12 +
                    (
                        media_payload_size >= 254
                            ? 4
                            : 1
                    );

                HBITMAP hClone = NULL;

                if (
                    media_payload_size > 0 &&
                    media_payload_offset + media_payload_size <= length
                ) {
                    BYTE* media_payload =
                        unenc_response + media_payload_offset;

                    if (documents[i].photo_size == 1) {
                        int width = 0;
                        int height = 0;

                        BYTE* rgba =
                            WebPDecodeRGBA(
                                media_payload,
                                media_payload_size,
                                &width,
                                &height
                            );

                        if (
                            rgba &&
                            width > 0 &&
                            height > 0
                        ) {
                            hClone =
                                rgb_to_bmp(
                                    rgba,
                                    true,
                                    width,
                                    height
                                );

                            WebPFree(rgba);
                        }

                        if (!hClone) {
                            hClone =
                                jpg_to_bmp(
                                    media_payload,
                                    media_payload_size
                                );
                        }

                        diag_log(
                            "chat v81 sticker thumb bytes=%d decoded=%d",
                            media_payload_size,
                            hClone ? 1 : 0
                        );
                    } else {
                        hClone =
                            jpg_to_bmp(
                                media_payload,
                                media_payload_size
                            );
                    }
                }'''

s = s[:sticker_pos] + new_decode + s[else_end:]

# The following v7.7 replacement helper should only be called for a valid bitmap.
call_pos = s.find("media_chat_replace_loaded_bitmap(", sticker_pos)
if call_pos < 0:
    raise SystemExit("Could not locate v7.7 loaded-bitmap replacement call.")

call_end = s.find(");", call_pos)
if call_end < 0:
    raise SystemExit("Could not isolate v7.7 loaded-bitmap call.")
call_end += 2

old_call = s[call_pos:call_end]
new_call = r'''if (hClone) {
                    media_chat_replace_loaded_bitmap(
                        &documents[i],
                        hClone
                    );
                } else {
                    diag_log(
                        "chat v81 media thumb decode failed document=%d type=%d",
                        i,
                        (int)documents[i].photo_size
                    );
                }'''
s = s[:call_pos] + new_call + s[call_end:]
write(r, s)

# ---------------------------------------------------------------------------
# 4) Preserve the RichEdit pixel viewport while replacing media OLEs. Scrollbar
# positions are line/range based and visibly jump when the document height is
# changing asynchronously; EM_GET/SETSCROLLPOS preserves the exact pixel origin.
# ---------------------------------------------------------------------------
s = read(t)

for signature in (
    "static bool media_chat_upgrade_photo_in_place(",
    "bool media_chat_replace_loaded_bitmap(",
):
    fs, fe = function_range(s, signature)
    func = s[fs:fe]

    old_scroll = r'''    SCROLLINFO scroll = {0};
    scroll.cbSize = sizeof(scroll);
    scroll.fMask = SIF_RANGE | SIF_PAGE | SIF_POS | SIF_TRACKPOS;
    GetScrollInfo(chat, SB_VERT, &scroll);'''

    if old_scroll not in func:
        raise SystemExit(f"Could not locate scroll capture in {signature}")

    new_scroll = r'''    POINT media_v81_scroll = {0, 0};
    BOOL media_v81_have_scroll =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&media_v81_scroll
        );'''

    func = func.replace(old_scroll, new_scroll, 1)

    old_restore_start = func.find(
        "    if (was_drawchat) {\n        SendMessageW(chat, WM_SETREDRAW, TRUE, 0);"
    )
    if old_restore_start < 0:
        raise SystemExit(f"Could not locate redraw/scroll restore in {signature}")

    old_restore_end = func.find(
        "\n    }",
        old_restore_start
    )
    # This first close belongs to the nested if in the original block on some
    # revisions; extend to the close immediately before diag_log.
    diag_pos = func.find("\n\n    diag_log(", old_restore_start)
    if diag_pos < 0:
        raise SystemExit(f"Could not locate diagnostic after scroll restore in {signature}")

    old_restore = func[old_restore_start:diag_pos]
    new_restore = r'''    if (media_v81_have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&media_v81_scroll
        );
    }

    if (was_drawchat) {
        SendMessageW(chat, WM_SETREDRAW, TRUE, 0);
        InvalidateRect(chat, NULL, FALSE);
    }

    // Restore once more after redraw is enabled. RichEdit may internally
    // recalculate OLE metrics during WM_SETREDRAW and otherwise move a few px.
    if (media_v81_have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&media_v81_scroll
        );
    }'''

    func = func[:old_restore_start] + new_restore + func[diag_pos:]
    s = s[:fs] + func + s[fe:]

write(t, s)

# ---------------------------------------------------------------------------
# 5) Make double-click save/open deterministic. v7.8 inserted its completion
# hook by searching the first reset(false) globally; the supplied log proves the
# double-click flag reaches the active transfer, but no saved/opened line occurs.
# Re-home the completion hook inside the exact full-photo upload handler.
# Also remember which photos are already full so later single clicks do not
# re-download/repaint the same OLE over and over.
# ---------------------------------------------------------------------------
s = read(t)

state_anchor = "static bool media_chat_full_photo_open_when_done = false; // chat_photo_click_download_v78"
if state_anchor not in s:
    raise SystemExit("Could not locate v7.8 full-photo action state.")

state_extra = r'''
static bool media_chat_v81_skip_replace_when_done = false;
static std::vector<unsigned __int64> media_chat_v81_loaded_full_photos;

static unsigned __int64 media_chat_v81_photo_key(
    const Document* document
) {
    if (!document)
        return 0;

    unsigned __int64 id =
        (unsigned __int64)read_le(
            (BYTE*)document->id,
            8
        );

    unsigned __int64 hash =
        (unsigned __int64)read_le(
            (BYTE*)document->access_hash,
            8
        );

    return id ^ (hash * 0x9E3779B97F4A7C15ULL);
}

static bool media_chat_v81_photo_is_full(
    const Document* document
) {
    unsigned __int64 key =
        media_chat_v81_photo_key(document);

    if (!key)
        return false;

    for (
        int i = 0;
        i < (int)media_chat_v81_loaded_full_photos.size();
        i++
    ) {
        if (
            media_chat_v81_loaded_full_photos[i] ==
            key
        ) {
            return true;
        }
    }

    return false;
}

static void media_chat_v81_mark_photo_full(
    const Document* document
) {
    unsigned __int64 key =
        media_chat_v81_photo_key(document);

    if (!key)
        return;

    if (media_chat_v81_photo_is_full(document))
        return;

    media_chat_v81_loaded_full_photos.push_back(key);
}

'''
s = s.replace(state_anchor, state_anchor + state_extra, 1)

# Reset the skip-repaint flag with transfer state.
rs, re_ = function_range(s, "static void media_chat_full_photo_reset(bool allow_retry)")
reset_func = s[rs:re_]
close = reset_func.rfind("}")
if close < 0:
    raise SystemExit("Could not locate full-photo reset close for v8.1.")
reset_func = (
    reset_func[:close] +
    "\n    media_chat_v81_skip_replace_when_done = false;\n" +
    reset_func[close:]
)
s = s[:rs] + reset_func + s[re_:]

# Avoid redundant single-click transfers once the OLE already contains the full
# image. A double click may still re-download the exact JPEG for persistence,
# but it skips repainting the already-full card.
us, ue = function_range(s, "static bool media_chat_full_photo_user_action(")
user_func = s[us:ue]

validation_end = user_func.find("\n\n    bool same_active")
if validation_end < 0:
    raise SystemExit("Could not locate v7.8 user-action validation end.")

loaded_guard = r'''

    bool already_full =
        media_chat_v81_photo_is_full(document);

    if (
        already_full &&
        !save_and_open
    ) {
        diag_log(
            "chat v81 full photo already loaded; single click ignored"
        );
        return true;
    }

'''
user_func = user_func[:validation_end] + loaded_guard + user_func[validation_end:]

start_anchor = "    media_chat_full_photo_open_when_done = save_and_open;"
if start_anchor not in user_func:
    raise SystemExit("Could not locate v7.8 open-when-done assignment.")

user_func = user_func.replace(
    start_anchor,
    start_anchor +
    "\n    media_chat_v81_skip_replace_when_done = already_full && save_and_open;",
    1,
)

s = s[:us] + user_func + s[ue:]

# Rewrite the decoded full-image completion block so an already-full double
# click saves/opens without changing the chat layout a second time.
hs, he = function_range(
    s,
    "bool media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length)"
)
handler = s[hs:he]

block_start = handler.find(
    "    if (target >= 0 && !media_chat_full_photo_bytes.empty()) {"
)
if block_start < 0:
    raise SystemExit("Could not locate full-photo decode block.")

bs, be = block_range(handler, block_start)
old_block = handler[bs:be]

new_block = r'''    if (target >= 0 && !media_chat_full_photo_bytes.empty()) {
        HBITMAP full_bitmap = jpg_to_bmp(
            &media_chat_full_photo_bytes[0],
            (int)media_chat_full_photo_bytes.size()
        );

        if (full_bitmap) {
            bool replaced = true;

            if (!media_chat_v81_skip_replace_when_done) {
                replaced =
                    media_chat_upgrade_photo_in_place(
                        &documents[target],
                        full_bitmap
                    );
            } else {
                diag_log(
                    "chat v81 full photo repaint skipped target=%d",
                    target
                );
            }

            DeleteObject(full_bitmap);

            if (replaced) {
                media_chat_v81_mark_photo_full(
                    &documents[target]
                );

                diag_log(
                    "chat full photo replaced target=%d via v81",
                    target
                );
            } else {
                diag_log(
                    "chat full photo kept fallback target=%d via v81",
                    target
                );
            }
        } else {
            diag_log("chat full photo JPEG decode failed");
        }
    }'''

handler = handler[:bs] + new_block + handler[be:]

# Remove any old v7.8 completion hook from this handler, wherever it landed.
old_open = r'''    if (media_chat_full_photo_open_when_done) {
        if (!media_chat_full_photo_save_and_open())
            MessageBeep(MB_ICONASTERISK);
    }

'''
handler = handler.replace(old_open, "")

reset_pos = handler.find("    media_chat_full_photo_reset(false);")
if reset_pos < 0:
    raise SystemExit("Could not locate successful full-photo reset in handler.")

open_hook = r'''    bool media_v81_open_after_completion =
        media_chat_full_photo_open_when_done;

    if (media_v81_open_after_completion) {
        diag_log(
            "chat v81 double-click completion opening downloaded photo"
        );

        if (!media_chat_full_photo_save_and_open()) {
            diag_log(
                "chat v81 double-click save/open failed"
            );
            MessageBeep(MB_ICONASTERISK);
        }
    }

'''

handler = handler[:reset_pos] + open_hook + handler[reset_pos:]
s = s[:hs] + handler + s[he:]

# Add audit marker.
audit_anchor = "// chat_media_ole_rebind_v80"
if audit_anchor not in s:
    raise SystemExit("Could not locate v8.0 audit marker.")
s = s.replace(
    audit_anchor,
    audit_anchor + "\n// chat_photo_open_sticker_viewport_v81",
    1,
)

write(t, s)

checks = {
    h: [
        "chat_photo_open_sticker_viewport_v81",
        "Automatic chat media uses the native Telegram thumb request below",
    ],
    m: [
        "chat_photo_open_sticker_viewport_v81",
        "IMAGELOADPOLICY != 0) get_photo(NULL, &document, &dcInfoMain)",
    ],
    r: [
        "chat v81 sticker thumb bytes=",
        "WebPFree(rgba)",
        "media_payload_offset",
        "chat v81 media thumb decode failed",
    ],
    t: [
        "chat_photo_open_sticker_viewport_v81",
        "EM_GETSCROLLPOS",
        "EM_SETSCROLLPOS",
        "chat v81 double-click completion opening downloaded photo",
        "media_chat_v81_photo_is_full",
        "chat v81 full photo repaint skipped",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v8.1 verification failed in {path.name}: {token}")

print(
    "Applied chat photo/sticker/viewport v8.1: automatic media uses medium "
    "Telegram thumbnails while explicit clicks own full-resolution transfer; "
    "double-click save/open is anchored inside the real completion handler; "
    "already-full photos are not repainted repeatedly; RichEdit pixel viewport "
    "is preserved during OLE replacement; and static plus animated/video "
    "stickers load their Telegram poster thumbnails with WebP/JPEG fallback."
)
