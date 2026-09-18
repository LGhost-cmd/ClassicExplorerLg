#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_channel_media_layout_v77.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
hp = root / "src" / "helpers.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"

for path in (h, hp, r, t):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


def call_end(source, start):
    paren = source.find("(", start)
    if paren < 0:
        return -1
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    i = paren
    while i < len(source):
        c = source[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        elif in_char:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "'":
                in_char = False
        else:
            if c == '"':
                in_string = True
            elif c == "'":
                in_char = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    semi = source.find(";", i)
                    return semi + 1 if semi >= 0 else i + 1
        i += 1
    return -1


if "chat_channel_media_layout_v77" in read(t):
    print("Chat channel media/layout v7.7 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_runtime_recovery_v76", t),
    ("media_inplace_upgrade_v73", t),
    ("chat_scope_sync_v74", t),
    ("chat_media_resilience_v71", hp),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

# ---------------------------------------------------------------------------
# 1) Search-only public channels: use the native upload.getFile path for normal
# photos, exactly like the video-thumbnail path that is already working there.
# The serial v6.6 loader remains the default for ordinary persisted dialogs.
# ---------------------------------------------------------------------------
s = read(hp)
old = r'''    if (
        !rce &&
        document &&
        document->visible &&
        document->photo_size != 0 &&
        document->photo_size != 1 &&
        document->photo_size != 3 &&
        IMAGELOADPOLICY != 0
    ) {
        if (media_chat_full_photo_begin(document, dcInfo))
            return;
    }
'''
new = r'''    if (
        !rce &&
        document &&
        document->visible &&
        document->photo_size != 0 &&
        document->photo_size != 1 &&
        document->photo_size != 3 &&
        IMAGELOADPOLICY != 0 &&
        !global_chat_search_is_result_peer(current_peer) // chat_channel_media_layout_v77
    ) {
        if (media_chat_full_photo_begin(document, dcInfo))
            return;
    }
'''
if old not in s:
    raise SystemExit("Could not locate v7.1 full-photo interceptor.")
s = s.replace(old, new, 1)

# Export the already-proven video-card compositor so the safe in-place replacer
# can preserve the play overlay instead of treating a video as a plain photo.
video_sig = "static HBITMAP media_chat_make_video_preview("
if s.count(video_sig) != 1:
    raise SystemExit(
        f"Expected one static video preview helper, found {s.count(video_sig)}."
    )
s = s.replace(video_sig, "HBITMAP media_chat_make_video_preview(", 1)
write(hp, s)

# ---------------------------------------------------------------------------
# 2) Shared declaration for async native media replacement.
# ---------------------------------------------------------------------------
s = read(h)
anchor = "HBITMAP media_chat_make_photo_card(HBITMAP source); // chat_media_layout_v60"
if anchor not in s:
    raise SystemExit("Could not locate photo-card declaration.")

extra = r'''
HBITMAP media_chat_make_video_preview(HBITMAP source); // chat_channel_media_layout_v77
bool media_chat_replace_loaded_bitmap(
    Document* document,
    HBITMAP decoded
); // chat_channel_media_layout_v77'''
if "media_chat_replace_loaded_bitmap(" not in s:
    s = s.replace(anchor, anchor + extra, 1)
write(h, s)

# ---------------------------------------------------------------------------
# 3) Never trust a stale Document::min/max when an async photo/video thumbnail
# arrives. Locate the actual RichEdit OLE placeholder and replace one object
# character in place. This prevents a late video preview from deleting/splitting
# the surrounding text.
# ---------------------------------------------------------------------------
s = read(t)
insert_at = s.find("// media_inplace_upgrade_v73")
if insert_at < 0:
    raise SystemExit("Could not locate v7.3 OLE helper.")

helper = r'''// chat_channel_media_layout_v77
bool media_chat_replace_loaded_bitmap(
    Document* document,
    HBITMAP decoded
) {
    if (!document || !decoded || !chat)
        return false;

    IRichEditOle* ole = NULL;
    SendMessageW(chat, EM_GETOLEINTERFACE, 0, (LPARAM)&ole);
    if (!ole)
        return false;

    int expected = document->min;
    int lower = expected > 96 ? expected - 96 : 0;
    int upper = expected + 96;
    bool message_range = false;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            expected >= messages[i].start_char - 4 &&
            expected <= messages[i].end_footer + 4
        ) {
            lower = messages[i].start_char;
            upper = messages[i].end_footer;
            message_range = true;
            break;
        }
    }

    int best_cp = -1;
    int best_distance = INT_MAX;
    int candidates = 0;

    LONG object_count = ole->GetObjectCount();
    for (LONG i = 0; i < object_count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (FAILED(ole->GetObject(i, &reo, REO_GETOBJ_NO_INTERFACES)))
            continue;

        int cp = (int)reo.cp;
        if (cp < lower || cp > upper)
            continue;

        candidates++;
        int distance = cp >= expected ? cp - expected : expected - cp;
        if (distance < best_distance) {
            best_distance = distance;
            best_cp = cp;
        }
    }

    ole->Release();

    // Inside a message there should normally be exactly one media OLE. If the
    // stale range still identifies the owning message, accept that object even
    // after a large offset drift. Outside a message keep a strict distance cap.
    if (
        best_cp < 0 ||
        (!message_range && best_distance > 48)
    ) {
        diag_log(
            "media v77 native replace skipped expected=%d range=%d..%d candidates=%d distance=%d",
            expected,
            lower,
            upper,
            candidates,
            best_distance
        );
        return false;
    }

    HBITMAP decorated =
        document->photo_size == 3
            ? media_chat_make_video_preview(decoded)
            : media_chat_make_photo_card(decoded);

    HBITMAP display = decorated ? decorated : decoded;

    CHARRANGE selection = {0};
    SendMessageW(chat, EM_EXGETSEL, 0, (LPARAM)&selection);

    SCROLLINFO scroll = {0};
    scroll.cbSize = sizeof(scroll);
    scroll.fMask = SIF_RANGE | SIF_PAGE | SIF_POS | SIF_TRACKPOS;
    GetScrollInfo(chat, SB_VERT, &scroll);

    bool was_drawchat = drawchat;
    if (was_drawchat)
        SendMessageW(chat, WM_SETREDRAW, FALSE, 0);

    SendMessageW(chat, EM_SETSEL, best_cp, best_cp + 1);
    SendMessageW(chat, EM_REPLACESEL, FALSE, (LPARAM)L"");
    insert_image(chat, NULL, display);

    if (document->photo_size == 3) {
        SendMessageW(chat, EM_SETSEL, best_cp, best_cp + 1);

        CHARFORMAT2W link_format = {0};
        link_format.cbSize = sizeof(link_format);
        link_format.dwMask = CFM_LINK;
        link_format.dwEffects = CFE_LINK;

        SendMessageW(
            chat,
            EM_SETCHARFORMAT,
            SCF_SELECTION,
            (LPARAM)&link_format
        );
    }

    if (decorated)
        DeleteObject(decorated);

    document->min = best_cp;
    document->max = best_cp + 1;

    if (selection.cpMin >= 0 && selection.cpMax >= 0)
        SendMessageW(chat, EM_EXSETSEL, 0, (LPARAM)&selection);

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
        "media v77 native replaced OLE expected=%d actual=%d distance=%d video=%d candidates=%d",
        expected,
        best_cp,
        best_distance,
        document->photo_size == 3 ? 1 : 0,
        candidates
    );

    return true;
}


'''
s = s[:insert_at] + helper + s[insert_at:]
write(t, s)

# ---------------------------------------------------------------------------
# 4) Route the legacy native upload.file completion through the OLE-aware helper.
# It is used by video thumbnails and now by search-only channel photos.
# ---------------------------------------------------------------------------
s = read(r)
branch = s.find(
    "} else if (memcmp(&documents[i].photo_msg_id, last_rpcresult_msgid, 8) == 0)"
)
if branch < 0:
    raise SystemExit("Could not locate document upload.file completion branch.")

call = s.find("replace_in_chat(", branch)
if call < 0:
    raise SystemExit("Could not locate native document replace_in_chat call.")

end_call = call_end(s, call)
if end_call < 0:
    raise SystemExit("Could not isolate native document replace_in_chat call.")

replacement = r'''media_chat_replace_loaded_bitmap(
                    &documents[i],
                    hClone
                )'''
s = s[:call] + replacement + s[end_call:]
write(r, s)

# ---------------------------------------------------------------------------
# 5) v7.6 only rolled back empty rows when the safe envelope explicitly exposed
# a media object. The remaining "wave of dates" consists of successfully parsed
# empty rows whose body is absent but whose footer timestamp was committed.
# Suppress any newly prepended row with no body and no Document, while leaving
# service messages (which have visible body text) intact.
# ---------------------------------------------------------------------------
s = read(r)
old_orphan = r'''            !history_v76_renderer_bad &&
            safe_media &&
            safe_media_length > 0 &&
            (int)messages.size() > history_v76_messages_before &&
            (int)documents.size() == history_v76_documents_before
'''
new_orphan = r'''            !history_v76_renderer_bad &&
            (int)messages.size() > history_v76_messages_before &&
            (int)documents.size() == history_v76_documents_before
'''
if old_orphan not in s:
    raise SystemExit("Could not locate v7.6 orphan-row predicate.")
s = s.replace(old_orphan, new_orphan, 1)

log_old = '"history v76 skipped dirty render item=%d id=%d safe=%d rendered=%d orphan_media=%d exception=0x%08X"'
log_new = '"history v77 skipped empty/footer-only row item=%d id=%d safe=%d rendered=%d empty_row=%d exception=0x%08X"'
if log_old not in s:
    raise SystemExit("Could not locate v7.6 orphan-row diagnostic.")
s = s.replace(log_old, log_new, 1)
write(r, s)

checks = {
    h: [
        "media_chat_make_video_preview(HBITMAP source)",
        "media_chat_replace_loaded_bitmap(",
        "chat_channel_media_layout_v77",
    ],
    hp: [
        "!global_chat_search_is_result_peer(current_peer)",
        "HBITMAP media_chat_make_video_preview(",
    ],
    t: [
        "chat_channel_media_layout_v77",
        "media v77 native replaced OLE",
        "document->photo_size == 3",
    ],
    r: [
        "media_chat_replace_loaded_bitmap(",
        "history v77 skipped empty/footer-only row",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v7.7 verification failed in {path.name}: {token}")

print(
    "Applied chat channel media/layout v7.7: search-only channels use the native "
    "photo transport that already works for video, async photo/video previews "
    "replace the real RichEdit OLE instead of stale character ranges, and "
    "footer-only history rows are rolled back."
)
