#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_runtime_recovery_v76.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for path in (h, t, r):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


def cpp_function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")

    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")

    depth = 0
    in_string = False
    in_char = False
    escaped = False
    i = brace

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
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return start, i + 1

        i += 1

    raise SystemExit(f"Could not locate closing brace: {signature}")


if "chat_runtime_recovery_v76" in read(t):
    print("Chat runtime recovery v7.6 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_interaction_paging_v75", t),
    ("chat_scope_sync_v74", t),
    ("history v75 renderer skipped", r),
    ("media_inplace_upgrade_v73", t),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

# ---------------------------------------------------------------------------
# Header: response.cpp needs to release a stuck full-photo transfer on a
# non-migration rpc_error.  The function deliberately uses only primitive
# types so it can live beside the early media declarations in the legacy header.
# ---------------------------------------------------------------------------
s = read(h)
anchor = (
    "bool media_chat_photo_handle_chat_mouse(HWND hWnd, UINT msg, "
    "WPARAM wParam, LPARAM lParam); // chat_interaction_paging_v75"
)
if anchor not in s:
    raise SystemExit("Could not locate v7.5 photo mouse declaration.")

decl = (
    "\nbool media_chat_full_photo_handle_rpc_error("
    "const BYTE* rpc_id, int error_code, const wchar_t* error_message"
    "); // chat_runtime_recovery_v76"
)
s = s.replace(anchor, anchor + decl, 1)
write(h, s)

# ---------------------------------------------------------------------------
# Runtime media recovery.
#
# 1) a chat change cancels a transfer owned by the previous document deque;
# 2) a double click is an explicit user retry, so it preempts any old serial
#    transfer instead of merely returning 'already active';
# 3) a non-FILE_MIGRATE rpc_error releases the serial queue.
# ---------------------------------------------------------------------------
s = read(t)

reset_sig = "static void media_chat_full_photo_reset(bool allow_retry)"
reset_start, reset_end = cpp_function_range(s, reset_sig)

error_helper = r'''

// chat_runtime_recovery_v76
bool media_chat_full_photo_handle_rpc_error(
    const BYTE* rpc_id,
    int error_code,
    const wchar_t* error_message
) {
    if (
        !media_chat_full_photo_active ||
        !rpc_id ||
        memcmp(rpc_id, media_chat_full_photo_rpc_id, 8) != 0
    ) {
        return false;
    }

    // 303 FILE_MIGRATE_X is intentionally handled by Telegacy's existing
    // media-DC path; v6.6 restarts the same transfer on that DC.
    if (error_code == 303)
        return false;

    diag_log(
        "chat v76 full photo rpc error released queue code=%d text=%ls",
        error_code,
        error_message ? error_message : L""
    );

    media_chat_full_photo_reset(true);
    return true;
}

'''
s = s[:reset_end] + error_helper + s[reset_end:]

click_old = r'''        memset(document->photo_msg_id, 0, sizeof(document->photo_msg_id));

        bool started = media_chat_full_photo_begin(
'''
click_new = r'''        // chat_runtime_recovery_v76: double-click is a force retry.
        // A previous request can otherwise leave the serial loader active
        // forever and every later photo only waits behind it.
        if (media_chat_full_photo_active) {
            diag_log(
                "chat v76 photo click preempting active transfer"
            );
            media_chat_full_photo_reset(true);
        }

        memset(document->photo_msg_id, 0, sizeof(document->photo_msg_id));

        bool started = media_chat_full_photo_begin(
'''
if click_old not in s:
    raise SystemExit("Could not locate v7.5 photo retry start block.")
s = s.replace(click_old, click_new, 1)

peer_assign = "\t\t\tcurrent_peer = selected_peer;"
if s.count(peer_assign) != 1:
    raise SystemExit(
        f"Expected one selected_peer assignment, found {s.count(peer_assign)}."
    )
peer_new = r'''			if (
				current_peer != selected_peer &&
				media_chat_full_photo_active
			) {
				diag_log(
					"chat v76 peer switch cancelled stale full-photo transfer"
				);
				media_chat_full_photo_reset(true);
			}

			current_peer = selected_peer;'''.replace("\\t", "\t")
s = s.replace(peer_assign, peer_new, 1)

write(t, s)

# ---------------------------------------------------------------------------
# History renderer recovery.
#
# v7.5 learned to skip an object when the legacy renderer disagrees with the
# bounds-checked envelope parser.  The legacy renderer can, however, already
# have prepended a timestamp/footer before throwing or can successfully return
# a message that contains unsupported media but no renderable body.  Both cases
# leave the "wave of dates" visible in the RichEdit.
#
# Roll back only the characters/state created by the current to-front message.
# ---------------------------------------------------------------------------
s = read(r)

safe_sig = "static bool history_safe_message_envelope("
safe_start, safe_end = cpp_function_range(s, safe_sig)

rollback_helper = r'''

// chat_runtime_recovery_v76
static void history_v76_rollback_front_render(
    int text_before,
    int messages_before,
    int documents_before,
    int links_before,
    int old_front_start,
    int old_document_min,
    const BYTE* old_group_id,
    wchar_t* old_sender
) {
    int text_after =
        chat ? GetWindowTextLengthW(chat) : text_before;

    int inserted_chars = text_after - text_before;
    if (inserted_chars < 0)
        inserted_chars = 0;

    // New history items are prepended. Free only objects created by this one
    // renderer call; do not touch the already-visible chat state.
    while ((int)documents.size() > documents_before) {
        free(documents.front().filename);
        free(documents.front().file_reference);
        documents.pop_front();
    }

    while ((int)messages.size() > messages_before)
        messages.pop_front();

    while ((int)links.size() > links_before) {
        free(links.back().lpstrText);
        links.pop_back();
    }

    // message_adder() shifts every pre-existing range when a to-front message
    // reaches its commit point.  Detect that independently of the RichEdit
    // character delta so an SEH exit before the commit is also safe.
    int structural_shift = 0;

    if (
        messages_before > 0 &&
        !messages.empty() &&
        old_front_start >= 0
    ) {
        structural_shift =
            messages.front().start_char - old_front_start;
    } else if (
        documents_before > 0 &&
        !documents.empty() &&
        old_document_min >= 0
    ) {
        structural_shift =
            documents.front().min - old_document_min;
    }

    if (chat && inserted_chars > 0) {
        SendMessageW(chat, EM_SETSEL, 0, inserted_chars);
        SendMessageW(
            chat,
            EM_REPLACESEL,
            FALSE,
            (LPARAM)L""
        );
    }

    if (structural_shift)
        update_positions(-structural_shift, -1, 0);

    if (old_group_id)
        memcpy(group_id_tofront, old_group_id, 8);

    last_tofront_sender = old_sender;

    diag_log(
        "history v76 rollback chars=%d structural_shift=%d msgs=%d docs=%d links=%d",
        inserted_chars,
        structural_shift,
        (int)messages.size() - messages_before,
        (int)documents.size() - documents_before,
        (int)links.size() - links_before
    );
}

'''
s = s[:safe_end] + rollback_helper + s[safe_end:]

handler_pos = s.find(
    "int consumed = media_archive_safe_message_handler(",
    safe_end
)
if handler_pos < 0:
    raise SystemExit("Could not locate v7.5 guarded renderer call.")

block_start = s.rfind("\n", 0, handler_pos) + 1
offset_pos = s.find("offset_msg += consumed;", handler_pos)
if offset_pos < 0:
    raise SystemExit("Could not locate v7.5 accepted renderer offset advance.")
block_end = s.find("\n", offset_pos)
if block_end < 0:
    block_end = len(s)
else:
    block_end += 1

indent = s[block_start:handler_pos]
inner = indent + "\t"

renderer = (
    f"{indent}int history_v76_text_before = chat ? GetWindowTextLengthW(chat) : 0;\n"
    f"{indent}int history_v76_messages_before = (int)messages.size();\n"
    f"{indent}int history_v76_documents_before = (int)documents.size();\n"
    f"{indent}int history_v76_links_before = (int)links.size();\n"
    f"{indent}int history_v76_old_front_start =\n"
    f"{inner}messages.empty() ? -1 : messages.front().start_char;\n"
    f"{indent}int history_v76_old_document_min =\n"
    f"{inner}documents.empty() ? -1 : documents.front().min;\n"
    f"{indent}BYTE history_v76_group_before[8] = {{0}};\n"
    f"{indent}memcpy(history_v76_group_before, group_id_tofront, 8);\n"
    f"{indent}wchar_t* history_v76_sender_before = last_tofront_sender;\n\n"
    f"{indent}int consumed = media_archive_safe_message_handler(\n"
    f"{inner}unenc_response + offset_msg\n"
    f"{indent});\n\n"
    f"{indent}bool history_v76_renderer_bad =\n"
    f"{inner}consumed <= 0 ||\n"
    f"{inner}consumed > available ||\n"
    f"{inner}consumed != safe_consumed;\n\n"
    f"{indent}bool history_v76_orphan_media = false;\n"
    f"{indent}if (\n"
    f"{inner}!history_v76_renderer_bad &&\n"
    f"{inner}safe_media &&\n"
    f"{inner}safe_media_length > 0 &&\n"
    f"{inner}(int)messages.size() > history_v76_messages_before &&\n"
    f"{inner}(int)documents.size() == history_v76_documents_before\n"
    f"{indent}) {{\n"
    f"{inner}const Message& rendered = messages.front();\n"
    f"{inner}int body_chars = rendered.end_char - rendered.end_header;\n"
    f"{inner}history_v76_orphan_media = body_chars <= 1;\n"
    f"{indent}}}\n\n"
    f"{indent}if (history_v76_renderer_bad || history_v76_orphan_media) {{\n"
    f"{inner}history_v76_rollback_front_render(\n"
    f"{inner}\thistory_v76_text_before,\n"
    f"{inner}\thistory_v76_messages_before,\n"
    f"{inner}\thistory_v76_documents_before,\n"
    f"{inner}\thistory_v76_links_before,\n"
    f"{inner}\thistory_v76_old_front_start,\n"
    f"{inner}\thistory_v76_old_document_min,\n"
    f"{inner}\thistory_v76_group_before,\n"
    f"{inner}\thistory_v76_sender_before\n"
    f"{inner});\n\n"
    f"{inner}diag_log(\n"
    f"{inner}\t\"history v76 skipped dirty render item=%d id=%d safe=%d rendered=%d orphan_media=%d exception=0x%08X\",\n"
    f"{inner}\ti,\n"
    f"{inner}\tsafe_message_id,\n"
    f"{inner}\tsafe_consumed,\n"
    f"{inner}\tconsumed,\n"
    f"{inner}\thistory_v76_orphan_media ? 1 : 0,\n"
    f"{inner}\t(unsigned int)media_archive_last_parse_exception\n"
    f"{inner});\n"
    f"{inner}offset_msg += safe_consumed;\n"
    f"{inner}continue;\n"
    f"{indent}}}\n\n"
    f"{indent}offset_msg += consumed;\n"
)

s = s[:block_start] + renderer + s[block_end:]

# The reply-resolution range must use the number of messages actually inserted,
# not the raw Telegram vector count, because v7.6 can intentionally suppress an
# unsupported media-only row.
reply_old = (
    "\t\tint reply_check = count;\n"
    "\t\twhile (reply_check < messages.size() && messages[reply_check-1].end_char == messages[reply_check-1].end_footer) reply_check++;\n"
    "\t\tif (messages_count_old != messages.size()) for (i = 0; i < reply_check; i++) {"
)
reply_new = (
    "\t\tint history_v76_inserted_count = (int)messages.size() - messages_count_old;\n"
    "\t\tif (history_v76_inserted_count < 0) history_v76_inserted_count = 0;\n"
    "\t\tint reply_check = history_v76_inserted_count;\n"
    "\t\twhile (\n"
    "\t\t\treply_check > 0 &&\n"
    "\t\t\treply_check < (int)messages.size() &&\n"
    "\t\t\tmessages[reply_check - 1].end_char == messages[reply_check - 1].end_footer\n"
    "\t\t) reply_check++;\n"
    "\t\tif (messages_count_old != (int)messages.size()) for (i = 0; i < reply_check && i < (int)messages.size(); i++) {"
)
if reply_old not in s:
    raise SystemExit("Could not locate history reply_check block.")
s = s.replace(reply_old, reply_new, 1)

# A skipped/duplicate/unsupported item is not end-of-history. Determine EOF from
# the raw Telegram page length, not from how many objects the old renderer kept.
#
# Older Media patches reformat this tail while adding viewport preservation.
# Bound the replacement to the getHistory response case instead of relying on
# one exact spelling of the old two-line condition.
history_case_pos = s.find("case 0x3a54685e:")
if history_case_pos < 0:
    raise SystemExit("Could not locate messages history response case.")

history_update_pos = s.find("UpdateWindow(chat);", history_case_pos)
if history_update_pos < 0:
    raise SystemExit("Could not locate history UpdateWindow(chat) tail.")

history_update_end = s.find("\n", history_update_pos)
if history_update_end < 0:
    raise SystemExit("Could not isolate history UpdateWindow(chat) line.")
history_update_end += 1

history_break_pos = s.find("\n\t\tbreak;", history_update_end)
if history_break_pos < 0:
    raise SystemExit("Could not locate history response break after UpdateWindow.")

history_tail = s[history_update_end:history_break_pos]
if (
    "no_more_msgs" not in history_tail or
    "get_history()" not in history_tail
):
    raise SystemExit(
        "History response tail no longer contains the expected EOF/pagination logic."
    )

end_new = r'''\t\tint history_v76_rendered_count =
\t\t\t(int)messages.size() - messages_count_old;

\t\tno_more_msgs = count < MSGSFETCHCOUNT;

\t\tdiag_log(
\t\t\t"history v76 page raw=%d rendered=%d limit=%d end=%d",
\t\t\tcount,
\t\t\thistory_v76_rendered_count,
\t\t\tMSGSFETCHCOUNT,
\t\t\tno_more_msgs ? 1 : 0
\t\t);

\t\tif (
\t\t\t!no_more_msgs &&
\t\t\tSendMessage(chat, EM_GETFIRSTVISIBLELINE, 0, 0) == 0
\t\t) {
\t\t\tget_history();
\t\t}
'''.replace("\\t", "\t")

s = s[:history_update_end] + end_new + s[history_break_pos:]

# Search-only public channels are not stored in peers[]. The old channel
# difference parser searches only peers[], so requesting a difference for a
# temporary global-search clone is guaranteed to be ignored. Keep its initial
# getHistory read-only and avoid the orphan timer/request.
channel_old = (
    "\t\tif (current_peer->type == 2 && messages_count_old == 0 && messages.size() > 0) {"
)
channel_new = (
    "\t\tif (\n"
    "\t\t\tcurrent_peer->type == 2 &&\n"
    "\t\t\tmessages_count_old == 0 &&\n"
    "\t\t\tmessages.size() > 0 &&\n"
    "\t\t\t!global_chat_search_is_result_peer(current_peer)\n"
    "\t\t) { // chat_runtime_recovery_v76"
)
if channel_old not in s:
    raise SystemExit("Could not locate initial channel difference block.")
s = s.replace(channel_old, channel_new, 1)

# Release a full-photo serial request on ordinary rpc errors.  FILE_MIGRATE_*
# must continue into the existing 303 branch so v6.6 can switch DCs.
rpc_anchor = (
    "\t\tint error_code = read_le(unenc_response + 4, 4);\n"
    "\t\twchar_t error_message[50];\n"
    "\t\tread_string(unenc_response + 8, error_message);\n"
)
if rpc_anchor not in s:
    raise SystemExit("Could not locate rpc_error header.")
rpc_new = rpc_anchor + (
    "\t\tif (media_chat_full_photo_handle_rpc_error(\n"
    "\t\t\tlast_rpcresult_msgid,\n"
    "\t\t\terror_code,\n"
    "\t\t\terror_message\n"
    "\t\t)) {\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
)
s = s.replace(rpc_anchor, rpc_new, 1)

write(r, s)

checks = {
    h: [
        "media_chat_full_photo_handle_rpc_error",
        "chat_runtime_recovery_v76",
    ],
    t: [
        "chat_runtime_recovery_v76",
        "photo click preempting active transfer",
        "peer switch cancelled stale full-photo transfer",
        "full photo rpc error released queue",
    ],
    r: [
        "history_v76_rollback_front_render",
        "history v76 skipped dirty render",
        "history_v76_inserted_count",
        "history v76 page raw=",
        "!global_chat_search_is_result_peer(current_peer)",
        "media_chat_full_photo_handle_rpc_error(",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v7.6 verification failed in {path.name}: {token}")

print(
    "Applied chat runtime recovery v7.6: partial/unsupported history rows are "
    "rolled back instead of leaving orphan timestamps, pagination uses the raw "
    "Telegram page size, and full-photo loading is reset on peer switch, forced "
    "double-click retry, or non-migration RPC errors."
)
