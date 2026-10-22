#!/usr/bin/env python3
"""Concept 98 v9.1: coherent layout, real global search, stable rendering.

Runs immediately AFTER patch_concept98_shell_v90.py, without touching Telegram
network, RichEdit OLE identities, sticker overlays or storage.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_concept98_polish_v91.py <Telegacy source root>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
h = root / "src" / "helpers.cpp"

def read(p):
    return p.read_text(encoding="latin-1")

def write(p, data):
    p.write_text(data, encoding="latin-1", newline="\r\n")

def function_span(data, name):
    at = data.find(name)
    if at < 0:
        raise SystemExit("Concept 98 v9.1 function not found: " + name)
    start = data.find("{", at)
    if start < 0:
        raise SystemExit("Concept 98 v9.1 function opening brace missing: " + name)
    depth, quote, ch, line, block, escape = 0, False, False, False, False, False
    i = start
    while i < len(data):
        c = data[i]
        n = data[i+1] if i+1 < len(data) else ""
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
                return at, i+1
        i += 1
    raise SystemExit("Concept 98 v9.1 unclosed C++ function: " + name)

def replace_func(data, signature, new_body):
    a,b = function_span(data, signature)
    return data[:a] + new_body + data[b:]

def one(data, old, new, desc):
    if old not in data:
        raise SystemExit("Concept 98 v9.1 anchor missing: " + desc)
    return data.replace(old,new,1)

s = read(t)
if "concept98_polish_v91" in s:
    print("Concept 98 v9.1 already applied")
    raise SystemExit(0)

for token in (
    "concept98_shell_v90", "concept98_sync()",
    "global_chat_search_mode", "hChatScopeTabs",
    "hMessageSearchStatus", "hMediaArchiveButton",
    "chat_runtime_sticker_stability_v88"
):
    if token not in s:
        raise SystemExit("v9.1 dependency missing: " + token)

# A real shared sidebar: cached list for local peers and the ORIGINAL native
# combo for live global-search results. All items come from existing Telegram
# state; the visual layer does not fabricate result items.
sync_code = r'''static DWORD concept98_previous_badge_hash_v91 = 0;
static bool concept98_previous_global_v91 = false;
static int concept98_previous_public_count_v91 = -1;
static HFONT concept98_heading_font_v91 = NULL;
static HWND concept98_divider_v91 = NULL;
static HWND concept98_brand_icon_v91 = NULL;
static HWND concept98_sidebar_hint_v91 = NULL;
static bool concept98_last_writable_v91 = true;

static DWORD concept98_badge_hash_v91(
    const std::vector<int>& mapping
) {
    DWORD hash = 2166136261u;
    if (!current_folder || !peers) return hash;

    for (int i = 0; i < (int)mapping.size(); ++i) {
        int slot = mapping[i];
        if (slot < 0 || slot >= current_folder->count) continue;
        int index = current_folder->peers[slot];
        if (index < 0 || index >= peers_count) continue;

        const Peer* peer = &peers[index];
        hash = (hash ^ (DWORD)peer->unread_msgs_count) * 16777619u;
        hash = (hash ^ (DWORD)peer->type) * 16777619u;
        if (peer->name) {
            for (int j = 0; peer->name[j] && j < 64; ++j) {
                hash = (hash ^ (DWORD)peer->name[j]) * 16777619u;
            }
        }
    }
    return hash;
}

static void concept98_sync() {
    if (!concept98_enabled || !concept98_list || concept98_refreshing)
        return;

    concept98_refreshing = true;
    const bool global_mode = global_chat_search_mode;
    const bool changed_scope = global_mode != concept98_previous_global_v91;
    concept98_previous_global_v91 = global_mode;

    // Scope tab and real global-search results are intentionally independent
    // of the local Peer list. The global results are owned by Telegacy.
    if (changed_scope) {
        if (concept98_sidebar_hint_v91) {
            SetWindowTextW(
                concept98_sidebar_hint_v91,
                global_mode
                    ? L"\x041f\x043e\x0438\x0441\x043a \x043f\x043e Telegram"
                    : L"\x0412\x0430\x0448\x0438 \x043f\x0435\x0440\x0435\x043f\x0438\x0441\x043a\x0438"
            );
        }
        if (concept98_filter)
            ShowWindow(concept98_filter, global_mode ? SW_HIDE : SW_SHOW);
        if (hChatSearch)
            ShowWindow(hChatSearch, global_mode ? SW_SHOW : SW_HIDE);
        // Use one visible owner-draw list for local and global results;
        // the native combo still owns the authoritative selection.
        ShowWindow(concept98_list, SW_SHOW);
        ShowWindow(hComboBoxChats, SW_HIDE);
    }

    if (!global_mode) {
        wchar_t query[96] = {0};
        if (concept98_filter)
            GetWindowTextW(concept98_filter, query, ARRAYSIZE(query));

        std::vector<int> filtered;
        if (current_folder && current_folder->peers && peers) {
            for (int i = 0; i < current_folder->count; ++i) {
                int id = current_folder->peers[i];
                if (id < 0 || id >= peers_count) continue;
                if (concept98_match(peers[id].name, query))
                    filtered.push_back(i);
            }
        }

        bool mapping_changed =
            changed_scope ||
            current_folder != concept98_list_folder ||
            filtered != concept98_folder_indices ||
            wcscmp(query, concept98_previous_filter) != 0;

        if (mapping_changed) {
            int top = (int)SendMessageW(
                concept98_list, LB_GETTOPINDEX, 0, 0
            );
            concept98_folder_indices.swap(filtered);
            concept98_list_folder = current_folder;
            wcscpy_s(concept98_previous_filter, query);

            SendMessageW(concept98_list, WM_SETREDRAW, FALSE, 0);
            SendMessageW(
                concept98_list, LB_SETCOUNT,
                (WPARAM)concept98_folder_indices.size(), 0
            );
            if (!concept98_folder_indices.empty()) {
                int last = (int)concept98_folder_indices.size()-1;
                SendMessageW(concept98_list, LB_SETTOPINDEX,
                             top < last ? top : last, 0);
            }
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
        if ((int)SendMessageW(concept98_list, LB_GETCURSEL, 0, 0)
                != selected) {
            SendMessageW(concept98_list, LB_SETCURSEL, selected, 0);
            mapping_changed = true;
        }

        const DWORD hash = concept98_badge_hash_v91(
            concept98_folder_indices
        );
        if (hash != concept98_previous_badge_hash_v91 || mapping_changed) {
            concept98_previous_badge_hash_v91 = hash;
            InvalidateRect(concept98_list, NULL, FALSE);
        }

        if (concept98_list_caption) {
            wchar_t label[70] = {0};
            _snwprintf_s(
                label, ARRAYSIZE(label), _TRUNCATE,
                L"\x0427\x0430\x0442\x044b  (%u)",
                (unsigned int)concept98_folder_indices.size()
            );
            wchar_t previous[70] = {0};
            GetWindowTextW(concept98_list_caption, previous,
                           ARRAYSIZE(previous));
            if (wcscmp(previous, label) != 0)
                SetWindowTextW(concept98_list_caption, label);
        }
    } else {
        // Mirror COUNT and SELECTION from Telegram's native search combo,
        // without taking ownership of its result peers.
        int count = hComboBoxChats ?
            (int)SendMessageW(hComboBoxChats, CB_GETCOUNT, 0, 0) : 0;
        if (count < 0) count = 0;
        if (changed_scope || count != concept98_previous_public_count_v91) {
            concept98_previous_public_count_v91 = count;
            SendMessageW(concept98_list, LB_SETCOUNT, count, 0);
            InvalidateRect(concept98_list, NULL, FALSE);
        }
        int selected = hComboBoxChats ?
            (int)SendMessageW(hComboBoxChats, CB_GETCURSEL, 0, 0) : -1;
        if ((int)SendMessageW(concept98_list, LB_GETCURSEL, 0, 0)
              != selected)
            SendMessageW(concept98_list, LB_SETCURSEL, selected, 0);
        wchar_t label[70] = {0};
        _snwprintf_s(
            label, ARRAYSIZE(label), _TRUNCATE,
            L"\x0420\x0435\x0437\x0443\x043b\x044c\x0442\x0430\x0442\x044b  (%d)", count
        );
        if (concept98_list_caption) {
            wchar_t previous[70] = {0};
            GetWindowTextW(concept98_list_caption, previous,
                           ARRAYSIZE(previous));
            if (wcscmp(previous, label) != 0)
                SetWindowTextW(concept98_list_caption, label);
        }
    }

    if (current_peer && current_peer->name) {
        wchar_t oldname[256] = {0};
        GetWindowTextW(concept98_chat_title, oldname, ARRAYSIZE(oldname));
        if (wcscmp(oldname, current_peer->name) != 0)
            SetWindowTextW(concept98_chat_title, current_peer->name);

        const wchar_t* type =
            current_peer->type == 2
                ? L"\x041a\x0430\x043d\x0430\x043b" :
            current_peer->type == 1
                ? L"\x0413\x0440\x0443\x043f\x043f\x0430" :
                L"\x041b\x0438\x0447\x043d\x044b\x0439 \x0447\x0430\x0442";
        wchar_t oldtype[80] = {0};
        GetWindowTextW(concept98_chat_detail, oldtype, ARRAYSIZE(oldtype));
        if (wcscmp(oldtype, type) != 0)
            SetWindowTextW(concept98_chat_detail, type);
    } else {
        SetWindowTextW(concept98_chat_title,
                       L"\x0412\x044b\x0431\x0435\x0440\x0438\x0442\x0435 \x0447\x0430\x0442");
        SetWindowTextW(concept98_chat_detail, L"Telegram / Telegacy");
    }

    if (concept98_profile_button)
        EnableWindow(concept98_profile_button, current_peer != NULL);
    if (concept98_more_button)
        EnableWindow(concept98_more_button, current_peer != NULL);
    concept98_refreshing = false;
}
'''

s = replace_func(s, "static void concept98_sync()", sync_code)

# Resize only when coordinates change: moving RichEdit during async OLE
# replacement causes a scroll jump and an unnecessary sticker overlay reflow.
layout_code = r'''// concept98_polish_v91 - fixed Win9x layout, no empty 170px top band.
static void concept98_move_v91(
    HWND control, int x, int y, int w, int h
) {
    if (!control || !IsWindow(control)) return;
    if (w < 1) w = 1;
    if (h < 1) h = 1;

    RECT old = {0};
    GetWindowRect(control, &old);
    HWND parent = GetParent(control);
    if (parent) {
        POINT a = {old.left, old.top};
        POINT b = {old.right, old.bottom};
        ScreenToClient(parent, &a);
        ScreenToClient(parent, &b);
        if (a.x == x && a.y == y &&
            (b.x - a.x) == w && (b.y - a.y) == h)
            return;
    }
    MoveWindow(control, x, y, w, h, TRUE);
}

static void concept98_apply_layout(HWND hwnd) {
    if (!concept98_list || !IsWindow(concept98_list)) return;

    HWND extras[] = {
        concept98_list, concept98_filter, concept98_caption,
        concept98_chat_title, concept98_chat_detail,
        concept98_list_caption, concept98_rule,
        concept98_search_button, concept98_profile_button,
        concept98_more_button, concept98_divider_v91,
        concept98_brand_icon_v91, concept98_sidebar_hint_v91
    };

    if (!concept98_enabled) {
        for (int i=0;i<(int)ARRAYSIZE(extras);++i)
            if (extras[i]) ShowWindow(extras[i], SW_HIDE);

        if (hChatScopeTabs) {
            concept98_move_v91(hChatScopeTabs, 10, 7, 180, 29);
            ShowWindow(hChatScopeTabs, SW_SHOW);
        }
        ShowWindow(hComboBoxFolders, SW_SHOW);
        ShowWindow(hComboBoxChats, SW_SHOW);
        ShowWindow(hChatSearch, SW_SHOW);
        concept98_move_v91(hComboBoxFolders, 195, 10, 115, 300);
        concept98_move_v91(hChatSearch, 315, 10, 150, 22);
        concept98_move_v91(hComboBoxChats, 470, 10, 260, 300);
        return;
    }

    RECT rc = {0};
    GetClientRect(hwnd, &rc);
    int w = rc.right - rc.left;
    int h = rc.bottom - rc.top;

    // At 900px the sidebar is 238px; wide windows get up to 315px.
    int left = w/4;
    if (left < 238) left = 238;
    if (left > 315) left = 315;
    const int inset = 8;
    const int content_x = left + inset;
    int content_w = w - content_x - inset;
    if (content_w < 400) content_w = 400;

    for (int i=0;i<(int)ARRAYSIZE(extras);++i)
        if (extras[i]) ShowWindow(extras[i], SW_SHOW);

    const bool global_mode = global_chat_search_mode;
    // Scope tabs and folder picker now belong to the sidebar.
    concept98_move_v91(hChatScopeTabs, 7, 7, left-14, 28);
    concept98_move_v91(hComboBoxFolders, 7, 43, left-14, 250);
    concept98_move_v91(concept98_brand_icon_v91, 7, 75, 18, 18);
    concept98_move_v91(concept98_sidebar_hint_v91, 29, 75,
                       left-35, 20);
    concept98_move_v91(hChatSearch, 7, 100, left-14, 24);
    concept98_move_v91(concept98_filter, 7, 100, left-14, 24);
    concept98_move_v91(concept98_list_caption, 10, 133,
                       left-20, 20);
    concept98_move_v91(concept98_list, 7, 156, left-14,
                       h-165);
    concept98_move_v91(hComboBoxChats, 7, 156, left-14,
                       h-165);
    concept98_move_v91(concept98_divider_v91, left-1, 0,
                       2, h-1);
    // A public Telegram result must never be hidden behind our local list.
    ShowWindow(concept98_filter, global_mode ? SW_HIDE : SW_SHOW);
    ShowWindow(hChatSearch, global_mode ? SW_SHOW : SW_HIDE);
    ShowWindow(concept98_list, SW_SHOW);
    ShowWindow(hComboBoxChats, SW_HIDE);

    // Main conversation header: identity + native actions.
    const int header_top = 7;
    const int button_width = 88;
    const int gap = 4;
    const int action_area = button_width*3 + gap*2;
    const int action_x = content_x + content_w - action_area;
    int title_w = action_x - content_x - 12;
    if (title_w < 110) title_w = 110;

    concept98_move_v91(concept98_caption, content_x, 8,
                       title_w, 20);
    concept98_move_v91(concept98_chat_title, content_x, 30,
                       title_w, 26);
    concept98_move_v91(concept98_chat_detail, content_x, 57,
                       title_w, 17);
    concept98_move_v91(concept98_search_button,
                       action_x, header_top+23, button_width, 27);
    concept98_move_v91(concept98_profile_button,
                       action_x+button_width+gap,
                       header_top+23, button_width, 27);
    concept98_move_v91(concept98_more_button,
                       action_x+(button_width+gap)*2,
                       header_top+23, button_width, 27);

    // Message search toolbar (fully live): preserve prev/next/status/Media.
    int media_width = 86;
    int nav_width = 27;
    int nav_x = content_x + content_w - media_width - gap - nav_width*2 - gap;
    int search_w = nav_x - content_x - 12;
    if (search_w > 270) search_w = 270;
    if (search_w < 95) search_w = 95;

    concept98_move_v91(hMessageSearch, content_x, 82,
                       search_w, 24);
    concept98_move_v91(hMessageSearchPrev, nav_x, 82,
                       nav_width, 24);
    concept98_move_v91(hMessageSearchNext, nav_x+nav_width+1,
                       82, nav_width, 24);
    concept98_move_v91(hMediaArchiveButton,
                       content_x+content_w-media_width, 82,
                       media_width, 24);
    if (hMessageSearchStatus) {
        int status_x = content_x + search_w + 8;
        int status_w = nav_x - status_x - 4;
        if (status_w < 1) status_w = 1;
        concept98_move_v91(hMessageSearchStatus,
                           status_x, 85, status_w, 20);
    }

    concept98_move_v91(concept98_rule, content_x, 112,
                       content_w, 2);
    const int chat_y = 117;
    const bool cantwrite =
        current_peer && !current_peer->perm.cansendmsg;

    // The regular Telegacy editor stays at its original bottom coordinates.
    const int bottom = cantwrite ?
        h-28 : h-124+edits_border_offset;

    concept98_move_v91(
        chat, content_x, chat_y, content_w,
        bottom-chat_y
    );
    concept98_move_v91(
        hToolbar, content_x,
        h-(ie3 ? 120 : 124)+edits_border_offset,
        content_w, 25
    );
    concept98_move_v91(
        splitter, content_x,
        h-124+edits_border_offset, content_w, 3
    );
    concept98_move_v91(
        msgInput, content_x,
        h-95+edits_border_offset,
        content_w, 65-edits_border_offset
    );
    concept98_move_v91(
        tbSeparatorHider,
        content_x+(content_w/2),
        h-118+edits_border_offset, 35, 21
    );
    concept98_move_v91(
        hTabs, w-224, h-334+edits_border_offset, 214, 214
    );
    concept98_move_v91(
        hOverlayTabs, w-224, h-334+edits_border_offset, 214, 214
    );

    int status_parts[2] = {left, -1};
    SendMessageW(hStatus, SB_SETPARTS, 2, (LPARAM)status_parts);
    concept98_last_writable_v91 = !cantwrite;
}'''

s = replace_func(s, "static void concept98_apply_layout(HWND hwnd)", layout_code)

# Visual coherence: proper system colors, 50px rows, no white text strips.
row_code = r'''static bool concept98_draw_row(
    const DRAWITEMSTRUCT* dis
) {
    if (!dis || dis->CtlID != CONCEPT98_LIST_ID)
        return false;
    if (dis->itemID == (UINT)-1) return true;
    Peer* peer = NULL;
    if (global_chat_search_mode) {
        // Telegacy retains peer ownership, we look up by result slot.
        int count = (int)SendMessageW(
            hComboBoxChats, CB_GETCOUNT, 0, 0
        );
        if (count < 0 || dis->itemID >= (UINT)count) return true;
        LRESULT item = SendMessageW(
            hComboBoxChats, CB_GETITEMDATA, dis->itemID, 0
        );
        if (item == CB_ERR || item == 0) return true;
        peer = (Peer*)item;
    } else {
        if (dis->itemID >= concept98_folder_indices.size() ||
            !current_folder || !peers) return true;
        int slot = concept98_folder_indices[dis->itemID];
        if (slot < 0 || slot >= current_folder->count) return true;
        int id = current_folder->peers[slot];
        if (id < 0 || id >= peers_count) return true;
        peer = &peers[id];
    }

    RECT rc = dis->rcItem;
    HDC dc = dis->hDC;
    bool selected = (dis->itemState & ODS_SELECTED) != 0;

    COLORREF background = selected ?
        GetSysColor(COLOR_HIGHLIGHT) : GetSysColor(COLOR_WINDOW);
    COLORREF textcolor = selected ?
        GetSysColor(COLOR_HIGHLIGHTTEXT) :
        GetSysColor(COLOR_WINDOWTEXT);

    HBRUSH fill = CreateSolidBrush(background);
    FillRect(dc, &rc, fill);
    DeleteObject(fill);

    const int tile = 32;
    RECT avatar = {
        rc.left+7, rc.top+8,
        rc.left+7+tile, rc.top+8+tile
    };
    COLORREF category_color =
        peer->type == 2 ? RGB(74, 102, 142) :
        peer->type == 1 ? RGB(92, 116, 93) :
        RGB(111, 96, 117);
    HBRUSH tile_brush = CreateSolidBrush(category_color);
    FillRect(dc, &avatar, tile_brush);
    DeleteObject(tile_brush);
    DrawEdge(dc, &avatar, EDGE_SUNKEN, BF_RECT);

    HFONT oldfont = (HFONT)SelectObject(dc, hFonts[2]);
    int oldmode = SetBkMode(dc, TRANSPARENT);
    COLORREF oldcolor = SetTextColor(dc, RGB(255,255,255));
    wchar_t initials[2] = {
        peer->name && peer->name[0] ?
            (wchar_t)towupper(peer->name[0]) : L'?',
        0
    };
    DrawTextW(dc, initials, -1, &avatar,
              DT_SINGLELINE | DT_CENTER | DT_VCENTER);

    const bool unread = peer->unread_msgs_count > 0;
    RECT name = {
        rc.left+49, rc.top+6, rc.right-(unread ? 45 : 8),
        rc.top+26
    };
    SetTextColor(dc, textcolor);
    if (peer->name)
        DrawTextW(dc, peer->name, -1, &name,
                  DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);

    const wchar_t* subtitle =
        peer->type == 2 ? L"\x041a\x0430\x043d\x0430\x043b" :
        peer->type == 1 ? L"\x0413\x0440\x0443\x043f\x043f\x0430" :
        L"\x041b\x0438\x0447\x043d\x044b\x0439 \x0447\x0430\x0442";
    RECT detail = {
        rc.left+49, rc.top+27, rc.right-6, rc.top+47
    };
    SetTextColor(
        dc, selected ? textcolor : GetSysColor(COLOR_GRAYTEXT)
    );
    DrawTextW(dc, subtitle, -1, &detail,
              DT_SINGLELINE | DT_END_ELLIPSIS | DT_VCENTER);

    if (unread) {
        wchar_t count[12] = {0};
        if (peer->unread_msgs_count >= 10000)
            wcscpy_s(count, L"9999+");
        else
            _snwprintf_s(
                count, ARRAYSIZE(count), _TRUNCATE,
                L"%d", peer->unread_msgs_count
            );

        RECT badge = {rc.right-45, rc.top+16,
                      rc.right-6, rc.top+34};
        HBRUSH brush = CreateSolidBrush(
            selected ? RGB(52, 70, 117) : RGB(138, 52, 72)
        );
        FillRect(dc, &badge, brush);
        DeleteObject(brush);
        SetTextColor(dc, RGB(255,255,255));
        DrawTextW(dc, count, -1, &badge,
                  DT_SINGLELINE | DT_CENTER | DT_VCENTER);
    }

    SelectObject(dc, oldfont);
    SetBkMode(dc, oldmode);
    SetTextColor(dc, oldcolor);

    if (!selected) {
        HPEN pen = CreatePen(PS_SOLID, 1, GetSysColor(COLOR_3DLIGHT));
        HPEN prev = (HPEN)SelectObject(dc, pen);
        MoveToEx(dc, rc.left+49, rc.bottom-1, NULL);
        LineTo(dc, rc.right-2, rc.bottom-1);
        SelectObject(dc, prev);
        DeleteObject(pen);
    }
    if (dis->itemState & ODS_FOCUS)
        DrawFocusRect(dc, &rc);
    return true;
}'''

s = replace_func(s, "static bool concept98_draw_row(", row_code)

s = one(s, "            if (idx >= 0 && idx < (int)concept98_folder_indices.size()) {\n                int folder_idx = concept98_folder_indices[idx];\n                SendMessageW(hComboBoxChats, CB_SETCURSEL, folder_idx, 0);", "            int combo_idx = -1;\n            if (global_chat_search_mode) {\n                int count = (int)SendMessageW(\n                    hComboBoxChats, CB_GETCOUNT, 0, 0\n                );\n                if (idx >= 0 && idx < count) combo_idx = idx;\n            } else if (idx >= 0 &&\n                       idx < (int)concept98_folder_indices.size()) {\n                combo_idx = concept98_folder_indices[idx];\n            }\n            if (combo_idx >= 0) {\n                SendMessageW(hComboBoxChats, CB_SETCURSEL, combo_idx, 0);", "global search listbox routing")

# Existing controls are preserved and styled, with no duplicate chat search
# that masquerades as the global Telegram server-search engine.
create_code = r'''static void concept98_create_controls(HWND hwnd) {
    const DWORD panel =
        WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS;

    LOGFONTW font_info = {0};
    if (hFonts[2] &&
        GetObjectW(hFonts[2], sizeof(font_info), &font_info)) {
        font_info.lfWeight = FW_BOLD;
        if (font_info.lfHeight > -17)
            font_info.lfHeight = -17;
        concept98_heading_font_v91 = CreateFontIndirectW(&font_info);
    }

    concept98_caption = CreateWindowW(
        L"STATIC", L"TELEGACY  /  TELEGRAM 98",
        panel | SS_LEFT,
        250,8,270,20,hwnd,NULL,NULL,NULL
    );
    concept98_chat_title = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT | SS_ENDELLIPSIS,
        250,30,220,26,hwnd,NULL,NULL,NULL
    );
    concept98_chat_detail = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT,
        250,57,220,17,hwnd,NULL,NULL,NULL
    );
    concept98_rule = CreateWindowW(
        L"STATIC", L"", panel | SS_ETCHEDHORZ,
        250,112,300,2,hwnd,NULL,NULL,NULL
    );

    concept98_sidebar_hint_v91 = CreateWindowW(
        L"STATIC",
        L"\x0412\x0430\x0448\x0438 \x043f\x0435\x0440\x0435\x043f\x0438\x0441\x043a\x0438",
        panel | SS_LEFT,
        29,75,190,20,hwnd,NULL,NULL,NULL
    );
    concept98_brand_icon_v91 = CreateWindowW(
        L"STATIC", NULL, panel | SS_ICON,
        7,75,18,18,hwnd,NULL,NULL,NULL
    );
    SendMessageW(
        concept98_brand_icon_v91, STM_SETICON,
        (WPARAM)LoadIconW(
            GetModuleHandleW(NULL), MAKEINTRESOURCEW(IDI_ICON)
        ), 0
    );
    concept98_list_caption = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT,
        10,133,210,20,hwnd,NULL,NULL,NULL
    );
    concept98_divider_v91 = CreateWindowW(
        L"STATIC", L"", panel | SS_ETCHEDVERT,
        238,0,2,600,hwnd,NULL,NULL,NULL
    );

    concept98_filter = CreateWindowExW(
        WS_EX_CLIENTEDGE, L"EDIT", L"",
        panel | ES_AUTOHSCROLL,
        7,100,225,24,hwnd,(HMENU)8911,NULL,NULL
    );
    SendMessageW(
        concept98_filter, 0x1501, TRUE,
        (LPARAM)L"\x0424\x0438\x043b\x044c\x0442\x0440 \x0447\x0430\x0442\x043e\x0432..."
    );
    concept98_list = CreateWindowExW(
        WS_EX_CLIENTEDGE, L"LISTBOX", L"",
        panel | WS_VSCROLL | LBS_NODATA | LBS_OWNERDRAWFIXED |
        LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
        7,156,225,400,hwnd,(HMENU)CONCEPT98_LIST_ID,
        NULL,NULL
    );
    SendMessageW(concept98_list, LB_SETITEMHEIGHT, 0, 50);

    concept98_search_button = CreateWindowW(
        L"BUTTON", L"\x041f\x043e\x0438\x0441\x043a",
        panel | BS_PUSHBUTTON, 0,0,88,27,hwnd,
        (HMENU)8912,NULL,NULL
    );
    concept98_profile_button = CreateWindowW(
        L"BUTTON", L"\x041f\x0440\x043e\x0444\x0438\x043b\x044c",
        panel | BS_PUSHBUTTON, 0,0,88,27,hwnd,
        (HMENU)8913,NULL,NULL
    );
    concept98_more_button = CreateWindowW(
        L"BUTTON", L"\x0415\x0449\x0451...",
        panel | BS_PUSHBUTTON, 0,0,88,27,hwnd,
        (HMENU)8914,NULL,NULL
    );

    HWND labels[] = {
        concept98_caption, concept98_filter,
        concept98_list_caption, concept98_sidebar_hint_v91,
        concept98_chat_title, concept98_chat_detail,
        concept98_search_button, concept98_profile_button,
        concept98_more_button, concept98_list
    };
    for (int i=0;i<(int)ARRAYSIZE(labels);++i)
        if (labels[i])
            SendMessageW(
                labels[i], WM_SETFONT, (WPARAM)hFonts[2], TRUE
            );

    if (concept98_heading_font_v91) {
        SendMessageW(
            concept98_chat_title, WM_SETFONT,
            (WPARAM)concept98_heading_font_v91, TRUE
        );
    }

    HMENU tools = GetSubMenu(hMenuBar, 2);
    if (tools) {
        AppendMenuW(tools, MF_SEPARATOR, 0, NULL);
        AppendMenuW(
            tools,
            MF_STRING | (concept98_enabled ? MF_CHECKED : MF_UNCHECKED),
            8915, L"Telegram 98 \x2014 \x0432\x0438\x0434"
        );
        DrawMenuBar(hwnd);
    }

    SetTimer(hwnd, CONCEPT98_TIMER, 1800, NULL);
    concept98_apply_layout(hwnd);
    concept98_sync();
    diag_log("concept98 v91 created split-pane classic shell");
}'''

s = replace_func(s, "static void concept98_create_controls(HWND hwnd)", create_code)

# Never reflow the OLE/RichEdit viewport on every refresh/status tick:
# reflow only for resize, chat writable-state change or actual scope switch.
s = one(
    s,
    '    if (msg == WM_APP + 0x390) {\n        concept98_sync();\n        concept98_apply_layout(hWnd);\n        return 0;\n    }',
    '''    if (msg == WM_APP + 0x390) {
        bool scope_before = concept98_previous_global_v91;
        bool was_writable = concept98_last_writable_v91;
        concept98_sync();
        bool writable = !(current_peer && !current_peer->perm.cansendmsg);
        if (concept98_enabled &&
            (scope_before != concept98_previous_global_v91 ||
             writable != was_writable))
            concept98_apply_layout(hWnd);
        return 0;
    }''',
    "avoid chat reflow for simple sync",
)
s = one(
    s,
    '    if (msg == WM_TIMER && wParam == CONCEPT98_TIMER) {\n        concept98_sync();\n        return 0;\n    }',
    '''    if (msg == WM_TIMER && wParam == CONCEPT98_TIMER) {
        bool scope_before = concept98_previous_global_v91;
        concept98_sync();
        if (concept98_enabled &&
            scope_before != concept98_previous_global_v91)
            concept98_apply_layout(hWnd);
        return 0;
    }''',
    "avoid timer RichEdit invalidation",
)

# Win9x header labels must use palette-matched backgrounds, not the Telegram
# theme's chat paper brush (which produced white strips in the screenshot).
proc_anchor = '    if (msg == WM_GETMINMAXINFO && concept98_enabled) {'
s = one(
    s, proc_anchor,
    '''    if (msg == WM_CTLCOLORSTATIC && concept98_enabled) {
        HWND control = (HWND)lParam;
        if (control == concept98_chat_title ||
            control == concept98_chat_detail ||
            control == concept98_caption ||
            control == concept98_list_caption ||
            control == concept98_sidebar_hint_v91) {
            HDC dc = (HDC)wParam;
            SetTextColor(dc, GetSysColor(COLOR_BTNTEXT));
            SetBkColor(dc, GetSysColor(COLOR_BTNFACE));
            return (LRESULT)GetSysColorBrush(COLOR_BTNFACE);
        }
    }
''' + proc_anchor,
    "palette matched static text",
)

# Make the menu toggle restore both old controls and old geometry. The stock
# resize event repositions every legacy control before applying our layout.
destroy = 'case WM_DESTROY:\n\t\tKillTimer(hWnd, CONCEPT98_TIMER);\n\t\tCoUninitialize();'
s = one(
    s,destroy,
    'case WM_DESTROY:\n\t\tKillTimer(hWnd, CONCEPT98_TIMER);\n'
    '\t\tif (concept98_heading_font_v91) {\n'
    '\t\t\tDeleteObject(concept98_heading_font_v91);\n'
    '\t\t\tconcept98_heading_font_v91 = NULL;\n'
    '\t\t}\n\t\tCoUninitialize();',
    "heading font cleanup",
)

write(t,s)

# Notification: correct contrast, separate dark text from system-grey backdrop,
# typography at readable size, properly sized message area and buttons.
src = read(h)
start = src.find('    if (concept98_enabled && msg == WM_INITDIALOG) {')
end = src.find('    if (concept98_enabled && msg == WM_COMMAND)',start)
if start < 0 or end < 0:
    raise SystemExit("v9.1 notification override anchor missing")

notification = r'''    // concept98_polish_v91 - native Win9x popup with readable controls.
    if (concept98_enabled &&
        (msg == WM_CTLCOLORDLG || msg == WM_CTLCOLORSTATIC)) {
        HDC dc = (HDC)wParam;
        if (dc) {
            SetTextColor(dc, GetSysColor(COLOR_WINDOWTEXT));
            SetBkColor(dc, GetSysColor(COLOR_BTNFACE));
        }
        return (INT_PTR)GetSysColorBrush(COLOR_BTNFACE);
    }
    if (concept98_enabled && msg == WM_INITDIALOG) {
        NOTIFYICONDATAV2* data = (NOTIFYICONDATAV2*)lParam;
        SetWindowTextW(
            hDlg,
            L"\x041d\x043e\x0432\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435 \x2014 Telegacy"
        );

        RECT work = {0};
        SystemParametersInfoW(SPI_GETWORKAREA, 0, &work, 0);
        const int w = 390;
        const int h = 182;
        int x = work.right - w - 12;
        int y = work.bottom - h - 12;

        SetWindowPos(
            hDlg, HWND_TOPMOST, x, y, w, h,
            SWP_SHOWWINDOW | SWP_NOACTIVATE
        );

        HWND title = CreateWindowW(
            L"STATIC", data ? data->szInfoTitle : L"Telegram",
            WS_VISIBLE | WS_CHILD | SS_LEFT | SS_ENDELLIPSIS,
            54, 14, 310, 24, hDlg, NULL, NULL, NULL
        );

        HWND body = CreateWindowW(
            L"STATIC", data ? data->szInfo : L"",
            WS_VISIBLE | WS_CHILD | SS_LEFT,
            54, 40, 305, 69, hDlg, NULL, NULL, NULL
        );

        HWND icon = CreateWindowW(
            L"STATIC", NULL, WS_VISIBLE | WS_CHILD | SS_ICON,
            13, 15, 34, 34, hDlg, NULL, NULL, NULL
        );
        SendMessageW(
            icon, STM_SETICON,
            (WPARAM)LoadIconW(NULL, IDI_INFORMATION), 0
        );

        HWND button_reply = CreateWindowW(
            L"BUTTON", L"\x041e\x0442\x0432\x0435\x0442\x0438\x0442\x044c",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            54, 117, 139, 28, hDlg, (HMENU)1, NULL, NULL
        );
        HWND button_open = CreateWindowW(
            L"BUTTON", L"\x041e\x0442\x043a\x0440\x044b\x0442\x044c \x0447\x0430\x0442",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            200, 117, 158, 28, hDlg, (HMENU)2, NULL, NULL
        );

        HWND text_controls[] = {
            title, body, button_reply, button_open
        };
        for (int i = 0; i < (int)ARRAYSIZE(text_controls); ++i)
            if (text_controls[i])
                SendMessageW(
                    text_controls[i], WM_SETFONT,
                    (WPARAM)hFonts[2], TRUE
                );

        SetTimer(hDlg, 1, 12000, NULL);
        diag_log("concept98 v91 new-message popup displayed");
        return TRUE;
    }
'''
src = src[:start]+notification+src[end:]
write(h,src)

for p, needles in {
    t: [
        "concept98_polish_v91",
        "concept98_previous_global_v91",
        "concept98_badge_hash_v91",
        "concept98_move_v91",
        "global_chat_search_mode",
        "hMessageSearchPrev", "hMessageSearchNext",
        "hMediaArchiveButton",
        "concept98_sidebar_hint_v91",
        "concept98_heading_font_v91"
    ],
    h: [
        "concept98_polish_v91",
        "GetSysColorBrush(COLOR_BTNFACE)",
        "concept98 v91 new-message popup displayed"
    ]
}.items():
    source = read(p)
    for needle in needles:
        if needle not in source:
            raise SystemExit("v9.1 verification missing %s in %s" %
                             (needle, p.name))

print(
    "Applied Concept 98 v9.1: compact two-pane Win9x layout, fully accessible "
    "native global-search results, functional legacy search/media toolbar, "
    "flicker-resistant list redraw, toolbar/header contrast and fonts, "
    "readable notification popup and reduced RichEdit reflow."
)
