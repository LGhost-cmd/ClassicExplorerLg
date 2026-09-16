#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_resilience_v71.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
m = root / "src" / "message.cpp"
h = root / "src" / "helpers.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"

for p in (m, h, r, t):
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
# v7.0 deliberately disabled Telegram's stripped JPEG while waiting for a
# network preview. That makes any failed/stalled preview look like an empty
# message. Keep the stripped JPEG as an immediate fallback; it will be replaced
# by the higher-quality server image when that image arrives.
# ---------------------------------------------------------------------------
s = read(m)
old = "if (size == 'i' && false) { // chat_media_preview_v70: stripped preview is metadata only"
new = "if (size == 'i' && IMAGELOADPOLICY) { // chat_media_resilience_v71: stripped preview is a fallback"
if old not in s:
    raise SystemExit("Could not locate v7.0 stripped-preview suppression.")
s = s.replace(old, new, 1)

# ---------------------------------------------------------------------------
# 2) Treat photo/video OLE objects as real RichEdit blocks.
# Channel posts do not always follow the same header/footer path as ordinary
# chats, so relying on those flags can put a video bitmap in the middle of the
# text line. Ask RichEdit for the real caret line and insert exactly one newline
# only when needed. This fixes overlap without manufacturing extra blank rows.
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
# 3) Ordinary chat photos go back through the v6.4/v6.6 serial full-photo
# loader rather than v7.0's native legacy get_photo transport.
#
# Earlier diagnostic runs had already shown access violations in the native
# path on modern Telegram file references. v6.6 added correct FILE_MIGRATE/DC
# retry to the serial loader. v7.0 made native get_photo safer, but switching
# ordinary photos back to it reintroduced the risky path and, in the supplied
# run, coincides with stalled previews plus another access violation. Keep the
# hardened native path for video thumbs/custom emoji, but intercept normal
# visible photos with the migration-aware serial loader.
# ---------------------------------------------------------------------------
s = read(h)
native_comment = '''    // chat_media_preview_v70: visible chat photos intentionally use the native
    // get_photo/upload.file transport below, exactly like Media previews. The
    // old v6.4 full-photo interceptor remains compiled only for compatibility
    // with already-patched response code, but it is no longer entered here.
'''
restored_interceptor = r'''    // chat_media_resilience_v71: normal visible chat photos use the proven
    // v6.4/v6.6 serial loader. photo_size==3 (video preview), stickers/custom
    // emoji and ordinary file downloads continue through the native path below.
    if (
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
if native_comment not in s:
    raise SystemExit("Could not locate v7.0 native-photo transport marker in helpers.cpp.")
s = s.replace(native_comment, restored_interceptor, 1)
write(h, s)

# ---------------------------------------------------------------------------
# 4) Crash containment around every Telegram response, not only getHistory.
# v6.9 protects the normal history loop, but modern objects can also arrive via
# updates, channel differences and nested rpc_result payloads. Put the complete
# legacy response parser behind a tiny SEH boundary. Recursive response_handler
# calls go through the same boundary. This converts parser AVs into a rejected
# packet and releases the lazy-history lock instead of terminating Telegacy.
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

        InterlockedExchange(&history_request_pending, 0);
    }
}

'''
s = s.replace(signature, wrapper + unsafe_signature, 1)
write(r, s)

# Audit marker in telegacy.cpp.
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
    h: [
        "chat_media_resilience_v71: normal visible chat photos use the proven",
        "media_chat_full_photo_begin(document, dcInfo)",
        "document->photo_size != 3",
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
    "Applied chat/media resilience v7.1: stripped photo fallback restored; ordinary "
    "photos use the migration-aware serial loader; photo/video cards are forced to "
    "real RichEdit line boundaries; and all Telegram response parsing is contained "
    "behind an SEH boundary."
)
