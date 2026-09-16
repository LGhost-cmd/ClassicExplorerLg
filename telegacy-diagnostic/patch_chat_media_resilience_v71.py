#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_resilience_v71.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
m = root / "src" / "message.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"

for p in (m, r, t):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


if "chat_media_resilience_v71" in read(m):
    print("Chat/media resilience v7.1 already applied.")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# 1) Never leave an ordinary photo as a featureless grey loading rectangle.
# v7.0 intentionally disabled Telegram's stripped JPEG while waiting for the
# server preview. On slow/failed/migrated preview requests that placeholder can
# remain forever. Keep the stripped image as a visual fallback; the normal
# get_photo()/upload.file request still runs and replaces it with the server
# preview when it arrives.
# ---------------------------------------------------------------------------
s = read(m)
old = "if (size == 'i' && false) { // chat_media_preview_v70: stripped preview is metadata only"
new = "if (size == 'i' && IMAGELOADPOLICY) { // chat_media_resilience_v71: stripped preview is a fallback"
if old not in s:
    raise SystemExit("Could not locate v7.0 stripped-preview suppression.")
s = s.replace(old, new, 1)

# ---------------------------------------------------------------------------
# 2) Treat photo/video OLE objects as real RichEdit blocks.
# The old layout inferred line boundaries from header/footer/group flags. That
# is not reliable for channel posts: a video can be inserted while the caret is
# still on the text line, which makes the bitmap overlap/interrupt the caption.
# Query RichEdit itself and add a separator only when the caret is not already
# at the start of its current line. This avoids both overlap and double blank
# rows.
# ---------------------------------------------------------------------------
anchor = "// chat_media_preview_v70\nstatic HBITMAP media_chat_photo_placeholder()"
if anchor not in s:
    raise SystemExit("Could not locate v7.0 photo placeholder insertion point.")

helper = r'''// chat_media_resilience_v71
static int media_chat_ensure_line_start(HWND control) {
    if (!control)
        return 0;

    CHARRANGE selection = {0};
    SendMessageW(
        control,
        EM_EXGETSEL,
        0,
        (LPARAM)&selection
    );

    LRESULT line = SendMessageW(
        control,
        EM_LINEFROMCHAR,
        (WPARAM)selection.cpMin,
        0
    );

    if (line < 0)
        return 0;

    LRESULT line_start = SendMessageW(
        control,
        EM_LINEINDEX,
        (WPARAM)line,
        0
    );

    if (line_start < 0 || selection.cpMin <= line_start)
        return 0;

    return riched_write(control, L"\n");
}


'''
s = s.replace(anchor, helper + anchor, 1)

# Ordinary photos: enforce a line boundary immediately before the OLE range.
photo_ctor = "} else if (doc != NULL && read_le(doc, 4) == 0x695150d7 && (read_le(doc + 4, 4) & (1 << 0))) {"
photo_start = s.find(photo_ctor)
if photo_start < 0:
    raise SystemExit("Could not locate ordinary photo branch for v7.1.")
photo_end = s.find("\n\tbool addnewline =", photo_start)
if photo_end < 0:
    raise SystemExit("Could not locate ordinary photo branch end for v7.1.")
photo = s[photo_start:photo_end]
photo_min = "\t\tdocument.min = cr_startmsg.cpMin + written;"
if photo.count(photo_min) != 1:
    raise SystemExit(f"Expected one ordinary-photo range start, found {photo.count(photo_min)}.")
photo = photo.replace(
    photo_min,
    "\t\twritten += media_chat_ensure_line_start(chat);\n" + photo_min,
    1,
)
s = s[:photo_start] + photo + s[photo_end:]

# Video cards: enforce a line boundary before the generated unified video row.
video_anchor = (
    "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n\n"
    "\t\t\t// media_chat_video_unified_v56\n"
    "\t\t\tif (video && video_has_thumb && !same_photo) {"
)
video_replacement = (
    "\t\t\tif (video && video_has_thumb && !same_photo)\n"
    "\t\t\t\twritten += media_chat_ensure_line_start(chat);\n\n"
    "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n\n"
    "\t\t\t// media_chat_video_unified_v56\n"
    "\t\t\tif (video && video_has_thumb && !same_photo) {"
)
if video_anchor not in s:
    raise SystemExit("Could not locate unified video row for v7.1 block layout.")
s = s.replace(video_anchor, video_replacement, 1)
write(m, s)

# ---------------------------------------------------------------------------
# 3) Crash containment around every Telegram response, not only getHistory.
# The v6.9 guard protects the normal history message loop, but modern Telegram
# objects can also arrive through updates, channel-difference, nested rpc_result
# and other response paths. A parser AV there used to terminate the whole app.
# Keep the legacy parser unchanged as response_handler_unsafe and call it through
# a tiny SEH boundary. Nested response_handler calls are guarded as well.
# ---------------------------------------------------------------------------
s = read(r)
signature = "void response_handler(DCInfo* dcInfo, BYTE* unenc_response, bool acknowledgement, int length) {"
if s.count(signature) != 1:
    raise SystemExit(f"Expected one response_handler definition, found {s.count(signature)}.")

unsafe_signature = "static void response_handler_unsafe(DCInfo* dcInfo, BYTE* unenc_response, bool acknowledgement, int length) {"
wrapper = r'''// chat_media_resilience_v71
static void response_handler_unsafe(
    DCInfo* dcInfo,
    BYTE* unenc_response,
    bool acknowledgement,
    int length
);

void response_handler(
    DCInfo* dcInfo,
    BYTE* unenc_response,
    bool acknowledgement,
    int length
) {
    if (!dcInfo || !unenc_response || length < 4) {
        diag_log(
            "response v71 rejected invalid envelope dc=%p response=%p length=%d",
            dcInfo,
            unenc_response,
            length
        );
        InterlockedExchange(&history_request_pending, 0);
        return;
    }

    __try {
        response_handler_unsafe(
            dcInfo,
            unenc_response,
            acknowledgement,
            length
        );
    }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        unsigned int ctor =
            length >= 4
                ? (unsigned int)read_le(unenc_response, 4)
                : 0;

        diag_log(
            "response v71 recovered parser exception=0x%08X ctor=0x%08X length=%d dc=%d",
            (unsigned int)GetExceptionCode(),
            ctor,
            length,
            dcInfo ? dcInfo->dc : -1
        );

        // Never leave lazy history permanently locked after a rejected packet.
        InterlockedExchange(&history_request_pending, 0);
    }
}

'''
s = s.replace(signature, wrapper + unsafe_signature, 1)
write(r, s)

# Audit marker in telegacy.cpp, useful when inspecting packaged diagnostic source.
s = read(t)
marker = "// chat_media_preview_v70"
if marker not in s:
    raise SystemExit("Could not locate v7.0 audit marker in telegacy.cpp.")
s = s.replace(marker, marker + "\n// chat_media_resilience_v71", 1)
write(t, s)

checks = {
    m: [
        "chat_media_resilience_v71",
        "if (size == 'i' && IMAGELOADPOLICY) { // chat_media_resilience_v71",
        "static int media_chat_ensure_line_start(HWND control)",
        "written += media_chat_ensure_line_start(chat);",
    ],
    r: [
        "static void response_handler_unsafe(",
        "response v71 recovered parser exception=",
        "InterlockedExchange(&history_request_pending, 0);",
    ],
    t: ["chat_media_resilience_v71"],
}

for p, tokens in checks.items():
    data = read(p)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat/media resilience v7.1 verification failed in {p.name}: {token}")

print(
    "Applied chat/media resilience v7.1: stripped photo fallback restored, photo/video "
    "cards are forced to RichEdit line boundaries, and all Telegram response parsing "
    "is contained behind an SEH boundary so malformed/unsupported packets cannot "
    "terminate the client."
)
