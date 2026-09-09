#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_server_search.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"
helpers = root / "src" / "helpers.cpp"

for p in (h, t, r, helpers):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


# =============================================================================
# include/telegacy.h
# =============================================================================

s = read(h)

if "extern bool message_search_mode;" not in s:
    anchor = "void media_archive_show();"
    block = r'''

// Server-side message search.
extern bool message_search_mode;
extern bool message_search_pending;
extern bool message_search_dirty;
extern bool message_search_suppress_change;
extern BYTE message_search_rpc_id[8];
extern BYTE message_search_peer_id[8];
extern std::vector<int> message_search_current_ids;
extern int message_search_total;

bool message_search_matches_rpc(const BYTE* msg_id);
bool message_search_accept_response();
void message_search_finish_response(int total);
void message_search_handle_rpc_error(int error_code, const wchar_t* error_message);
void message_search_clear_chat_view();
'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate media archive declarations in telegacy.h. "
            "Run patch_search_media.py before patch_server_search.py."
        )

    s = s.replace(anchor, anchor + block, 1)

write(h, s)


# =============================================================================
# src/telegacy.cpp
# Replace the local RichEdit-only search with Telegram messages.search.
# =============================================================================

s = read(t)

position_marker = "static LONG message_search_position = 0;"
local_search_start_marker = "static bool message_search_range_is_body("
local_search_end_marker = "static HBITMAP media_archive_make_thumbnail("

position_pos = s.find(position_marker)
local_start = s.find(local_search_start_marker)
local_end = s.find(local_search_end_marker)

if (
    position_pos < 0 or
    local_start < 0 or
    local_end < 0 or
    local_end <= local_start
):
    if "message_search_send_request" not in s:
        raise SystemExit(
            "Could not locate local message-search implementation. "
            "Run patch_search_media.py before patch_server_search.py."
        )
else:
    server_search_impl = r'''bool message_search_mode = false;
bool message_search_pending = false;
bool message_search_dirty = false;
bool message_search_suppress_change = false;
BYTE message_search_rpc_id[8] = {0};
BYTE message_search_peer_id[8] = {0};
std::vector<int> message_search_current_ids;
int message_search_total = 0;

static wchar_t message_search_sent_query[256] = {0};
static std::vector<int> message_search_page_offsets;

static void message_search_update_buttons() {
    if (!hMessageSearchPrev || !hMessageSearchNext)
        return;

    bool can_newer = message_search_page_offsets.size() > 1;

    int already_before = 0;
    if (message_search_page_offsets.size() > 0) {
        already_before =
            ((int)message_search_page_offsets.size() - 1) * 20;
    }

    bool can_older =
        !message_search_current_ids.empty() &&
        (
            message_search_total <= 0 ||
            already_before + (int)message_search_current_ids.size()
                < message_search_total
        );

    EnableWindow(hMessageSearchPrev, can_newer ? TRUE : FALSE);
    EnableWindow(hMessageSearchNext, can_older ? TRUE : FALSE);
}

void message_search_clear_chat_view() {
    for (int i = (int)documents.size() - 1; i >= 0; i--) {
        free(documents[i].filename);
        free(documents[i].file_reference);
    }

    documents.clear();

    for (int i = (int)links.size() - 1; i >= 0; i--) {
        free(links[i].lpstrText);
    }

    links.clear();
    messages.clear();

    memset(group_id_tofront, 0, sizeof(group_id_tofront));
    memset(group_id, 0, sizeof(group_id));

    if (chat)
        SendMessageW(chat, WM_SETTEXT, 0, (LPARAM)L"");

    media_archive_clear();
}

static void message_search_restore_normal_history() {
    message_search_mode = false;
    message_search_current_ids.clear();
    message_search_total = 0;
    message_search_page_offsets.clear();
    message_search_update_buttons();

    if (!current_peer || !chat)
        return;

    message_search_clear_chat_view();

    no_more_msgs = false;
    InterlockedExchange(&history_request_pending, 0);
    get_history();
}

static bool message_search_send_request(int offset_id) {
    if (!current_peer || !hMessageSearch)
        return false;

    wchar_t query[256] = {0};
    GetWindowTextW(hMessageSearch, query, ARRAYSIZE(query));

    if (!query[0])
        return false;

    if (message_search_pending) {
        message_search_dirty = true;
        return false;
    }

    BYTE unenc_query[2048] = {0};
    BYTE enc_query[2072] = {0};

    internal_header(unenc_query, true);

    // Telegacy 1.0.4 invokes Telegram API layer 196.
    // messages.search#29ee847a at this layer.
    int offset = 32;

    write_le(unenc_query + offset, 0x29ee847a, 4);
    offset += 4;

    // flags = 0: current peer only, no from_id/top_msg_id/saved filters.
    memset(unenc_query + offset, 0, 4);
    offset += 4;

    offset += place_peer(
        unenc_query + offset,
        current_peer,
        true
    );

    write_string(unenc_query + offset, query);
    offset += tlstr_len(unenc_query + offset, true);

    // inputMessagesFilterEmpty#57e2f66c
    write_le(unenc_query + offset, 0x57e2f66c, 4);
    offset += 4;

    // min_date, max_date
    memset(unenc_query + offset, 0, 8);
    offset += 8;

    // offset_id
    write_le(unenc_query + offset, offset_id, 4);
    offset += 4;

    // add_offset
    memset(unenc_query + offset, 0, 4);
    offset += 4;

    // limit
    write_le(unenc_query + offset, 20, 4);
    offset += 4;

    // max_id, min_id
    memset(unenc_query + offset, 0, 8);
    offset += 8;

    // hash:long
    memset(unenc_query + offset, 0, 8);
    offset += 8;

    write_le(
        unenc_query + 28,
        offset - 32,
        4
    );

    int padding_len = get_padding(offset);
    fortuna_read(
        unenc_query + offset,
        padding_len,
        &prng
    );
    offset += padding_len;

    memcpy(
        message_search_rpc_id,
        unenc_query + 16,
        8
    );

    memcpy(
        message_search_peer_id,
        current_peer->id,
        8
    );

    lstrcpynW(
        message_search_sent_query,
        query,
        ARRAYSIZE(message_search_sent_query)
    );

    if (!convert_message(
        unenc_query,
        enc_query,
        offset,
        0
    )) {
        return false;
    }

    int sent = send_query(
        enc_query,
        offset + 24
    );

    if (sent <= 0) {
        diag_log(
            "message search send failed offset_id=%d",
            offset_id
        );
        return false;
    }

    message_search_pending = true;
    message_search_dirty = false;
    message_search_mode = true;

    diag_log(
        "message search request offset_id=%d",
        offset_id
    );

    return true;
}

static void message_search_begin_from_ui() {
    if (!hMessageSearch)
        return;

    wchar_t query[256] = {0};
    GetWindowTextW(hMessageSearch, query, ARRAYSIZE(query));

    if (!query[0]) {
        if (message_search_mode)
            message_search_restore_normal_history();
        return;
    }

    if (message_search_pending) {
        message_search_dirty = true;
        return;
    }

    message_search_page_offsets.clear();
    message_search_page_offsets.push_back(0);
    message_search_current_ids.clear();
    message_search_total = 0;
    message_search_update_buttons();

    message_search_send_request(0);
}

static void message_search_newer_page() {
    if (
        message_search_pending ||
        message_search_page_offsets.size() <= 1
    ) {
        return;
    }

    int old_offset = message_search_page_offsets.back();
    message_search_page_offsets.pop_back();

    int offset_id = message_search_page_offsets.back();

    if (!message_search_send_request(offset_id)) {
        message_search_page_offsets.push_back(old_offset);
    }
}

static void message_search_older_page() {
    if (
        message_search_pending ||
        message_search_current_ids.empty()
    ) {
        return;
    }

    int already_before =
        ((int)message_search_page_offsets.size() - 1) * 20;

    if (
        message_search_total > 0 &&
        already_before + (int)message_search_current_ids.size()
            >= message_search_total
    ) {
        MessageBeep(MB_ICONASTERISK);
        return;
    }

    int offset_id = message_search_current_ids.back();
    message_search_page_offsets.push_back(offset_id);

    if (!message_search_send_request(offset_id)) {
        message_search_page_offsets.pop_back();
    }
}

bool message_search_matches_rpc(const BYTE* msg_id) {
    return
        message_search_pending &&
        msg_id &&
        memcmp(message_search_rpc_id, msg_id, 8) == 0;
}

bool message_search_accept_response() {
    message_search_pending = false;

    wchar_t query[256] = {0};
    if (hMessageSearch) {
        GetWindowTextW(
            hMessageSearch,
            query,
            ARRAYSIZE(query)
        );
    }

    bool same_peer =
        current_peer &&
        memcmp(
            current_peer->id,
            message_search_peer_id,
            8
        ) == 0;

    bool same_query =
        query[0] &&
        wcscmp(query, message_search_sent_query) == 0;

    if (
        message_search_dirty ||
        !same_peer ||
        !same_query
    ) {
        diag_log(
            "message search stale response discarded dirty=%d same_peer=%d same_query=%d",
            message_search_dirty ? 1 : 0,
            same_peer ? 1 : 0,
            same_query ? 1 : 0
        );

        message_search_dirty = false;

        if (query[0] && same_peer) {
            SetTimer(hMain, 31, 30, NULL);
        }

        return false;
    }

    return true;
}

void message_search_finish_response(int total) {
    message_search_total = total;
    message_search_dirty = false;
    message_search_update_buttons();

    diag_log(
        "message search page loaded count=%d total=%d page=%d",
        (int)message_search_current_ids.size(),
        message_search_total,
        message_search_page_offsets.empty()
            ? 0
            : (int)message_search_page_offsets.size()
    );
}

void message_search_handle_rpc_error(
    int error_code,
    const wchar_t* error_message
) {
    message_search_pending = false;

    diag_log(
        "message search rpc_error code=%d",
        error_code
    );

    if (message_search_dirty) {
        message_search_dirty = false;
        SetTimer(hMain, 31, 30, NULL);
    }
}

'''

    # Preserve MediaArchiveItem and all media archive globals which sit
    # between message_search_position and the old local-search functions.
    s = s.replace(
        position_marker,
        server_search_impl,
        1
    )

    local_start = s.find(local_search_start_marker)
    local_end = s.find(local_search_end_marker)

    if local_start < 0 or local_end < 0 or local_end <= local_start:
        raise SystemExit(
            "Could not isolate old local message-search helper functions"
        )

    s = s[:local_start] + s[local_end:]


# -----------------------------------------------------------------------------
# Replace the local search WM_COMMAND handlers.
# -----------------------------------------------------------------------------

old_handlers = r'''\t\tcase 3001: { // message search
\t\t\tif (HIWORD(wParam) == EN_CHANGE) {
\t\t\t\tmessage_search_position = 0;
\t\t\t\tmessage_search_find(false);
\t\t\t}
\t\t\tbreak;
\t\t}

\t\tcase 3002: { // previous message-search result
\t\t\tmessage_search_find(true);
\t\t\tbreak;
\t\t}

\t\tcase 3003: { // next message-search result
\t\t\tmessage_search_find(false);
\t\t\tbreak;
\t\t}
'''.replace('\\t', '\t')

new_handlers = r'''\t\tcase 3001: { // server-side message search
\t\t\tif (HIWORD(wParam) != EN_CHANGE)
\t\t\t\tbreak;

\t\t\tif (message_search_suppress_change)
\t\t\t\tbreak;

\t\t\tKillTimer(hWnd, 31);

\t\t\twchar_t query[256] = {0};
\t\t\tGetWindowTextW(
\t\t\t\thMessageSearch,
\t\t\t\tquery,
\t\t\t\tARRAYSIZE(query)
\t\t\t);

\t\t\tif (!query[0]) {
\t\t\t\tmessage_search_dirty = true;

\t\t\t\tif (message_search_mode)
\t\t\t\t\tmessage_search_restore_normal_history();

\t\t\t\tbreak;
\t\t\t}

\t\t\tmessage_search_dirty = true;
\t\t\tSetTimer(hWnd, 31, 350, NULL);
\t\t\tbreak;
\t\t}

\t\tcase 3002: { // newer server-search page
\t\t\tmessage_search_newer_page();
\t\t\tbreak;
\t\t}

\t\tcase 3003: { // older server-search page
\t\t\tmessage_search_older_page();
\t\t\tbreak;
\t\t}
'''.replace('\\t', '\t')

if old_handlers in s:
    s = s.replace(old_handlers, new_handlers, 1)
elif "case 3001: { // server-side message search" not in s:
    raise SystemExit("Could not locate local message-search WM_COMMAND handlers")


# -----------------------------------------------------------------------------
# Debounce timer 31.
# -----------------------------------------------------------------------------

old_timer = "\tcase WM_TIMER:\n\t\tif (wParam == 0) {"
new_timer = (
    "\tcase WM_TIMER:\n"
    "\t\tif (wParam == 31) {\n"
    "\t\t\tKillTimer(hWnd, 31);\n"
    "\t\t\tmessage_search_begin_from_ui();\n"
    "\t\t} else if (wParam == 0) {"
)

if old_timer in s:
    s = s.replace(old_timer, new_timer, 1)
elif "message_search_begin_from_ui();" not in s[s.find("case WM_TIMER:"):]:
    raise SystemExit("Could not locate WM_TIMER handler")


# -----------------------------------------------------------------------------
# Chat switch: clear the search field without starting a second history request.
# -----------------------------------------------------------------------------

old_switch = r'''\t\t\tmedia_archive_clear();
\t\t\tmessage_search_position = 0;

\t\t\tif (hMessageSearch)
\t\t\t\tSetWindowTextW(hMessageSearch, L"");
'''.replace('\\t', '\t')

new_switch = r'''\t\t\tmedia_archive_clear();
\t\t\tmessage_search_mode = false;
\t\t\tmessage_search_dirty = true;
\t\t\tmessage_search_current_ids.clear();
\t\t\tmessage_search_total = 0;
\t\t\tmessage_search_page_offsets.clear();
\t\t\tmessage_search_update_buttons();

\t\t\tif (hMessageSearch) {
\t\t\t\tmessage_search_suppress_change = true;
\t\t\t\tSetWindowTextW(hMessageSearch, L"");
\t\t\t\tmessage_search_suppress_change = false;
\t\t\t}
'''.replace('\\t', '\t')

if old_switch in s:
    s = s.replace(old_switch, new_switch, 1)
elif "message_search_position = 0;" in s:
    raise SystemExit("Could not replace chat-switch message-search reset")

write(t, s)


# =============================================================================
# src/helpers.cpp
# Do not mix normal history pages into the temporary server-search view.
# =============================================================================

s = read(helpers)

if "get_history skipped: message search mode" not in s:
    anchor = "void get_history() {\n"
    insert = (
        "void get_history() {\n"
        "\tif (message_search_mode) {\n"
        "\t\tdiag_log(\"get_history skipped: message search mode\");\n"
        "\t\treturn;\n"
        "\t}\n"
    )

    if anchor not in s:
        raise SystemExit("Could not locate get_history() in helpers.cpp")

    s = s.replace(anchor, insert, 1)

write(helpers, s)


# =============================================================================
# src/response.cpp
# Intercept responses belonging to messages.search before the normal history
# handler sees them.
# =============================================================================

s = read(r)

if "message_search_handle_server_response" not in s:
    include_anchor = "#include <telegacy.h>\n"

    response_helpers = r'''

static int message_search_extract_id(BYTE* message) {
    if (!message)
        return 0;

    unsigned int constructor = read_le(message, 4);

    if (constructor == 0x90a6ca84) {
        // messageEmpty
        return read_le(message + 8, 4);
    }

    if (constructor == 0xd3d28540) {
        // messageService
        return read_le(message + 8, 4);
    }

    // Regular Message in the layer parsed by Telegacy.
    return read_le(message + 12, 4);
}

static bool message_search_get_vector(
    unsigned int constructor,
    BYTE* response,
    int length,
    int* vector_offset,
    int* total_count
) {
    if (!response || length < 12)
        return false;

    int offset = 0;
    int total = 0;

    if (
        constructor == 0x8c718e87 ||
        constructor == 0x1d73e7ea
    ) {
        offset = 4;
    } else if (
        constructor == 0x3a54685e ||
        constructor == 0x5f206716
    ) {
        int flags = read_le(response + 4, 4);
        total = read_le(response + 8, 4);
        offset = 12;

        if (flags & (1 << 0))
            offset += 4;

        if (flags & (1 << 2))
            offset += 4;

        if (flags & (1 << 3)) {
            diag_log(
                "message search unsupported messagesSlice flags=0x%08X",
                flags
            );
            return false;
        }
    } else if (
        constructor == 0xc776ba4e ||
        constructor == 0x64479808
    ) {
        int flags = read_le(response + 4, 4);
        total = read_le(response + 12, 4);
        offset = 16;

        if (flags & (1 << 2))
            offset += 4;
    } else {
        return false;
    }

    if (offset + 8 > length)
        return false;

    if (read_le(response + offset, 4) != 0x1cb5c415) {
        diag_log(
            "message search vector constructor mismatch ctor=0x%08X at=%d got=0x%08X",
            constructor,
            offset,
            read_le(response + offset, 4)
        );
        return false;
    }

    int count = read_le(response + offset + 4, 4);

    if (count < 0 || count > 1000)
        return false;

    if (!total)
        total = count;

    *vector_offset = offset + 8;
    *total_count = total;
    return true;
}

static void message_search_handle_server_response(
    unsigned int constructor,
    BYTE* response,
    int length
) {
    bool accept = message_search_accept_response();

    if (!accept)
        return;

    int offset = 0;
    int total = 0;

    if (!message_search_get_vector(
        constructor,
        response,
        length,
        &offset,
        &total
    )) {
        diag_log(
            "message search response parse failed ctor=0x%08X length=%d",
            constructor,
            length
        );
        message_search_finish_response(0);
        return;
    }

    int vector_header = offset - 8;
    int count = read_le(response + vector_header + 4, 4);

    message_search_clear_chat_view();
    message_search_current_ids.clear();

    for (int i = 0; i < count; i++) {
        if (offset + 16 > length) {
            diag_log(
                "message search truncated before item=%d offset=%d length=%d",
                i,
                offset,
                length
            );
            break;
        }

        int id = message_search_extract_id(
            response + offset
        );

        int consumed = message_handler(
            true,
            response + offset,
            false,
            false,
            false
        );

        if (consumed <= 0 || offset + consumed > length) {
            diag_log(
                "message search invalid message size item=%d consumed=%d offset=%d length=%d",
                i,
                consumed,
                offset,
                length
            );
            break;
        }

        if (id > 0)
            message_search_current_ids.push_back(id);

        offset += consumed;
    }

    if (chat) {
        SendMessage(chat, WM_SETREDRAW, TRUE, 0);
        InvalidateRect(chat, NULL, TRUE);
        UpdateWindow(chat);
        SendMessage(chat, WM_VSCROLL, SB_BOTTOM, 0);
    }

    message_search_finish_response(total);
}

'''

    if include_anchor not in s:
        raise SystemExit("Could not locate response.cpp include anchor")

    s = s.replace(
        include_anchor,
        include_anchor + response_helpers,
        1
    )


# -----------------------------------------------------------------------------
# Intercept search RPC errors so the single-flight state does not remain stuck.
# -----------------------------------------------------------------------------

rpc_error_anchor = "\tcase 0x2144ca19: { // rpc_error\n"

if "message_search_handle_rpc_error(error_code" not in s:
    replacement = (
        rpc_error_anchor +
        "\t\tint error_code = read_le(unenc_response + 4, 4);\n"
        "\t\twchar_t error_message[50];\n"
        "\t\tread_string(unenc_response + 8, error_message);\n"
        "\t\tif (message_search_matches_rpc(last_rpcresult_msgid)) {\n"
        "\t\t\tmessage_search_handle_rpc_error(error_code, error_message);\n"
        "\t\t\tbreak;\n"
        "\t\t}\n"
    )

    old = (
        rpc_error_anchor +
        "\t\tint error_code = read_le(unenc_response + 4, 4);\n"
        "\t\twchar_t error_message[50];\n"
        "\t\tread_string(unenc_response + 8, error_message);\n"
    )

    if old not in s:
        raise SystemExit("Could not locate rpc_error prologue in response.cpp")

    s = s.replace(old, replacement, 1)


# -----------------------------------------------------------------------------
# Extend the messages.Messages handler family and intercept the search response.
# -----------------------------------------------------------------------------

old_cases = (
    "\tcase 0x3a54685e: // messages.messagesSlice\n"
    "\tcase 0xc776ba4e: // messages.channelMessages\n"
    "\tcase 0x8c718e87: { // messages.Messages\n"
)

new_cases = (
    "\tcase 0x5f206716: // messages.messagesSlice (newer)\n"
    "\tcase 0x1d73e7ea: // messages.messages (newer)\n"
    "\tcase 0x64479808: // messages.channelMessages (older)\n"
    "\tcase 0x3a54685e: // messages.messagesSlice\n"
    "\tcase 0xc776ba4e: // messages.channelMessages\n"
    "\tcase 0x8c718e87: { // messages.Messages\n"
    "\t\tif (message_search_matches_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmessage_search_handle_server_response(\n"
    "\t\t\t\tconstructor,\n"
    "\t\t\t\tunenc_response,\n"
    "\t\t\t\tlength\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
    "\n"
    "\t\tif (message_search_mode) {\n"
    "\t\t\tInterlockedExchange(&history_request_pending, 0);\n"
    "\t\t\tdiag_log(\"history response ignored while message search mode is active\");\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
    "\n"
    "\t\tif (\n"
    "\t\t\tconstructor == 0x5f206716 ||\n"
    "\t\t\tconstructor == 0x1d73e7ea ||\n"
    "\t\t\tconstructor == 0x64479808\n"
    "\t\t) {\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
)

if old_cases in s:
    s = s.replace(old_cases, new_cases, 1)
elif "message_search_handle_server_response(" not in s[s.find("case 0x3a54685e"):]:
    raise SystemExit("Could not locate messages.Messages switch cases in response.cpp")

write(r, s)

print("Applied real server-side Telegram message search patch.")
