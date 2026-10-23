#!/usr/bin/env python3
"""v11.0: calm Win98 Explorer chrome, warm paper chat, classic bevels and hierarchy.
Native GDI/Win32 only; keep original mouse interactions, split panes and shortcut IDs.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_shell_polish_v110.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_shell_polish_v110" in s:
    print("v11.0 already applied");raise SystemExit(0)
if "concept98_sticker_first_frame_v109" not in s:
    raise SystemExit("v10.9 prerequisite absent")
def one(a,b,name):
    global s
    n=s.count(a)
    if n!=1:raise SystemExit(f"v11.0 expected one {name}: {n}")
    s=s.replace(a,b,1)

# Retain flexible resizable sidebar, give conversation more horizontal space.
one('if (max_left > 405) max_left = 405;',
    'if (max_left > 360) max_left = 360; // concept98_shell_polish_v110',
    'sidebar max')
one('if (max_left < 228) max_left = 228;',
    'if (max_left < 252) max_left = 252;',
    'sidebar min1')
one('if (left < 228) left = 228;',
    'if (left < 252) left = 252;',
    'sidebar min2')

# A compact Explorer-style sidebar: tab, folder combo, quick search, history.
one('concept98_move_v91(hChatScopeTabs, 7, 7, left-14, 28);',
    'concept98_move_v91(hChatScopeTabs, 8, 7, left-16, 27);',
    'chat scope tabs')
one('concept98_move_v91(hComboBoxFolders, 7, 43, left-14, 250);',
    'concept98_move_v91(hComboBoxFolders, 8, 42, left-16, 250);',
    'folder combo')
one('concept98_move_v91(concept98_brand_icon_v91, 7, 75, 18, 18);',
    'concept98_move_v91(concept98_brand_icon_v91, 9, 75, 18, 18);',
    'folder icon')
one('concept98_move_v91(concept98_sidebar_hint_v91, 29, 75,',
    'concept98_move_v91(concept98_sidebar_hint_v91, 32, 75,',
    'folder label')
one('concept98_move_v91(hChatSearch, 7, 100, left-14, 24);',
    'concept98_move_v91(hChatSearch, 8, 101, left-16, 26);',
    'chat search')
one('concept98_move_v91(concept98_filter, 7, 100, left-14, 24);',
    'concept98_move_v91(concept98_filter, 8, 101, left-16, 26);',
    'filter')
one('concept98_move_v91(concept98_list_caption, 10, 133,',
    'concept98_move_v91(concept98_list_caption, 10, 137,',
    'list label')
one('concept98_move_v91(concept98_list, 7, 156, left-14,\n                       h-165);',
    'concept98_move_v91(concept98_list, 8, 159, left-16,\n                       h-170);',
    'list geometry')

# Neutral warm content surface; actual beveled Win98 widgets remain native.
defn='static void concept98_apply_layout(HWND hwnd) {'
one(defn,defn+r'''
    // concept98_shell_polish_v110
    // The chat and editor are kept on a warm, high-contrast Windows paper
    // background. No gradients, glass effects, rounded cards or custom scrollbars.
    if (chat) SendMessageW(chat,EM_SETBKGNDCOLOR,0,
                           (LPARAM)RGB(247,246,242));
    if (msgInput) SendMessageW(msgInput,EM_SETBKGNDCOLOR,0,
                               (LPARAM)RGB(250,249,245));
''','chat color setup')

# Selection uses restrained Explorer blue; unread indicator is native bevel
# instead of a saturated, modern red badge.
one('COLORREF background = selected ?\n        GetSysColor(COLOR_HIGHLIGHT) : GetSysColor(COLOR_WINDOW);',
    'COLORREF background = selected ?\n        RGB(39,75,115) : RGB(247,246,242);',
    'row background')
one('COLORREF textcolor = selected ?\n        GetSysColor(COLOR_HIGHLIGHTTEXT) :\n        GetSysColor(COLOR_WINDOWTEXT);',
    'COLORREF textcolor = selected ?\n        RGB(255,255,255) : RGB(34,36,39);',
    'row text')
one('dc, selected ? textcolor : GetSysColor(COLOR_GRAYTEXT)',
    'dc, selected ? textcolor : RGB(101,101,106)',
    'secondary text')
start=s.index('    if (unread) {',s.index('static bool concept98_draw_row('))
end=s.index('    SelectObject(dc, oldfont);',start)
badges=r'''    if (unread) {
        wchar_t count[12]={0};
        if (peer->unread_msgs_count>=10000)
            wcscpy_s(count,L"9999+");
        else
            _snwprintf_s(count,ARRAYSIZE(count),_TRUNCATE,
                         L"%d",peer->unread_msgs_count);
        RECT indicator={rc.right-48,rc.top+15,rc.right-7,rc.top+35};
        HBRUSH badgeBrush=CreateSolidBrush(
            selected ? RGB(222,227,233) : RGB(231,232,223));
        FillRect(dc,&indicator,badgeBrush);
        DeleteObject(badgeBrush);
        DrawEdge(dc,&indicator,EDGE_RAISED,BF_RECT);
        SetTextColor(dc,RGB(29,57,91));
        DrawTextW(dc,count,-1,&indicator,
                  DT_SINGLELINE|DT_CENTER|DT_VCENTER);
    }

'''
s=s[:start]+badges+s[end:]
one('HPEN pen = CreatePen(PS_SOLID, 1, GetSysColor(COLOR_3DLIGHT));',
    'HPEN pen = CreatePen(PS_SOLID, 1, RGB(222,221,214));',
    'list dividers')
# Stable 98-era caption, no large pseudo-brand occupying the chat pane.
one('L"Telegacy 98  |  Telegram Client"',
    'L"Telegacy 98   |   Переписка"',
    'chat caption')
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v11.0 warm Win98 Explorer shell: calmer chat paper, classic unread bevels, better split width, compact sidebar.")
