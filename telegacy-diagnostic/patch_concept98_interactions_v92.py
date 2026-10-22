#!/usr/bin/env python3
"""Concept 98 v9.2: resizable sidebar, keyboard navigation, context menu."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_concept98_interactions_v92.py <src-root>")

root=Path(sys.argv[1]).resolve()
path=root/"src"/"telegacy.cpp"
s=path.read_text(encoding="latin-1")

if "concept98_interactions_v92" in s:
    print("Concept 98 interactions already applied")
    raise SystemExit(0)

if "concept98_polish_v91" not in s:
    raise SystemExit("Concept 98 v9.1 prerequisite missing")

def sub(old,new,desc):
    global s
    if old not in s:
        raise SystemExit("Concept 98 v9.2 anchor missing: "+desc)
    s=s.replace(old,new,1)

sub(
    "static bool concept98_last_writable_v91 = true;",
    """static bool concept98_last_writable_v91 = true;
// concept98_interactions_v92
static int concept98_sidebar_width_v92 = -1;
static bool concept98_resizing_v92 = false;
static WNDPROC concept98_old_divider_proc_v92 = NULL;""",
    "splitter state"
)

divider=r'''// Native drag handle: keeps the Telegacy layout resizable without a custom
// graphics toolkit. The persisted width is used only in Concept 98 mode.
static void concept98_apply_layout(HWND hwnd);

static LRESULT CALLBACK concept98_divider_proc_v92(
    HWND hwnd, UINT msg, WPARAM wp, LPARAM lp
) {
    if (msg == WM_SETCURSOR) {
        SetCursor(LoadCursorW(NULL, IDC_SIZEWE));
        return TRUE;
    }
    if (msg == WM_LBUTTONDOWN && concept98_enabled) {
        concept98_resizing_v92 = true;
        SetCapture(hwnd);
        return 0;
    }
    if (msg == WM_MOUSEMOVE &&
        concept98_resizing_v92 &&
        GetCapture() == hwnd) {
        HWND parent = GetParent(hwnd);
        RECT bounds = {0};
        POINT position = {0};
        GetCursorPos(&position);
        GetClientRect(parent, &bounds);
        ScreenToClient(parent, &position);
        int max_width = bounds.right - 470;
        if (max_width > 405) max_width = 405;
        if (max_width < 228) max_width = 228;
        int candidate = position.x;
        if (candidate < 228) candidate = 228;
        if (candidate > max_width) candidate = max_width;

        if (concept98_sidebar_width_v92 != candidate) {
            concept98_sidebar_width_v92 = candidate;
            concept98_apply_layout(parent);
        }
        return 0;
    }
    if (msg == WM_LBUTTONUP && concept98_resizing_v92) {
        concept98_resizing_v92 = false;
        if (GetCapture() == hwnd) ReleaseCapture();
        wchar_t value[32] = {0};
        _snwprintf_s(
            value, ARRAYSIZE(value), _TRUNCATE,
            L"%d", concept98_sidebar_width_v92
        );
        WritePrivateProfileStringW(
            L"Concept98", L"sidebar_width",
            value, get_path(appdata_path, L"options.ini")
        );
        return 0;
    }
    if (msg == WM_CAPTURECHANGED) {
        concept98_resizing_v92 = false;
    }
    if (concept98_old_divider_proc_v92)
        return CallWindowProcW(
            concept98_old_divider_proc_v92, hwnd, msg, wp, lp
        );
    return DefWindowProcW(hwnd, msg, wp, lp);
}

'''
sub(
    "static void concept98_move_v91(",
    divider+"static void concept98_move_v91(",
    "drag handle method"
)

sub(
    """    int left = w/4;
    if (left < 238) left = 238;
    if (left > 315) left = 315;""",
    """    int left = concept98_sidebar_width_v92 > 0
        ? concept98_sidebar_width_v92 : w/4;
    int max_left = w-470;
    if (max_left > 405) max_left = 405;
    if (max_left < 228) max_left = 228;
    if (left < 228) left = 228;
    if (left > max_left) left = max_left;""",
    "persisted sidebar width"
)
sub(
    """    concept98_move_v91(concept98_divider_v91, left-1, 0,
                       2, h-1);""",
    """    concept98_move_v91(concept98_divider_v91, left-3, 0,
                       6, h-1);""",
    "larger resize grip"
)

sub(
    """    concept98_divider_v91 = CreateWindowW(
        L"STATIC", L"", panel | SS_ETCHEDVERT,
        238,0,2,600,hwnd,NULL,NULL,NULL
    );""",
    """    concept98_divider_v91 = CreateWindowW(
        L"STATIC", L"", panel | SS_ETCHEDVERT | SS_NOTIFY,
        238,0,6,600,hwnd,NULL,NULL,NULL
    );
    concept98_sidebar_width_v92 = GetPrivateProfileIntW(
        L"Concept98", L"sidebar_width", -1,
        get_path(appdata_path, L"options.ini")
    );
    if (concept98_divider_v91) {
        concept98_old_divider_proc_v92 = (WNDPROC)SetWindowLongPtrW(
            concept98_divider_v91,
            GWLP_WNDPROC, (LONG_PTR)concept98_divider_proc_v92
        );
    }""",
    "subclass resize divider"
)

# Global search results are backed by the existing owner-draw combo.
# Right-click always selects that item first so native Chat menu acts on it.
anchor='    if (msg == WM_COMMAND && LOWORD(wParam) == 8915) {'
extra=r'''    if (msg == WM_CONTEXTMENU &&
        (HWND)wParam == concept98_list && concept98_enabled) {
        POINT screen = {GET_X_LPARAM(lParam), GET_Y_LPARAM(lParam)};
        POINT pt = screen;
        if (pt.x == -1 && pt.y == -1) {
            int selected = (int)SendMessageW(
                concept98_list, LB_GETCURSEL, 0, 0
            );
            if (selected < 0) return 0;
            RECT item = {0};
            SendMessageW(
                concept98_list, LB_GETITEMRECT,
                selected, (LPARAM)&item
            );
            pt.x = item.left+20;
            pt.y = item.top+20;
            ClientToScreen(concept98_list, &pt);
            screen = pt;
        }
        ScreenToClient(concept98_list, &pt);
        LRESULT hit = SendMessageW(
            concept98_list, LB_ITEMFROMPOINT, 0,
            MAKELPARAM(pt.x, pt.y)
        );
        if (HIWORD(hit)) return 0;
        int selected = LOWORD(hit);
        if (selected < 0) return 0;
        SendMessageW(concept98_list, LB_SETCURSEL, selected, 0);
        SendMessageW(
            hWnd, WM_COMMAND,
            MAKEWPARAM(CONCEPT98_LIST_ID, LBN_SELCHANGE),
            (LPARAM)concept98_list
        );
        HMENU menu = GetSubMenu(hMenuBar, 1);
        if (menu && current_peer) {
            TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_LEFTALIGN,
                screen.x, screen.y, 0, hWnd, NULL
            );
        }
        return 0;
    }
'''
sub(anchor,extra+anchor,"right-click context menu")

# Keyboard messages are delivered to focused child controls, not the parent.
# Route shortcuts from the outer pump before IsDialogMessage consumes them.
loop_start='while (GetMessage(&msg, NULL, 0, 0)) {\n\t\tif (!IsDialogMessage(current_dialog, &msg)) {'
loop_new=r'''while (GetMessage(&msg, NULL, 0, 0)) {
        if (concept98_enabled && msg.message == WM_KEYDOWN) {
            bool ctrl = (GetKeyState(VK_CONTROL) & 0x8000) != 0;
            if (ctrl &&
                (msg.wParam == 'K' || msg.wParam == 'F' ||
                 msg.wParam == 'L')) {
                if (msg.wParam == 'K') {
                    SetFocus(
                        global_chat_search_mode ?
                        hChatSearch : concept98_filter
                    );
                } else if (msg.wParam == 'F') {
                    if (hMessageSearch) SetFocus(hMessageSearch);
                } else if (msgInput && IsWindowVisible(msgInput)) {
                    SetFocus(msgInput);
                }
                continue;
            }
            if (msg.wParam == VK_ESCAPE &&
                (msg.hwnd == concept98_filter ||
                 msg.hwnd == hChatSearch)) {
                SetWindowTextW(msg.hwnd, L"");
                SetFocus(concept98_list);
                continue;
            }
        }
        if (!IsDialogMessage(current_dialog, &msg)) {'''
sub(loop_start,loop_new,"keyboard dispatcher")

path.write_text(s,encoding="latin-1",newline="\r\n")
for token in (
    "concept98_interactions_v92",
    "concept98_divider_proc_v92",
    "Concept98\", L\"sidebar_width",
    "msg.wParam == 'K'",
    "WM_CONTEXTMENU",
    "concept98_move_v91(concept98_divider_v91, left-3"
):
    if token not in s:
        raise SystemExit("v9.2 verification failed: "+token)

print("Applied Concept 98 v9.2: draggable persistent sidebar, Ctrl+K/F/L, "
      "Escape-to-clear and real native chat context menu.")
