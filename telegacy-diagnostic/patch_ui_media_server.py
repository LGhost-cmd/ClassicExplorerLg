#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_ui_media_server.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for p in (h, t, r):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


def cpp_function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")

    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")

    depth = 0
    i = brace
    while i < len(source):
        c = source[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1

    raise SystemExit(f"Could not locate closing brace: {signature}")


def insert_after_create_call(source, variable, code, marker):
    if marker in source:
        return source

    pos = source.find(variable + " = CreateWindow")
    if pos < 0:
        raise SystemExit(f"Could not locate creation of {variable}")

    open_paren = source.find("(", pos)
    if open_paren < 0:
        raise SystemExit(f"Could not locate CreateWindow call for {variable}")

    depth = 0
    i = open_paren
    in_string = False
    escaped = False

    while i < len(source):
        c = source[i]

        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    semi = source.find(";", i)
                    if semi < 0:
                        raise SystemExit(
                            f"Could not locate semicolon after {variable} CreateWindow"
                        )
                    return (
                        source[:semi + 1]
                        + "\n"
                        + code
                        + source[semi + 1:]
                    )
        i += 1

    raise SystemExit(f"Could not isolate CreateWindow call for {variable}")


# =============================================================================
# include/telegacy.h
# =============================================================================

s = read(h)

if "bool media_archive_matches_rpc(" not in s:
    anchor = "void media_archive_show();"

    block = r'''

// Server-backed Media archive.
extern bool media_archive_server_active;
extern bool media_archive_search_pending;
extern BYTE media_archive_search_rpc_id[8];

bool media_archive_matches_rpc(const BYTE* msg_id);
bool media_archive_accept_response();
void media_archive_finish_server_page(
    int last_id,
    int count,
    int total
);
void media_archive_handle_rpc_error(
    int error_code,
    const wchar_t* error_message
);
void media_archive_start_next_download();
'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate media archive declarations in telegacy.h. "
            "Run patch_search_media.py first."
        )

    s = s.replace(anchor, anchor + block, 1)

write(h, s)


# =============================================================================
# src/telegacy.cpp
# =============================================================================

s = read(t)


# -----------------------------------------------------------------------------
# 1. Chat filter: remove blank/uninitialized peers from the ComboBox.
# -----------------------------------------------------------------------------

if "// filtered chat list: skip blank peer names" not in s:
    old = (
        "        if (!peer || !peer->name)\n"
        "            continue;"
    )

    new = (
        "        // filtered chat list: skip blank peer names\n"
        "        if (!peer || !peer->name || !peer->name[0])\n"
        "            continue;"
    )

    if old not in s:
        raise SystemExit(
            "Could not locate blank-name guard in rebuild_chat_combo_by_name()."
        )

    s = s.replace(old, new, 1)


# -----------------------------------------------------------------------------
# 2. Native grey cue banners + magnifying-glass glyph.
#
# EM_SETCUEBANNER == 0x1501.  We use the numeric value because Telegacy keeps
# old WINVER/_WIN32_WINNT values for compatibility.
# Universal character escapes keep the old source file entirely ASCII-safe.
# -----------------------------------------------------------------------------

chat_cue = r'''		// search cue: native grey placeholder + magnifying glass
		SendMessageW(
			hChatSearch,
			0x1501,
			TRUE,
			(LPARAM)L"\U0001F50D  \u041F\u043E\u0438\u0441\u043A \u0447\u0430\u0442\u043E\u0432"
		);'''

s = insert_after_create_call(
    s,
    "hChatSearch",
    chat_cue,
    "// search cue: native grey placeholder + magnifying glass"
)

message_cue_marker = "// message search cue: native grey placeholder + magnifying glass"

if message_cue_marker not in s:
    message_cue = r'''		// message search cue: native grey placeholder + magnifying glass
		SendMessageW(
			hMessageSearch,
			0x1501,
			TRUE,
			(LPARAM)L"\U0001F50D  \u041F\u043E\u0438\u0441\u043A \u0441\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u0439"
		);'''

    s = insert_after_create_call(
        s,
        "hMessageSearch",
        message_cue,
        message_cue_marker
    )


# -----------------------------------------------------------------------------
# 3. Add server-backed Media state and messages.search(PhotoVideo) sender.
# -----------------------------------------------------------------------------

if "media_archive_request_server_page(" not in s:
    anchor = "static HIMAGELIST hMediaArchiveImages = NULL;"

    server_impl = r'''

// ======================================================================================
// Server-backed Media archive
// ======================================================================================

bool media_archive_server_active = false;
bool media_archive_search_pending = false;
BYTE media_archive_search_rpc_id[8] = {0};

static BYTE media_archive_search_peer_id[8] = {0};
static int media_archive_next_offset_id = 0;
static int media_archive_loaded_count = 0;
static int media_archive_total = 0;
static bool media_archive_no_more = false;

static bool media_archive_request_server_page(
    int offset_id
) {
    if (
        !current_peer ||
        media_archive_search_pending
    ) {
        return false;
    }

    BYTE unenc_query[512] = {0};
    BYTE enc_query[536] = {0};

    internal_header(
        unenc_query,
        true
    );

    int offset = 32;

    // messages.search#29ee847a, API layer 196.
    write_le(
        unenc_query + offset,
        0x29ee847a,
        4
    );
    offset += 4;

    // flags = 0
    memset(
        unenc_query + offset,
        0,
        4
    );
    offset += 4;

    offset += place_peer(
        unenc_query + offset,
        current_peer,
        true
    );

    // q = ""
    write_string(
        unenc_query + offset,
        L""
    );
    offset += tlstr_len(
        unenc_query + offset,
        true
    );

    // inputMessagesFilterPhotoVideo#56e9f0e4
    write_le(
        unenc_query + offset,
        0x56e9f0e4,
        4
    );
    offset += 4;

    // min_date, max_date
    memset(
        unenc_query + offset,
        0,
        8
    );
    offset += 8;

    // offset_id
    write_le(
        unenc_query + offset,
        offset_id,
        4
    );
    offset += 4;

    // add_offset
    memset(
        unenc_query + offset,
        0,
        4
    );
    offset += 4;

    // limit
    write_le(
        unenc_query + offset,
        20,
        4
    );
    offset += 4;

    // max_id, min_id
    memset(
        unenc_query + offset,
        0,
        8
    );
    offset += 8;

    // hash:long
    memset(
        unenc_query + offset,
        0,
        8
    );
    offset += 8;

    write_le(
        unenc_query + 28,
        offset - 32,
        4
    );

    int padding_len =
        get_padding(offset);

    fortuna_read(
        unenc_query + offset,
        padding_len,
        &prng
    );

    offset += padding_len;

    memcpy(
        media_archive_search_rpc_id,
        unenc_query + 16,
        8
    );

    memcpy(
        media_archive_search_peer_id,
        current_peer->id,
        8
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
            "media server search send failed offset_id=%d",
            offset_id
        );
        return false;
    }

    media_archive_search_pending = true;

    if (hMediaArchiveOlder)
        EnableWindow(
            hMediaArchiveOlder,
            FALSE
        );

    diag_log(
        "media server search request offset_id=%d",
        offset_id
    );

    return true;
}

bool media_archive_matches_rpc(
    const BYTE* msg_id
) {
    return
        media_archive_server_active &&
        media_archive_search_pending &&
        msg_id &&
        memcmp(
            media_archive_search_rpc_id,
            msg_id,
            8
        ) == 0;
}

bool media_archive_accept_response() {
    media_archive_search_pending = false;

    bool same_peer =
        current_peer &&
        memcmp(
            current_peer->id,
            media_archive_search_peer_id,
            8
        ) == 0;

    if (
        !media_archive_server_active ||
        !same_peer
    ) {
        diag_log(
            "media server search stale response active=%d same_peer=%d",
            media_archive_server_active ? 1 : 0,
            same_peer ? 1 : 0
        );

        return false;
    }

    return true;
}

void media_archive_finish_server_page(
    int last_id,
    int count,
    int total
) {
    if (last_id > 0)
        media_archive_next_offset_id =
            last_id;

    media_archive_loaded_count +=
        count;

    if (total > 0)
        media_archive_total = total;

    media_archive_no_more =
        count < 20 ||
        last_id <= 0 ||
        (
            media_archive_total > 0 &&
            media_archive_loaded_count >=
                media_archive_total
        );

    if (hMediaArchiveOlder) {
        EnableWindow(
            hMediaArchiveOlder,
            media_archive_no_more
                ? FALSE
                : TRUE
        );
    }

    diag_log(
        "media server page count=%d total=%d loaded=%d next=%d end=%d",
        count,
        media_archive_total,
        media_archive_loaded_count,
        media_archive_next_offset_id,
        media_archive_no_more ? 1 : 0
    );
}

void media_archive_handle_rpc_error(
    int error_code,
    const wchar_t* error_message
) {
    media_archive_search_pending = false;

    if (
        hMediaArchiveOlder &&
        media_archive_server_active &&
        !media_archive_no_more
    ) {
        EnableWindow(
            hMediaArchiveOlder,
            TRUE
        );
    }

    diag_log(
        "media server rpc_error code=%d",
        error_code
    );
}

void media_archive_start_next_download() {
    if (!media_archive_server_active)
        return;

    // Server-media documents are kept at the front of `documents` and are
    // marked visible=false. Start the highest-index unrequested one; the
    // original upload.file loop then naturally walks down through the rest.
    for (
        int i = (int)documents.size() - 1;
        i >= 0;
        i--
    ) {
        if (
            documents[i].visible ||
            documents[i].photo_size <= 1
        ) {
            continue;
        }

        if (!read_le(
            documents[i].photo_msg_id,
            8
        )) {
            get_photo(
                NULL,
                &documents[i],
                &dcInfoMain
            );

            diag_log(
                "media thumbnail download start index=%d msg=%d",
                i,
                documents[i].min < 0
                    ? -documents[i].min
                    : 0
            );

            break;
        }
    }
}
'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate Media archive globals. "
            "Run patch_search_media.py first."
        )

    s = s.replace(
        anchor,
        anchor + server_impl,
        1
    )


# -----------------------------------------------------------------------------
# Media window's Older button now requests the next Telegram media page.
# -----------------------------------------------------------------------------

start, end = cpp_function_range(
    s,
    "static LRESULT CALLBACK TelegacyMediaArchiveWindow("
)
window_func = s[start:end]

if "media_archive_request_server_page(media_archive_next_offset_id);" not in window_func:
    old = (
        "                if (\n"
        "                    current_peer &&\n"
        "                    !no_more_msgs\n"
        "                ) {\n"
        "                    get_history();\n"
        "                }"
    )

    new = (
        "                if (\n"
        "                    current_peer &&\n"
        "                    media_archive_server_active &&\n"
        "                    !media_archive_search_pending &&\n"
        "                    !media_archive_no_more\n"
        "                ) {\n"
        "                    media_archive_request_server_page(\n"
        "                        media_archive_next_offset_id\n"
        "                    );\n"
        "                }"
    )

    if old not in window_func:
        raise SystemExit(
            "Could not locate Media Older/get_history block."
        )

    window_func = window_func.replace(
        old,
        new,
        1
    )

    s = (
        s[:start]
        + window_func
        + s[end:]
    )


# -----------------------------------------------------------------------------
# Clear server-only Document entries when the archive is reset.
# -----------------------------------------------------------------------------

start, end = cpp_function_range(
    s,
    "void media_archive_clear()"
)
clear_func = s[start:end]

if "// purge server-only media documents" not in clear_func:
    brace = clear_func.find("{")
    inject = r'''
    // purge server-only media documents
    media_archive_server_active = false;
    media_archive_search_pending = false;
    media_archive_next_offset_id = 0;
    media_archive_loaded_count = 0;
    media_archive_total = 0;
    media_archive_no_more = false;

    for (
        int i = (int)documents.size() - 1;
        i >= 0;
        i--
    ) {
        if (documents[i].visible)
            continue;

        free(documents[i].filename);
        free(documents[i].file_reference);
        documents.erase(
            documents.begin() + i
        );
    }

'''
    clear_func = (
        clear_func[:brace + 1]
        + inject
        + clear_func[brace + 1:]
    )

    s = s[:start] + clear_func + s[end:]


# -----------------------------------------------------------------------------
# A server-only Document carries its message id as -document.min.
# Also prevent ordinary currently-loaded chat media from being mixed into the
# server-backed Media window while it is active.
# -----------------------------------------------------------------------------

start, end = cpp_function_range(
    s,
    "void media_archive_add_document("
)
add_func = s[start:end]

if "// server-backed archive accepts only server-only documents while active" not in add_func:
    guard_anchor = "    __int64 document_id = 0;"

    guard = r'''    // server-backed archive accepts only server-only documents while active
    if (
        media_archive_server_active &&
        document->visible
    ) {
        return;
    }

    if (
        !media_archive_server_active &&
        !document->visible
    ) {
        return;
    }

'''

    if guard_anchor not in add_func:
        raise SystemExit(
            "Could not locate media_archive_add_document body."
        )

    add_func = add_func.replace(
        guard_anchor,
        guard + guard_anchor,
        1
    )

    msg_anchor = "    int message_id = 0;"

    msg_new = r'''    int message_id = 0;

    if (
        !document->visible &&
        document->min < 0
    ) {
        message_id =
            -document->min;
    }'''

    if msg_anchor not in add_func:
        raise SystemExit(
            "Could not locate media archive message-id calculation."
        )

    add_func = add_func.replace(
        msg_anchor,
        msg_new,
        1
    )

    s = s[:start] + add_func + s[end:]


# -----------------------------------------------------------------------------
# First opening Media starts a real Telegram search page.
# -----------------------------------------------------------------------------

start, end = cpp_function_range(
    s,
    "void media_archive_show()"
)
show_func = s[start:end]

if "// start real Telegram shared-media retrieval" not in show_func:
    closing_brace = show_func.rfind("}")
    inject = r'''
    // start real Telegram shared-media retrieval
    if (!media_archive_server_active) {
        media_archive_clear();

        media_archive_server_active = true;
        media_archive_search_pending = false;
        media_archive_next_offset_id = 0;
        media_archive_loaded_count = 0;
        media_archive_total = 0;
        media_archive_no_more = false;

        media_archive_request_server_page(0);
    }
'''

    show_func = (
        show_func[:closing_brace]
        + inject
        + show_func[closing_brace:]
    )

    s = s[:start] + show_func + s[end:]

write(t, s)


# =============================================================================
# src/response.cpp
# =============================================================================

s = read(r)


# -----------------------------------------------------------------------------
# Parse a Telegram messages.search(PhotoVideo) result without disturbing the
# visible chat. We temporarily swap out the real chat data and point `chat`
# at a hidden RichEdit20W, reuse Telegacy's own message parser, then move only
# the resulting media Documents back into the real document deque.
# -----------------------------------------------------------------------------

if "media_archive_handle_server_response(" not in s:
    anchor = "void response_handler("

    handler = r'''
static HWND media_archive_parser_chat = NULL;

static bool media_archive_saved_has_document(
    const std::deque<Document>& docs,
    const BYTE* id
) {
    if (!id)
        return false;

    for (
        int i = 0;
        i < (int)docs.size();
        i++
    ) {
        if (
            !docs[i].visible &&
            memcmp(
                docs[i].id,
                id,
                8
            ) == 0
        ) {
            return true;
        }
    }

    return false;
}

static void media_archive_handle_server_response(
    unsigned int constructor,
    BYTE* response,
    int length
) {
    if (!media_archive_accept_response())
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
            "media server response parse failed ctor=0x%08X length=%d",
            constructor,
            length
        );

        media_archive_finish_server_page(
            0,
            0,
            0
        );

        return;
    }

    int vector_header =
        offset - 8;

    int count =
        read_le(
            response + vector_header + 4,
            4
        );

    if (!media_archive_parser_chat) {
        media_archive_parser_chat =
            CreateWindowW(
                L"RichEdit20W",
                NULL,
                WS_CHILD |
                ES_LEFT |
                ES_MULTILINE |
                ES_READONLY,
                0,
                0,
                1,
                1,
                hMain,
                NULL,
                NULL,
                NULL
            );

        if (
            media_archive_parser_chat &&
            hFonts[0]
        ) {
            SendMessageW(
                media_archive_parser_chat,
                WM_SETFONT,
                (WPARAM)hFonts[0],
                FALSE
            );
        }
    }

    if (!media_archive_parser_chat) {
        diag_log(
            "media parser RichEdit creation failed error=%lu",
            GetLastError()
        );

        media_archive_finish_server_page(
            0,
            0,
            total
        );

        return;
    }

    std::deque<Document>
        saved_documents;
    std::deque<Message>
        saved_messages;
    std::vector<TEXTRANGE>
        saved_links;

    saved_documents.swap(
        documents
    );
    saved_messages.swap(
        messages
    );
    saved_links.swap(
        links
    );

    HWND saved_chat = chat;
    bool saved_drawchat = drawchat;
    wchar_t* saved_last_sender =
        last_tofront_sender;

    BYTE saved_group_front[8];
    BYTE saved_group[8];

    memcpy(
        saved_group_front,
        group_id_tofront,
        8
    );
    memcpy(
        saved_group,
        group_id,
        8
    );

    chat =
        media_archive_parser_chat;
    drawchat = false;
    last_tofront_sender = NULL;

    memset(
        group_id_tofront,
        0,
        8
    );
    memset(
        group_id,
        0,
        8
    );

    SendMessageW(
        chat,
        WM_SETTEXT,
        0,
        (LPARAM)L""
    );

    int last_id = 0;
    int parsed_count = 0;

    for (
        int i = 0;
        i < count;
        i++
    ) {
        if (
            offset + 16 >
            length
        ) {
            diag_log(
                "media server response truncated item=%d offset=%d length=%d",
                i,
                offset,
                length
            );

            break;
        }

        int id =
            message_search_extract_id(
                response + offset
            );

        int consumed =
            message_handler(
                true,
                response + offset,
                false,
                false,
                false
            );

        if (
            consumed <= 0 ||
            offset + consumed >
                length
        ) {
            diag_log(
                "media server invalid message item=%d consumed=%d offset=%d length=%d",
                i,
                consumed,
                offset,
                length
            );

            break;
        }

        if (id > 0)
            last_id = id;

        parsed_count++;
        offset += consumed;
    }

    // Move only photo/video thumbnail Documents into the real deque.
    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        Document& d =
            documents[i];

        int message_id = 0;

        for (
            int j = 0;
            j < (int)messages.size();
            j++
        ) {
            if (
                d.min >=
                    messages[j].start_char &&
                d.max <=
                    messages[j].end_footer
            ) {
                message_id =
                    messages[j].id;
                break;
            }
        }

        bool usable =
            d.photo_size > 1 &&
            !media_archive_saved_has_document(
                saved_documents,
                d.id
            );

        if (
            usable &&
            message_id > 0
        ) {
            d.visible = false;
            d.min = -message_id;
            d.max = -message_id;

            // No file request has been issued for this server-only document yet.
            memset(
                d.photo_msg_id,
                0,
                8
            );

            saved_documents.push_front(
                d
            );

            // Ownership of these pointers is now with saved_documents.
            d.filename = NULL;
            d.file_reference = NULL;
        }
    }

    // Free parser-only Document pointer members which were not moved.
    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        free(
            documents[i].filename
        );
        free(
            documents[i].file_reference
        );
    }

    documents.clear();

    for (
        int i = 0;
        i < (int)links.size();
        i++
    ) {
        free(
            links[i].lpstrText
        );
    }

    links.clear();
    messages.clear();

    SendMessageW(
        chat,
        WM_SETTEXT,
        0,
        (LPARAM)L""
    );

    chat = saved_chat;
    drawchat = saved_drawchat;
    last_tofront_sender =
        saved_last_sender;

    memcpy(
        group_id_tofront,
        saved_group_front,
        8
    );
    memcpy(
        group_id,
        saved_group,
        8
    );

    saved_documents.swap(
        documents
    );
    saved_messages.swap(
        messages
    );
    saved_links.swap(
        links
    );

    media_archive_finish_server_page(
        last_id,
        parsed_count,
        total
    );

    media_archive_start_next_download();
}

'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate response_handler() in response.cpp."
        )

    s = s.replace(
        anchor,
        handler + anchor,
        1
    )


# -----------------------------------------------------------------------------
# Route messages.Messages-family responses belonging to Media before normal
# server-search handling.
# -----------------------------------------------------------------------------

media_route = (
    "\t\tif (media_archive_matches_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmedia_archive_handle_server_response(\n"
    "\t\t\t\tconstructor,\n"
    "\t\t\t\tunenc_response,\n"
    "\t\t\t\tlength\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
    "\n"
)

if media_route not in s:
    # Find the actual CALL inside response_handler(), not the static helper
    # definition near the top of response.cpp.
    call_marker = (
        "\t\t\tmessage_search_handle_server_response(\n"
    )

    call_pos = s.find(call_marker)

    if call_pos < 0:
        raise SystemExit(
            "Could not locate server-search response handler call. "
            "Run patch_server_search.py before this patch."
        )

    condition = (
        "\t\tif (message_search_matches_rpc(last_rpcresult_msgid)) {"
    )

    route_pos = s.rfind(
        condition,
        0,
        call_pos
    )

    if (
        route_pos < 0 or
        call_pos - route_pos >
            2000
    ):
        raise SystemExit(
            "Could not associate messages.search response handler call "
            "with its message_search_matches_rpc() route."
        )

    s = (
        s[:route_pos]
        + media_route
        + s[route_pos:]
    )


# -----------------------------------------------------------------------------
# Route Media rpc_error before the message-search rpc_error route.
# -----------------------------------------------------------------------------

media_error_route = (
    "\t\tif (media_archive_matches_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmedia_archive_handle_rpc_error(\n"
    "\t\t\t\terror_code,\n"
    "\t\t\t\terror_message\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
)

if media_error_route not in s:
    # As above, key off the indented CALL in the rpc_error case.
    call_marker = (
        "\t\t\tmessage_search_handle_rpc_error(\n"
    )

    call_pos = s.find(call_marker)

    if call_pos < 0:
        raise SystemExit(
            "Could not locate server-search rpc_error handler call."
        )

    condition = (
        "\t\tif (message_search_matches_rpc(last_rpcresult_msgid)) {"
    )

    route_pos = s.rfind(
        condition,
        0,
        call_pos
    )

    if (
        route_pos < 0 or
        call_pos - route_pos >
            2000
    ):
        raise SystemExit(
            "Could not associate server-search rpc_error handler call "
            "with its message_search_matches_rpc() route."
        )

    s = (
        s[:route_pos]
        + media_error_route
        + s[route_pos:]
    )


# -----------------------------------------------------------------------------
# Server-only media Documents must never replace text in the visible RichEdit.
# They still go through the existing decode path and media_archive_add_document.
# -----------------------------------------------------------------------------

capture_marker = (
    "media_archive_add_document(&documents[i], hClone);"
)

capture_pos = s.find(
    capture_marker
)

if capture_pos < 0:
    raise SystemExit(
        "Could not locate Media archive bitmap capture in upload.file. "
        "Run patch_search_media.py first."
    )

replace_call = (
    "\t\t\t\treplace_in_chat(NULL, &cr, NULL, hClone, NULL, NULL, NULL);"
)

replace_pos = s.rfind(
    replace_call,
    max(0, capture_pos - 1200),
    capture_pos
)

if replace_pos < 0:
    conditional = (
        "if (documents[i].visible)\n"
        "\t\t\t\t\treplace_in_chat(NULL, &cr, NULL, hClone, NULL, NULL, NULL);"
    )
    if conditional not in s:
        raise SystemExit(
            "Could not locate upload.file replace_in_chat near Media capture."
        )
else:
    replacement = (
        "\t\t\t\tif (documents[i].visible)\n"
        "\t\t\t\t\treplace_in_chat(NULL, &cr, NULL, hClone, NULL, NULL, NULL);"
    )

    s = (
        s[:replace_pos]
        + replacement
        + s[
            replace_pos
            + len(replace_call):
        ]
    )

write(r, s)

print(
    "Applied UI polish + true Telegram server-backed Media archive."
)
