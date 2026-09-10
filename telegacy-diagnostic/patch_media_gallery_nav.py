#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_media_gallery_nav.py <Telegacy source directory>"
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
    in_string = False
    escaped = False
    i = open_paren

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


s = read(t)

if "media_archive_gallery_navigation_v1" in s:
    print("Media gallery/search UI patch already applied.")
    raise SystemExit(0)

if "media_archive_server_active" not in s:
    raise SystemExit(
        "Server-backed Media archive was not found. "
        "Run patch_ui_media_server.py before this patch."
    )

if "TelegacyMediaArchiveWindow" not in s:
    raise SystemExit(
        "Media archive window was not found. "
        "Run patch_search_media.py before this patch."
    )


# =============================================================================
# Search fields: classic placeholder + GDI magnifier.
# =============================================================================

search_helper_anchor = "bool chat_search_updating = false;"

search_helper = r'''

// media_archive_gallery_navigation_v1
// Reliable classic search-field decoration.
static WNDPROC telegacy_search_edit_original_proc = NULL;

static const wchar_t* telegacy_search_hint_text(HWND hwnd) {
    if (hwnd == hChatSearch) {
        return L"\u041F\u043E\u0438\u0441\u043A \u0447\u0430\u0442\u043E\u0432...";
    }

    if (hwnd == hMessageSearch) {
        return L"\u041F\u043E\u0438\u0441\u043A \u0441\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u0439...";
    }

    return L"";
}

static void telegacy_search_draw_magnifier(
    HWND hwnd,
    HDC hdc
) {
    RECT rc;
    GetClientRect(hwnd, &rc);

    int cy = (rc.bottom - rc.top) / 2;
    COLORREF grey = GetSysColor(COLOR_GRAYTEXT);

    HPEN pen = CreatePen(
        PS_SOLID,
        1,
        grey
    );

    if (!pen)
        return;

    HGDIOBJ old_pen =
        SelectObject(hdc, pen);

    HGDIOBJ old_brush =
        SelectObject(
            hdc,
            GetStockObject(HOLLOW_BRUSH)
        );

    Ellipse(
        hdc,
        5,
        cy - 5,
        14,
        cy + 4
    );

    MoveToEx(
        hdc,
        12,
        cy + 2,
        NULL
    );

    LineTo(
        hdc,
        17,
        cy + 7
    );

    SelectObject(
        hdc,
        old_brush
    );

    SelectObject(
        hdc,
        old_pen
    );

    DeleteObject(pen);
}

static void telegacy_search_draw_hint(
    HWND hwnd
) {
    HDC hdc = GetDC(hwnd);

    if (!hdc)
        return;

    telegacy_search_draw_magnifier(
        hwnd,
        hdc
    );

    if (
        GetWindowTextLengthW(hwnd) == 0
    ) {
        RECT rc;
        GetClientRect(hwnd, &rc);

        rc.left = 22;
        rc.right -= 3;

        HFONT font =
            (HFONT)SendMessageW(
                hwnd,
                WM_GETFONT,
                0,
                0
            );

        HGDIOBJ old_font = NULL;

        if (font) {
            old_font =
                SelectObject(
                    hdc,
                    font
                );
        }

        int old_bk =
            SetBkMode(
                hdc,
                TRANSPARENT
            );

        COLORREF old_color =
            SetTextColor(
                hdc,
                GetSysColor(COLOR_GRAYTEXT)
            );

        DrawTextW(
            hdc,
            telegacy_search_hint_text(hwnd),
            -1,
            &rc,
            DT_LEFT |
            DT_VCENTER |
            DT_SINGLELINE |
            DT_NOPREFIX |
            DT_END_ELLIPSIS
        );

        SetTextColor(
            hdc,
            old_color
        );

        SetBkMode(
            hdc,
            old_bk
        );

        if (old_font) {
            SelectObject(
                hdc,
                old_font
            );
        }
    }

    ReleaseDC(
        hwnd,
        hdc
    );
}

static LRESULT CALLBACK TelegacySearchEditProc(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    if (!telegacy_search_edit_original_proc) {
        return DefWindowProcW(
            hwnd,
            msg,
            wParam,
            lParam
        );
    }

    LRESULT result =
        CallWindowProcW(
            telegacy_search_edit_original_proc,
            hwnd,
            msg,
            wParam,
            lParam
        );

    if (msg == WM_PAINT) {
        telegacy_search_draw_hint(hwnd);
    }

    if (
        msg == WM_SETTEXT ||
        msg == WM_CHAR ||
        msg == WM_KEYUP ||
        msg == WM_CUT ||
        msg == WM_PASTE ||
        msg == WM_CLEAR ||
        msg == WM_SETFOCUS ||
        msg == WM_KILLFOCUS
    ) {
        InvalidateRect(
            hwnd,
            NULL,
            TRUE
        );
    }

    return result;
}

static void telegacy_install_search_decoration(
    HWND hwnd
) {
    if (!hwnd)
        return;

    WNDPROC original =
        (WNDPROC)GetWindowLongPtrW(
            hwnd,
            GWLP_WNDPROC
        );

    if (!telegacy_search_edit_original_proc) {
        telegacy_search_edit_original_proc =
            original;
    }

    SetWindowLongPtrW(
        hwnd,
        GWLP_WNDPROC,
        (LONG_PTR)TelegacySearchEditProc
    );

    SendMessageW(
        hwnd,
        EM_SETMARGINS,
        EC_LEFTMARGIN,
        MAKELPARAM(21, 0)
    );

    InvalidateRect(
        hwnd,
        NULL,
        TRUE
    );
}
'''

if search_helper_anchor not in s:
    raise SystemExit(
        "Could not locate chat_search_updating anchor."
    )

s = s.replace(
    search_helper_anchor,
    search_helper_anchor + search_helper,
    1
)

s = insert_after_create_call(
    s,
    "hChatSearch",
    "\t\ttelegacy_install_search_decoration(hChatSearch);",
    "telegacy_install_search_decoration(hChatSearch)"
)

s = insert_after_create_call(
    s,
    "hMessageSearch",
    "\t\ttelegacy_install_search_decoration(hMessageSearch);",
    "telegacy_install_search_decoration(hMessageSearch)"
)


# =============================================================================
# Media gallery: cached page navigation instead of ever-growing list.
# =============================================================================

old_struct = r'''struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    HBITMAP bitmap;
};'''

new_struct = r'''struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    int page_index;
    HBITMAP bitmap;
    wchar_t file_path[MAX_PATH];
};'''

if old_struct not in s:
    raise SystemExit(
        "Could not locate MediaArchiveItem."
    )

s = s.replace(
    old_struct,
    new_struct,
    1
)

old_globals = r'''static std::vector<MediaArchiveItem> media_archive_items;
static HWND hMediaArchiveWindow = NULL;
static HWND hMediaArchiveList = NULL;
static HWND hMediaArchiveOlder = NULL;
static HIMAGELIST hMediaArchiveImages = NULL;'''

new_globals = r'''static std::vector<MediaArchiveItem> media_archive_items;
static HWND hMediaArchiveWindow = NULL;
static HWND hMediaArchiveList = NULL;
static HWND hMediaArchiveNewer = NULL;
static HWND hMediaArchiveOlder = NULL;
static HWND hMediaArchivePageLabel = NULL;
static HIMAGELIST hMediaArchiveImages = NULL;

static int media_archive_current_page = 0;
static int media_archive_request_page = 0;
static int media_archive_highest_page = 0;
static bool media_archive_page_loading = false;
static std::vector<int> media_archive_page_offsets;'''


if old_globals not in s:
    raise SystemExit(
        "Could not locate Media archive globals."
    )

s = s.replace(
    old_globals,
    new_globals,
    1
)

server_state_anchor = "static bool media_archive_no_more = false;"

server_helpers = r'''

static void media_archive_refresh();

static void media_archive_update_nav() {
    if (hMediaArchiveNewer) {
        EnableWindow(
            hMediaArchiveNewer,
            media_archive_current_page > 0
        );
    }

    if (hMediaArchiveOlder) {
        bool can_move_to_cached =
            media_archive_current_page <
                media_archive_highest_page;

        bool can_request_older =
            media_archive_current_page ==
                media_archive_highest_page &&
            !media_archive_no_more &&
            !media_archive_search_pending &&
            !media_archive_page_loading;

        EnableWindow(
            hMediaArchiveOlder,
            can_move_to_cached ||
            can_request_older
        );
    }

    if (hMediaArchivePageLabel) {
        wchar_t page_text[64];

        int total_pages = 0;

        if (media_archive_total > 0) {
            total_pages =
                (
                    media_archive_total +
                    19
                ) / 20;
        }

        if (total_pages > 0) {
            _snwprintf(
                page_text,
                ARRAYSIZE(page_text) - 1,
                L"%d / %d",
                media_archive_current_page + 1,
                total_pages
            );
        } else {
            _snwprintf(
                page_text,
                ARRAYSIZE(page_text) - 1,
                L"%d",
                media_archive_current_page + 1
            );
        }

        page_text[
            ARRAYSIZE(page_text) - 1
        ] = 0;

        SetWindowTextW(
            hMediaArchivePageLabel,
            page_text
        );
    }
}

static bool media_archive_server_queue_empty() {
    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        if (
            !documents[i].visible &&
            documents[i].photo_size > 1 &&
            !read_le(
                documents[i].photo_msg_id,
                8
            )
        ) {
            return false;
        }
    }

    return true;
}

static bool media_archive_save_bitmap(
    HBITMAP bitmap,
    __int64 document_id,
    wchar_t* out_path,
    int out_count
) {
    if (
        !bitmap ||
        !out_path ||
        out_count < 16
    ) {
        return false;
    }

    out_path[0] = 0;

    wchar_t temp_dir[MAX_PATH] = {0};

    DWORD temp_len =
        GetTempPathW(
            MAX_PATH,
            temp_dir
        );

    if (
        !temp_len ||
        temp_len >= MAX_PATH
    ) {
        return false;
    }

    if (
        wcslen(temp_dir) + 16 >=
            MAX_PATH
    ) {
        return false;
    }

    wcscat(
        temp_dir,
        L"TelegacyMedia"
    );

    CreateDirectoryW(
        temp_dir,
        NULL
    );

    _snwprintf(
        out_path,
        out_count - 1,
        L"%s\\%016I64X.bmp",
        temp_dir,
        document_id
    );

    out_path[out_count - 1] = 0;

    BITMAP bm = {0};

    if (!GetObject(
        bitmap,
        sizeof(bm),
        &bm
    )) {
        out_path[0] = 0;
        return false;
    }

    if (
        bm.bmWidth <= 0 ||
        bm.bmHeight == 0
    ) {
        out_path[0] = 0;
        return false;
    }

    int height =
        bm.bmHeight < 0
            ? -bm.bmHeight
            : bm.bmHeight;

    DWORD stride =
        (
            (
                bm.bmWidth * 24 +
                31
            ) / 32
        ) * 4;

    DWORD image_size =
        stride *
        height;

    BYTE* bits =
        (BYTE*)malloc(
            image_size
        );

    if (!bits) {
        out_path[0] = 0;
        return false;
    }

    BITMAPINFO bmi = {0};

    bmi.bmiHeader.biSize =
        sizeof(BITMAPINFOHEADER);

    bmi.bmiHeader.biWidth =
        bm.bmWidth;

    bmi.bmiHeader.biHeight =
        height;

    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 24;
    bmi.bmiHeader.biCompression = BI_RGB;
    bmi.bmiHeader.biSizeImage =
        image_size;

    HDC hdc = GetDC(NULL);

    int scanlines = 0;

    if (hdc) {
        scanlines =
            GetDIBits(
                hdc,
                bitmap,
                0,
                height,
                bits,
                &bmi,
                DIB_RGB_COLORS
            );

        ReleaseDC(
            NULL,
            hdc
        );
    }

    if (!scanlines) {
        free(bits);
        out_path[0] = 0;
        return false;
    }

    FILE* f =
        _wfopen(
            out_path,
            L"wb"
        );

    if (!f) {
        free(bits);
        out_path[0] = 0;
        return false;
    }

    BITMAPFILEHEADER bfh = {0};

    bfh.bfType = 0x4D42;
    bfh.bfOffBits =
        sizeof(BITMAPFILEHEADER) +
        sizeof(BITMAPINFOHEADER);

    bfh.bfSize =
        bfh.bfOffBits +
        image_size;

    fwrite(
        &bfh,
        sizeof(bfh),
        1,
        f
    );

    fwrite(
        &bmi.bmiHeader,
        sizeof(BITMAPINFOHEADER),
        1,
        f
    );

    fwrite(
        bits,
        1,
        image_size,
        f
    );

    fclose(f);
    free(bits);

    return true;
}

static void media_archive_open_item(
    int item_index
) {
    if (
        item_index < 0 ||
        item_index >=
            (int)media_archive_items.size()
    ) {
        return;
    }

    const wchar_t* path =
        media_archive_items[
            item_index
        ].file_path;

    if (!path || !path[0]) {
        MessageBeep(
            MB_ICONASTERISK
        );
        return;
    }

    typedef HINSTANCE (
        WINAPI *ShellExecuteWProc
    )(
        HWND,
        LPCWSTR,
        LPCWSTR,
        LPCWSTR,
        LPCWSTR,
        INT
    );

    HMODULE shell =
        LoadLibraryW(
            L"shell32.dll"
        );

    if (!shell) {
        MessageBeep(
            MB_ICONASTERISK
        );
        return;
    }

    ShellExecuteWProc proc =
        (ShellExecuteWProc)GetProcAddress(
            shell,
            "ShellExecuteW"
        );

    if (proc) {
        HINSTANCE result =
            proc(
                hMediaArchiveWindow,
                L"open",
                path,
                NULL,
                NULL,
                SW_SHOWNORMAL
            );

        if (
            (INT_PTR)result <= 32
        ) {
            MessageBeep(
                MB_ICONASTERISK
            );
        }
    }

    FreeLibrary(shell);
}
'''

if server_state_anchor not in s:
    raise SystemExit(
        "Could not locate Media server-state anchor."
    )

s = s.replace(
    server_state_anchor,
    server_state_anchor + server_helpers,
    1
)


# request: mark server page as loading.
rs, re = function_range(
    s,
    "static bool media_archive_request_server_page("
)
request_func = s[rs:re]

old_pending = r'''    media_archive_search_pending = true;

    if (hMediaArchiveOlder)
        EnableWindow(
            hMediaArchiveOlder,
            FALSE
        );'''

new_pending = r'''    media_archive_search_pending = true;
    media_archive_page_loading = true;

    media_archive_update_nav();'''

if old_pending not in request_func:
    raise SystemExit(
        "Could not locate Media request pending block."
    )

request_func = request_func.replace(
    old_pending,
    new_pending,
    1
)

s = s[:rs] + request_func + s[re:]


finish_func = r'''void media_archive_finish_server_page(
    int last_id,
    int count,
    int total
) {
    if (total > 0)
        media_archive_total = total;

    media_archive_loaded_count += count;

    if (
        count > 0 &&
        media_archive_request_page >
        media_archive_highest_page
    ) {
        media_archive_highest_page =
            media_archive_request_page;
    }

    if (
        count <= 0 &&
        media_archive_current_page >
        media_archive_highest_page
    ) {
        media_archive_current_page =
            media_archive_highest_page;
    }

    while (
        (int)media_archive_page_offsets.size() <=
        media_archive_request_page + 1
    ) {
        media_archive_page_offsets.push_back(0);
    }

    if (last_id > 0) {
        media_archive_next_offset_id = last_id;

        media_archive_page_offsets[
            media_archive_request_page + 1
        ] = last_id;
    }

    media_archive_no_more =
        count < 20 ||
        last_id <= 0 ||
        (
            media_archive_total > 0 &&
            media_archive_loaded_count >=
                media_archive_total
        );

    if (count <= 0) {
        media_archive_page_loading = false;
    }

    media_archive_update_nav();

    diag_log(
        "media gallery page=%d count=%d total=%d loaded=%d next=%d end=%d",
        media_archive_request_page,
        count,
        media_archive_total,
        media_archive_loaded_count,
        media_archive_next_offset_id,
        media_archive_no_more ? 1 : 0
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
        media_archive_request_page >
        media_archive_highest_page
    ) {
        media_archive_current_page =
            media_archive_highest_page;
    }

    media_archive_update_nav();

    diag_log(
        "media gallery rpc_error page=%d code=%d",
        media_archive_request_page,
        error_code
    );
}'''

s = replace_function(
    s,
    "void media_archive_handle_rpc_error(",
    error_func
)


start_download_func = r'''void media_archive_start_next_download() {
    if (!media_archive_server_active)
        return;

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
                "media gallery thumbnail start page=%d index=%d msg=%d",
                media_archive_request_page,
                i,
                documents[i].min < 0
                    ? -documents[i].min
                    : 0
            );

            return;
        }
    }

    media_archive_page_loading = false;
    media_archive_update_nav();
}'''

s = replace_function(
    s,
    "void media_archive_start_next_download()",
    start_download_func
)


refresh_func = r'''static void media_archive_refresh() {
    if (!hMediaArchiveList)
        return;

    ListView_DeleteAllItems(
        hMediaArchiveList
    );

    if (hMediaArchiveImages) {
        ListView_SetImageList(
            hMediaArchiveList,
            NULL,
            LVSIL_NORMAL
        );

        ImageList_Destroy(
            hMediaArchiveImages
        );

        hMediaArchiveImages = NULL;
    }

    const int thumb_size = 96;
    int current_count = 0;

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].page_index ==
            media_archive_current_page
        ) {
            current_count++;
        }
    }

    hMediaArchiveImages =
        ImageList_Create(
            thumb_size,
            thumb_size,
            ILC_COLOR32,
            current_count > 0
                ? current_count
                : 1,
            16
        );

    if (!hMediaArchiveImages) {
        media_archive_update_nav();
        return;
    }

    ListView_SetImageList(
        hMediaArchiveList,
        hMediaArchiveImages,
        LVSIL_NORMAL
    );

    SendMessage(
        hMediaArchiveList,
        LVM_SETICONSPACING,
        0,
        MAKELPARAM(112, 118)
    );

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].page_index !=
            media_archive_current_page
        ) {
            continue;
        }

        HBITMAP thumb =
            media_archive_make_thumbnail(
                media_archive_items[i].bitmap,
                thumb_size
            );

        int image_index = -1;

        if (thumb) {
            image_index =
                ImageList_Add(
                    hMediaArchiveImages,
                    thumb,
                    NULL
                );

            DeleteObject(thumb);
        }

        if (image_index < 0)
            continue;

        wchar_t label[32] = {0};

        if (
            media_archive_items[i].message_id
        ) {
            _snwprintf(
                label,
                ARRAYSIZE(label) - 1,
                L"#%d",
                media_archive_items[i].message_id
            );

            label[
                ARRAYSIZE(label) - 1
            ] = 0;
        }

        LVITEMW item = {0};

        item.mask =
            LVIF_IMAGE |
            LVIF_PARAM |
            LVIF_TEXT;

        item.iItem =
            ListView_GetItemCount(
                hMediaArchiveList
            );

        item.iImage = image_index;
        item.lParam = i;
        item.pszText = label;

        SendMessageW(
            hMediaArchiveList,
            LVM_INSERTITEMW,
            0,
            (LPARAM)&item
        );
    }

    media_archive_update_nav();
}'''

s = replace_function(
    s,
    "static void media_archive_refresh() {",
    refresh_func
)


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

            hMediaArchiveOlder =
                CreateWindowW(
                    L"BUTTON",
                    L"->",
                    WS_CHILD |
                    WS_VISIBLE |
                    BS_PUSHBUTTON,
                    57,
                    7,
                    44,
                    24,
                    hwnd,
                    (HMENU)2,
                    NULL,
                    NULL
                );

            hMediaArchivePageLabel =
                CreateWindowW(
                    L"STATIC",
                    L"1",
                    WS_CHILD |
                    WS_VISIBLE |
                    SS_CENTER |
                    SS_CENTERIMAGE,
                    108,
                    7,
                    90,
                    24,
                    hwnd,
                    (HMENU)3,
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
                    (HMENU)4,
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
                hMediaArchivePageLabel,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
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
                hMediaArchiveOlder,
                57,
                7,
                44,
                24,
                TRUE
            );

            MoveWindow(
                hMediaArchivePageLabel,
                108,
                7,
                90,
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
                if (
                    media_archive_current_page >
                    0
                ) {
                    media_archive_current_page--;
                    media_archive_refresh();
                }

                return 0;
            }

            if (command == 2) {
                if (
                    media_archive_current_page <
                    media_archive_highest_page
                ) {
                    media_archive_current_page++;
                    media_archive_refresh();
                    return 0;
                }

                if (
                    current_peer &&
                    media_archive_server_active &&
                    !media_archive_search_pending &&
                    !media_archive_page_loading &&
                    !media_archive_no_more
                ) {
                    int next_page =
                        media_archive_current_page +
                        1;

                    int next_offset =
                        media_archive_next_offset_id;

                    if (
                        next_page <
                        (int)media_archive_page_offsets.size() &&
                        media_archive_page_offsets[
                            next_page
                        ] > 0
                    ) {
                        next_offset =
                            media_archive_page_offsets[
                                next_page
                            ];
                    }

                    media_archive_request_page =
                        next_page;

                    media_archive_current_page =
                        next_page;

                    media_archive_refresh();

                    if (!media_archive_request_server_page(
                        next_offset
                    )) {
                        media_archive_current_page--;
                        media_archive_request_page =
                            media_archive_current_page;

                        media_archive_page_loading =
                            false;

                        media_archive_refresh();
                    }
                }

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
            hMediaArchivePageLabel = NULL;
            hMediaArchiveWindow = NULL;

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


clear_func = r'''void media_archive_clear() {
    media_archive_server_active = false;
    media_archive_search_pending = false;
    media_archive_page_loading = false;

    media_archive_next_offset_id = 0;
    media_archive_loaded_count = 0;
    media_archive_total = 0;
    media_archive_no_more = false;

    media_archive_current_page = 0;
    media_archive_request_page = 0;
    media_archive_highest_page = 0;

    media_archive_page_offsets.clear();
    media_archive_page_offsets.push_back(0);

    for (
        int i = (int)documents.size() - 1;
        i >= 0;
        i--
    ) {
        if (documents[i].visible)
            continue;

        free(
            documents[i].filename
        );

        free(
            documents[i].file_reference
        );

        documents.erase(
            documents.begin() + i
        );
    }

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].bitmap
        ) {
            DeleteObject(
                media_archive_items[i].bitmap
            );
        }

        if (
            media_archive_items[i].file_path[0]
        ) {
            DeleteFileW(
                media_archive_items[i].file_path
            );
        }
    }

    media_archive_items.clear();

    if (hMediaArchiveWindow) {
        media_archive_refresh();
    }
}'''

s = replace_function(
    s,
    "void media_archive_clear()",
    clear_func
)


add_func = r'''void media_archive_add_document(
    Document* document,
    HBITMAP bitmap
) {
    if (
        !document ||
        !bitmap ||
        document->photo_size == 1
    ) {
        return;
    }

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

    __int64 document_id = 0;

    memcpy(
        &document_id,
        document->id,
        sizeof(document_id)
    );

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].document_id ==
            document_id
        ) {
            return;
        }
    }

    int message_id = 0;

    if (
        !document->visible &&
        document->min < 0
    ) {
        message_id =
            -document->min;
    }

    if (document->visible) {
        for (
            int i = 0;
            i < (int)messages.size();
            i++
        ) {
            if (
                document->min >=
                    messages[i].start_char &&
                document->max <=
                    messages[i].end_footer
            ) {
                message_id =
                    messages[i].id;
                break;
            }
        }
    }

    HBITMAP copy =
        (HBITMAP)CopyImage(
            bitmap,
            IMAGE_BITMAP,
            0,
            0,
            LR_CREATEDIBSECTION
        );

    if (!copy)
        return;

    MediaArchiveItem item;

    item.document_id =
        document_id;

    item.message_id =
        message_id;

    item.page_index =
        media_archive_server_active
            ? media_archive_request_page
            : 0;

    item.bitmap = copy;
    item.file_path[0] = 0;

    media_archive_save_bitmap(
        copy,
        document_id,
        item.file_path,
        ARRAYSIZE(item.file_path)
    );

    media_archive_items.push_back(
        item
    );

    if (
        media_archive_server_active &&
        media_archive_server_queue_empty()
    ) {
        media_archive_page_loading = false;
    }

    if (
        hMediaArchiveWindow &&
        item.page_index ==
            media_archive_current_page
    ) {
        media_archive_refresh();
    } else {
        media_archive_update_nav();
    }
}'''

s = replace_function(
    s,
    "void media_archive_add_document(",
    add_func
)


show_func = r'''void media_archive_show() {
    if (!current_peer)
        return;

    if (
        hMediaArchiveWindow &&
        IsWindow(
            hMediaArchiveWindow
        )
    ) {
        media_archive_refresh();

        ShowWindow(
            hMediaArchiveWindow,
            SW_SHOW
        );

        SetForegroundWindow(
            hMediaArchiveWindow
        );

        return;
    }

    HINSTANCE instance =
        GetModuleHandleW(NULL);

    WNDCLASSEXW wc = {0};

    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc =
        TelegacyMediaArchiveWindow;

    wc.hInstance = instance;
    wc.hCursor =
        LoadCursor(
            NULL,
            IDC_ARROW
        );

    wc.hbrBackground =
        (HBRUSH)(
            COLOR_BTNFACE + 1
        );

    wc.lpszClassName =
        L"TelegacyMediaArchive";

    if (
        !GetClassInfoExW(
            instance,
            wc.lpszClassName,
            &wc
        )
    ) {
        if (!RegisterClassExW(&wc)) {
            diag_log(
                "media archive window class registration failed error=%lu",
                GetLastError()
            );

            return;
        }
    }

    wchar_t title[320];

    _snwprintf(
        title,
        ARRAYSIZE(title) - 1,
        L"Media - %s",
        current_peer->name
            ? current_peer->name
            : L"chat"
    );

    title[
        ARRAYSIZE(title) - 1
    ] = 0;

    hMediaArchiveWindow =
        CreateWindowExW(
            WS_EX_TOOLWINDOW,
            wc.lpszClassName,
            title,
            WS_OVERLAPPEDWINDOW |
            WS_VISIBLE,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            620,
            500,
            hMain,
            NULL,
            instance,
            NULL
        );

    if (!hMediaArchiveWindow) {
        diag_log(
            "media archive window creation failed error=%lu",
            GetLastError()
        );

        return;
    }

    if (!media_archive_server_active) {
        media_archive_clear();

        media_archive_server_active = true;
        media_archive_search_pending = false;
        media_archive_page_loading = false;

        media_archive_next_offset_id = 0;
        media_archive_loaded_count = 0;
        media_archive_total = 0;
        media_archive_no_more = false;

        media_archive_current_page = 0;
        media_archive_request_page = 0;
        media_archive_highest_page = 0;

        media_archive_page_offsets.clear();
        media_archive_page_offsets.push_back(0);

        media_archive_refresh();

        media_archive_request_server_page(
            0
        );
    }
}'''

s = replace_function(
    s,
    "void media_archive_show()",
    show_func
)


# Remove old native cue-banner calls because our subclass is now authoritative.
for comment in (
    "// search cue: native grey placeholder + magnifying glass",
    "// message search cue: native grey placeholder + magnifying glass",
):
    pos = s.find(comment)

    if pos >= 0:
        line_start = s.rfind("\n", 0, pos) + 1
        call_end = s.find("\n\t\t);", pos)

        if call_end >= 0:
            call_end += len("\n\t\t);")
            s = s[:line_start] + s[call_end:]


required = [
    "media_archive_gallery_navigation_v1",
    "telegacy_install_search_decoration(hChatSearch);",
    "telegacy_install_search_decoration(hMessageSearch);",
    'L"<-"',
    'L"->"',
    "media_archive_open_item(",
    "media_archive_current_page",
    "item.page_index",
    "media_archive_save_bitmap(",
]

for token in required:
    if token not in s:
        raise SystemExit(
            "Internal patch verification failed: " + token
        )

write(t, s)

print(
    "Applied gallery page navigation, double-click image opening, "
    "and reliable classic search placeholders."
)
