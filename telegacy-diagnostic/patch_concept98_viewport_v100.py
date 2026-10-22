#!/usr/bin/env python3
"""Concept98 v10.0: verified sticker geometry and initially settled chat viewport."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_viewport_v100.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_viewport_v100" in s:
    print("v10.0 already applied");raise SystemExit(0)
if "concept98_sticker_anchors_v94" not in s or "concept98_fast_avatars_v99" not in s:
    raise SystemExit("Requires v9.9")

def rep(a,b,desc):
    global s
    if a not in s:raise SystemExit("v10.0 missing "+desc)
    s=s.replace(a,b,1)

rep("if (distance > 1 || !large_object)",
    "if (distance != 0 || !large_object)",
    "sticker exact OLE location guard")
# When EM_POSFROMCHAR fails, cached coordinates, even at the same cp, have
# proven unreliable in RichEdit with async OLE layout changes. Fail closed.
needle=r'''        if (
            !direct_geometry &&
            sticker->have_geometry_v88 &&
            sticker_cp == sticker->last_cp_v88 &&'''
rep(needle,r'''        // concept98_viewport_v100: position inference from older scroll
        // coordinates is intentionally disabled. RichEdit may have moved
        // OLE objects after async image replacement without changing cp.
        if (
            false &&
            !direct_geometry &&
            sticker->have_geometry_v88 &&
            sticker_cp == sticker->last_cp_v88 &&''',"disable stale sticker placement")
rep('    if (\n        !chat ||\n        media_chat_animated_stickers.empty()\n    ) {\n        return;\n    }\n\n    RECT viewport = {0};',
    '    if (\n        !chat ||\n        !IsWindowVisible(chat) ||\n        media_chat_animated_stickers.empty()\n    ) {\n        return;\n    }\n\n    RECT viewport = {0};',
    "prevent animation updates during chat bootstrap")

# Stabilize initial scroll silently instead of showing a half-loaded RichEdit
# and visibly jumping to SB_BOTTOM after the first history response.
point="static DWORD concept98_previous_badge_hash_v91 = 0;"
v=r'''// concept98_viewport_v100
static bool concept98_bootstrap_v100=false;
static DWORD concept98_bootstrap_started_v100=0;
static int concept98_bootstrap_last_chars_v100=-1;
static int concept98_bootstrap_last_range_v100=-1;
static DWORD concept98_bootstrap_stable_since_v100=0;

static void concept98_bootstrap_begin_v100(HWND hwnd) {
    if (!concept98_enabled || !chat || !IsWindow(chat)) return;
    if (concept98_bootstrap_v100) {
        KillTimer(hwnd,8997);
        ShowWindow(chat,SW_SHOW);
    }
    concept98_bootstrap_v100=true;
    concept98_bootstrap_started_v100=GetTickCount();
    concept98_bootstrap_last_chars_v100=-1;
    concept98_bootstrap_last_range_v100=-1;
    concept98_bootstrap_stable_since_v100=0;
    // Do not disable the message editor; only hide the scrollable document
    // while the native handler selects a new history and performs layout.
    ShowWindow(chat,SW_HIDE);
    SetTimer(hwnd,8997,90,NULL);
}
static void concept98_bootstrap_tick_v100(HWND hwnd) {
    if (!concept98_bootstrap_v100 || !chat || !IsWindow(chat)) {
        KillTimer(hwnd,8997);return;
    }
    DWORD now=GetTickCount();
    int chars=GetWindowTextLengthW(chat);
    SCROLLINFO scroll={0};
    scroll.cbSize=sizeof(scroll);
    scroll.fMask=SIF_RANGE|SIF_PAGE|SIF_POS;
    GetScrollInfo(chat,SB_VERT,&scroll);
    if (chars!=concept98_bootstrap_last_chars_v100 ||
        scroll.nMax!=concept98_bootstrap_last_range_v100) {
        concept98_bootstrap_last_chars_v100=chars;
        concept98_bootstrap_last_range_v100=scroll.nMax;
        concept98_bootstrap_stable_since_v100=now;
    }
    // Scroll while hidden, only for a fresh peer selection. Existing chat
    // scrolling/history pagination is never forced to the bottom.
    SendMessageW(chat,WM_VSCROLL,SB_BOTTOM,0);
    SendMessageW(chat,WM_VSCROLL,SB_ENDSCROLL,0);
    bool stable=chars>0 && now-concept98_bootstrap_started_v100>=340 &&
        now-concept98_bootstrap_stable_since_v100>=270;
    if (!stable && now-concept98_bootstrap_started_v100<1700)
        return;
    concept98_bootstrap_v100=false;
    KillTimer(hwnd,8997);
    ShowWindow(chat,SW_SHOW);
    SendMessageW(chat,WM_VSCROLL,SB_BOTTOM,0);
    SendMessageW(chat,WM_VSCROLL,SB_ENDSCROLL,0);
    InvalidateRect(chat,NULL,FALSE);
    diag_log("concept98 v100 initial scroll settled chars=%d stable=%d",
             chars,stable?1:0);
}

'''
rep(point,v+point,"viewport bootstrap state")
# Parent event hook follows the original CBN listener. Enter before native
# Telegacy destroys/recreates its RichEdit document on peer switch.
needle='    if (msg == WM_COMMAND &&\n        (LOWORD(wParam) == 2 || LOWORD(wParam) == 3) &&\n        HIWORD(wParam) == CBN_SELCHANGE) {'
rep(needle,r'''    if (msg == WM_COMMAND && concept98_enabled &&
        LOWORD(wParam) == 3 && HIWORD(wParam) == CBN_SELCHANGE &&
        (HWND)lParam == hComboBoxChats) {
        media_chat_animated_sticker_clear();
        concept98_bootstrap_begin_v100(hWnd);
    }
'''+needle,"peer switch initialization")
needle='    if (msg == WM_TIMER && wParam == 8998) {'
rep(needle,r'''    if (msg == WM_TIMER && wParam == 8997) {
        concept98_bootstrap_tick_v100(hWnd);
        return 0;
    }
'''+needle,"bootstrap timer dispatch")
needle='\t\tKillTimer(hWnd, 8998);'
rep(needle,needle+'\n\t\tKillTimer(hWnd, 8997);',"bootstrap timer cleanup")
p.write_text(s,encoding="latin-1",newline="\r\n")
for marker in ("concept98_viewport_v100","concept98_bootstrap_tick_v100",
               "distance != 0 || !large_object","!IsWindowVisible(chat)"):
    if marker not in s:raise SystemExit("v10.0 missing "+marker)
print("Concept98 v10.0: no inferred sticker positions, exact anchor only; "
      "new chat viewport hidden until initial bottom layout settles.")
