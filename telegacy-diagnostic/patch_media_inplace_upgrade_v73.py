#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_media_inplace_upgrade_v73.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing expected Telegacy file: {t}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


s = read(t)
if "media_inplace_upgrade_v73" in s:
    print("Media in-place upgrade v7.3 already applied.")
    raise SystemExit(0)

if "chat_media_resilience_v71" not in s:
    raise SystemExit("v7.1 media resilience must be applied before v7.3.")

handler_sig = "bool media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length) {"
pos = s.find(handler_sig)
if pos < 0:
    raise SystemExit("Could not locate chat full-photo upload handler.")

helper = r'''
// media_inplace_upgrade_v73
// Replace the existing low-resolution OLE object itself.  Document::min/max can
// drift by one or more characters when a forwarded header, grouped-media footer
// or an asynchronously inserted line break is added after the thumbnail.  Using
// a stale range with replace_in_chat can therefore leave the stripped thumbnail
// in place and insert the full image beside/below it.  Resolve the actual OLE
// character from RichEdit and replace exactly one object character.
static bool media_chat_upgrade_photo_in_place(
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
    int best_cp = -1;
    int best_distance = INT_MAX;

    // Prefer objects inside the owning message. This prevents a grouped album
    // from accidentally upgrading a neighbouring message's attachment.
    int lower = expected > 8 ? expected - 8 : 0;
    int upper = document->max + 8;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            expected >= messages[i].start_char - 2 &&
            expected <= messages[i].end_footer + 2
        ) {
            lower = messages[i].start_char;
            upper = messages[i].end_footer;
            break;
        }
    }

    LONG object_count = ole->GetObjectCount();
    for (LONG i = 0; i < object_count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (FAILED(ole->GetObject(i, &reo, REO_GETOBJ_NO_INTERFACES)))
            continue;

        int cp = (int)reo.cp;
        if (cp < lower || cp > upper)
            continue;

        int distance = cp >= expected ? cp - expected : expected - cp;
        if (distance < best_distance) {
            best_distance = distance;
            best_cp = cp;
        }
    }

    ole->Release();

    // A very distant object is not a trustworthy match. Keeping the blurry
    // fallback is preferable to creating a duplicate full-size attachment.
    if (best_cp < 0 || best_distance > 32) {
        diag_log(
            "media v73 upgrade skipped: OLE not found expected=%d min=%d max=%d distance=%d",
            expected,
            document->min,
            document->max,
            best_distance
        );
        return false;
    }

    HBITMAP card = media_chat_make_photo_card(decoded);
    HBITMAP display = card ? card : decoded;

    CHARRANGE old_selection = {0};
    SendMessageW(
        chat,
        EM_EXGETSEL,
        0,
        (LPARAM)&old_selection
    );

    SCROLLINFO scroll = {0};
    scroll.cbSize = sizeof(scroll);
    scroll.fMask = SIF_RANGE | SIF_PAGE | SIF_POS | SIF_TRACKPOS;
    GetScrollInfo(chat, SB_VERT, &scroll);

    bool was_drawchat = drawchat;
    if (was_drawchat)
        SendMessageW(chat, WM_SETREDRAW, FALSE, 0);

    // One embedded object occupies exactly one RichEdit character (U+FFFC).
    SendMessageW(chat, EM_SETSEL, best_cp, best_cp + 1);
    SendMessageW(chat, EM_REPLACESEL, FALSE, (LPARAM)L"");
    insert_image(chat, NULL, display);

    if (card)
        DeleteObject(card);

    document->min = best_cp;
    document->max = best_cp + 1;

    if (
        old_selection.cpMin >= 0 &&
        old_selection.cpMax >= 0
    ) {
        SendMessageW(
            chat,
            EM_EXSETSEL,
            0,
            (LPARAM)&old_selection
        );
    }

    if (was_drawchat) {
        SendMessageW(chat, WM_SETREDRAW, TRUE, 0);
        InvalidateRect(chat, NULL, TRUE);
        UpdateWindow(chat);

        if (scroll.nPos >= (int)(scroll.nMax - scroll.nPage) - 25)
            SendMessageW(chat, WM_VSCROLL, SB_BOTTOM, 0);
        else
            SendMessageW(
                chat,
                WM_VSCROLL,
                MAKEWPARAM(SB_THUMBPOSITION, scroll.nPos),
                0
            );
    }

    diag_log(
        "media v73 upgraded OLE in place expected=%d actual=%d distance=%d",
        expected,
        best_cp,
        best_distance
    );

    return true;
}

'''

s = s[:pos] + helper + s[pos:]

old = r'''        if (full_bitmap) {
            CHARRANGE cr;
            cr.cpMin = documents[target].min;
            cr.cpMax = documents[target].max;
            replace_in_chat(NULL, &cr, NULL, full_bitmap, NULL, NULL, NULL);
            DeleteObject(full_bitmap);
            diag_log("chat full photo replaced target=%d", target);
        } else {'''
new = r'''        if (full_bitmap) {
            bool replaced = media_chat_upgrade_photo_in_place(
                &documents[target],
                full_bitmap
            );
            DeleteObject(full_bitmap);

            if (replaced)
                diag_log("chat full photo replaced target=%d via v73", target);
            else
                diag_log("chat full photo kept fallback target=%d via v73", target);
        } else {'''

if old not in s:
    raise SystemExit("Could not locate v6.4 full-photo replacement block.")
s = s.replace(old, new, 1)

write(t, s)

check = read(t)
for token in (
    "media_inplace_upgrade_v73",
    "media_chat_upgrade_photo_in_place(",
    "REO_GETOBJ_NO_INTERFACES",
    "media v73 upgraded OLE in place",
    "chat full photo kept fallback target=%d via v73",
):
    if token not in check:
        raise SystemExit(f"v7.3 verification failed: {token}")

print(
    "Applied media in-place upgrade v7.3: full-resolution photo completion now "
    "locates and replaces the real RichEdit OLE object. If the object cannot be "
    "matched safely, the low-resolution fallback is retained instead of inserting "
    "a duplicate image."
)
