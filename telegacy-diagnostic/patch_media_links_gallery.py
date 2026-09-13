#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_media_links_gallery.py <Telegacy source directory>")

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
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = brace

    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "'":
                in_char = False
            i += 1
            continue

        if c == "/" and n == "/":
            in_line_comment = True
            i += 2
            continue

        if c == "/" and n == "*":
            in_block_comment = True
            i += 2
            continue

        if c == '"':
            in_string = True
            i += 1
            continue

        if c == "'":
            in_char = True
            i += 1
            continue

        if c == "{":
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


# This patch intentionally layers on top of the successful Media A/V v4 build.
if "media_tabs_av_runtime_v4" not in read(t):
    raise SystemExit(
        "Media A/V v4 is not present. Run patch_media_tabs_av.py before this patch."
    )

if "media_links_gallery_v1" in read(t):
    print("Media links/gallery patch already applied.")
    raise SystemExit(0)


# =============================================================================
# telegacy.h: cross-file helpers
# =============================================================================
s = read(h)

anchor = "bool media_inline_audio_handle_chat_mouse(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);"
if anchor not in s:
    raise SystemExit("Could not locate Media v4 declarations in telegacy.h.")

s = s.replace(
    anchor,
    anchor
    + "\nvoid media_archive_add_link_item(int message_id, const wchar_t* url, const wchar_t* excerpt);"
    + "\nvoid media_album_mark_document(const BYTE* id);"
    + "\nbool media_album_is_document(const BYTE* id);"
    + "\nHBITMAP media_album_make_tile(HBITMAP source);",
    1,
)

write(h, s)


# =============================================================================
# telegacy.cpp
# - Links tab
# - report/list presentation for Music and Links
# - hide phantom combo rows without changing combo indexes
# - shared album-tile helper
# =============================================================================
s = read(t)

# Extend MediaArchiveItem with a second line/column for link context.
struct_anchor = "    wchar_t display_name[260];\n};"
if struct_anchor not in s:
    raise SystemExit("Could not locate MediaArchiveItem tail.")

s = s.replace(
    struct_anchor,
    "    wchar_t display_name[260];\n"
    "    wchar_t secondary_text[260]; // media_links_gallery_v1\n"
    "};",
    1,
)

# Shared grouped-photo registry + uniform gallery tile renderer.
insert_pos = s.find("static HRESULT media_mf_create_player(")
if insert_pos < 0:
    raise SystemExit("Could not locate Media helper insertion point.")

album_helpers = r'''
// media_links_gallery_v1
static std::vector<__int64> media_album_document_ids;

void media_album_mark_document(
    const BYTE* id
) {
    if (!id)
        return;

    __int64 value = 0;
    memcpy(&value, id, 8);

    for (
        int i = 0;
        i < (int)media_album_document_ids.size();
        i++
    ) {
        if (media_album_document_ids[i] == value)
            return;
    }

    media_album_document_ids.push_back(value);

    // Keep this tiny registry bounded over very long sessions.
    if (media_album_document_ids.size() > 4096)
        media_album_document_ids.erase(media_album_document_ids.begin());
}

bool media_album_is_document(
    const BYTE* id
) {
    if (!id)
        return false;

    __int64 value = 0;
    memcpy(&value, id, 8);

    for (
        int i = 0;
        i < (int)media_album_document_ids.size();
        i++
    ) {
        if (media_album_document_ids[i] == value)
            return true;
    }

    return false;
}

HBITMAP media_album_make_tile(
    HBITMAP source
) {
    if (!source)
        return NULL;

    BITMAP bm = {0};
    if (!GetObject(source, sizeof(bm), &bm))
        return NULL;

    int src_w = bm.bmWidth;
    int src_h = bm.bmHeight < 0 ? -bm.bmHeight : bm.bmHeight;

    if (src_w <= 0 || src_h <= 0)
        return NULL;

    const int tile_w = 132;
    const int tile_h = 104;
    const int pad = 4;

    HDC screen = GetDC(NULL);
    if (!screen)
        return NULL;

    HBITMAP tile = CreateCompatibleBitmap(screen, tile_w, tile_h);
    ReleaseDC(NULL, screen);

    if (!tile)
        return NULL;

    HDC src_dc = CreateCompatibleDC(NULL);
    HDC dst_dc = CreateCompatibleDC(NULL);

    if (!src_dc || !dst_dc) {
        if (src_dc) DeleteDC(src_dc);
        if (dst_dc) DeleteDC(dst_dc);
        DeleteObject(tile);
        return NULL;
    }

    HGDIOBJ old_src = SelectObject(src_dc, source);
    HGDIOBJ old_dst = SelectObject(dst_dc, tile);

    RECT all = {0, 0, tile_w, tile_h};
    FillRect(dst_dc, &all, GetSysColorBrush(COLOR_WINDOW));

    RECT frame = {1, 1, tile_w - 1, tile_h - 1};
    DrawEdge(dst_dc, &frame, EDGE_SUNKEN, BF_RECT);

    int area_w = tile_w - pad * 2;
    int area_h = tile_h - pad * 2;

    double scale_x = (double)area_w / (double)src_w;
    double scale_y = (double)area_h / (double)src_h;
    double scale = scale_x < scale_y ? scale_x : scale_y;

    int draw_w = (int)(src_w * scale);
    int draw_h = (int)(src_h * scale);

    if (draw_w < 1) draw_w = 1;
    if (draw_h < 1) draw_h = 1;

    int draw_x = (tile_w - draw_w) / 2;
    int draw_y = (tile_h - draw_h) / 2;

    SetStretchBltMode(dst_dc, HALFTONE);
    SetBrushOrgEx(dst_dc, 0, 0, NULL);

    StretchBlt(
        dst_dc,
        draw_x,
        draw_y,
        draw_w,
        draw_h,
        src_dc,
        0,
        0,
        src_w,
        src_h,
        SRCCOPY
    );

    SelectObject(src_dc, old_src);
    SelectObject(dst_dc, old_dst);
    DeleteDC(src_dc);
    DeleteDC(dst_dc);

    return tile;
}

void media_archive_add_link_item(
    int message_id,
    const wchar_t* url,
    const wchar_t* excerpt
) {
    if (message_id <= 0 || !url || !url[0])
        return;

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].media_kind == 3 &&
            media_archive_items[i].message_id == message_id
        ) {
            return;
        }
    }

    MediaArchiveItem item = {0};
    item.document_id = (__int64)message_id;
    item.message_id = message_id;
    item.page_index = media_archive_request_page;
    item.media_kind = 3;
    item.has_document = false;
    item.bitmap = NULL;
    item.file_path[0] = 0;

    wcsncpy(
        item.display_name,
        url,
        ARRAYSIZE(item.display_name) - 1
    );
    item.display_name[ARRAYSIZE(item.display_name) - 1] = 0;

    if (excerpt && excerpt[0]) {
        wcsncpy(
            item.secondary_text,
            excerpt,
            ARRAYSIZE(item.secondary_text) - 1
        );
        item.secondary_text[ARRAYSIZE(item.secondary_text) - 1] = 0;
    }

    media_archive_items.push_back(item);
}

static bool telegacy_chat_combo_peer_is_named(
    Peer* peer
) {
    if (!peer || peer == (Peer*)CB_ERR)
        return false;

    bool known = false;

    for (int i = 0; i < peers_count; i++) {
        if (peer == &peers[i]) {
            known = true;
            break;
        }
    }

    return
        known &&
        peer->name &&
        peer->name[0];
}

static void telegacy_hide_phantom_chat_rows() {
    if (!hComboBoxChats)
        return;

    int count =
        (int)SendMessage(
            hComboBoxChats,
            CB_GETCOUNT,
            0,
            0
        );

    int normal_height = 21;

    SendMessage(
        hComboBoxChats,
        CB_SETITEMHEIGHT,
        (WPARAM)-1,
        normal_height
    );

    for (int i = 0; i < count; i++) {
        LRESULT data =
            SendMessage(
                hComboBoxChats,
                CB_GETITEMDATA,
                i,
                0
            );

        Peer* peer =
            data == CB_ERR
                ? NULL
                : (Peer*)data;

        SendMessage(
            hComboBoxChats,
            CB_SETITEMHEIGHT,
            i,
            telegacy_chat_combo_peer_is_named(peer)
                ? normal_height
                : 1
        );
    }
}

'''

s = s[:insert_pos] + album_helpers + s[insert_pos:]

# Fourth server-side filter: messages containing URLs.
filter_v5 = r'''static unsigned int media_archive_filter_constructor() {
    if (media_archive_kind == 1)
        return 0x9fc00e65; // inputMessagesFilterVideo

    if (media_archive_kind == 2)
        return 0x3751b49e; // inputMessagesFilterMusic

    if (media_archive_kind == 3)
        return 0x7ef0dd87; // inputMessagesFilterUrl

    return 0x9609a51c; // inputMessagesFilterPhotos
}'''
s = replace_function(s, "static unsigned int media_archive_filter_constructor()", filter_v5)

# Allow kind 3 in reset_for_kind.
start, end = function_range(s, "static void media_archive_reset_for_kind(")
reset_func = s[start:end]
if "kind > 2" in reset_func:
    reset_func = reset_func.replace("kind > 2", "kind > 3", 1)
elif "kind > 3" not in reset_func:
    raise SystemExit("Could not extend media_archive_reset_for_kind to Links.")
s = s[:start] + reset_func + s[end:]

# Double click on a Link opens the URL; Images/Video/Music retain current behavior.
open_item_v5 = r'''static void media_archive_open_item(
    int item_index
) {
    if (
        item_index < 0 ||
        item_index >= (int)media_archive_items.size()
    ) {
        return;
    }

    MediaArchiveItem* item =
        &media_archive_items[item_index];

    if (item->media_kind == 0) {
        if (!media_archive_begin_full_photo_download(item_index))
            MessageBeep(MB_ICONASTERISK);
        return;
    }

    if (item->media_kind == 3) {
        if (!item->display_name[0]) {
            MessageBeep(MB_ICONASTERISK);
            return;
        }

        media_archive_shell_open(
            item->display_name
        );
        return;
    }

    media_archive_begin_av_download(
        item_index
    );
}'''
s = replace_function(s, "static void media_archive_open_item(", open_item_v5)

# Better Music text and a proper Links table.
refresh_v5 = r'''static void media_archive_refresh() {
    if (!hMediaArchiveList)
        return;

    SendMessageW(
        hMediaArchiveList,
        WM_SETREDRAW,
        FALSE,
        0
    );

    bool icon_grid =
        media_archive_kind == 0 ||
        media_archive_kind == 1;

    LONG_PTR old_style =
        GetWindowLongPtrW(
            hMediaArchiveList,
            GWL_STYLE
        );

    LONG_PTR desired_type =
        icon_grid
            ? LVS_ICON
            : LVS_REPORT;

    if ((old_style & LVS_TYPEMASK) != desired_type) {
        SetWindowLongPtrW(
            hMediaArchiveList,
            GWL_STYLE,
            (old_style & ~LVS_TYPEMASK) |
                desired_type
        );
    }

    ListView_DeleteAllItems(
        hMediaArchiveList
    );

    while (
        SendMessageW(
            hMediaArchiveList,
            LVM_DELETECOLUMN,
            0,
            0
        )
    ) {
    }

    HIMAGELIST old_images =
        hMediaArchiveImages;

    hMediaArchiveImages = NULL;

    if (icon_grid) {
        hMediaArchiveImages =
            ImageList_Create(
                96,
                96,
                ILC_COLOR32,
                20,
                16
            );

        if (hMediaArchiveImages) {
            ListView_SetImageList(
                hMediaArchiveList,
                hMediaArchiveImages,
                LVSIL_NORMAL
            );

            SendMessageW(
                hMediaArchiveList,
                LVM_SETICONSPACING,
                0,
                MAKELPARAM(116, 120)
            );
        }
    } else {
        ListView_SetImageList(
            hMediaArchiveList,
            NULL,
            LVSIL_NORMAL
        );

        LVCOLUMNW column = {0};
        column.mask = LVCF_TEXT | LVCF_WIDTH | LVCF_FMT;
        column.fmt = LVCFMT_LEFT;

        if (media_archive_kind == 2) {
            column.pszText = (LPWSTR)L"\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435";
            column.cx = 360;
            SendMessageW(hMediaArchiveList, LVM_INSERTCOLUMNW, 0, (LPARAM)&column);

            column.pszText = (LPWSTR)L"\u0414\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c";
            column.cx = 95;
            SendMessageW(hMediaArchiveList, LVM_INSERTCOLUMNW, 1, (LPARAM)&column);

            column.pszText = (LPWSTR)L"\u0420\u0430\u0437\u043c\u0435\u0440";
            column.cx = 100;
            SendMessageW(hMediaArchiveList, LVM_INSERTCOLUMNW, 2, (LPARAM)&column);
        } else {
            column.pszText = (LPWSTR)L"\u0421\u0441\u044b\u043b\u043a\u0430";
            column.cx = 330;
            SendMessageW(hMediaArchiveList, LVM_INSERTCOLUMNW, 0, (LPARAM)&column);

            column.pszText = (LPWSTR)L"\u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435";
            column.cx = 330;
            SendMessageW(hMediaArchiveList, LVM_INSERTCOLUMNW, 1, (LPARAM)&column);
        }
    }

    if (old_images)
        ImageList_Destroy(old_images);

    HFONT list_font = hFonts[1]
        ? hFonts[1]
        : (HFONT)GetStockObject(DEFAULT_GUI_FONT);

    SendMessageW(
        hMediaArchiveList,
        WM_SETFONT,
        (WPARAM)list_font,
        TRUE
    );

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        MediaArchiveItem* archive_item =
            &media_archive_items[i];

        if (
            archive_item->media_kind != media_archive_kind ||
            archive_item->page_index != media_archive_current_page
        ) {
            continue;
        }

        LVITEMW item = {0};
        item.iItem =
            ListView_GetItemCount(
                hMediaArchiveList
            );
        item.lParam = i;

        wchar_t label[340] = {0};

        if (icon_grid) {
            HBITMAP thumb =
                media_archive_kind == 1
                    ? media_archive_make_video_thumbnail(
                        archive_item->bitmap
                    )
                    : media_archive_make_thumbnail(
                        archive_item->bitmap,
                        96
                    );

            if (!thumb || !hMediaArchiveImages) {
                if (thumb)
                    DeleteObject(thumb);
                continue;
            }

            int image_index =
                ImageList_Add(
                    hMediaArchiveImages,
                    thumb,
                    NULL
                );

            DeleteObject(thumb);

            if (image_index < 0)
                continue;

            if (media_archive_kind == 1) {
                if (archive_item->duration > 0) {
                    _snwprintf(
                        label,
                        ARRAYSIZE(label) - 1,
                        L"%02d:%02d",
                        archive_item->duration / 60,
                        archive_item->duration % 60
                    );
                } else {
                    wcscpy(label, L"Video");
                }
            } else if (archive_item->message_id > 0) {
                _snwprintf(
                    label,
                    ARRAYSIZE(label) - 1,
                    L"#%d",
                    archive_item->message_id
                );
            }

            item.mask =
                LVIF_IMAGE |
                LVIF_PARAM |
                LVIF_TEXT;
            item.iImage = image_index;
            item.pszText = label;

            SendMessageW(
                hMediaArchiveList,
                LVM_INSERTITEMW,
                0,
                (LPARAM)&item
            );
            continue;
        }

        item.mask = LVIF_PARAM | LVIF_TEXT;
        item.pszText = archive_item->display_name;

        int row =
            (int)SendMessageW(
                hMediaArchiveList,
                LVM_INSERTITEMW,
                0,
                (LPARAM)&item
            );

        if (row < 0)
            continue;

        if (media_archive_kind == 2) {
            wchar_t duration_text[32] = {0};
            wchar_t size_text[48] = {0};

            if (archive_item->duration > 0) {
                if (archive_item->duration < 3600) {
                    _snwprintf(
                        duration_text,
                        ARRAYSIZE(duration_text) - 1,
                        L"%02d:%02d",
                        archive_item->duration / 60,
                        archive_item->duration % 60
                    );
                } else {
                    _snwprintf(
                        duration_text,
                        ARRAYSIZE(duration_text) - 1,
                        L"%02d:%02d:%02d",
                        archive_item->duration / 3600,
                        (archive_item->duration / 60) % 60,
                        archive_item->duration % 60
                    );
                }
            }

            if (
                archive_item->has_document &&
                archive_item->av_document.size > 0
            ) {
                double size =
                    (double)archive_item->av_document.size;
                int unit = 0;
                const wchar_t* units[] = {
                    L"B", L"KB", L"MB", L"GB"
                };

                while (size >= 1024.0 && unit < 3) {
                    size /= 1024.0;
                    unit++;
                }

                if (unit == 0)
                    _snwprintf(size_text, ARRAYSIZE(size_text) - 1, L"%.0f %s", size, units[unit]);
                else
                    _snwprintf(size_text, ARRAYSIZE(size_text) - 1, L"%.1f %s", size, units[unit]);
            }

            ListView_SetItemText(
                hMediaArchiveList,
                row,
                1,
                duration_text
            );

            ListView_SetItemText(
                hMediaArchiveList,
                row,
                2,
                size_text
            );
        } else {
            ListView_SetItemText(
                hMediaArchiveList,
                row,
                1,
                archive_item->secondary_text
            );
        }
    }

    media_archive_update_nav();

    SendMessageW(
        hMediaArchiveList,
        WM_SETREDRAW,
        TRUE,
        0
    );

    RedrawWindow(
        hMediaArchiveList,
        NULL,
        NULL,
        RDW_INVALIDATE |
        RDW_UPDATENOW |
        RDW_ALLCHILDREN
    );
}'''
s = replace_function(s, "static void media_archive_refresh() {", refresh_v5)

# Add a fourth tab and allow it to be selected.
start, end = function_range(s, "static LRESULT CALLBACK TelegacyMediaArchiveWindow(")
wnd = s[start:end]

music_tab = r'''            tab.pszText =
                (LPWSTR)L"\u041C\u0443\u0437\u044B\u043A\u0430";
            TabCtrl_InsertItem(
                hMediaArchiveTabs,
                2,
                &tab
            );'''

links_tab = music_tab + r'''

            tab.pszText =
                (LPWSTR)L"\u0421\u0441\u044B\u043B\u043A\u0438";
            TabCtrl_InsertItem(
                hMediaArchiveTabs,
                3,
                &tab
            );'''

if music_tab not in wnd:
    raise SystemExit("Could not locate Music tab insertion.")

wnd = wnd.replace(music_tab, links_tab, 1)
wnd = wnd.replace("selected <= 2", "selected <= 3", 1)
s = s[:start] + wnd + s[end:]

# Make the Chats combo variable-height, then collapse unnamed placeholder rows
# to 1px while retaining the original folder/index mapping.
combo_start = s.find("hComboBoxChats = CreateWindow(")
if combo_start < 0:
    raise SystemExit("Could not locate Chats combo creation.")

combo_end = s.find(");", combo_start)
if combo_end < 0:
    raise SystemExit("Could not locate end of Chats combo creation.")

combo_fragment = s[combo_start:combo_end]
if "CBS_OWNERDRAWFIXED" not in combo_fragment:
    raise SystemExit("Could not locate Chats combo owner-draw style.")

combo_fragment = combo_fragment.replace(
    "CBS_OWNERDRAWFIXED",
    "CBS_OWNERDRAWVARIABLE",
    1,
)
s = s[:combo_start] + combo_fragment + s[combo_end:]

old_dropdown = "if (nt3 && HIWORD(wParam) == CBN_DROPDOWN) nt3_combobox_fit(hComboBoxChats);"
new_dropdown = r'''if (HIWORD(wParam) == CBN_DROPDOWN) {
                telegacy_hide_phantom_chat_rows();
                if (nt3)
                    nt3_combobox_fit(hComboBoxChats);
            }'''

if old_dropdown not in s:
    raise SystemExit("Could not locate chat-combo dropdown handler.")

s = s.replace(old_dropdown, new_dropdown, 1)

measure_anchor = "\tcase WM_DRAWITEM: {"
if measure_anchor not in s:
    raise SystemExit("Could not locate main WM_DRAWITEM handler.")

measure_code = r'''	case WM_MEASUREITEM: {
		MEASUREITEMSTRUCT* measure =
			(MEASUREITEMSTRUCT*)lParam;

		if (measure && measure->CtlID == 3) {
			measure->itemHeight = 21;
			return TRUE;
		}

		break;
	}
'''

s = s.replace(measure_anchor, measure_code + measure_anchor, 1)

write(t, s)


# =============================================================================
# response.cpp
# - server-side Links tab parser
# - keep grouped chat photos tiled even after Telegram preview replacement
# =============================================================================
s = read(r)

handler_pos = s.find("static void media_archive_handle_server_response(")
if handler_pos < 0:
    raise SystemExit("Could not locate Media server response handler.")

link_helper = r'''
// Extract the first URL from a normal Telegram message. Supports both visible
// messageEntityUrl and hidden messageEntityTextUrl entities, with a text scan
// fallback for ordinary http(s)/www links.
static bool media_archive_extract_link(
    BYTE* message,
    int available,
    wchar_t* url,
    int url_count,
    wchar_t* excerpt,
    int excerpt_count
) {
    if (
        !message ||
        available < 16 ||
        !url ||
        url_count < 8
    ) {
        return false;
    }

    url[0] = 0;
    if (excerpt && excerpt_count > 0)
        excerpt[0] = 0;

    int constructor = read_le(message, 4);
    if (constructor != 0x96fdbbe9)
        return false;

    int offset = 4;
    int flags = read_le(message + offset, 4);
    int flags2 = read_le(message + offset + 4, 4);
    offset += 12;

    if (flags & (1 << 8)) offset += 12;
    if (flags & (1 << 29)) offset += 4;
    offset += 12;
    if (flags & (1 << 28)) offset += 12;

    if (flags & (1 << 2)) {
        if (offset + 4 > available) return false;
        int n = msgfwd_offset(message + offset);
        if (n <= 0) return false;
        offset += n;
    }

    if (flags & (1 << 11)) offset += 8;
    if (flags2 & (1 << 0)) offset += 8;

    if (flags & (1 << 3)) {
        if (offset + 4 > available) return false;
        int n = msgrpl_offset(message + offset);
        if (n <= 0) return false;
        offset += n;
    }

    // date:int
    offset += 4;

    if (offset < 0 || offset >= available)
        return false;

    int text_tl_len =
        tlstr_len(
            message + offset,
            true
        );

    if (
        text_tl_len <= 0 ||
        offset + text_tl_len > available
    ) {
        return false;
    }

    wchar_t* text =
        read_string(
            message + offset,
            NULL
        );

    if (!text)
        return false;

    if (excerpt && excerpt_count > 0) {
        wcsncpy(excerpt, text, excerpt_count - 1);
        excerpt[excerpt_count - 1] = 0;

        for (int i = 0; excerpt[i]; i++) {
            if (excerpt[i] == L'\r' || excerpt[i] == L'\n' || excerpt[i] == L'\t')
                excerpt[i] = L' ';
        }
    }

    offset += text_tl_len;

    if (flags & (1 << 9)) {
        if (offset + 4 > available) {
            free(text);
            return false;
        }

        int n = messagemedia_offset(message + offset);
        if (n <= 0 || offset + n > available) {
            free(text);
            return false;
        }

        offset += n;
    }

    if (flags & (1 << 6)) {
        if (offset + 4 > available) {
            free(text);
            return false;
        }

        int n = replymarkup_offset(message + offset);
        if (n <= 0 || offset + n > available) {
            free(text);
            return false;
        }

        offset += n;
    }

    if (flags & (1 << 7)) {
        if (offset + 8 <= available) {
            int count = read_le(message + offset + 4, 4);
            offset += 8;

            if (count >= 0 && count <= 10000) {
                for (int i = 0; i < count && offset + 12 <= available; i++) {
                    int entity_constructor = read_le(message + offset, 4);
                    int entity_offset = read_le(message + offset + 4, 4);
                    int entity_length = read_le(message + offset + 8, 4);

                    if (entity_constructor == 0x76a6d327) {
                        // messageEntityTextUrl#76a6d327
                        if (offset + 12 < available) {
                            wchar_t* entity_url =
                                read_string(
                                    message + offset + 12,
                                    NULL
                                );

                            if (entity_url && entity_url[0]) {
                                wcsncpy(url, entity_url, url_count - 1);
                                url[url_count - 1] = 0;
                                free(entity_url);
                                free(text);
                                return true;
                            }

                            free(entity_url);
                        }
                    } else if (
                        entity_constructor == 0x6ed02538 &&
                        entity_offset >= 0 &&
                        entity_length > 0
                    ) {
                        // messageEntityUrl#6ed02538. Telegram offsets are
                        // UTF-16 units, matching wchar_t in this Win32 build.
                        int text_len = (int)wcslen(text);

                        if (entity_offset < text_len) {
                            int copy_len = entity_length;
                            if (entity_offset + copy_len > text_len)
                                copy_len = text_len - entity_offset;
                            if (copy_len > url_count - 1)
                                copy_len = url_count - 1;

                            wcsncpy(url, text + entity_offset, copy_len);
                            url[copy_len] = 0;
                            free(text);
                            return url[0] != 0;
                        }
                    }

                    int n = msgent_offset(message + offset, NULL);
                    if (n <= 0 || offset + n > available)
                        break;
                    offset += n;
                }
            }
        }
    }

    // Fallback: scan the visible text.
    const wchar_t* starts[] = {
        L"https://",
        L"http://",
        L"www."
    };

    const wchar_t* found = NULL;

    for (int i = 0; i < 3; i++) {
        const wchar_t* candidate = wcsstr(text, starts[i]);
        if (candidate && (!found || candidate < found))
            found = candidate;
    }

    if (found) {
        int length = 0;

        while (
            found[length] &&
            found[length] != L' ' &&
            found[length] != L'\r' &&
            found[length] != L'\n' &&
            found[length] != L'\t' &&
            found[length] != L'<' &&
            found[length] != L'>'
        ) {
            length++;
        }

        while (
            length > 0 &&
            (
                found[length - 1] == L'.' ||
                found[length - 1] == L',' ||
                found[length - 1] == L';' ||
                found[length - 1] == L':' ||
                found[length - 1] == L')' ||
                found[length - 1] == L']'
            )
        ) {
            length--;
        }

        if (length > 0) {
            bool bare_www =
                wcsncmp(found, L"www.", 4) == 0;

            int prefix = bare_www ? 8 : 0; // "https://"
            int max_copy = url_count - 1 - prefix;
            if (length > max_copy)
                length = max_copy;

            if (bare_www)
                wcscpy(url, L"https://");

            wcsncpy(url + prefix, found, length);
            url[prefix + length] = 0;
        }
    }

    free(text);
    return url[0] != 0;
}

'''

s = s[:handler_pos] + link_helper + s[handler_pos:]

start, end = function_range(s, "static void media_archive_handle_server_response(")
handler = s[start:end]

# Links do not need MessageMedia, so parse them directly from the message body.
media_branch_anchor = r'''        if (
            media &&
            media_archive_kind == 0
        ) {'''

link_branch = r'''        if (media_archive_kind == 3) {
            wchar_t url[512] = {0};
            wchar_t excerpt[260] = {0};

            if (
                media_archive_extract_link(
                    response + offset,
                    consumed,
                    url,
                    ARRAYSIZE(url),
                    excerpt,
                    ARRAYSIZE(excerpt)
                )
            ) {
                media_archive_add_link_item(
                    message_id,
                    url,
                    excerpt
                );
                added_count++;
            }
        }

'''

if media_branch_anchor not in handler:
    raise SystemExit("Could not locate Media image branch in server response.")

handler = handler.replace(media_branch_anchor, link_branch + media_branch_anchor, 1)

old_av_cond = r'''        if (
            media &&
            media_archive_kind != 0
        ) {'''
new_av_cond = r'''        if (
            media &&
            (
                media_archive_kind == 1 ||
                media_archive_kind == 2
            )
        ) {'''

if old_av_cond not in handler:
    raise SystemExit("Could not restrict A/V document parsing away from Links.")

handler = handler.replace(old_av_cond, new_av_cond, 1)
s = s[:start] + handler + s[end:]

# When a grouped album preview finishes downloading, keep the same uniform tile
# instead of replacing it with a raw small Telegram preview bitmap.
old_replace = "\t\t\t\tif (documents[i].visible)\n\t\t\t\t\treplace_in_chat(NULL, &cr, NULL, hClone, NULL, NULL, NULL);"

new_replace = r'''				if (documents[i].visible) {
                    HBITMAP chat_bitmap = hClone;
                    HBITMAP album_tile = NULL;

                    if (
                        hClone &&
                        media_album_is_document(
                            documents[i].id
                        )
                    ) {
                        album_tile =
                            media_album_make_tile(
                                hClone
                            );

                        if (album_tile)
                            chat_bitmap = album_tile;
                    }

                    replace_in_chat(
                        NULL,
                        &cr,
                        NULL,
                        chat_bitmap,
                        NULL,
                        NULL,
                        NULL
                    );

                    if (album_tile)
                        DeleteObject(album_tile);
                }'''

if old_replace not in s:
    raise SystemExit("Could not locate chat photo replacement block.")

s = s.replace(old_replace, new_replace, 1)

write(r, s)


# =============================================================================
# message.cpp
# - mark Telegram grouped photos
# - render each grouped image as an equal-sized gallery tile
# =============================================================================
s = read(m)

photo_id_anchor = "\t\t\tmemcpy(document.id, doc + 16, 8);"
if photo_id_anchor not in s:
    raise SystemExit("Could not locate photo document id parsing.")

s = s.replace(
    photo_id_anchor,
    photo_id_anchor
    + "\n\t\t\tif (group_media) media_album_mark_document(document.id);",
    1,
)

photo_insert_old = r'''		} else if (IMAGELOADPOLICY) {
			insert_image(chat, NULL, hClone);
			DeleteObject(hClone);
		} else {'''.replace('\\t', '\t')

photo_insert_new = r'''		} else if (IMAGELOADPOLICY) {
			HBITMAP display_bitmap = hClone;
			HBITMAP gallery_tile = NULL;

			if (group_media && hClone) {
				gallery_tile = media_album_make_tile(hClone);
				if (gallery_tile)
					display_bitmap = gallery_tile;
			}

			insert_image(chat, NULL, display_bitmap);

			if (gallery_tile)
				DeleteObject(gallery_tile);

			DeleteObject(hClone);
		} else {'''.replace('\\t', '\t')

if photo_insert_old not in s:
    raise SystemExit("Could not locate inline photo insertion block.")

s = s.replace(photo_insert_old, photo_insert_new, 1)

write(m, s)


# =============================================================================
# Final checks
# =============================================================================
checks = {
    h: [
        "media_archive_add_link_item",
        "media_album_make_tile",
    ],
    t: [
        "media_links_gallery_v1",
        "inputMessagesFilterUrl",
        "LVS_REPORT",
        "L\"\\u0421\\u0441\\u044b\\u043b\\u043a\\u0430\"",
        "CBS_OWNERDRAWVARIABLE",
        "telegacy_hide_phantom_chat_rows",
    ],
    r: [
        "media_archive_extract_link",
        "messageEntityTextUrl#76a6d327",
        "media_archive_kind == 3",
        "media_album_is_document",
    ],
    m: [
        "media_album_mark_document(document.id)",
        "media_album_make_tile(hClone)",
    ],
}

for path, tokens in checks.items():
    text = read(path)
    for token in tokens:
        if token not in text:
            raise SystemExit(
                f"Media links/gallery verification failed in {path.name}: {token}"
            )

print(
    "Applied Media links/gallery patch: Links tab, phantom-row collapse, "
    "clean Music columns, and grouped-photo gallery tiles."
)
