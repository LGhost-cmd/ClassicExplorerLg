#!/usr/bin/env python3
"""Concept98 v12.2: native Win98 UI finish (search and notification).
Use real system colors, client-edge edit, same font/grid, and a recessed white
notification message pane. No custom gradients, new dependencies or bitmap skins.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_ui_finish_v122.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
h=root/"src"/"helpers.cpp"
s=p.read_text(encoding="latin-1")
a=h.read_text(encoding="latin-1")
if "concept98_ui_finish_v122" in s:raise SystemExit(0)
if "concept98_forum_search_cached_photo_v121" not in s:raise SystemExit("v12.1 required")
def one(body,old,new,name):
    c=body.count(old)
    if c!=1:raise SystemExit("v12.2 %s expected 1 found %d"%(name,c))
    return body.replace(old,new,1)
# Search is a classic EDIT, not the default bright themed strip:
# subdued cue until focus, Win98 sunken client edge, system text/select colors.
s=one(s,
'''    const int search_left_v121 = content_x+46;''',
'''    // concept98_ui_finish_v122: match the Win98 title/subject text grid.
    // Only once per HWND: no focus loss or flickering during resize.
    static HWND themed_search_v122=NULL;
    if(hMessageSearch && IsWindow(hMessageSearch) &&
       themed_search_v122!=hMessageSearch){
        themed_search_v122=hMessageSearch;
        LONG_PTR ex=GetWindowLongPtrW(hMessageSearch,GWL_EXSTYLE);
        SetWindowLongPtrW(hMessageSearch,GWL_EXSTYLE,
                          ex|WS_EX_CLIENTEDGE);
        SendMessageW(hMessageSearch,WM_SETFONT,
                     (WPARAM)hFonts[2],TRUE);
        SendMessageW(hMessageSearch,EM_SETMARGINS,
                     EC_LEFTMARGIN|EC_RIGHTMARGIN,MAKELONG(5,5));
        SetWindowPos(hMessageSearch,NULL,0,0,0,0,
          SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED);
    }
    const int search_left_v121 = content_x+46;''',
"search line themed")
# Read-only forum search remains channel-wide: indicate scope visually.
# Reset scope on leaving forum/ordinary chats, not during every layout.
s=one(s,
'''    if(hMessageSearch)EnableWindow(hMessageSearch,TRUE);
    concept98_forum_visibility_v119();
}
static void concept98_forum_request_v119(){''',
'''    if(hMessageSearch) {
        EnableWindow(hMessageSearch,TRUE);
        SendMessageW(hMessageSearch,0x1501,TRUE,
          (LPARAM)L"\x041f\x043e\x0438\x0441\x043a \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0439...");
    }
    concept98_forum_visibility_v119();
}
static void concept98_forum_request_v119(){''',
"reset search cue")
p.write_text(s,encoding="latin-1",newline="\r\n")
# Notification popup: Win98 system-title stays native, inside is a recessed
# white message surface as in 1998-era instant messenger popups.
a=one(a,
'''    if (concept98_enabled &&
        (msg == WM_CTLCOLORDLG || msg == WM_CTLCOLORSTATIC)) {
        HDC dc = (HDC)wParam;
        if (dc) {
            SetTextColor(dc, GetSysColor(COLOR_WINDOWTEXT));
            SetBkColor(dc, GetSysColor(COLOR_BTNFACE));
        }
        return (INT_PTR)GetSysColorBrush(COLOR_BTNFACE);
    }''',
'''    // concept98_ui_finish_v122: native Win98 sunken white message area.
    if(concept98_enabled && msg==WM_CTLCOLORSTATIC){
        HDC dc=(HDC)wParam;
        int id=lParam?GetDlgCtrlID((HWND)lParam):0;
        bool paper=(id==9021||id==9022||id==9023);
        if(dc){
            SetTextColor(dc,GetSysColor(COLOR_WINDOWTEXT));
            SetBkColor(dc,GetSysColor(
                 paper?COLOR_WINDOW:COLOR_BTNFACE));
        }
        return (INT_PTR)GetSysColorBrush(
                 paper?COLOR_WINDOW:COLOR_BTNFACE);
    }
    if(concept98_enabled && msg==WM_CTLCOLORDLG)
        return (INT_PTR)GetSysColorBrush(COLOR_BTNFACE);''',
"notification paint colors")
a=one(a,
'''        HWND title = CreateWindowW(
            L"STATIC", data ? data->szInfoTitle : L"Telegram",
            WS_VISIBLE | WS_CHILD | SS_LEFT | SS_ENDELLIPSIS,
            54, 14, 310, 24, hDlg, NULL, NULL, NULL
        );''',
'''        HWND panel=CreateWindowExW(
            WS_EX_CLIENTEDGE,L"STATIC",L"",
            WS_VISIBLE|WS_CHILD|SS_LEFT,
            10,10,370,103,hDlg,(HMENU)9023,NULL,NULL
        );
        HWND title = CreateWindowW(
            L"STATIC", data ? data->szInfoTitle : L"Telegram",
            WS_VISIBLE | WS_CHILD | SS_LEFT | SS_ENDELLIPSIS,
            54, 18, 307, 24, hDlg, (HMENU)9021, NULL, NULL
        );''',
"notification white panel and title")
a=one(a,
'''            54, 40, 305, 69, hDlg, NULL, NULL, NULL
''',
'''            54, 45, 303, 59, hDlg, (HMENU)9022, NULL, NULL
''',
"notification message body")
a=one(a,
'''            13, 15, 34, 34, hDlg, NULL, NULL, NULL''',
'''            16, 19, 34, 34, hDlg, NULL, NULL, NULL''',
"notification 98 icon")
a=one(a,
'''            54, 117, 139, 28, hDlg, (HMENU)1, NULL, NULL''',
'''            54, 122, 139, 28, hDlg, (HMENU)1, NULL, NULL''',
"notification reply button")
a=one(a,
'''            200, 117, 158, 28, hDlg, (HMENU)2, NULL, NULL''',
'''            200, 122, 158, 28, hDlg, (HMENU)2, NULL, NULL''',
"notification open button")
# Keep the native Win98 popup compact and align the v9.3 extra controls.
a=one(a,
'''            54, 150, 110, 24, hDlg,(HMENU)3,NULL,NULL''',
'''            54, 158, 139, 26, hDlg,(HMENU)3,NULL,NULL''',
"notification hide button grid")
a=one(a,
'''            172,150,186,24,hDlg,(HMENU)4,NULL,NULL''',
'''            200,158,158,26,hDlg,(HMENU)4,NULL,NULL''',
"notification DND button grid")
a=one(a,"        const int h = 214;","        const int h = 216;",
"notification Win98 popup height")
# Glyph availability depends on the active Windows 98 bitmap font.
# Avoid making the entire build fail if another patch already replaced the title.
a=a.replace(r"\x2014 Telegacy",r"| Telegacy")

h.write_text(a,encoding="latin-1",newline="\r\n")
print("v12.2: proper recessed Win98 notification pane, system-color text, aligned themed message search.")
