#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_search_media.py <Telegacy source directory>")

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


# =============================================================================
# include/telegacy.h
# =============================================================================

s = read(h)

if "void media_archive_add_document(" not in s:
    anchor = "extern volatile LONG history_request_pending;"
    block = r'''

// Search/media archive extension.
struct Document;
void media_archive_add_document(Document* document, HBITMAP bitmap);
void media_archive_clear();
void media_archive_show();
'''
    if anchor not in s:
        raise SystemExit("Could not locate history_request_pending declaration in telegacy.h")
    s = s.replace(anchor, anchor + block, 1)

write(h, s)


# =============================================================================
# src/telegacy.cpp
# =============================================================================

s = read(t)

if "TelegacyMediaArchiveWindow" not in s:
    anchor = "int lang_codepage = 0;\n"

    helpers = r'''

// ======================================================================================
// In-chat message search + media archive
// ======================================================================================

HWND hMessageSearch = NULL;
HWND hMessageSearchPrev = NULL;
HWND hMessageSearchNext = NULL;
HWND hMediaArchiveButton = NULL;

static LONG message_search_position = 0;

struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    HBITMAP bitmap;
};

static std::vector<MediaArchiveItem> media_archive_items;
static HWND hMediaArchiveWindow = NULL;
static HWND hMediaArchiveList = NULL;
static HWND hMediaArchiveOlder = NULL;
static HIMAGELIST hMediaArchiveImages = NULL;

static bool message_search_range_is_body(LONG start, LONG end) {
    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            start >= messages[i].end_header &&
            end <= messages[i].end_char
        ) {
            return true;
        }
    }

    return false;
}

static bool message_search_find(bool backwards) {
    if (!chat || !hMessageSearch)
        return false;

    wchar_t query[256] = {0};
    GetWindowTextW(hMessageSearch, query, ARRAYSIZE(query));

    if (!query[0])
        return false;

    LONG text_length = GetWindowTextLengthW(chat);
    if (text_length <= 0)
        return false;

    LONG first_position = message_search_position;

    if (first_position < 0 || first_position > text_length) {
        first_position = backwards ? text_length : 0;
    }

    for (int pass = 0; pass < 2; pass++) {
        LONG cursor;

        if (pass == 0) {
            cursor = first_position;
        } else {
            // Wrap exactly once.
            cursor = backwards ? text_length : 0;
        }

        while (true) {
            FINDTEXTEXW ft = {0};

            if (backwards) {
                if (cursor <= 0)
                    break;

                ft.chrg.cpMin = cursor;
                ft.chrg.cpMax = 0;
            } else {
                if (cursor >= text_length)
                    break;

                ft.chrg.cpMin = cursor;
                ft.chrg.cpMax = -1;
            }

            ft.lpstrText = query;

            DWORD flags = backwards ? 0 : FR_DOWN;

            LRESULT result = SendMessageW(
                chat,
                EM_FINDTEXTEXW,
                flags,
                (LPARAM)&ft
            );

            if (result == -1)
                break;

            if (
                message_search_range_is_body(
                    ft.chrgText.cpMin,
                    ft.chrgText.cpMax
                )
            ) {
                CHARRANGE cr;
                cr.cpMin = ft.chrgText.cpMin;
                cr.cpMax = ft.chrgText.cpMax;

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

                message_search_position =
                    backwards
                        ? ft.chrgText.cpMin
                        : ft.chrgText.cpMax;

                return true;
            }

            // Ignore matches in message headers, dates, names, etc.
            if (backwards) {
                cursor = ft.chrgText.cpMin - 1;
            } else {
                cursor = ft.chrgText.cpMax;

                if (cursor <= ft.chrgText.cpMin)
                    cursor = ft.chrgText.cpMin + 1;
            }
        }
    }

    MessageBeep(MB_ICONASTERISK);
    return false;
}

static HBITMAP media_archive_make_thumbnail(
    HBITMAP source,
    int thumb_size
) {
    if (!source)
        return NULL;

    BITMAP bm = {0};
    if (!GetObject(source, sizeof(bm), &bm))
        return NULL;

    if (bm.bmWidth <= 0 || bm.bmHeight <= 0)
        return NULL;

    HDC screen = GetDC(NULL);
    if (!screen)
        return NULL;

    HDC src_dc = CreateCompatibleDC(screen);
    HDC dst_dc = CreateCompatibleDC(screen);

    if (!src_dc || !dst_dc) {
        if (src_dc) DeleteDC(src_dc);
        if (dst_dc) DeleteDC(dst_dc);
        ReleaseDC(NULL, screen);
        return NULL;
    }

    HBITMAP thumb = CreateCompatibleBitmap(
        screen,
        thumb_size,
        thumb_size
    );

    if (!thumb) {
        DeleteDC(src_dc);
        DeleteDC(dst_dc);
        ReleaseDC(NULL, screen);
        return NULL;
    }

    HGDIOBJ old_src = SelectObject(src_dc, source);
    HGDIOBJ old_dst = SelectObject(dst_dc, thumb);

    RECT rc = {0, 0, thumb_size, thumb_size};
    FillRect(
        dst_dc,
        &rc,
        GetSysColorBrush(COLOR_WINDOW)
    );

    double scale_x =
        (double)thumb_size / (double)bm.bmWidth;

    double scale_y =
        (double)thumb_size / (double)bm.bmHeight;

    double scale =
        scale_x < scale_y ? scale_x : scale_y;

    int width = (int)(bm.bmWidth * scale);
    int height = (int)(bm.bmHeight * scale);

    if (width < 1) width = 1;
    if (height < 1) height = 1;

    int x = (thumb_size - width) / 2;
    int y = (thumb_size - height) / 2;

    SetStretchBltMode(dst_dc, HALFTONE);
    SetBrushOrgEx(dst_dc, 0, 0, NULL);

    StretchBlt(
        dst_dc,
        x,
        y,
        width,
        height,
        src_dc,
        0,
        0,
        bm.bmWidth,
        bm.bmHeight,
        SRCCOPY
    );

    SelectObject(src_dc, old_src);
    SelectObject(dst_dc, old_dst);

    DeleteDC(src_dc);
    DeleteDC(dst_dc);
    ReleaseDC(NULL, screen);

    return thumb;
}

static void media_archive_jump_to_message(int message_id) {
    if (!message_id)
        return;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (messages[i].id != message_id)
            continue;

        CHARRANGE cr;
        cr.cpMin = messages[i].start_char;
        cr.cpMax = messages[i].start_char;

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

        SetForegroundWindow(hMain);
        SetFocus(chat);
        break;
    }
}

static void media_archive_refresh() {
    if (!hMediaArchiveList)
        return;

    ListView_DeleteAllItems(hMediaArchiveList);

    if (hMediaArchiveImages) {
        ListView_SetImageList(
            hMediaArchiveList,
            NULL,
            LVSIL_NORMAL
        );

        ImageList_Destroy(hMediaArchiveImages);
        hMediaArchiveImages = NULL;
    }

    const int thumb_size = 96;

    hMediaArchiveImages = ImageList_Create(
        thumb_size,
        thumb_size,
        ILC_COLOR32,
        media_archive_items.size() > 0
            ? (int)media_archive_items.size()
            : 1,
        16
    );

    if (!hMediaArchiveImages)
        return;

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

    for (int i = 0; i < (int)media_archive_items.size(); i++) {
        HBITMAP thumb = media_archive_make_thumbnail(
            media_archive_items[i].bitmap,
            thumb_size
        );

        int image_index = -1;

        if (thumb) {
            image_index = ImageList_Add(
                hMediaArchiveImages,
                thumb,
                NULL
            );

            DeleteObject(thumb);
        }

        if (image_index < 0)
            continue;

        wchar_t label[32];
        label[0] = 0;

        if (media_archive_items[i].message_id) {
            _snwprintf(
                label,
                ARRAYSIZE(label) - 1,
                L"#%d",
                media_archive_items[i].message_id
            );

            label[ARRAYSIZE(label) - 1] = 0;
        }

        LVITEMW item = {0};
        item.mask =
            LVIF_IMAGE |
            LVIF_PARAM |
            LVIF_TEXT;

        item.iItem = ListView_GetItemCount(
            hMediaArchiveList
        );

        item.iImage = image_index;
        item.lParam =
            media_archive_items[i].message_id;

        item.pszText = label;

        ListView_InsertItemW(
            hMediaArchiveList,
            &item
        );
    }
}

static LRESULT CALLBACK TelegacyMediaArchiveWindow(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    switch (msg) {
        case WM_CREATE: {
            hMediaArchiveOlder = CreateWindowW(
                L"BUTTON",
                L"Older",
                WS_CHILD |
                WS_VISIBLE |
                BS_PUSHBUTTON,
                8,
                7,
                75,
                24,
                hwnd,
                (HMENU)1,
                NULL,
                NULL
            );

            hMediaArchiveList = CreateWindowExW(
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
                (HMENU)2,
                NULL,
                NULL
            );

            HFONT font =
                (HFONT)GetStockObject(DEFAULT_GUI_FONT);

            SendMessage(
                hMediaArchiveOlder,
                WM_SETFONT,
                (WPARAM)font,
                TRUE
            );

            ListView_SetExtendedListViewStyle(
                hMediaArchiveList,
                LVS_EX_BORDERSELECT
            );

            media_archive_refresh();
            return 0;
        }

        case WM_SIZE: {
            RECT rc;
            GetClientRect(hwnd, &rc);

            MoveWindow(
                hMediaArchiveOlder,
                8,
                7,
                75,
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
            if (LOWORD(wParam) == 1) {
                // Intentionally one page per click. The existing
                // history single-flight guard prevents request storms.
                if (
                    current_peer &&
                    !no_more_msgs
                ) {
                    get_history();
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
                hdr->hwndFrom == hMediaArchiveList &&
                hdr->code == NM_DBLCLK
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
                        ListView_GetItemW(
                            hMediaArchiveList,
                            &item
                        )
                    ) {
                        media_archive_jump_to_message(
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
            hMediaArchiveOlder = NULL;
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
}

void media_archive_clear() {
    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (media_archive_items[i].bitmap) {
            DeleteObject(
                media_archive_items[i].bitmap
            );
        }
    }

    media_archive_items.clear();

    if (hMediaArchiveWindow) {
        media_archive_refresh();
    }
}

void media_archive_add_document(
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

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            document->min >= messages[i].start_char &&
            document->max <= messages[i].end_footer
        ) {
            message_id = messages[i].id;
            break;
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
    item.document_id = document_id;
    item.message_id = message_id;
    item.bitmap = copy;

    media_archive_items.push_back(item);

    if (hMediaArchiveWindow) {
        media_archive_refresh();
    }
}

void media_archive_show() {
    if (!current_peer)
        return;

    if (
        hMediaArchiveWindow &&
        IsWindow(hMediaArchiveWindow)
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
        LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground =
        (HBRUSH)(COLOR_BTNFACE + 1);
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

    title[ARRAYSIZE(title) - 1] = 0;

    hMediaArchiveWindow = CreateWindowExW(
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
    }
}

'''

    if anchor not in s:
        raise SystemExit("Could not locate lang_codepage anchor in telegacy.cpp")

    s = s.replace(anchor, anchor + helpers, 1)


# -----------------------------------------------------------------------------
# Create the in-chat search controls above the RichEdit chat
# -----------------------------------------------------------------------------

if "hMessageSearch = CreateWindowExW(" not in s:
    anchor = '\t\tmsgInput = CreateWindow(L"RichEdit20W"'

    controls = r'''		hMessageSearch = CreateWindowExW(
			WS_EX_CLIENTEDGE,
			L"EDIT",
			L"",
			WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
			10,
			40,
			width - 205,
			22,
			hWnd,
			(HMENU)31,
			NULL,
			NULL
		);

		hMessageSearchPrev = CreateWindowW(
			L"BUTTON",
			L"<",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 190,
			40,
			45,
			22,
			hWnd,
			(HMENU)32,
			NULL,
			NULL
		);

		hMessageSearchNext = CreateWindowW(
			L"BUTTON",
			L">",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 140,
			40,
			45,
			22,
			hWnd,
			(HMENU)33,
			NULL,
			NULL
		);

		hMediaArchiveButton = CreateWindowW(
			L"BUTTON",
			L"Media",
			WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
			width - 90,
			40,
			80,
			22,
			hWnd,
			(HMENU)34,
			NULL,
			NULL
		);

		HFONT searchFont = (HFONT)GetStockObject(DEFAULT_GUI_FONT);

		SendMessage(
			hMessageSearch,
			WM_SETFONT,
			(WPARAM)searchFont,
			TRUE
		);

		SendMessage(
			hMessageSearchPrev,
			WM_SETFONT,
			(WPARAM)searchFont,
			TRUE
		);

		SendMessage(
			hMessageSearchNext,
			WM_SETFONT,
			(WPARAM)searchFont,
			TRUE
		);

		SendMessage(
			hMediaArchiveButton,
			WM_SETFONT,
			(WPARAM)searchFont,
			TRUE
		);

'''

    pos = s.find(anchor)
    if pos < 0:
        raise SystemExit("Could not locate msgInput creation anchor")

    s = s[:pos] + controls + s[pos:]


# Move the chat down by one control row.
old_chat_create = (
    '\t\tchat = CreateWindow(L"RichEdit20W", NULL, '
    'WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | ES_LEFT | ES_MULTILINE | '
    'ES_READONLY | WS_CLIPSIBLINGS,\n'
    '\t\t\t10, 40, width - 30, height - 190, hWnd, NULL, NULL, NULL);'
)

new_chat_create = (
    '\t\tchat = CreateWindow(L"RichEdit20W", NULL, '
    'WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | ES_LEFT | ES_MULTILINE | '
    'ES_READONLY | WS_CLIPSIBLINGS,\n'
    '\t\t\t10, 68, width - 30, height - 218, hWnd, NULL, NULL, NULL);'
)

if old_chat_create in s:
    s = s.replace(old_chat_create, new_chat_create, 1)
elif new_chat_create not in s:
    raise SystemExit("Could not locate chat RichEdit creation geometry")


# -----------------------------------------------------------------------------
# WM_COMMAND handlers: live search, previous, next, media archive
# -----------------------------------------------------------------------------

if "case 31: { // message search" not in s:
    anchor = (
        "\t\tcase 3: {\n"
        "\t\t\tif (nt3 && HIWORD(wParam) == CBN_DROPDOWN) "
        "nt3_combobox_fit(hComboBoxChats);"
    )

    handlers = r'''		case 31: { // message search
			if (HIWORD(wParam) == EN_CHANGE) {
				message_search_position = 0;
				message_search_find(false);
			}
			break;
		}

		case 32: { // previous message-search result
			message_search_find(true);
			break;
		}

		case 33: { // next message-search result
			message_search_find(false);
			break;
		}

		case 34: { // media archive
			media_archive_show();
			break;
		}

'''

    pos = s.find(anchor)
    if pos < 0:
        raise SystemExit("Could not locate chat combobox WM_COMMAND handler")

    s = s[:pos] + handlers + s[pos:]


# -----------------------------------------------------------------------------
# Clear search/media state when changing the selected chat
# -----------------------------------------------------------------------------

case3_pos = s.find("\t\tcase 3: {")
if case3_pos >= 0 and "media_archive_clear();" not in s[case3_pos:case3_pos + 5000]:
    original = (
        "\t\t\tcurrent_peer = (Peer*)SendMessage("
        "hComboBoxChats, CB_GETITEMDATA, selIndex, 0);"
    )

    filtered = "\t\t\tcurrent_peer = selected_peer;"

    clear_block = r'''
			media_archive_clear();
			message_search_position = 0;

			if (hMessageSearch)
				SetWindowTextW(hMessageSearch, L"");
'''

    if filtered in s:
        s = s.replace(filtered, filtered + clear_block, 1)
    elif original in s:
        s = s.replace(original, original + clear_block, 1)
    else:
        raise SystemExit("Could not locate current_peer assignment for chat switch")


# -----------------------------------------------------------------------------
# Resize the new row and move chat down
# -----------------------------------------------------------------------------

resize_anchor = (
    "\t\t\thdwp = DeferWindowPos(hdwp, chat, NULL, 10, 40, width - 20, "
    "cantwrite ? height - 70 : (height - 165 + edits_border_offset), SWP_NOZORDER);"
)

resize_replacement = r'''			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearch,
				NULL,
				10,
				40,
				width - 205,
				22,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchPrev,
				NULL,
				width - 190,
				40,
				45,
				22,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				hMessageSearchNext,
				NULL,
				width - 140,
				40,
				45,
				22,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				hMediaArchiveButton,
				NULL,
				width - 90,
				40,
				80,
				22,
				SWP_NOZORDER
			);

			hdwp = DeferWindowPos(
				hdwp,
				chat,
				NULL,
				10,
				68,
				width - 20,
				cantwrite
					? height - 98
					: (height - 193 + edits_border_offset),
				SWP_NOZORDER
			);'''

if resize_anchor in s:
    s = s.replace(resize_anchor, resize_replacement, 1)
elif "hMessageSearchPrev" not in s[s.find("WM_SIZE"):]:
    raise SystemExit("Could not locate chat resize anchor")

if "HDWP hdwp = BeginDeferWindowPos(9);" in s:
    s = s.replace(
        "HDWP hdwp = BeginDeferWindowPos(9);",
        "HDWP hdwp = BeginDeferWindowPos(16);",
        1
    )

write(t, s)


# =============================================================================
# src/response.cpp
# Capture already-decoded chat photos for the media archive.
# =============================================================================

s = read(r)

if "media_archive_add_document(&documents[i], hClone);" not in s:
    old = (
        "\t\t\t\treplace_in_chat(NULL, &cr, NULL, hClone, NULL, NULL, NULL);\n"
        "\t\t\t\tDeleteObject(hClone);\n"
        "\t\t\t\tfound = true;"
    )

    new = (
        "\t\t\t\treplace_in_chat(NULL, &cr, NULL, hClone, NULL, NULL, NULL);\n"
        "\n"
        "\t\t\t\t// Keep a private bitmap copy for the grid archive.\n"
        "\t\t\t\t// photo_size == 1 is the sticker path and is intentionally excluded.\n"
        "\t\t\t\tif (documents[i].photo_size != 1 && hClone)\n"
        "\t\t\t\t\tmedia_archive_add_document(&documents[i], hClone);\n"
        "\n"
        "\t\t\t\tDeleteObject(hClone);\n"
        "\t\t\t\tfound = true;"
    )

    if old not in s:
        raise SystemExit("Could not locate decoded document image insertion in response.cpp")

    s = s.replace(old, new, 1)

write(r, s)

print("Applied Telegacy in-chat search and media archive patch.")
