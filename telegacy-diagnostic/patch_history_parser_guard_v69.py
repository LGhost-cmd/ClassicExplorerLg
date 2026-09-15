#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_history_parser_guard_v69.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
r = root / "src" / "response.cpp"

if not r.exists():
    raise SystemExit(f"Missing expected Telegacy file: {r}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


s = read(r)

if "history_parser_guard_v69" in s:
    print("History parser guard v6.9 already applied.")
    raise SystemExit(0)

# The safe Media parser already contains a bounds-checked message envelope parser.
# Wrap it in SEH as well because several legacy offset helpers predate explicit
# length arguments and can still touch an invalid address before returning a size.
anchor = "static void media_archive_free_document_fields(\n"
if anchor not in s:
    raise SystemExit("Could not locate media archive safe-parser insertion point.")

wrapper = r'''// history_parser_guard_v69
static bool history_safe_message_envelope(
    BYTE* message,
    int available,
    int* consumed_out,
    int* message_id_out,
    BYTE** media_out,
    int* media_length_out
) {
    bool ok = false;
    media_archive_last_parse_exception = 0;

    __try {
        ok = media_archive_message_envelope(
            message,
            available,
            consumed_out,
            message_id_out,
            media_out,
            media_length_out
        );
    }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        media_archive_last_parse_exception = GetExceptionCode();
        ok = false;
    }

    return ok;
}


'''

s = s.replace(anchor, wrapper + anchor, 1)

old = '''\t\tfor (int i = 0; i < count; i++)
\t\t\toffset_msg +=
\t\t\t\tmessage_handler(
\t\t\t\t\ttrue,
\t\t\t\t\tunenc_response + offset_msg,
\t\t\t\t\tfalse,
\t\t\t\t\tfalse,
\t\t\t\t\tfalse
\t\t\t\t);
\t\tint reply_check = count;'''

new = '''\t\t// history_parser_guard_v69
\t\t// Never hand an unchecked Telegram object to Telegacy 1.0.4's legacy
\t\t// message parser. Modern message flags can otherwise make one of the
\t\t// offset helpers walk beyond the decompressed RPC buffer and crash in
\t\t// read_le()/memcpy. The Media archive parser already knows how to validate
\t\t// the complete message envelope against an explicit byte count, so reuse it
\t\t// here before rendering each history item.
\t\tbool history_parse_failed = false;
\t\tint history_failed_item = -1;
\t\tint history_failed_offset = -1;
\n\t\tfor (int i = 0; i < count; i++) {
\t\t\tif (offset_msg < 0 || offset_msg >= length) {
\t\t\t\tdiag_log(
\t\t\t\t\t"history v69 offset outside response item=%d offset=%d length=%d",
\t\t\t\t\ti,
\t\t\t\t\toffset_msg,
\t\t\t\t\tlength
\t\t\t\t);
\t\t\t\thistory_parse_failed = true;
\t\t\t\thistory_failed_item = i;
\t\t\t\thistory_failed_offset = offset_msg;
\t\t\t\tbreak;
\t\t\t}
\n\t\t\tint available = length - offset_msg;
\t\t\tint safe_consumed = 0;
\t\t\tint safe_message_id = 0;
\t\t\tBYTE* safe_media = NULL;
\t\t\tint safe_media_length = 0;
\n\t\t\tbool envelope_ok = history_safe_message_envelope(
\t\t\t\tunenc_response + offset_msg,
\t\t\t\tavailable,
\t\t\t\t&safe_consumed,
\t\t\t\t&safe_message_id,
\t\t\t\t&safe_media,
\t\t\t\t&safe_media_length
\t\t\t);
\n\t\t\tif (!envelope_ok || safe_consumed <= 0 || safe_consumed > available) {
\t\t\t\tunsigned int bad_ctor =
\t\t\t\t\tavailable >= 4
\t\t\t\t\t\t? (unsigned int)read_le(unenc_response + offset_msg, 4)
\t\t\t\t\t\t: 0;
\t\t\t\tunsigned int bad_flags =
\t\t\t\t\tavailable >= 8
\t\t\t\t\t\t? (unsigned int)read_le(unenc_response + offset_msg + 4, 4)
\t\t\t\t\t\t: 0;
\n\t\t\t\tdiag_log(
\t\t\t\t\t"history v69 envelope rejected item=%d offset=%d available=%d ctor=0x%08X flags=0x%08X consumed=%d exception=0x%08X",
\t\t\t\t\ti,
\t\t\t\t\toffset_msg,
\t\t\t\t\tavailable,
\t\t\t\t\tbad_ctor,
\t\t\t\t\tbad_flags,
\t\t\t\t\tsafe_consumed,
\t\t\t\t\t(unsigned int)media_archive_last_parse_exception
\t\t\t\t);
\n\t\t\t\thistory_parse_failed = true;
\t\t\t\thistory_failed_item = i;
\t\t\t\thistory_failed_offset = offset_msg;
\t\t\t\tbreak;
\t\t\t}
\n\t\t\tint consumed = media_archive_safe_message_handler(
\t\t\t\tunenc_response + offset_msg
\t\t\t);
\n\t\t\tif (
\t\t\t\tconsumed <= 0 ||
\t\t\t\tconsumed > available ||
\t\t\t\tconsumed != safe_consumed
\t\t\t) {
\t\t\t\tdiag_log(
\t\t\t\t\t"history v69 renderer rejected item=%d offset=%d available=%d id=%d safe=%d rendered=%d exception=0x%08X",
\t\t\t\t\ti,
\t\t\t\t\toffset_msg,
\t\t\t\t\tavailable,
\t\t\t\t\tsafe_message_id,
\t\t\t\t\tsafe_consumed,
\t\t\t\t\tconsumed,
\t\t\t\t\t(unsigned int)media_archive_last_parse_exception
\t\t\t\t);
\n\t\t\t\thistory_parse_failed = true;
\t\t\t\thistory_failed_item = i;
\t\t\t\thistory_failed_offset = offset_msg;
\t\t\t\tbreak;
\t\t\t}
\n\t\t\toffset_msg += consumed;
\t\t}
\n\t\tif (history_parse_failed) {
\t\t\t// A bad page must not leave the RichEdit transaction permanently
\t\t\t// frozen. Keep any messages that were safely rendered before the bad
\t\t\t// object, stop automatic pagination for this chat session, and return to
\t\t\t// the UI instead of allowing an access violation to terminate Telegacy.
\t\t\tif (history_keep_view) {
\t\t\t\tdrawchat = history_old_drawchat;
\t\t\t\tmedia_chat_layout_transaction = false;
\n\t\t\t\tSendMessageW(chat, WM_SETREDRAW, TRUE, 0);
\t\t\t\tRedrawWindow(
\t\t\t\t\tchat,
\t\t\t\t\tNULL,
\t\t\t\t\tNULL,
\t\t\t\t\tRDW_INVALIDATE |
\t\t\t\t\tRDW_ERASE |
\t\t\t\t\tRDW_UPDATENOW |
\t\t\t\t\tRDW_ALLCHILDREN
\t\t\t\t);
\t\t\t}
\n\t\t\tInterlockedExchange(&history_request_pending, 0);
\t\t\tno_more_msgs = true;
\n\t\t\tdiag_log(
\t\t\t\t"history v69 page aborted safely item=%d offset=%d raw_count=%d inserted_so_far=%d",
\t\t\t\thistory_failed_item,
\t\t\t\thistory_failed_offset,
\t\t\t\tcount,
\t\t\t\t(int)messages.size() - messages_count_old
\t\t\t);
\t\t\tbreak;
\t\t}
\n\t\tint reply_check = count;'''

if old not in s:
    raise SystemExit("Could not locate normal history message loop for v6.9 guard.")

s = s.replace(old, new, 1)
write(r, s)

verify = read(r)
for token in (
    "history_parser_guard_v69",
    "history_safe_message_envelope(",
    "history v69 envelope rejected",
    "history v69 renderer rejected",
    "history v69 page aborted safely",
):
    if token not in verify:
        raise SystemExit(f"History parser guard v6.9 verification failed: {token}")

print(
    "Applied history parser guard v6.9: normal getHistory pages are now bounds-checked "
    "with the proven Media message envelope parser and rendered through an SEH guard; "
    "malformed/unsupported Telegram messages abort the page safely instead of crashing."
)
