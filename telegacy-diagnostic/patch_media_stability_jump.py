#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_media_stability_jump.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"
m = root / "src" / "message.cpp"

for p in (h, t, r, m):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


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


def replace_function(source, signature, replacement):
    start, end = function_range(source, signature)
    return source[:start] + replacement + source[end:]


# Clean/idempotent application check.
if (
    "media_archive_stability_jump_v1" in read(h)
    and "MEDIA_ARCHIVE_CLICK_TIMER" in read(t)
    and "media_archive_safe_message_handler" in read(r)
    and "Media metadata parser deliberately skips emoji/OLE decoration." in read(m)
):
    print("Media stability/go-to-message patch already applied.")
    raise SystemExit(0)


# =============================================================================
# Header: shared state/routes needed by response.cpp and message.cpp.
# =============================================================================

s = read(h)

if "media_archive_stability_jump_v1" not in s:
    anchor = "void media_archive_start_next_download();"

    addition = r'''

// media_archive_stability_jump_v1
extern bool media_archive_parser_mode;
extern bool media_archive_jump_pending;
extern BYTE media_archive_jump_rpc_id[8];

bool media_archive_jump_matches_rpc(const BYTE* msg_id);
bool media_archive_jump_accept_response();
void media_archive_finish_jump();
void media_archive_handle_jump_rpc_error(
    int error_code,
    const wchar_t* error_message
);
'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate Media server declarations in telegacy.h. "
            "Run patch_ui_media_server.py first."
        )

    s = s.replace(anchor, anchor + addition, 1)

write(h, s)


# =============================================================================
# message.cpp: hidden Media parsing must not spawn custom-emoji work.
#
# The crash log ends inside the Media response parser, before the page-complete
# line. The hidden parser does not need emoji/OLE rendering at all; it only
# needs Document metadata. Skipping this block also prevents rces from growing
# while browsing Media.
# =============================================================================

s = read(m)

if "// Media metadata parser deliberately skips emoji/OLE decoration." not in s:
    old = "\t{\n\t\tint deleted_wchars = 0;\n"

    new = (
        "\t// Media metadata parser deliberately skips emoji/OLE decoration.\n"
        "\tif (!media_archive_parser_mode) {\n"
        "\t\tint deleted_wchars = 0;\n"
    )

    if s.count(old) != 1:
        raise SystemExit(
            "Could not uniquely locate message emoji-decoration block."
        )

    s = s.replace(old, new, 1)

old_tail = "if (!to_front) get_unknown_custom_emojis();"
new_tail = (
    "if (!to_front && !media_archive_parser_mode) "
    "get_unknown_custom_emojis();"
)

if old_tail in s:
    s = s.replace(old_tail, new_tail, 1)
elif new_tail not in s:
    raise SystemExit(
        "Could not locate get_unknown_custom_emojis tail in message.cpp."
    )

write(m, s)


# =============================================================================
# telegacy.cpp: single click = go to message, double click = open cached image.
# =============================================================================

s = read(t)

if "media_archive_stability_jump_v1" not in s:
    state_anchor = (
        "static WNDPROC media_archive_page_edit_original_proc = NULL;"
    )

    jump_state = r'''

// media_archive_stability_jump_v1
bool media_archive_parser_mode = false;
bool media_archive_jump_pending = false;
BYTE media_archive_jump_rpc_id[8] = {0};

static BYTE media_archive_jump_peer_id[8] = {0};
static int media_archive_jump_target_id = 0;

static int media_archive_pending_click_item = -1;
static const UINT_PTR MEDIA_ARCHIVE_CLICK_TIMER = 77;
'''

    if state_anchor not in s:
        raise SystemExit(
            "Could not locate Media page-jump state. "
            "Run patch_media_page_jump.py first."
        )

    s = s.replace(
        state_anchor,
        state_anchor + jump_state,
        1
    )


jump_function = r'''void media_archive_jump_to_message(
    int message_id
) {
    if (
        message_id <= 0 ||
        !current_peer ||
        !chat
    ) {
        return;
    }

    // Fast path: the message is already present in the visible history.
    for (
        int i = 0;
        i < (int)messages.size();
        i++
    ) {
        if (
            messages[i].id !=
            message_id
        ) {
            continue;
        }

        CHARRANGE cr;
        cr.cpMin =
            messages[i].start_char;
        cr.cpMax =
            messages[i].start_char;

        SendMessageW(
            chat,
            EM_EXSETSEL,
            0,
            (LPARAM)&cr
        );

        SendMessageW(
            chat,
            EM_SCROLLCARET,
            0,
            0
        );

        if (
            hMediaArchiveWindow &&
            IsWindow(hMediaArchiveWindow)
        ) {
            DestroyWindow(
                hMediaArchiveWindow
            );
        }

        SetForegroundWindow(
            hMain
        );

        SetFocus(chat);

        diag_log(
            "media jump local target=%d",
            message_id
        );

        return;
    }

    if (media_archive_jump_pending) {
        MessageBeep(
            MB_ICONASTERISK
        );
        return;
    }

    BYTE unenc_query[112] = {0};
    BYTE enc_query[136] = {0};

    internal_header(
        unenc_query,
        true
    );

    int offset = 32;

    // messages.getHistory#4423e6c5
    write_le(
        unenc_query + offset,
        0x4423e6c5,
        4
    );
    offset += 4;

    offset += place_peer(
        unenc_query + offset,
        current_peer,
        true
    );

    // Center a 20-message context around the media message.
    write_le(
        unenc_query + offset,
        message_id,
        4
    );
    offset += 4;

    // offset_date
    memset(
        unenc_query + offset,
        0,
        4
    );
    offset += 4;

    // add_offset = -10
    write_le(
        unenc_query + offset,
        -10,
        4
    );
    offset += 4;

    // limit = 20
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
        media_archive_jump_rpc_id,
        unenc_query + 16,
        8
    );

    memcpy(
        media_archive_jump_peer_id,
        current_peer->id,
        8
    );

    media_archive_jump_target_id =
        message_id;

    if (!convert_message(
        unenc_query,
        enc_query,
        offset,
        0
    )) {
        return;
    }

    int sent =
        send_query(
            enc_query,
            offset + 24
        );

    if (sent <= 0) {
        diag_log(
            "media jump send failed target=%d",
            message_id
        );
        return;
    }

    media_archive_jump_pending = true;

    // A click means "go to message"; close the tool window and bring the
    // conversation forward. A double-click is delayed/cancelled separately.
    if (
        hMediaArchiveWindow &&
        IsWindow(hMediaArchiveWindow)
    ) {
        DestroyWindow(
            hMediaArchiveWindow
        );
    }

    SetForegroundWindow(
        hMain
    );

    diag_log(
        "media jump request target=%d add_offset=-10 limit=20",
        message_id
    );
}

bool media_archive_jump_matches_rpc(
    const BYTE* msg_id
) {
    return
        media_archive_jump_pending &&
        msg_id &&
        memcmp(
            media_archive_jump_rpc_id,
            msg_id,
            8
        ) == 0;
}

bool media_archive_jump_accept_response() {
    media_archive_jump_pending = false;

    bool same_peer =
        current_peer &&
        memcmp(
            current_peer->id,
            media_archive_jump_peer_id,
            8
        ) == 0;

    if (!same_peer) {
        diag_log(
            "media jump stale response target=%d",
            media_archive_jump_target_id
        );
        return false;
    }

    return true;
}

void media_archive_finish_jump() {
    if (
        !chat ||
        media_archive_jump_target_id <= 0
    ) {
        return;
    }

    for (
        int i = 0;
        i < (int)messages.size();
        i++
    ) {
        if (
            messages[i].id !=
            media_archive_jump_target_id
        ) {
            continue;
        }

        CHARRANGE selection;

        selection.cpMin =
            messages[i].start_char;

        selection.cpMax =
            messages[i].start_char;

        SendMessageW(
            chat,
            EM_EXSETSEL,
            0,
            (LPARAM)&selection
        );

        SendMessageW(
            chat,
            EM_SCROLLCARET,
            0,
            0
        );

        SetForegroundWindow(
            hMain
        );

        SetFocus(chat);

        diag_log(
            "media jump displayed target=%d",
            media_archive_jump_target_id
        );

        return;
    }

    diag_log(
        "media jump target missing from returned context target=%d",
        media_archive_jump_target_id
    );
}

void media_archive_handle_jump_rpc_error(
    int error_code,
    const wchar_t* error_message
) {
    media_archive_jump_pending = false;

    SetForegroundWindow(
        hMain
    );

    MessageBeep(
        MB_ICONASTERISK
    );

    diag_log(
        "media jump rpc_error target=%d code=%d",
        media_archive_jump_target_id,
        error_code
    );
}'''

s = replace_function(
    s,
    "static void media_archive_jump_to_message(",
    jump_function
)


# Replace just WM_NOTIFY .. before WM_DESTROY in the Media window.
ws, we = function_range(
    s,
    "static LRESULT CALLBACK TelegacyMediaArchiveWindow("
)
window_func = s[ws:we]

notify_start = window_func.find(
    "        case WM_NOTIFY: {"
)
destroy_start = window_func.find(
    "        case WM_DESTROY: {",
    notify_start
)

if notify_start < 0 or destroy_start < 0:
    raise SystemExit(
        "Could not isolate Media WM_NOTIFY block."
    )

notify_timer_block = r'''        case WM_NOTIFY: {
            LPNMHDR hdr =
                (LPNMHDR)lParam;

            if (
                hdr &&
                hdr->hwndFrom ==
                    hMediaArchiveList &&
                hdr->code ==
                    NM_CLICK
            ) {
                LPNMITEMACTIVATE activate =
                    (LPNMITEMACTIVATE)lParam;

                if (
                    activate &&
                    activate->iItem >= 0
                ) {
                    LVITEMW item = {0};

                    item.mask = LVIF_PARAM;
                    item.iItem =
                        activate->iItem;

                    if (
                        SendMessageW(
                            hMediaArchiveList,
                            LVM_GETITEMW,
                            0,
                            (LPARAM)&item
                        )
                    ) {
                        media_archive_pending_click_item =
                            (int)item.lParam;

                        KillTimer(
                            hwnd,
                            MEDIA_ARCHIVE_CLICK_TIMER
                        );

                        // Delay the single-click action so a second click can
                        // turn it into NM_DBLCLK without navigating away first.
                        SetTimer(
                            hwnd,
                            MEDIA_ARCHIVE_CLICK_TIMER,
                            GetDoubleClickTime() + 20,
                            NULL
                        );
                    }
                }

                return 0;
            }

            if (
                hdr &&
                hdr->hwndFrom ==
                    hMediaArchiveList &&
                hdr->code ==
                    NM_DBLCLK
            ) {
                KillTimer(
                    hwnd,
                    MEDIA_ARCHIVE_CLICK_TIMER
                );

                media_archive_pending_click_item =
                    -1;

                LPNMITEMACTIVATE activate =
                    (LPNMITEMACTIVATE)lParam;

                if (
                    activate &&
                    activate->iItem >= 0
                ) {
                    LVITEMW item = {0};

                    item.mask = LVIF_PARAM;
                    item.iItem =
                        activate->iItem;

                    if (
                        SendMessageW(
                            hMediaArchiveList,
                            LVM_GETITEMW,
                            0,
                            (LPARAM)&item
                        )
                    ) {
                        media_archive_open_item(
                            (int)item.lParam
                        );
                    }
                }

                return 0;
            }

            break;
        }

        case WM_TIMER: {
            if (
                wParam ==
                MEDIA_ARCHIVE_CLICK_TIMER
            ) {
                KillTimer(
                    hwnd,
                    MEDIA_ARCHIVE_CLICK_TIMER
                );

                int item_index =
                    media_archive_pending_click_item;

                media_archive_pending_click_item =
                    -1;

                if (
                    item_index >= 0 &&
                    item_index <
                        (int)media_archive_items.size()
                ) {
                    media_archive_jump_to_message(
                        media_archive_items[
                            item_index
                        ].message_id
                    );
                }

                return 0;
            }

            break;
        }

'''

window_func = (
    window_func[:notify_start]
    + notify_timer_block
    + window_func[destroy_start:]
)

# Ensure teardown cancels the delayed single-click.
destroy_anchor = r'''        case WM_DESTROY: {
            if (hMediaArchiveImages) {'''

destroy_replacement = r'''        case WM_DESTROY: {
            KillTimer(
                hwnd,
                MEDIA_ARCHIVE_CLICK_TIMER
            );

            media_archive_pending_click_item =
                -1;

            if (hMediaArchiveImages) {'''

if destroy_anchor not in window_func:
    raise SystemExit(
        "Could not locate Media WM_DESTROY prologue."
    )

window_func = window_func.replace(
    destroy_anchor,
    destroy_replacement,
    1
)

s = s[:ws] + window_func + s[we:]

write(t, s)


# =============================================================================
# response.cpp: catch bad Media-message parsing and route "go to message".
# =============================================================================

s = read(r)

if "media_archive_safe_message_handler" not in s:
    anchor = "static void media_archive_handle_server_response("

    safe_helper = r'''
static DWORD media_archive_last_parse_exception = 0;

static int media_archive_safe_message_handler(
    BYTE* message_bytes
) {
    int consumed = -1;

    media_archive_last_parse_exception = 0;

    __try {
        consumed =
            message_handler(
                true,
                message_bytes,
                false,
                false,
                false
            );
    }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        media_archive_last_parse_exception =
            GetExceptionCode();

        consumed = -1;
    }

    return consumed;
}

'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate Media server response handler."
        )

    s = s.replace(
        anchor,
        safe_helper + anchor,
        1
    )


server_handler = r'''static void media_archive_handle_server_response(
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
    media_archive_parser_mode = true;

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
    bool parser_exception = false;

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

        diag_log(
            "media parser item begin item=%d id=%d offset=%d ctor=0x%08X",
            i,
            id,
            offset,
            (unsigned int)read_le(
                response + offset,
                4
            )
        );

        int consumed =
            media_archive_safe_message_handler(
                response + offset
            );

        if (
            consumed < 0 &&
            media_archive_last_parse_exception
        ) {
            parser_exception = true;

            diag_log(
                "media parser SEH item=%d id=%d code=0x%08X offset=%d",
                i,
                id,
                (unsigned int)media_archive_last_parse_exception,
                offset
            );

            break;
        }

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

    media_archive_parser_mode = false;

    if (!parser_exception) {
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

                memset(
                    d.photo_msg_id,
                    0,
                    8
                );

                saved_documents.push_front(
                    d
                );

                d.filename = NULL;
                d.file_reference = NULL;
            }
        }

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

        for (
            int i = 0;
            i < (int)links.size();
            i++
        ) {
            free(
                links[i].lpstrText
            );
        }
    } else {
        // message_handler may have stopped halfway through an object. Avoid
        // dereferencing/freeing parser-owned pointer fields after SEH. These
        // temporary objects are simply discarded; the real chat state below
        // is restored intact.
        diag_log(
            "media parser page aborted safely parsed=%d raw=%d total=%d",
            parsed_count,
            count,
            total
        );
    }

    documents.clear();
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

    if (parser_exception) {
        // Preserve Telegram's total-page information, roll back the failed
        // gallery navigation, and most importantly keep the client alive.
        media_archive_finish_server_page(
            0,
            0,
            total
        );

        return;
    }

    media_archive_finish_server_page(
        last_id,
        parsed_count,
        total
    );

    media_archive_start_next_download();
}'''

s = replace_function(
    s,
    "static void media_archive_handle_server_response(",
    server_handler
)


# Dedicated visible-context parser used by a single click in Media.
if "media_archive_handle_jump_response(" not in s:
    anchor = "void response_handler("

    jump_response = r'''
static void media_archive_handle_jump_response(
    unsigned int constructor,
    BYTE* response,
    int length
) {
    if (!media_archive_jump_accept_response())
        return;

    int offset = 0;
    int ignored_total = 0;

    if (!message_search_get_vector(
        constructor,
        response,
        length,
        &offset,
        &ignored_total
    )) {
        diag_log(
            "media jump context parse failed ctor=0x%08X length=%d",
            constructor,
            length
        );

        media_archive_finish_jump();
        return;
    }

    int vector_header =
        offset - 8;

    int count =
        read_le(
            response + vector_header + 4,
            4
        );

    // Leave search mode: after "go to message" this is an ordinary visible
    // chat context and subsequent history requests must be accepted.
    message_search_mode = false;

    message_search_clear_chat_view();

    no_more_msgs = false;

    InterlockedExchange(
        &history_request_pending,
        0
    );

    if (chat) {
        SendMessage(
            chat,
            WM_SETREDRAW,
            FALSE,
            0
        );
    }

    int documents_count_old =
        (int)documents.size();

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
                "media jump truncated item=%d offset=%d length=%d",
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
            media_archive_safe_message_handler(
                response + offset
            );

        if (
            consumed < 0 &&
            media_archive_last_parse_exception
        ) {
            diag_log(
                "media jump parser SEH item=%d id=%d code=0x%08X",
                i,
                id,
                (unsigned int)media_archive_last_parse_exception
            );

            break;
        }

        if (
            consumed <= 0 ||
            offset + consumed >
                length
        ) {
            diag_log(
                "media jump invalid item=%d id=%d consumed=%d",
                i,
                id,
                consumed
            );

            break;
        }

        offset += consumed;
    }

    if (
        IMAGELOADPOLICY == 2 &&
        documents_count_old !=
            (int)documents.size()
    ) {
        for (
            int i =
                (int)documents.size() -
                documents_count_old -
                1;
            i >= 0;
            i--
        ) {
            if (
                documents[i].photo_size == 1
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

                break;
            }
        }
    }

    get_unknown_custom_emojis();

    if (chat) {
        SendMessage(
            chat,
            WM_SETREDRAW,
            TRUE,
            0
        );

        InvalidateRect(
            chat,
            NULL,
            TRUE
        );

        UpdateWindow(chat);
    }

    media_archive_finish_jump();
}

'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate response_handler for Media jump parser."
        )

    s = s.replace(
        anchor,
        jump_response + anchor,
        1
    )


# Route Media-jump messages.Messages before all other search/media routes.
jump_route = (
    "\t\tif (media_archive_jump_matches_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmedia_archive_handle_jump_response(\n"
    "\t\t\t\tconstructor,\n"
    "\t\t\t\tunenc_response,\n"
    "\t\t\t\tlength\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
    "\n"
)

if jump_route not in s:
    messages_case = "\tcase 0x8c718e87: { // messages.Messages"
    case_pos = s.find(messages_case)

    if case_pos < 0:
        raise SystemExit(
            "Could not locate final messages.Messages case label."
        )

    route_anchor = (
        "\t\tif (message_search_matches_context_rpc(last_rpcresult_msgid)) {"
    )

    pos = s.find(
        route_anchor,
        case_pos
    )

    next_case = s.find(
        "\n\tcase ",
        case_pos + len(messages_case)
    )

    if (
        pos < 0 or
        (next_case >= 0 and pos >= next_case)
    ):
        raise SystemExit(
            "Could not locate messages.Messages context route inside handler block."
        )

    s = s[:pos] + jump_route + s[pos:]


# Route Media-jump rpc_error as well.
jump_error_route = (
    "\t\tif (media_archive_jump_matches_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmedia_archive_handle_jump_rpc_error(\n"
    "\t\t\t\terror_code,\n"
    "\t\t\t\terror_message\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
)

if jump_error_route not in s:
    error_case = "\tcase 0x2144ca19: { // rpc_error\n"
    case_pos = s.find(error_case)

    if case_pos < 0:
        raise SystemExit(
            "Could not locate rpc_error case."
        )

    route_anchor = (
        "\t\tif (message_search_matches_context_rpc(last_rpcresult_msgid)) {"
    )

    pos = s.find(
        route_anchor,
        case_pos
    )

    if pos < 0:
        raise SystemExit(
            "Could not locate rpc_error context route."
        )

    s = s[:pos] + jump_error_route + s[pos:]


write(r, s)


# =============================================================================
# Final verification.
# =============================================================================

checks = {
    h: [
        "media_archive_stability_jump_v1",
        "media_archive_jump_matches_rpc",
        "media_archive_parser_mode",
    ],
    t: [
        "MEDIA_ARCHIVE_CLICK_TIMER",
        "media jump request target",
        "NM_CLICK",
        "NM_DBLCLK",
        "media_archive_jump_matches_rpc",
    ],
    r: [
        "media_archive_safe_message_handler",
        "media parser SEH",
        "media_archive_handle_jump_response",
        "media_archive_jump_matches_rpc(last_rpcresult_msgid)",
    ],
    m: [
        "Media metadata parser deliberately skips emoji/OLE decoration.",
        "!to_front && !media_archive_parser_mode",
    ],
}

for p, tokens in checks.items():
    text = read(p)

    for token in tokens:
        if token not in text:
            raise SystemExit(
                f"Internal verification failed in {p.name}: {token}"
            )

print(
    "Applied Media crash containment + single-click go-to-message "
    "(double-click still opens the cached image)."
)
