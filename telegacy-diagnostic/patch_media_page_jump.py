#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_media_page_jump.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing expected Telegacy file: {t}")


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


s = read(t)

if "media_archive_page_jump_v1" in s:
    print("Media page-jump patch already applied.")
    raise SystemExit(0)

required_before = [
    "media_archive_gallery_navigation_v1",
    "media_archive_request_server_page(",
    "media_archive_current_page",
    "hMediaArchivePageLabel",
    "TelegacyMediaArchiveWindow",
]

for token in required_before:
    if token not in s:
        raise SystemExit(
            "Required working gallery code not found: " + token +
            ". Run patch_media_gallery_nav.py before this patch."
        )


# =============================================================================
# State for arbitrary server page retrieval.
# =============================================================================

old_state = r'''static HWND hMediaArchiveNewer = NULL;
static HWND hMediaArchiveOlder = NULL;
static HWND hMediaArchivePageLabel = NULL;
static HIMAGELIST hMediaArchiveImages = NULL;

static int media_archive_current_page = 0;
static int media_archive_request_page = 0;
static int media_archive_highest_page = 0;
static bool media_archive_page_loading = false;
static std::vector<int> media_archive_page_offsets;'''

new_state = r'''static HWND hMediaArchiveNewer = NULL;
static HWND hMediaArchiveOlder = NULL;
static HWND hMediaArchivePageEdit = NULL;
static HWND hMediaArchivePageTotal = NULL;
static HWND hMediaArchivePageGo = NULL;
static HIMAGELIST hMediaArchiveImages = NULL;

static int media_archive_current_page = 0;
static int media_archive_request_page = 0;
static int media_archive_previous_page = 0;
static int media_archive_highest_page = 0;
static bool media_archive_page_loading = false;
static std::vector<int> media_archive_page_offsets;
static std::vector<char> media_archive_loaded_pages;

// media_archive_page_jump_v1
static WNDPROC media_archive_page_edit_original_proc = NULL;'''

if old_state not in s:
    raise SystemExit(
        "Could not locate current Media gallery state block."
    )

s = s.replace(old_state, new_state, 1)


# =============================================================================
# Navigation UI state.
# =============================================================================

update_nav = r'''static int media_archive_total_pages() {
    if (media_archive_total <= 0)
        return 0;

    return (
        media_archive_total +
        19
    ) / 20;
}

static bool media_archive_page_is_loaded(
    int page_index
) {
    return
        page_index >= 0 &&
        page_index <
            (int)media_archive_loaded_pages.size() &&
        media_archive_loaded_pages[
            page_index
        ] != 0;
}

static void media_archive_update_nav() {
    int total_pages =
        media_archive_total_pages();

    bool busy =
        media_archive_search_pending ||
        media_archive_page_loading;

    if (hMediaArchiveNewer) {
        EnableWindow(
            hMediaArchiveNewer,
            !busy &&
            media_archive_current_page > 0
        );
    }

    if (hMediaArchiveOlder) {
        EnableWindow(
            hMediaArchiveOlder,
            !busy &&
            total_pages > 0 &&
            media_archive_current_page + 1 <
                total_pages
        );
    }

    if (hMediaArchivePageEdit) {
        if (
            GetFocus() !=
            hMediaArchivePageEdit
        ) {
            wchar_t page_text[32];

            _snwprintf(
                page_text,
                ARRAYSIZE(page_text) - 1,
                L"%d",
                media_archive_current_page + 1
            );

            page_text[
                ARRAYSIZE(page_text) - 1
            ] = 0;

            SetWindowTextW(
                hMediaArchivePageEdit,
                page_text
            );
        }

        EnableWindow(
            hMediaArchivePageEdit,
            !busy &&
            total_pages > 0
        );
    }

    if (hMediaArchivePageTotal) {
        wchar_t total_text[64];

        if (total_pages > 0) {
            _snwprintf(
                total_text,
                ARRAYSIZE(total_text) - 1,
                L"/ %d",
                total_pages
            );
        } else {
            wcscpy(
                total_text,
                L"/ ?"
            );
        }

        total_text[
            ARRAYSIZE(total_text) - 1
        ] = 0;

        SetWindowTextW(
            hMediaArchivePageTotal,
            total_text
        );
    }

    if (hMediaArchivePageGo) {
        EnableWindow(
            hMediaArchivePageGo,
            !busy &&
            total_pages > 0
        );
    }
}'''

s = replace_function(
    s,
    "static void media_archive_update_nav()",
    update_nav
)


# =============================================================================
# messages.search: extended sender with arbitrary add_offset.
#
# Telegram pagination defines the effective position as:
# offsetFromID(offset_id) + add_offset.
# For direct page N we use offset_id=0 and add_offset=N*20.
# =============================================================================

request_func = r'''static bool media_archive_request_server_page_ex(
    int offset_id,
    int add_offset
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
    write_le(
        unenc_query + offset,
        add_offset,
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

    int sent =
        send_query(
            enc_query,
            offset + 24
        );

    if (sent <= 0) {
        diag_log(
            "media page request send failed page=%d offset_id=%d add_offset=%d",
            media_archive_request_page,
            offset_id,
            add_offset
        );

        return false;
    }

    media_archive_search_pending = true;
    media_archive_page_loading = true;

    media_archive_update_nav();

    diag_log(
        "media page request page=%d offset_id=%d add_offset=%d",
        media_archive_request_page,
        offset_id,
        add_offset
    );

    return true;
}

static bool media_archive_request_server_page(
    int offset_id
) {
    return media_archive_request_server_page_ex(
        offset_id,
        0
    );
}

static bool media_archive_navigate_to_page(
    int page_index
) {
    int total_pages =
        media_archive_total_pages();

    if (
        page_index < 0 ||
        total_pages <= 0 ||
        page_index >= total_pages
    ) {
        MessageBeep(
            MB_ICONASTERISK
        );

        media_archive_update_nav();
        return false;
    }

    if (
        media_archive_search_pending ||
        media_archive_page_loading
    ) {
        return false;
    }

    if (
        page_index ==
        media_archive_current_page
    ) {
        media_archive_refresh();
        media_archive_update_nav();
        return true;
    }

    if (
        media_archive_page_is_loaded(
            page_index
        )
    ) {
        media_archive_previous_page =
            media_archive_current_page;

        media_archive_current_page =
            page_index;

        media_archive_request_page =
            page_index;

        media_archive_refresh();
        return true;
    }

    int previous_page =
        media_archive_current_page;

    media_archive_previous_page =
        previous_page;

    media_archive_request_page =
        page_index;

    media_archive_current_page =
        page_index;

    // Show the target page as empty while its 20 thumbnails are fetched.
    media_archive_refresh();

    int add_offset =
        page_index * 20;

    if (!media_archive_request_server_page_ex(
        0,
        add_offset
    )) {
        media_archive_current_page =
            previous_page;

        media_archive_request_page =
            previous_page;

        media_archive_page_loading =
            false;

        media_archive_refresh();
        return false;
    }

    return true;
}'''

s = replace_function(
    s,
    "static bool media_archive_request_server_page(",
    request_func
)


# =============================================================================
# Server response bookkeeping for non-sequential pages.
# =============================================================================

finish_func = r'''void media_archive_finish_server_page(
    int last_id,
    int count,
    int total
) {
    if (total > 0)
        media_archive_total = total;

    int total_pages =
        media_archive_total_pages();

    if (
        total_pages > 0 &&
        (int)media_archive_loaded_pages.size() <
            total_pages
    ) {
        media_archive_loaded_pages.resize(
            total_pages,
            0
        );
    }

    if (
        count > 0 &&
        media_archive_request_page >= 0 &&
        media_archive_request_page <
            (int)media_archive_loaded_pages.size()
    ) {
        media_archive_loaded_pages[
            media_archive_request_page
        ] = 1;
    }

    if (
        count > 0 &&
        media_archive_request_page >
            media_archive_highest_page
    ) {
        media_archive_highest_page =
            media_archive_request_page;
    }

    media_archive_loaded_count += count;

    if (last_id > 0) {
        media_archive_next_offset_id =
            last_id;
    }

    // With direct page jumps this flag only describes the page just received.
    media_archive_no_more =
        count < 20 ||
        (
            total_pages > 0 &&
            media_archive_request_page + 1 >=
                total_pages
        );

    if (count <= 0) {
        media_archive_page_loading = false;

        if (
            media_archive_current_page ==
            media_archive_request_page
        ) {
            media_archive_current_page =
                media_archive_previous_page;

            media_archive_request_page =
                media_archive_previous_page;

            MessageBeep(
                MB_ICONASTERISK
            );

            media_archive_refresh();
        }
    }

    media_archive_update_nav();

    diag_log(
        "media direct page=%d count=%d total=%d total_pages=%d loaded=%d",
        media_archive_request_page,
        count,
        media_archive_total,
        total_pages,
        media_archive_loaded_count
    );
}'''

s = replace_function(
    s,
    "void media_archive_finish_server_page(",
    finish_func
)


error_func = r'''void media_archive_handle_rpc_error(
    int error_code,
    const wchar_t* error_message
) {
    media_archive_search_pending = false;
    media_archive_page_loading = false;

    if (
        media_archive_current_page ==
        media_archive_request_page
    ) {
        media_archive_current_page =
            media_archive_previous_page;

        media_archive_request_page =
            media_archive_previous_page;
    }

    media_archive_refresh();
    media_archive_update_nav();

    diag_log(
        "media direct-page rpc_error code=%d return_page=%d",
        error_code,
        media_archive_current_page
    );
}'''

s = replace_function(
    s,
    "void media_archive_handle_rpc_error(",
    error_func
)


# =============================================================================
# Enter in the page box = OK.
# =============================================================================

page_edit_proc = r'''
static LRESULT CALLBACK TelegacyMediaPageEditProc(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    if (
        msg == WM_KEYDOWN &&
        wParam == VK_RETURN
    ) {
        SendMessageW(
            GetParent(hwnd),
            WM_COMMAND,
            MAKEWPARAM(
                5,
                BN_CLICKED
            ),
            (LPARAM)hMediaArchivePageGo
        );

        return 0;
    }

    if (!media_archive_page_edit_original_proc) {
        return DefWindowProcW(
            hwnd,
            msg,
            wParam,
            lParam
        );
    }

    return CallWindowProcW(
        media_archive_page_edit_original_proc,
        hwnd,
        msg,
        wParam,
        lParam
    );
}

'''

window_pos = s.find(
    "static LRESULT CALLBACK TelegacyMediaArchiveWindow("
)

if window_pos < 0:
    raise SystemExit(
        "Could not locate Media archive window procedure."
    )

s = (
    s[:window_pos]
    + page_edit_proc
    + s[window_pos:]
)


# =============================================================================
# Media window: <- [page] / total [OK] ->.
# =============================================================================

window_func = r'''static LRESULT CALLBACK TelegacyMediaArchiveWindow(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    switch (msg) {
        case WM_CREATE: {
            hMediaArchiveNewer =
                CreateWindowW(
                    L"BUTTON",
                    L"<-",
                    WS_CHILD |
                    WS_VISIBLE |
                    BS_PUSHBUTTON,
                    8,
                    7,
                    44,
                    24,
                    hwnd,
                    (HMENU)1,
                    NULL,
                    NULL
                );

            hMediaArchivePageEdit =
                CreateWindowExW(
                    WS_EX_CLIENTEDGE,
                    L"EDIT",
                    L"1",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_TABSTOP |
                    ES_NUMBER |
                    ES_CENTER |
                    ES_AUTOHSCROLL,
                    57,
                    7,
                    48,
                    24,
                    hwnd,
                    (HMENU)3,
                    NULL,
                    NULL
                );

            hMediaArchivePageTotal =
                CreateWindowW(
                    L"STATIC",
                    L"/ ?",
                    WS_CHILD |
                    WS_VISIBLE |
                    SS_LEFT |
                    SS_CENTERIMAGE,
                    111,
                    7,
                    65,
                    24,
                    hwnd,
                    (HMENU)4,
                    NULL,
                    NULL
                );

            hMediaArchivePageGo =
                CreateWindowW(
                    L"BUTTON",
                    L"\u041E\u041A",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_TABSTOP |
                    BS_PUSHBUTTON,
                    181,
                    7,
                    42,
                    24,
                    hwnd,
                    (HMENU)5,
                    NULL,
                    NULL
                );

            hMediaArchiveOlder =
                CreateWindowW(
                    L"BUTTON",
                    L"->",
                    WS_CHILD |
                    WS_VISIBLE |
                    BS_PUSHBUTTON,
                    228,
                    7,
                    44,
                    24,
                    hwnd,
                    (HMENU)2,
                    NULL,
                    NULL
                );

            hMediaArchiveList =
                CreateWindowExW(
                    WS_EX_CLIENTEDGE,
                    WC_LISTVIEWW,
                    L"",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_VSCROLL |
                    LVS_ICON |
                    LVS_SINGLESEL |
                    LVS_NOLABELWRAP,
                    8,
                    38,
                    580,
                    410,
                    hwnd,
                    (HMENU)6,
                    NULL,
                    NULL
                );

            HFONT font =
                (HFONT)GetStockObject(
                    DEFAULT_GUI_FONT
                );

            SendMessage(
                hMediaArchiveNewer,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
            );

            SendMessage(
                hMediaArchiveOlder,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
            );

            SendMessage(
                hMediaArchivePageEdit,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
            );

            SendMessage(
                hMediaArchivePageTotal,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
            );

            SendMessage(
                hMediaArchivePageGo,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
            );

            SendMessageW(
                hMediaArchivePageEdit,
                EM_SETLIMITTEXT,
                7,
                0
            );

            media_archive_page_edit_original_proc =
                (WNDPROC)SetWindowLongPtrW(
                    hMediaArchivePageEdit,
                    GWLP_WNDPROC,
                    (LONG_PTR)TelegacyMediaPageEditProc
                );

            ListView_SetExtendedListViewStyle(
                hMediaArchiveList,
                LVS_EX_BORDERSELECT
            );

            media_archive_refresh();
            media_archive_update_nav();

            return 0;
        }

        case WM_SIZE: {
            RECT rc;
            GetClientRect(
                hwnd,
                &rc
            );

            MoveWindow(
                hMediaArchiveNewer,
                8,
                7,
                44,
                24,
                TRUE
            );

            MoveWindow(
                hMediaArchivePageEdit,
                57,
                7,
                48,
                24,
                TRUE
            );

            MoveWindow(
                hMediaArchivePageTotal,
                111,
                7,
                65,
                24,
                TRUE
            );

            MoveWindow(
                hMediaArchivePageGo,
                181,
                7,
                42,
                24,
                TRUE
            );

            MoveWindow(
                hMediaArchiveOlder,
                228,
                7,
                44,
                24,
                TRUE
            );

            MoveWindow(
                hMediaArchiveList,
                8,
                38,
                rc.right - 16,
                rc.bottom - 46,
                TRUE
            );

            return 0;
        }

        case WM_COMMAND: {
            int command =
                LOWORD(wParam);

            if (command == 1) {
                media_archive_navigate_to_page(
                    media_archive_current_page - 1
                );

                return 0;
            }

            if (command == 2) {
                media_archive_navigate_to_page(
                    media_archive_current_page + 1
                );

                return 0;
            }

            if (command == 5) {
                wchar_t page_text[32] = {0};

                GetWindowTextW(
                    hMediaArchivePageEdit,
                    page_text,
                    ARRAYSIZE(page_text)
                );

                int requested =
                    _wtoi(page_text);

                int total_pages =
                    media_archive_total_pages();

                if (
                    requested < 1 ||
                    total_pages <= 0 ||
                    requested > total_pages
                ) {
                    MessageBeep(
                        MB_ICONASTERISK
                    );

                    media_archive_update_nav();
                    return 0;
                }

                media_archive_navigate_to_page(
                    requested - 1
                );

                return 0;
            }

            break;
        }

        case WM_NOTIFY: {
            LPNMHDR hdr =
                (LPNMHDR)lParam;

            if (
                hdr &&
                hdr->hwndFrom ==
                    hMediaArchiveList &&
                hdr->code ==
                    NM_DBLCLK
            ) {
                int index =
                    ListView_GetNextItem(
                        hMediaArchiveList,
                        -1,
                        LVNI_SELECTED
                    );

                if (index >= 0) {
                    LVITEMW item = {0};

                    item.mask = LVIF_PARAM;
                    item.iItem = index;

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

        case WM_DESTROY: {
            if (hMediaArchiveImages) {
                ImageList_Destroy(
                    hMediaArchiveImages
                );

                hMediaArchiveImages = NULL;
            }

            hMediaArchiveList = NULL;
            hMediaArchiveNewer = NULL;
            hMediaArchiveOlder = NULL;
            hMediaArchivePageEdit = NULL;
            hMediaArchivePageTotal = NULL;
            hMediaArchivePageGo = NULL;
            hMediaArchiveWindow = NULL;
            media_archive_page_edit_original_proc = NULL;

            return 0;
        }
    }

    return DefWindowProcW(
        hwnd,
        msg,
        wParam,
        lParam
    );
}'''

s = replace_function(
    s,
    "static LRESULT CALLBACK TelegacyMediaArchiveWindow(",
    window_func
)


# =============================================================================
# Clear/reset page cache.
# =============================================================================

clear_start, clear_end = function_range(
    s,
    "void media_archive_clear()"
)
clear_func = s[clear_start:clear_end]

old_clear = r'''    media_archive_current_page = 0;
    media_archive_request_page = 0;
    media_archive_highest_page = 0;

    media_archive_page_offsets.clear();
    media_archive_page_offsets.push_back(0);'''

new_clear = r'''    media_archive_current_page = 0;
    media_archive_request_page = 0;
    media_archive_previous_page = 0;
    media_archive_highest_page = 0;

    media_archive_page_offsets.clear();
    media_archive_page_offsets.push_back(0);

    media_archive_loaded_pages.clear();'''

if old_clear not in clear_func:
    raise SystemExit(
        "Could not locate gallery reset block."
    )

clear_func = clear_func.replace(
    old_clear,
    new_clear,
    1
)

s = (
    s[:clear_start]
    + clear_func
    + s[clear_end:]
)


# =============================================================================
# First page starts as page 0 and is recorded as the rollback target.
# =============================================================================

show_start, show_end = function_range(
    s,
    "void media_archive_show()"
)
show_func = s[show_start:show_end]

old_show_reset = r'''        media_archive_current_page = 0;
        media_archive_request_page = 0;
        media_archive_highest_page = 0;

        media_archive_page_offsets.clear();
        media_archive_page_offsets.push_back(0);'''

new_show_reset = r'''        media_archive_current_page = 0;
        media_archive_request_page = 0;
        media_archive_previous_page = 0;
        media_archive_highest_page = 0;

        media_archive_page_offsets.clear();
        media_archive_page_offsets.push_back(0);

        media_archive_loaded_pages.clear();'''

if old_show_reset not in show_func:
    raise SystemExit(
        "Could not locate gallery initial-page reset."
    )

show_func = show_func.replace(
    old_show_reset,
    new_show_reset,
    1
)

s = (
    s[:show_start]
    + show_func
    + s[show_end:]
)


# =============================================================================
# Sanity checks.
# =============================================================================

required_after = [
    "media_archive_page_jump_v1",
    "hMediaArchivePageEdit",
    "hMediaArchivePageTotal",
    "hMediaArchivePageGo",
    "media_archive_request_server_page_ex(",
    "media_archive_navigate_to_page(",
    "page_index * 20",
    "TelegacyMediaPageEditProc",
    'L"\\u041E\\u041A"',
]

for token in required_after:
    if token not in s:
        raise SystemExit(
            "Internal verification failed: " + token
        )

if "hMediaArchivePageLabel" in s:
    raise SystemExit(
        "Internal verification failed: old page label is still referenced."
    )

write(t, s)

print(
    "Applied direct Media page jump: editable page number, "
    "Enter/OK navigation, and arbitrary Telegram add_offset pagination."
)
