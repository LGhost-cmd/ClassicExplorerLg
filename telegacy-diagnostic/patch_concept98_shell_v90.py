#!/usr/bin/env python3
"""Concept 98 shell for Telegacy diagnostic: native functional two-pane Win32 UI.

No network, parser, chat document or media code is replaced. The original combo
remains the authoritative chat selector; the new list only mirrors and controls it.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_concept98_shell_v90.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
h = root / "src" / "helpers.cpp"

def read(p):
    return p.read_text(encoding="latin-1")

def write(p, text):
    p.write_text(text, encoding="latin-1", newline="\r\n")

def replace_once(source, old, new, label):
    if old not in source:
        raise SystemExit("Concept 98 anchor missing: " + label)
    return source.replace(old, new, 1)

def function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit("Function not found: " + signature)
    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit("Function brace not found: " + signature)
    depth, quote, ch, line, block, escape = 0, False, False, False, False, False
    i = brace
    while i < len(source):
        c = source[i]
        n = source[i+1] if i+1 < len(source) else ""
        if line:
            line = c != "\n"
            i += 1
            continue
        if block:
            if c == "*" and n == "/":
                block = False
                i += 2
            else:
                i += 1
            continue
        if quote or ch:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif (quote and c == '"') or (ch and c == "'"):
                quote, ch = False, False
            i += 1
            continue
        if c == "/" and n == "/":
            line = True
            i += 2
            continue
        if c == "/" and n == "*":
            block = True
            i += 2
            continue
        if c == '"':
            quote = True
            i += 1
            continue
        if c == "'":
            ch = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i+1
        i += 1
    raise SystemExit("Closing brace not found: " + signature)

for path in (t,h):
    if not path.exists():
        raise SystemExit("Missing Telegacy source: " + str(path))

s = read(t)
if "concept98_shell_v90" in s:
    print("Concept 98 v9.0 already applied.")
    raise SystemExit(0)

for marker in (
    "chat_runtime_sticker_stability_v88",
    "chat_media_identity_stability_v87",
    "hMessageSearch",
    "hChatSearch",
):
    if marker not in s:
        raise SystemExit("Expected runtime prerequisite not found: " + marker)

s = replace_once(
    s,
    "#include <telegacy.h>\n",
    "#include <telegacy.h>\n#include <wctype.h>\n",
    "include",
)

wnd_signature = "LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {"
if wnd_signature not in s:
    raise SystemExit("Cannot locate Win32 main window proc.")

shell = r'''
// concept98_shell_v90 - native Win9x-inspired, selectable working layout.
// These controls are a view of current_folder/current_peer; the existing combo,
// message editor, dialogs, network requests and media runtime remain authoritative.
bool concept98_enabled = true;

static HWND concept98_list = NULL;
static HWND concept98_filter = NULL;
static HWND concept98_caption = NULL;
static HWND concept98_chat_title = NULL;
static HWND concept98_chat_detail = NULL;
static HWND concept98_list_caption = NULL;
static HWND concept98_rule = NULL;
static HWND concept98_search_button = NULL;
static HWND concept98_profile_button = NULL;
static HWND concept98_more_button = NULL;
static std::vector<int> concept98_folder_indices;
static ChatsFolder* concept98_list_folder = NULL;
static wchar_t concept98_previous_filter[96] = {0};
static bool concept98_refreshing = false;
static const UINT_PTR CONCEPT98_TIMER = 8909;
static const int CONCEPT98_LIST_ID = 8910;

static bool concept98_match(
    const wchar_t* value,
    const wchar_t* needle
) {
    if (!needle || !needle[0])
        return true;
    if (!value)
        return false;

    size_t needle_len = wcslen(needle);
    for (const wchar_t* cursor = value; *cursor; ++cursor) {
        if (CompareStringW(LOCALE_USER_DEFAULT, NORM_IGNORECASE,
                           cursor, (int)needle_len,
                           needle, (int)needle_len) == CSTR_EQUAL)
            return true;
    }
    return false;
}

static void concept98_sync() {
    if (!concept98_enabled || !concept98_list || concept98_refreshing)
        return;

    concept98_refreshing = true;
    wchar_t query[96] = {0};
    if (concept98_filter)
        GetWindowTextW(concept98_filter, query, ARRAYSIZE(query));

    std::vector<int> filtered;
    if (current_folder && current_folder->peers && peers) {
        int n = current_folder->count;
        if (n > peers_count)
            n = peers_count;

        for (int i = 0; i < n; ++i) {
            int peer_index = current_folder->peers[i];
            if (peer_index < 0 || peer_index >= peers_count)
                continue;

            if (concept98_match(peers[peer_index].name, query))
                filtered.push_back(i);
        }
    }

    bool mapping_changed =
        current_folder != concept98_list_folder ||
        filtered != concept98_folder_indices ||
        wcscmp(query, concept98_previous_filter) != 0;

    if (mapping_changed) {
        concept98_folder_indices.swap(filtered);
        concept98_list_folder = current_folder;
        wcscpy_s(concept98_previous_filter, query);

        SendMessageW(concept98_list, WM_SETREDRAW, FALSE, 0);
        SendMessageW(
            concept98_list, LB_SETCOUNT,
            (WPARAM)concept98_folder_indices.size(), 0
        );
        SendMessageW(concept98_list, WM_SETREDRAW, TRUE, 0);
    }

    int selected = -1;
    for (int i = 0; i < (int)concept98_folder_indices.size(); ++i) {
        int slot = concept98_folder_indices[i];
        if (current_folder &&
            &peers[current_folder->peers[slot]] == current_peer) {
            selected = i;
            break;
        }
    }

    if ((int)SendMessageW(concept98_list, LB_GETCURSEL, 0, 0) != selected)
        SendMessageW(concept98_list, LB_SETCURSEL, selected, 0);

    if (current_peer && current_peer->name) {
        SetWindowTextW(concept98_chat_title, current_peer->name);
        const wchar_t* type =
            current_peer->type == 2 ? L"\x041a\x0430\x043d\x0430\x043b" :
            current_peer->type == 1 ? L"\x0413\x0440\x0443\x043f\x043f\x0430" :
            L"\x041a\x043e\x043d\x0442\x0430\x043a\x0442";
        SetWindowTextW(concept98_chat_detail, type);
    } else {
        SetWindowTextW(concept98_chat_title, L"\x0412\x044b\x0431\x0435\x0440\x0438\x0442\x0435 \x0447\x0430\x0442");
        SetWindowTextW(concept98_chat_detail, L"Telegram / Telegacy");
    }

    EnableWindow(concept98_profile_button, current_peer != NULL);
    EnableWindow(concept98_more_button, current_peer != NULL);

    InvalidateRect(concept98_list, NULL, FALSE);
    concept98_refreshing = false;
}

static void concept98_apply_layout(HWND hwnd) {
    if (!concept98_list || !IsWindow(concept98_list))
        return;

    HWND extras[] = {
        concept98_list, concept98_filter, concept98_caption,
        concept98_chat_title, concept98_chat_detail,
        concept98_list_caption, concept98_rule,
        concept98_search_button, concept98_profile_button,
        concept98_more_button
    };

    if (!concept98_enabled) {
        for (int i = 0; i < (int)ARRAYSIZE(extras); ++i)
            if (extras[i]) ShowWindow(extras[i], SW_HIDE);

        ShowWindow(hComboBoxChats, SW_SHOW);
        MoveWindow(hComboBoxFolders, 10, 10, 180, 240, TRUE);
        MoveWindow(hComboBoxChats, 200, 10, 230, 240, TRUE);
        return;
    }

    RECT rc = {0};
    GetClientRect(hwnd, &rc);
    int w = rc.right - rc.left;
    int h = rc.bottom - rc.top;
    int left = 240;
    int content_x = left + 10;
    int content_w = w - content_x - 10;
    if (content_w < 220)
        content_w = 220;

    for (int i = 0; i < (int)ARRAYSIZE(extras); ++i)
        if (extras[i]) ShowWindow(extras[i], SW_SHOW);

    // Keep the original combobox alive and fully populated. All peer switches
    // still run the original CBN_SELCHANGE path through it.
    ShowWindow(hComboBoxChats, SW_HIDE);
    MoveWindow(hComboBoxFolders, 8, 80, left-15, 260, TRUE);
    MoveWindow(concept98_filter, 8, 111, left-15, 24, TRUE);
    MoveWindow(concept98_list_caption, 9, 141, left-20, 19, TRUE);
    MoveWindow(concept98_list, 8, 160, left-15, h-190, TRUE);

    MoveWindow(concept98_caption, 8, 7, 235, 27, TRUE);
    MoveWindow(concept98_chat_title, content_x, 81, content_w - 310, 25, TRUE);
    MoveWindow(concept98_chat_detail, content_x, 110, content_w - 310, 19, TRUE);
    MoveWindow(concept98_rule, content_x, 137, content_w, 2, TRUE);

    int actions_x = content_x + content_w - 310;
    MoveWindow(concept98_search_button, actions_x, 86, 98, 29, TRUE);
    MoveWindow(concept98_profile_button, actions_x+101, 86, 98, 29, TRUE);
    MoveWindow(concept98_more_button, actions_x+202, 86, 102, 29, TRUE);

    // Existing functional top-bar search controls are retained. They can open
    // server search, message search, media archive, and navigation.
    if (hChatSearch)
        MoveWindow(hChatSearch, content_x, 11, 160, 25, TRUE);
    if (hMessageSearch)
        MoveWindow(hMessageSearch, content_x+170, 40, 160, 24, TRUE);

    bool cantwrite =
        current_peer && !current_peer->perm.cansendmsg;
    int chat_bottom =
        cantwrite ? h - 34 : h - 126 + edits_border_offset;
    int chat_height = chat_bottom - 143;
    if (chat_height < 1) chat_height = 1;

    MoveWindow(chat, content_x, 143, content_w, chat_height, TRUE);
    MoveWindow(msgInput, content_x, h - 95 + edits_border_offset,
               content_w, 65 - edits_border_offset, TRUE);
    MoveWindow(hToolbar, content_x, h-(ie3 ? 120 : 124)+edits_border_offset,
               content_w, 25, TRUE);
    MoveWindow(splitter, content_x, h-124+edits_border_offset,
               content_w, 3, TRUE);
    if (tbSeparatorHider)
        MoveWindow(tbSeparatorHider, content_x+content_w/2,
                   h-118+edits_border_offset, 35, 21, TRUE);

    // Do not alter the emoji popup's owner or input/toolbar command handlers.
    MoveWindow(hTabs, w-224, h-334+edits_border_offset, 214, 214, TRUE);
    MoveWindow(hOverlayTabs, w-224, h-334+edits_border_offset, 214, 214, TRUE);

    int status_parts[2] = {left, -1};
    SendMessageW(hStatus, SB_SETPARTS, 2, (LPARAM)status_parts);
}

static bool concept98_draw_row(
    const DRAWITEMSTRUCT* dis
) {
    if (!dis || dis->CtlID != CONCEPT98_LIST_ID)
        return false;
    if (dis->itemID == (UINT)-1 ||
        dis->itemID >= concept98_folder_indices.size() ||
        !current_folder || !peers)
        return true;

    int slot = concept98_folder_indices[dis->itemID];
    if (slot < 0 || slot >= current_folder->count)
        return true;
    int id = current_folder->peers[slot];
    if (id < 0 || id >= peers_count)
        return true;

    Peer* peer = &peers[id];
    HDC dc = dis->hDC;
    RECT rc = dis->rcItem;
    bool selected = (dis->itemState & ODS_SELECTED) != 0;

    COLORREF back =
        selected ? GetSysColor(COLOR_HIGHLIGHT) : GetSysColor(COLOR_WINDOW);
    COLORREF foreground =
        selected ? GetSysColor(COLOR_HIGHLIGHTTEXT) : GetSysColor(COLOR_WINDOWTEXT);

    HBRUSH background = CreateSolidBrush(back);
    FillRect(dc, &rc, background);
    DeleteObject(background);

    // Small inset colored contact tile instead of enlarged/scaled photos.
    RECT avatar = {rc.left+5, rc.top+8, rc.left+34, rc.top+37};
    COLORREF tile =
        peer->type == 2 ? RGB(72,97,133) :
        peer->type == 1 ? RGB(92,110,87) :
        RGB(120,102,117);
    HBRUSH avatar_brush = CreateSolidBrush(tile);
    FillRect(dc, &avatar, avatar_brush);
    DeleteObject(avatar_brush);
    DrawEdge(dc, &avatar, EDGE_SUNKEN, BF_RECT);

    wchar_t initial[2] = {
        peer->name && peer->name[0] ? peer->name[0] : L'?',
        0
    };
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(255,255,255));
    HFONT old_font = (HFONT)SelectObject(dc, hFonts[2]);
    DrawTextW(dc, initial, -1, &avatar,
              DT_SINGLELINE | DT_CENTER | DT_VCENTER);

    SetTextColor(dc, foreground);
    RECT name = {rc.left+43, rc.top+5, rc.right-32, rc.top+25};
    if (peer->name)
        DrawTextW(dc, peer->name, -1, &name,
                  DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);

    RECT detail = {rc.left+43, rc.top+26, rc.right-6, rc.bottom-3};
    const wchar_t* detail_text =
        peer->type == 2 ? L"\x041a\x0430\x043d\x0430\x043b" :
        peer->type == 1 ? L"\x0413\x0440\x0443\x043f\x043f\x0430" :
        L"\x041b\x0438\x0447\x043d\x044b\x0439 \x0447\x0430\x0442";
    SetTextColor(dc, selected ? foreground : GetSysColor(COLOR_GRAYTEXT));
    DrawTextW(dc, detail_text, -1, &detail, DT_SINGLELINE | DT_END_ELLIPSIS);

    if (peer->unread_msgs_count > 0) {
        wchar_t unread[16] = {0};
        _snwprintf_s(unread, ARRAYSIZE(unread), _TRUNCATE,
                     L"%d", peer->unread_msgs_count);
        RECT badge = {rc.right-36, rc.top+12, rc.right-6, rc.top+32};
        HBRUSH red = CreateSolidBrush(RGB(141,43,65));
        FillRect(dc, &badge, red);
        DeleteObject(red);
        SetTextColor(dc, RGB(255,255,255));
        DrawTextW(dc, unread, -1, &badge,
                  DT_SINGLELINE | DT_CENTER | DT_VCENTER);
    }

    SelectObject(dc, old_font);

    if (dis->itemState & ODS_FOCUS)
        DrawFocusRect(dc, &rc);
    return true;
}

static void concept98_create_controls(HWND hwnd) {
    const DWORD panel = WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS;
    concept98_caption = CreateWindowW(
        L"STATIC", L"Telegram 98 / Telegacy", panel | SS_LEFT,
        8,7,235,27,hwnd,NULL,NULL,NULL);
    concept98_filter = CreateWindowExW(
        WS_EX_CLIENTEDGE, L"EDIT", L"", panel | ES_AUTOHSCROLL,
        8,111,220,24,hwnd,(HMENU)8911,NULL,NULL);
    SendMessageW(concept98_filter, 0x1501, TRUE,
                 (LPARAM)L"\x041f\x043e\x0438\x0441\x043a \x043f\x043e \x0447\x0430\x0442\x0430\x043c...");
    concept98_list_caption = CreateWindowW(
        L"STATIC", L"\x0427\x0430\x0442\x044b", panel,
        9,141,210,19,hwnd,NULL,NULL,NULL);
    concept98_list = CreateWindowExW(
        WS_EX_CLIENTEDGE, L"LISTBOX", L"",
        panel | WS_VSCROLL | LBS_NODATA | LBS_OWNERDRAWFIXED |
        LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
        8,160,220,320,hwnd,(HMENU)CONCEPT98_LIST_ID,NULL,NULL);
    SendMessageW(concept98_list, LB_SETITEMHEIGHT, 0, 47);

    concept98_chat_title = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT,
        250,81,200,25,hwnd,NULL,NULL,NULL);
    concept98_chat_detail = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT,
        250,110,200,19,hwnd,NULL,NULL,NULL);
    concept98_rule = CreateWindowW(
        L"STATIC", L"", panel | SS_ETCHEDHORZ,
        250,137,300,2,hwnd,NULL,NULL,NULL);

    concept98_search_button = CreateWindowW(
        L"BUTTON", L"\x041f\x043e\x0438\x0441\x043a", panel | BS_PUSHBUTTON,
        0,0,98,29,hwnd,(HMENU)8912,NULL,NULL);
    concept98_profile_button = CreateWindowW(
        L"BUTTON", L"\x041f\x0440\x043e\x0444\x0438\x043b\x044c", panel | BS_PUSHBUTTON,
        0,0,98,29,hwnd,(HMENU)8913,NULL,NULL);
    concept98_more_button = CreateWindowW(
        L"BUTTON", L"\x0415\x0449\x0451...", panel | BS_PUSHBUTTON,
        0,0,102,29,hwnd,(HMENU)8914,NULL,NULL);

    HWND labels[] = {
        concept98_caption, concept98_filter, concept98_list_caption,
        concept98_chat_title, concept98_chat_detail,
        concept98_search_button, concept98_profile_button, concept98_more_button
    };
    for (int i=0;i<(int)ARRAYSIZE(labels);++i) {
        if (labels[i])
            SendMessageW(labels[i], WM_SETFONT, (WPARAM)hFonts[2], TRUE);
    }

    // The old menu is still fully functional. Add a reversible UI switch.
    HMENU tools = GetSubMenu(hMenuBar, 2);
    if (tools) {
        AppendMenuW(tools, MF_SEPARATOR, 0, NULL);
        AppendMenuW(
            tools,
            MF_STRING | (concept98_enabled ? MF_CHECKED : MF_UNCHECKED),
            8915,
            L"Telegram 98 \x2014 \x0432\x0438\x0434"
        );
        DrawMenuBar(hwnd);
    }

    SetTimer(hwnd, CONCEPT98_TIMER, 900, NULL);
    concept98_apply_layout(hwnd);
    concept98_sync();

    diag_log("concept98 v90 created enabled=%d", concept98_enabled ? 1 : 0);
}
'''

s = s.replace(wnd_signature, shell + "\n" + wnd_signature, 1)

# Persisted setting defaults ON for the concept branch. Increase launch dimensions
# only for the new variant; the user can disable it via Tools menu.
size_anchor = 'width = GetPrivateProfileInt(L"General", L"width", 500, get_path(appdata_path, L"options.ini"));'
size_insert = r'''
    concept98_enabled =
        GetPrivateProfileIntW(
            L"Concept98", L"enabled", 1, appdata_path
        ) != 0;
'''
s = replace_once(s, size_anchor, size_anchor + "\n" + size_insert, "concept setting")
height_anchor = 'height = GetPrivateProfileInt(L"General", L"height", 450, appdata_path);'
s = replace_once(
    s, height_anchor,
    height_anchor + r'''
    if (concept98_enabled) {
        if (width < 850) width = 850;
        if (height < 570) height = 570;
    }
''',
    "concept window size",
)

# Main message pump: the original UI keeps handling everything except explicit
# concept controls. Our list always forwards selection to the original CBN handler.
proc_start = wnd_signature
proc_hook = r'''
    if (msg == WM_TIMER && wParam == CONCEPT98_TIMER) {
        concept98_sync();
        return 0;
    }
    if (msg == WM_APP + 0x390) {
        concept98_sync();
        concept98_apply_layout(hWnd);
        return 0;
    }
    if (msg == WM_GETMINMAXINFO && concept98_enabled) {
        MINMAXINFO* sizes = (MINMAXINFO*)lParam;
        if (sizes) {
            sizes->ptMinTrackSize.x = 780;
            sizes->ptMinTrackSize.y = 510;
        }
        return 0;
    }
    if (msg == WM_COMMAND && concept98_list &&
        concept98_enabled) {
        int command = LOWORD(wParam);
        int notification = HIWORD(wParam);

        if (command == CONCEPT98_LIST_ID &&
            notification == LBN_SELCHANGE && !concept98_refreshing) {
            int idx = (int)SendMessageW(concept98_list, LB_GETCURSEL, 0, 0);
            if (idx >= 0 && idx < (int)concept98_folder_indices.size()) {
                int folder_idx = concept98_folder_indices[idx];
                SendMessageW(hComboBoxChats, CB_SETCURSEL, folder_idx, 0);
                SendMessageW(hWnd, WM_COMMAND,
                             MAKEWPARAM(3, CBN_SELCHANGE),
                             (LPARAM)hComboBoxChats);
                PostMessageW(hWnd, WM_APP + 0x390, 0, 0);
            }
            return 0;
        }
        if (command == 8911 && notification == EN_CHANGE) {
            concept98_sync();
            return 0;
        }
        if (command == 8912) {
            if (hMessageSearch) SetFocus(hMessageSearch);
            return 0;
        }
        if (command == 8913) {
            if (current_peer)
                SendMessageW(hWnd, WM_COMMAND, MAKEWPARAM(31, 0), 0);
            return 0;
        }
        if (command == 8914) {
            if (current_peer) {
                HMENU menu = GetSubMenu(hMenuBar, 1);
                RECT button = {0};
                GetWindowRect(concept98_more_button, &button);
                if (menu)
                    TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_TOPALIGN |
                                       TPM_RIGHTBUTTON,
                                   button.left, button.bottom, 0, hWnd, NULL);
            }
            return 0;
        }
    }
    if (msg == WM_COMMAND && LOWORD(wParam) == 8915) {
        concept98_enabled = !concept98_enabled;
        WritePrivateProfileStringW(
            L"Concept98", L"enabled",
            concept98_enabled ? L"1" : L"0",
            get_path(appdata_path, L"options.ini")
        );
        HMENU tools = GetSubMenu(hMenuBar, 2);
        if (tools)
            CheckMenuItem(tools, 8915,
                          MF_BYCOMMAND |
                          (concept98_enabled ? MF_CHECKED : MF_UNCHECKED));
        RECT bounds = {0};
        GetClientRect(hWnd, &bounds);
        SendMessageW(hWnd, WM_SIZE, SIZE_RESTORED,
                     MAKELPARAM(bounds.right, bounds.bottom));
        return 0;
    }
'''

s = replace_once(s, proc_start, proc_start + "\n" + proc_hook, "window event hook")

# Native left pane widgets are created only when the main chat/status controls
# already exist (avoids null hStatus/child references during early WM_SIZE).
status_anchor = 'if (nt3) SendMessage(hStatus, SB_SETMINHEIGHT, 18, 0);'
s = replace_once(
    s, status_anchor, status_anchor + "\n\t\tconcept98_create_controls(hWnd);",
    "create controls after status",
)

# A CBN_SELCHANGE event originates from the authoritative native combo. Its
# final UI state is mirrored asynchronously after the existing handler returns;
# no assumptions are made about the implementation of folder/peer replacement.
s = replace_once(
    s,
    '    if (msg == WM_COMMAND && concept98_list &&',
    '''    if (msg == WM_COMMAND &&
        (LOWORD(wParam) == 2 || LOWORD(wParam) == 3) &&
        HIWORD(wParam) == CBN_SELCHANGE) {
        PostMessageW(hWnd, WM_APP + 0x390, 0, 0);
    }
    if (msg == WM_COMMAND && concept98_list &&''',
    "authoritative combo selection events",
)

# Listbox owner drawing lives before the original combo/status owner drawing.
draw_anchor = 'case WM_DRAWITEM: {\n\t\tLPDRAWITEMSTRUCT lpdis = (LPDRAWITEMSTRUCT)lParam;'
s = replace_once(
    s, draw_anchor,
    'case WM_DRAWITEM: {\n'
    '\t\tLPDRAWITEMSTRUCT lpdis = (LPDRAWITEMSTRUCT)lParam;\n'
    '\t\tif (concept98_enabled && concept98_draw_row(lpdis)) return TRUE;',
    "owner draw",
)

# Original geometry is recalculated first, then reflowed into the two-pane view.
size_pos = s.find('case WM_SIZE:')
if size_pos < 0:
    raise SystemExit("WM_SIZE handler not found.")
pos = s.find("EndDeferWindowPos(hdwp);", size_pos)
if pos < 0:
    raise SystemExit("WM_SIZE DeferWindowPos terminator missing.")
s = s[:pos] + "EndDeferWindowPos(hdwp);\n\t\t\tconcept98_apply_layout(hWnd);" + s[pos+len("EndDeferWindowPos(hdwp);"):]

destroy_anchor = 'case WM_DESTROY:\n\t\tCoUninitialize();'
s = replace_once(
    s, destroy_anchor,
    'case WM_DESTROY:\n\t\tKillTimer(hWnd, CONCEPT98_TIMER);\n\t\tCoUninitialize();',
    "timer cleanup",
)

write(t, s)

# Concept-style native Windows-98 notifications, still routed through the
# existing Telegram notification peer identity/open-chat functions.
src = read(h)
notify_signature = "INT_PTR CALLBACK DlgProcNotification(HWND hDlg, UINT msg, WPARAM wParam, LPARAM lParam) {"
notify_injected = r'''
    if (concept98_enabled && msg == WM_INITDIALOG) {
        NOTIFYICONDATAV2* data = (NOTIFYICONDATAV2*)lParam;
        SetWindowTextW(hDlg, L"\x041d\x043e\x0432\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435 \x2014 Telegram 98");
        RECT work = {0};
        SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
        int x = work.right - 340;
        int y = work.bottom - 174;
        SetWindowPos(hDlg, HWND_TOPMOST, x, y, 328, 152,
                     SWP_SHOWWINDOW | SWP_NOACTIVATE);
        HWND title = CreateWindowW(
            L"STATIC", data ? data->szInfoTitle : L"Telegram",
            WS_VISIBLE | WS_CHILD | SS_LEFT,
            50, 12, 260, 22, hDlg, NULL, NULL, NULL);
        HWND body = CreateWindowW(
            L"STATIC", data ? data->szInfo : L"",
            WS_VISIBLE | WS_CHILD | SS_LEFT,
            50, 37, 260, 46, hDlg, NULL, NULL, NULL);
        HWND icon = CreateWindowW(
            L"STATIC", NULL,
            WS_VISIBLE | WS_CHILD | SS_ICON,
            12, 14, 32, 32, hDlg, NULL, NULL, NULL);
        SendMessageW(icon, STM_SETICON,
                     (WPARAM)LoadIconW(NULL, IDI_INFORMATION), 0);
        CreateWindowW(
            L"BUTTON", L"\x041e\x0442\x0432\x0435\x0442\x0438\x0442\x044c",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            50, 91, 114, 28, hDlg, (HMENU)1, NULL, NULL);
        CreateWindowW(
            L"BUTTON", L"\x041e\x0442\x043a\x0440\x044b\x0442\x044c \x0447\x0430\x0442",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            172, 91, 137, 28, hDlg, (HMENU)2, NULL, NULL);
        SendMessageW(title, WM_SETFONT, (WPARAM)hFonts[2], TRUE);
        SendMessageW(body, WM_SETFONT, (WPARAM)hFonts[2], TRUE);
        SetTimer(hDlg, 1, 10000, NULL);
        return TRUE;
    }
    if (concept98_enabled && msg == WM_COMMAND) {
        if (LOWORD(wParam) == 1 || LOWORD(wParam) == 2) {
            bool reply = LOWORD(wParam) == 1;
            click_on_notification();
            if (reply && msgInput && IsWindow(msgInput))
                SetFocus(msgInput);
            return TRUE;
        }
    }
    if (concept98_enabled && msg == WM_CLOSE) {
        remove_notification();
        return TRUE;
    }
'''
src = replace_once(
    src, notify_signature,
    notify_signature + "\n" + notify_injected,
    "native notification",
)
dialog_anchor = 'dlg->style = WS_POPUP | DS_MODALFRAME;'
src = replace_once(
    src, dialog_anchor,
    'dlg->style = concept98_enabled\n'
    '\t\t\t\t\t\t? (WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_MODALFRAME)\n'
    '\t\t\t\t\t\t: (WS_POPUP | DS_MODALFRAME);',
    "captioned concept popup",
)
src = replace_once(
    src, 'if (balloon_notifications) {\n\t\t\t\t\tnid.cbSize = sizeof(nid);',
    'if (balloon_notifications && !concept98_enabled) {\n'
    '\t\t\t\t\tnid.cbSize = sizeof(nid);',
    "native popup over balloon",
)
write(h, src)

# Make concept state visible to the notification renderer.
header = root / "include" / "telegacy.h"
s = read(header)
s = replace_once(
    s,
    "extern bool drawchat;",
    "extern bool drawchat;\nextern bool concept98_enabled; // concept98_shell_v90",
    "concept state declaration",
)
write(header, s)

for path, markers in {
    t: [
        "concept98_shell_v90",
        "concept98_draw_row",
        "concept98_sync",
        "concept98_apply_layout",
        "case WM_DRAWITEM",
        "LBN_SELCHANGE",
        "LBS_NODATA",
        "WM_APP + 0x390",
    ],
    h: [
        "if (concept98_enabled && msg == WM_INITDIALOG)",
        "if (balloon_notifications && !concept98_enabled)",
        "click_on_notification();",
    ],
    header: ["extern bool concept98_enabled;"],
}.items():
    data = read(path)
    for marker in markers:
        if marker not in data:
            raise SystemExit(f"Missing post-patch marker in {path.name}: {marker}")

print(
    "Applied Concept 98 v9.0: native Win9x-inspired permanent chat list, "
    "search/filter, two-pane responsive chat composer and actions, classic "
    "new-message dialog with Reply/Open, and a persistent reversible Tools "
    "menu switch; all original Telegram/network/media paths stay connected."
)
