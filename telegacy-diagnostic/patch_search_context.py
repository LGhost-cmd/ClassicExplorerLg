#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_search_context.py <Telegacy source directory>")

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

def replace_cpp_function(source, signature, replacement):
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
                return source[:start] + replacement + source[i + 1:]

        i += 1

    raise SystemExit(f"Could not locate closing brace: {signature}")


# =============================================================================
# include/telegacy.h
# =============================================================================

s = read(h)

if "extern bool message_search_context_pending;" not in s:
    anchor = "void message_search_clear_chat_view();"

    block = r'''

// Search-result context navigation.
extern bool message_search_context_pending;
extern BYTE message_search_context_rpc_id[8];

bool message_search_matches_context_rpc(const BYTE* msg_id);
bool message_search_context_accept_response();
void message_search_finish_context();
void message_search_handle_context_rpc_error(
    int error_code,
    const wchar_t* error_message
);
'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate server-search declarations. "
            "Run patch_server_search.py before patch_search_context.py."
        )

    s = s.replace(anchor, anchor + block, 1)

write(h, s)


# =============================================================================
# src/telegacy.cpp
# =============================================================================

s = read(t)

if "HWND hMessageSearchStatus = NULL;" not in s:
    anchor = "HWND hMediaArchiveButton = NULL;"

    if anchor not in s:
        raise SystemExit(
            "Could not locate search controls. "
            "Run patch_search_media.py first."
        )

    s = s.replace(
        anchor,
        anchor + "\nHWND hMessageSearchStatus = NULL;",
        1
    )


# -----------------------------------------------------------------------------
# Add context-search state after the server search state.
# -----------------------------------------------------------------------------

if "bool message_search_context_pending = false;" not in s:
    anchor = "int message_search_total = 0;"

    block = r'''

bool message_search_context_pending = false;
BYTE message_search_context_rpc_id[8] = {0};

static bool message_search_context_dirty = false;
static BYTE message_search_context_peer_id[8] = {0};
static int message_search_context_target_id = 0;
static wchar_t message_search_context_query[256] = {0};

static int message_search_selected = 0;
static int message_search_page_select_mode = 0;
'''

    if anchor not in s:
        raise SystemExit(
            "Could not locate server-search state. "
            "Run patch_server_search.py first."
        )

    s = s.replace(anchor, anchor + block, 1)


# -----------------------------------------------------------------------------
# Helpers for status, result navigation and loading message context.
# -----------------------------------------------------------------------------

if "static bool message_search_send_context(" not in s:
    anchor = "static void message_search_update_buttons() {"

    context_helpers = r'''static int message_search_page_base() {
    if (message_search_page_offsets.empty())
        return 0;

    return (
        (int)message_search_page_offsets.size() - 1
    ) * 20;
}

static void message_search_update_status() {
    if (!hMessageSearchStatus)
        return;

    if (
        message_search_total <= 0 ||
        message_search_current_ids.empty()
    ) {
        SetWindowTextW(
            hMessageSearchStatus,
            L"0 / 0"
        );
        return;
    }

    int position =
        message_search_page_base() +
        message_search_selected +
        1;

    if (position < 1)
        position = 1;

    if (position > message_search_total)
        position = message_search_total;

    wchar_t text[64];

    _snwprintf(
        text,
        ARRAYSIZE(text) - 1,
        L"%d / %d",
        position,
        message_search_total
    );

    text[ARRAYSIZE(text) - 1] = 0;

    SetWindowTextW(
        hMessageSearchStatus,
        text
    );
}

static bool message_search_send_context(
    int target_id
) {
    if (
        !message_search_mode ||
        !current_peer ||
        target_id <= 0
    ) {
        return false;
    }

    if (message_search_context_pending) {
        message_search_context_dirty = true;
        return false;
    }

    wchar_t query[256] = {0};

    if (hMessageSearch) {
        GetWindowTextW(
            hMessageSearch,
            query,
            ARRAYSIZE(query)
        );
    }

    if (!query[0])
        return false;

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

    // Telegram documents this combination as "messages around MSGID".
    write_le(
        unenc_query + offset,
        target_id,
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
        message_search_context_rpc_id,
        unenc_query + 16,
        8
    );

    memcpy(
        message_search_context_peer_id,
        current_peer->id,
        8
    );

    message_search_context_target_id =
        target_id;

    lstrcpynW(
        message_search_context_query,
        query,
        ARRAYSIZE(message_search_context_query)
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
            "message search context send failed target=%d",
            target_id
        );

        return false;
    }

    message_search_context_pending = true;
    message_search_context_dirty = false;

    diag_log(
        "message search context request target=%d add_offset=-10 limit=20",
        target_id
    );

    return true;
}

static void message_search_request_selected_context() {
    if (
        message_search_current_ids.empty() ||
        message_search_selected < 0 ||
        message_search_selected >=
            (int)message_search_current_ids.size()
    ) {
        return;
    }

    message_search_update_status();

    message_search_send_context(
        message_search_current_ids[
            message_search_selected
        ]
    );
}

'''

    pos = s.find(anchor)
    if pos < 0:
        raise SystemExit(
            "Could not locate message_search_update_buttons()."
        )

    s = s[:pos] + context_helpers + s[pos:]


# -----------------------------------------------------------------------------
# Replace button-state function: arrows now mean previous/next RESULT.
# -----------------------------------------------------------------------------

new_update_buttons = r'''static void message_search_update_buttons() {
    if (
        !hMessageSearchPrev ||
        !hMessageSearchNext
    ) {
        return;
    }

    bool busy =
        message_search_pending ||
        message_search_context_pending;

    int base =
        message_search_page_base();

    bool can_previous =
        !message_search_current_ids.empty() &&
        (
            message_search_selected > 0 ||
            base > 0
        );

    bool can_next =
        !message_search_current_ids.empty() &&
        (
            message_search_selected + 1 <
                (int)message_search_current_ids.size() ||
            (
                message_search_total > 0 &&
                base +
                (int)message_search_current_ids.size()
                    < message_search_total
            )
        );

    EnableWindow(
        hMessageSearchPrev,
        (!busy && can_previous)
            ? TRUE
            : FALSE
    );

    EnableWindow(
        hMessageSearchNext,
        (!busy && can_next)
            ? TRUE
            : FALSE
    );

    message_search_update_status();
}'''

s = replace_cpp_function(
    s,
    "static void message_search_update_buttons()",
    new_update_buttons
)


# -----------------------------------------------------------------------------
# Restore normal history and fully reset context mode.
# -----------------------------------------------------------------------------

new_restore = r'''static void message_search_restore_normal_history() {
    message_search_mode = false;
    message_search_dirty = false;
    message_search_context_dirty = false;

    message_search_current_ids.clear();
    message_search_total = 0;
    message_search_selected = 0;
    message_search_page_select_mode = 0;
    message_search_page_offsets.clear();

    if (hMessageSearchStatus)
        SetWindowTextW(
            hMessageSearchStatus,
            L""
        );

    message_search_update_buttons();

    if (!current_peer || !chat)
        return;

    message_search_clear_chat_view();

    no_more_msgs = false;

    InterlockedExchange(
        &history_request_pending,
        0
    );

    get_history();
}'''

s = replace_cpp_function(
    s,
    "static void message_search_restore_normal_history()",
    new_restore
)


# -----------------------------------------------------------------------------
# Initial search starts on the first result.
# -----------------------------------------------------------------------------

new_begin = r'''static void message_search_begin_from_ui() {
    if (!hMessageSearch)
        return;

    wchar_t query[256] = {0};

    GetWindowTextW(
        hMessageSearch,
        query,
        ARRAYSIZE(query)
    );

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
    message_search_selected = 0;
    message_search_page_select_mode = 0;

    message_search_update_buttons();

    message_search_send_request(0);
}'''

s = replace_cpp_function(
    s,
    "static void message_search_begin_from_ui()",
    new_begin
)


# -----------------------------------------------------------------------------
# Previous/next navigate individual hits. Page requests happen only at an edge.
# -----------------------------------------------------------------------------

new_previous = r'''static void message_search_previous_result() {
    if (
        message_search_pending ||
        message_search_context_pending ||
        message_search_current_ids.empty()
    ) {
        return;
    }

    if (message_search_selected > 0) {
        message_search_selected--;

        message_search_update_buttons();
        message_search_request_selected_context();
        return;
    }

    if (message_search_page_offsets.size() <= 1) {
        MessageBeep(MB_ICONASTERISK);
        return;
    }

    int old_offset =
        message_search_page_offsets.back();

    message_search_page_offsets.pop_back();

    int offset_id =
        message_search_page_offsets.back();

    message_search_page_select_mode = 1;

    if (!message_search_send_request(offset_id)) {
        message_search_page_offsets.push_back(
            old_offset
        );

        message_search_page_select_mode = 0;
    }
}'''

s = replace_cpp_function(
    s,
    "static void message_search_newer_page()",
    new_previous
)

new_next = r'''static void message_search_next_result() {
    if (
        message_search_pending ||
        message_search_context_pending ||
        message_search_current_ids.empty()
    ) {
        return;
    }

    if (
        message_search_selected + 1 <
        (int)message_search_current_ids.size()
    ) {
        message_search_selected++;

        message_search_update_buttons();
        message_search_request_selected_context();
        return;
    }

    int base =
        message_search_page_base();

    if (
        message_search_total <= 0 ||
        base +
        (int)message_search_current_ids.size()
            >= message_search_total
    ) {
        MessageBeep(MB_ICONASTERISK);
        return;
    }

    int offset_id =
        message_search_current_ids.back();

    message_search_page_offsets.push_back(
        offset_id
    );

    message_search_page_select_mode = 0;

    if (!message_search_send_request(offset_id)) {
        message_search_page_offsets.pop_back();
    }
}'''

s = replace_cpp_function(
    s,
    "static void message_search_older_page()",
    new_next
)


# -----------------------------------------------------------------------------
# Search response now chooses a hit and immediately loads its context.
# -----------------------------------------------------------------------------

new_finish_response = r'''void message_search_finish_response(int total) {
    message_search_total = total;
    message_search_dirty = false;

    if (message_search_current_ids.empty()) {
        message_search_selected = 0;
        message_search_clear_chat_view();
        message_search_update_buttons();

        diag_log(
            "message search page loaded count=0 total=%d",
            message_search_total
        );

        return;
    }

    if (message_search_page_select_mode == 1) {
        message_search_selected =
            (int)message_search_current_ids.size() - 1;
    } else {
        message_search_selected = 0;
    }

    message_search_page_select_mode = 0;

    message_search_update_buttons();

    diag_log(
        "message search page loaded count=%d total=%d base=%d selected=%d",
        (int)message_search_current_ids.size(),
        message_search_total,
        message_search_page_base(),
        message_search_selected
    );

    message_search_request_selected_context();
}'''

s = replace_cpp_function(
    s,
    "void message_search_finish_response(int total)",
    new_finish_response
)


# -----------------------------------------------------------------------------
# Context-response correlation and highlighted target.
# -----------------------------------------------------------------------------

if "bool message_search_matches_context_rpc(" not in s:
    anchor = "void message_search_handle_rpc_error("

    context_response_api = r'''bool message_search_matches_context_rpc(
    const BYTE* msg_id
) {
    return
        message_search_context_pending &&
        msg_id &&
        memcmp(
            message_search_context_rpc_id,
            msg_id,
            8
        ) == 0;
}

bool message_search_context_accept_response() {
    message_search_context_pending = false;

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
            message_search_context_peer_id,
            8
        ) == 0;

    bool same_query =
        query[0] &&
        wcscmp(
            query,
            message_search_context_query
        ) == 0;

    bool same_target =
        message_search_selected >= 0 &&
        message_search_selected <
            (int)message_search_current_ids.size() &&
        message_search_current_ids[
            message_search_selected
        ] == message_search_context_target_id;

    if (
        !message_search_mode ||
        message_search_context_dirty ||
        !same_peer ||
        !same_query ||
        !same_target
    ) {
        diag_log(
            "message search context stale mode=%d dirty=%d peer=%d query=%d target=%d",
            message_search_mode ? 1 : 0,
            message_search_context_dirty ? 1 : 0,
            same_peer ? 1 : 0,
            same_query ? 1 : 0,
            same_target ? 1 : 0
        );

        message_search_context_dirty = false;

        if (
            message_search_mode &&
            !message_search_pending &&
            same_peer &&
            query[0]
        ) {
            SetTimer(
                hMain,
                32,
                30,
                NULL
            );
        }

        message_search_update_buttons();
        return false;
    }

    message_search_context_dirty = false;
    return true;
}

void message_search_finish_context() {
    message_search_update_buttons();

    if (
        !chat ||
        message_search_context_target_id <= 0
    ) {
        return;
    }

    wchar_t query[256] = {0};

    if (hMessageSearch) {
        GetWindowTextW(
            hMessageSearch,
            query,
            ARRAYSIZE(query)
        );
    }

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            messages[i].id !=
            message_search_context_target_id
        ) {
            continue;
        }

        CHARRANGE selection;
        selection.cpMin =
            messages[i].start_char;
        selection.cpMax =
            messages[i].start_char;

        if (query[0]) {
            FINDTEXTEXW ft = {0};

            ft.chrg.cpMin =
                messages[i].end_header;

            ft.chrg.cpMax =
                messages[i].end_char;

            ft.lpstrText = query;

            LRESULT found =
                SendMessageW(
                    chat,
                    EM_FINDTEXTEXW,
                    FR_DOWN,
                    (LPARAM)&ft
                );

            if (found != -1) {
                selection.cpMin =
                    ft.chrgText.cpMin;

                selection.cpMax =
                    ft.chrgText.cpMax;
            }
        }

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

        diag_log(
            "message search context displayed target=%d",
            message_search_context_target_id
        );

        return;
    }

    diag_log(
        "message search target not present in returned context target=%d",
        message_search_context_target_id
    );
}

void message_search_handle_context_rpc_error(
    int error_code,
    const wchar_t* error_message
) {
    message_search_context_pending = false;

    diag_log(
        "message search context rpc_error code=%d",
        error_code
    );

    message_search_update_buttons();

    if (
        message_search_mode &&
        !message_search_pending &&
        !message_search_current_ids.empty()
    ) {
        SetTimer(
            hMain,
            32,
            250,
            NULL
        );
    }
}

'''

    pos = s.find(anchor)
    if pos < 0:
        raise SystemExit(
            "Could not locate message_search_handle_rpc_error()."
        )

    s = s[:pos] + context_response_api + s[pos:]


# -----------------------------------------------------------------------------
# Search-field timer 32 retries/loads selected context after stale responses.
# -----------------------------------------------------------------------------

timer_anchor = (
    "\tcase WM_TIMER:\n"
    "\t\tif (wParam == 31) {\n"
    "\t\t\tKillTimer(hWnd, 31);\n"
    "\t\t\tmessage_search_begin_from_ui();\n"
    "\t\t} else if (wParam == 0) {"
)

timer_new = (
    "\tcase WM_TIMER:\n"
    "\t\tif (wParam == 32) {\n"
    "\t\t\tKillTimer(hWnd, 32);\n"
    "\t\t\tmessage_search_request_selected_context();\n"
    "\t\t} else if (wParam == 31) {\n"
    "\t\t\tKillTimer(hWnd, 31);\n"
    "\t\t\tmessage_search_begin_from_ui();\n"
    "\t\t} else if (wParam == 0) {"
)

if timer_anchor in s:
    s = s.replace(
        timer_anchor,
        timer_new,
        1
    )
elif "wParam == 32" not in s[
    s.find("case WM_TIMER:"):
    s.find("case WM_TIMER:") + 1200
]:
    raise SystemExit(
        "Could not locate server-search WM_TIMER block."
    )


# -----------------------------------------------------------------------------
# Change arrow handlers from page navigation to hit navigation.
#
# Do not depend on case comments, indentation, or the exact command ID text.
# patch_server_search.py already owns the command IDs; here we only replace
# the two function calls inside those handlers.
# -----------------------------------------------------------------------------

if "message_search_previous_result();" not in s:
    if "message_search_newer_page();" not in s:
        raise SystemExit(
            "Could not locate server-search previous-page call in telegacy.cpp"
        )

    s = s.replace(
        "message_search_newer_page();",
        "message_search_previous_result();",
        1
    )

if "message_search_next_result();" not in s:
    if "message_search_older_page();" not in s:
        raise SystemExit(
            "Could not locate server-search next-page call in telegacy.cpp"
        )

    s = s.replace(
        "message_search_older_page();",
        "message_search_next_result();",
        1
    )


# -----------------------------------------------------------------------------
# Reset added context state when switching chats.
# -----------------------------------------------------------------------------

old_reset = r'''			message_search_mode = false;
			message_search_dirty = true;
			message_search_current_ids.clear();
			message_search_total = 0;
			message_search_page_offsets.clear();
			message_search_update_buttons();
'''

new_reset = r'''			message_search_mode = false;
			message_search_dirty = true;
			message_search_context_dirty = true;
			message_search_current_ids.clear();
			message_search_total = 0;
			message_search_selected = 0;
			message_search_page_select_mode = 0;
			message_search_page_offsets.clear();
			message_search_update_buttons();

			if (hMessageSearchStatus)
				SetWindowTextW(
					hMessageSearchStatus,
					L""
				);
'''

if old_reset in s:
    s = s.replace(
        old_reset,
        new_reset,
        1
    )
elif "message_search_context_dirty = true;" not in s:
    raise SystemExit(
        "Could not locate server-search chat-switch reset."
    )


# -----------------------------------------------------------------------------
# Add persistent status label and rebalance the search row.
# -----------------------------------------------------------------------------

if "hMessageSearchStatus = CreateWindowW(" not in s:
    prev_anchor = r'''		hMessageSearchPrev = CreateWindowW(
'''

    status_control = r'''		hMessageSearchStatus = CreateWindowW(
			L"STATIC",
			L"",
			WS_CHILD |
			WS_VISIBLE |
			SS_CENTER |
			SS_CENTERIMAGE,
			width - 245,
			40,
			65,
			22,
			hWnd,
			(HMENU)3005,
			NULL,
			NULL
		);

'''

    pos = s.find(prev_anchor)
    if pos < 0:
        raise SystemExit(
            "Could not locate previous-result button creation."
        )

    s = (
        s[:pos] +
        status_control +
        s[pos:]
    )

# Creation geometry.
search_create_old = r'''		hMessageSearch = CreateWindowExW(
			WS_EX_CLIENTEDGE,
			L"EDIT",
			L"",
			WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
			10,
			40,
			width - 205,
			22,
'''

search_create_new = r'''		hMessageSearch = CreateWindowExW(
			WS_EX_CLIENTEDGE,
			L"EDIT",
			L"",
			WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
			10,
			40,
			width - 260,
			22,
'''

if search_create_old in s:
    s = s.replace(
        search_create_old,
        search_create_new,
        1
    )

prev_create_old = r'''		hMessageSearchPrev = CreateWindowW(
			L"BUTTON",
			L"<",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 190,
			40,
			45,
'''

prev_create_new = r'''		hMessageSearchPrev = CreateWindowW(
			L"BUTTON",
			L"<",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 175,
			40,
			35,
'''

if prev_create_old in s:
    s = s.replace(
        prev_create_old,
        prev_create_new,
        1
    )

next_create_old = r'''		hMessageSearchNext = CreateWindowW(
			L"BUTTON",
			L">",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 140,
			40,
			45,
'''

next_create_new = r'''		hMessageSearchNext = CreateWindowW(
			L"BUTTON",
			L">",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 135,
			40,
			35,
'''

if next_create_old in s:
    s = s.replace(
        next_create_old,
        next_create_new,
        1
    )

media_create_old = r'''		hMediaArchiveButton = CreateWindowW(
			L"BUTTON",
			L"Media",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 90,
			40,
			80,
'''

media_create_new = r'''		hMediaArchiveButton = CreateWindowW(
			L"BUTTON",
			L"Media",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 95,
			40,
			85,
'''

if media_create_old in s:
    s = s.replace(
        media_create_old,
        media_create_new,
        1
    )

# Font for status control.
font_anchor = r'''		SendMessage(
			hMessageSearchPrev,
			WM_SETFONT,
'''

if "hMessageSearchStatus,\n\t\t\tWM_SETFONT" not in s:
    font_block = r'''		SendMessage(
			hMessageSearchStatus,
			WM_SETFONT,
			(WPARAM)searchFont,
			TRUE
		);

'''

    pos = s.find(font_anchor)
    if pos < 0:
        raise SystemExit(
            "Could not locate search-row font setup."
        )

    s = s[:pos] + font_block + s[pos:]


# Resize geometry.
search_resize_old = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearch,
				NULL,
				10,
				40,
				width - 205,
				22,
				SWP_NOZORDER
			);
'''

search_resize_new = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearch,
				NULL,
				10,
				40,
				width - 260,
				22,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchStatus,
				NULL,
				width - 245,
				40,
				65,
				22,
				SWP_NOZORDER
			);
'''

if search_resize_old in s:
    s = s.replace(
        search_resize_old,
        search_resize_new,
        1
    )
elif "hMessageSearchStatus" not in s[
    s.find("WM_SIZE"):
]:
    raise SystemExit(
        "Could not locate message-search resize block."
    )

prev_resize_old = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchPrev,
				NULL,
				width - 190,
				40,
				45,
'''

prev_resize_new = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchPrev,
				NULL,
				width - 175,
				40,
				35,
'''

if prev_resize_old in s:
    s = s.replace(
        prev_resize_old,
        prev_resize_new,
        1
    )

next_resize_old = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchNext,
				NULL,
				width - 140,
				40,
				45,
'''

next_resize_new = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchNext,
				NULL,
				width - 135,
				40,
				35,
'''

if next_resize_old in s:
    s = s.replace(
        next_resize_old,
        next_resize_new,
        1
    )

media_resize_old = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMediaArchiveButton,
				NULL,
				width - 90,
				40,
				80,
'''

media_resize_new = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMediaArchiveButton,
				NULL,
				width - 95,
				40,
				85,
'''

if media_resize_old in s:
    s = s.replace(
        media_resize_old,
        media_resize_new,
        1
    )

# Keep highlighted search selection visible when focus remains in the EDIT.
chat_style_old = (
    "ES_READONLY | WS_CLIPSIBLINGS,"
)

chat_style_new = (
    "ES_READONLY | ES_NOHIDESEL | WS_CLIPSIBLINGS,"
)

if chat_style_old in s:
    s = s.replace(
        chat_style_old,
        chat_style_new,
        1
    )

# One more deferred window.
if "BeginDeferWindowPos(16)" in s:
    s = s.replace(
        "BeginDeferWindowPos(16)",
        "BeginDeferWindowPos(17)",
        1
    )

write(t, s)


# =============================================================================
# src/response.cpp
# =============================================================================

s = read(r)


# -----------------------------------------------------------------------------
# Search response: collect hit IDs, then discard the temporary render and ask
# for context around the selected result.
# -----------------------------------------------------------------------------

new_search_response = r'''static void message_search_handle_server_response(
    unsigned int constructor,
    BYTE* response,
    int length
) {
    bool accept =
        message_search_accept_response();

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

        message_search_current_ids.clear();
        message_search_finish_response(0);
        return;
    }

    int vector_header =
        offset - 8;

    int count =
        read_le(
            response + vector_header + 4,
            4
        );

    if (chat)
        SendMessage(
            chat,
            WM_SETREDRAW,
            FALSE,
            0
        );

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
            offset + consumed > length
        ) {
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

    // The temporary render above is only used to reuse Telegacy's existing
    // message parser safely. The user should see context, not a hit-only page.
    message_search_clear_chat_view();

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

    message_search_finish_response(total);
}'''

s = replace_cpp_function(
    s,
    "static void message_search_handle_server_response(",
    new_search_response
)


# -----------------------------------------------------------------------------
# Context response: render ~10 newer + target + ~10 older, then highlight hit.
# -----------------------------------------------------------------------------

if "static void message_search_handle_context_response(" not in s:
    anchor = "void response_handler("

    context_response = r'''static void message_search_handle_context_response(
    unsigned int constructor,
    BYTE* response,
    int length
) {
    if (!message_search_context_accept_response())
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
            "message search context parse failed ctor=0x%08X length=%d",
            constructor,
            length
        );

        message_search_finish_context();
        return;
    }

    int vector_header =
        offset - 8;

    int count =
        read_le(
            response + vector_header + 4,
            4
        );

    message_search_clear_chat_view();

    if (chat)
        SendMessage(
            chat,
            WM_SETREDRAW,
            FALSE,
            0
        );

    int documents_count_old =
        (int)documents.size();

    for (int i = 0; i < count; i++) {
        if (offset + 16 > length) {
            diag_log(
                "message search context truncated item=%d offset=%d length=%d",
                i,
                offset,
                length
            );
            break;
        }

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
            offset + consumed > length
        ) {
            diag_log(
                "message search context invalid item=%d consumed=%d offset=%d length=%d",
                i,
                consumed,
                offset,
                length
            );
            break;
        }

        offset += consumed;
    }

    // Match normal history behavior: start one inline-media download at a time.
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
                !read_le(
                    documents[i].photo_msg_id,
                    8
                )
            ) {
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

    message_search_finish_context();
}

'''

    pos = s.find(anchor)
    if pos < 0:
        raise SystemExit(
            "Could not locate response_handler()."
        )

    s = s[:pos] + context_response + s[pos:]


# -----------------------------------------------------------------------------
# Route messages.Messages-family RPCs to context before search/history.
#
# Scope the search to the messages.Messages switch case. The same
# message_search_matches_rpc(...) condition is also used in rpc_error, so a
# global s.find() can insert the context handler into the wrong case.
# -----------------------------------------------------------------------------

context_route = (
    "\t\tif (message_search_matches_context_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmessage_search_handle_context_response(\n"
    "\t\t\t\tconstructor,\n"
    "\t\t\t\tunenc_response,\n"
    "\t\t\t\tlength\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
    "\n"
)

if context_route not in s:
    messages_case_candidates = [
        "\tcase 0x5f206716:",
        "\tcase 0x3a54685e:",
        "\tcase 0xc776ba4e:",
        "\tcase 0x8c718e87:",
    ]

    messages_case_pos = -1

    for marker in messages_case_candidates:
        pos = s.find(marker)
        if pos >= 0 and (
            messages_case_pos < 0 or
            pos < messages_case_pos
        ):
            messages_case_pos = pos

    if messages_case_pos < 0:
        raise SystemExit(
            "Could not locate messages.Messages switch case."
        )

    next_case_pos = s.find(
        "\n\tcase ",
        messages_case_pos + 1
    )

    search_route_pos = s.find(
        "\t\tif (message_search_matches_rpc(last_rpcresult_msgid)) {",
        messages_case_pos
    )

    if (
        search_route_pos < 0 or
        (
            next_case_pos >= 0 and
            search_route_pos >= next_case_pos
        )
    ):
        raise SystemExit(
            "Could not locate server-search response route inside messages.Messages."
        )

    s = (
        s[:search_route_pos] +
        context_route +
        s[search_route_pos:]
    )


# -----------------------------------------------------------------------------
# Route context rpc_error as well.
#
# Do not match the formatting of message_search_handle_rpc_error(...).
# patch_server_search.py may emit it on one line or on several lines depending
# on which diagnostic patches ran before it.
# -----------------------------------------------------------------------------

rpc_context = (
    "\t\tif (message_search_matches_context_rpc(last_rpcresult_msgid)) {\n"
    "\t\t\tmessage_search_handle_context_rpc_error(\n"
    "\t\t\t\terror_code,\n"
    "\t\t\t\terror_message\n"
    "\t\t\t);\n"
    "\t\t\tbreak;\n"
    "\t\t}\n"
)

if rpc_context not in s:
    rpc_case = "\tcase 0x2144ca19: { // rpc_error\n"
    rpc_case_pos = s.find(rpc_case)

    if rpc_case_pos < 0:
        raise SystemExit(
            "Could not locate rpc_error case in response.cpp."
        )

    next_case_pos = s.find(
        "\n\tcase ",
        rpc_case_pos + len(rpc_case)
    )

    search_route_pos = s.find(
        "\t\tif (message_search_matches_rpc(last_rpcresult_msgid)) {",
        rpc_case_pos
    )

    if (
        search_route_pos < 0 or
        (
            next_case_pos >= 0 and
            search_route_pos >= next_case_pos
        )
    ):
        raise SystemExit(
            "Could not locate server-search rpc_error route inside rpc_error case."
        )

    s = (
        s[:search_route_pos] +
        rpc_context +
        s[search_route_pos:]
    )


write(r, s)

print(
    "Applied Telegram-style search context navigation: "
    "one hit at a time, result counter, surrounding history, highlight."
)
