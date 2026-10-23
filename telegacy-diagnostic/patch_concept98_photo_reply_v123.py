#!/usr/bin/env python3
"""Concept98 v12.3: robust full-JPEG cache path, explicit visual refresh and
visible native Win98 "reply to" strip; no change to Telegram send semantics.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_photo_reply_v123.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
m=root/"src"/"message.cpp"
s=p.read_text(encoding="latin-1")
a=m.read_text(encoding="latin-1")
if "concept98_photo_reply_v123" in s:raise SystemExit(0)
if "concept98_retry_cached_photo_v121" not in s:raise SystemExit("requires v12.2")
def replace_once(old,new,label):
 global s
 n=s.count(old)
 if n!=1:raise SystemExit("v12.3 "+label+" occurrence="+str(n))
 s=s.replace(old,new,1)

# The Telegacy APPDATA base already ENDS IN A BACKSLASH.  Do not make the
# destination path with a doubled slash; CreateDirectoryW may reject it.
replace_once(
'''    _snwprintf_s(folder,ARRAYSIZE(folder),_TRUNCATE,
                 L"%s\\\\photo_cache98",appdata_path);
    CreateDirectoryW(folder,NULL);''',
'''    wcscpy_s(folder,ARRAYSIZE(folder),appdata_path);
    if (wcslen(folder)+16>=ARRAYSIZE(folder))return false;
    wcscat_s(folder,ARRAYSIZE(folder),L"photo_cache98");
    if (!CreateDirectoryW(folder,NULL) &&
        GetLastError()!=ERROR_ALREADY_EXISTS) {
        diag_log("concept98 v123 cache dir error=%lu",GetLastError());
        return false;
    }''',"cache directory double slash")
replace_once(
'''    FILE* file=_wfopen(path,L"wb");
    if (!file) return;''',
'''    FILE* file=_wfopen(path,L"wb");
    if (!file) {
        diag_log("concept98 v123 full JPEG cache file open failed err=%lu",
                 GetLastError());
        return;
    }''',"cache save write error diagnostic")
replace_once(
'''    if (written!=jpeg.size()) DeleteFileW(path);
    else diag_log("concept98 v101 cached full photo bytes=%Iu",
                  jpeg.size());''',
'''    if (written!=jpeg.size()) {
        DeleteFileW(path);
        diag_log("concept98 v123 full JPEG cache short write %Iu/%Iu",
                 written,jpeg.size());
    } else diag_log("concept98 v123 cached full JPEG bytes=%Iu",
                   jpeg.size());''',"cache write confirmation")
# A successful RichEdit insert may not be redrawn when drawchat==false,
# causing the old Loading image card to remain visibly stuck.
replace_once(
'''        diag_log(
            "chat v87 full photo replaced exact captured=%d old=%d new=%d",''',
'''        // concept98_photo_reply_v123: invalidate even with drawchat=false.
        // RichEdit could show a stale Loading image card after the real
        // bitmap OLE had already replaced it.
        InvalidateRect(chat,NULL,FALSE);
        if(IsWindowVisible(chat))UpdateWindow(chat);
        diag_log(
            "chat v87 full photo replaced exact captured=%d old=%d new=%d",''',
"force post-replacement paint")
# The v81 fast path trusts an in-memory full flag even if the card was
# rebuilt as Loading image. Always accept an explicit click/cache recovery.
replace_once(
'''            bool replaced = true;

            if (!media_chat_v81_skip_replace_when_done) {''',
'''            bool replaced = false;
            // v123: a stale "already full" flag is not sufficient proof.
            // A fresh JPEG has just decoded; always replace the exact
            // captured OLE, including the double-click or cache path.
            if (true) {''',
"disallow false positive repaint-skip")
# Reuse existing verified card after it is inserted into RichEdit during
# a repagination. Cache-first rebuild removes Loading... immediately.
# Native reply strip HWNDs and the selected source message snapshot.
decl="static HWND concept98_chat_detail = NULL;"
if s.count(decl)!=1:raise SystemExit("v12.3 no Concept98 declaration")
s=s.replace(decl,decl+'''
static HWND concept98_reply_strip_v123=NULL; // concept98_photo_reply_v123
static HWND concept98_reply_cancel_v123=NULL;
static bool concept98_reply_visible_v123=false;
''',1)
layout="static void concept98_apply_layout(HWND hwnd) {"
if s.count(layout)!=1:raise SystemExit("v12.3 no layout")
update=r'''
// concept98_photo_reply_v123: Native 1998-style one-line draft context.
// Source content is copied from CURRENT chat history; no cross-peer lookup,
// no dangling pointers, no alteration of the outgoing reply_to identifier.
static void concept98_reply_update_v123() {
    if(!concept98_reply_strip_v123 ||
       !IsWindow(concept98_reply_strip_v123))return;
    bool show=concept98_enabled && current_peer &&
        current_peer->perm.cansendmsg && replying_msg_id!=0;
    std::wstring label;
    if(show){
        label=L"\x0412 \x043e\x0442\x0432\x0435\x0442 \x043d\x0430: ";
        int idx=-1;
        for(int i=(int)messages.size()-1;i>=0;i--)
            if(messages[i].id==replying_msg_id){idx=i;break;}
        if(idx>=0 && chat){
            int from=messages[idx].start_char;
            int to=messages[idx].end_char;
            if(from<0)from=0;
            if(to-from>120)to=from+120;
            if(to>from){
                wchar_t preview[160]={0};
                TEXTRANGEW tr={0};
                tr.chrg.cpMin=from;
                tr.chrg.cpMax=to;
                tr.lpstrText=preview;
                LRESULT n=SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
                if(n>0 && n<159){
                    preview[n]=0;
                    for(int j=0;j<n;j++)
                        if(preview[j]==L'\n'||preview[j]==L'\r'||
                           preview[j]==0xFFFC)preview[j]=L' ';
                    label.append(preview);
                }
            }
        }
        if(label.size()<18)
            label+=L"\x0421\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
    }
    if(show){
        SetWindowTextW(concept98_reply_strip_v123,label.c_str());
        ShowWindow(concept98_reply_strip_v123,SW_SHOW);
        ShowWindow(concept98_reply_cancel_v123,SW_SHOW);
    } else {
        ShowWindow(concept98_reply_strip_v123,SW_HIDE);
        ShowWindow(concept98_reply_cancel_v123,SW_HIDE);
    }
    if(concept98_reply_visible_v123!=show){
        concept98_reply_visible_v123=show;
        PostMessageW(hMain,WM_APP+0x398,0,0);
    }
}
'''
s=s.replace(layout,update+"\n"+layout,1)
# Reply row occupies the 29 pixels immediately above the editor toolbar.
replace_once(
'''    const int bottom = cantwrite ?
        h-28 : h-124+edits_border_offset;

    concept98_move_v91(
        chat, content_x, chat_y, content_w,
        bottom-chat_y
    );''',
'''    const bool reply_row_v123 =
        !cantwrite && replying_msg_id!=0;
    const int bottom = cantwrite ?
        h-28 : h-124+edits_border_offset;
    concept98_move_v91(concept98_reply_strip_v123,
                       content_x+7,bottom-29,content_w-43,25);
    concept98_move_v91(concept98_reply_cancel_v123,
                       content_x+content_w-32,bottom-28,27,24);
    concept98_reply_update_v123();
    concept98_move_v91(
        chat, content_x, chat_y, content_w,
        bottom-chat_y-(reply_row_v123?30:0)
    );''',"reply strip layout")
# Background is COLOR_BTNFACE (system!) rather than white.
anchor='''    concept98_topic_combo_v119=CreateWindowExW('''
if s.count(anchor)!=1:raise SystemExit("v12.3 no header widget anchor")
creation=r'''    concept98_reply_strip_v123=CreateWindowExW(
        WS_EX_STATICEDGE,L"STATIC",L"",
        WS_CHILD|SS_LEFT|SS_CENTERIMAGE|SS_ENDELLIPSIS,
        250,500,300,25,hwnd,(HMENU)8993,NULL,NULL
    );
    concept98_reply_cancel_v123=CreateWindowW(
        L"BUTTON",L"x",WS_CHILD|BS_PUSHBUTTON,
        250,500,27,24,hwnd,(HMENU)8994,NULL,NULL
    );
    SendMessageW(concept98_reply_strip_v123,WM_SETFONT,
                 (WPARAM)hFonts[2],TRUE);
    SendMessageW(concept98_reply_cancel_v123,WM_SETFONT,
                 (WPARAM)hFonts[2],TRUE);
'''
s=s.replace(anchor,creation+anchor,1)
anchor='''    if (msg == WM_APP + 0x391) { // v120: socket -> UI thread'''
if s.count(anchor)!=1:raise SystemExit("v12.3 no WM_APP anchor")
s=s.replace(anchor,'''    if (msg==WM_APP+0x397) {
        concept98_reply_update_v123();
        return 0;
    }
    if (msg==WM_APP+0x398) {
        if(concept98_enabled)concept98_apply_layout(hWnd);
        return 0;
    }
'''+anchor,1)
anchor='''    if (msg == WM_CTLCOLORSTATIC && concept98_enabled) {'''
if s.count(anchor)!=1:raise SystemExit("v12.3 no control color anchor")
s=s.replace(anchor,anchor+'''
        if((HWND)lParam==concept98_reply_strip_v123){
            HDC dc=(HDC)wParam;
            SetTextColor(dc,GetSysColor(COLOR_BTNTEXT));
            SetBkColor(dc,GetSysColor(COLOR_BTNFACE));
            return (LRESULT)GetSysColorBrush(COLOR_BTNFACE);
        }
''',1)
# Reply start, cancel and after-send all share the same visible update.
replace_once(
'''\t\tcase 7: {
\t\t\treplying_msg_id = 0;''',
'''\t\tcase 7: {
\t\t\treplying_msg_id = 0;
\t\t\tPostMessageW(hWnd,WM_APP+0x397,0,0);''',"cancel native reply context")
replace_once(
'''\t\tcase 23: {
\t\t\treplying_msg_id = sel_msg_id;''',
'''\t\tcase 23: {
\t\t\treplying_msg_id = sel_msg_id;
\t\t\tPostMessageW(hWnd,WM_APP+0x397,0,0);''',"create native reply context")
# If an active reply is cleared by normal send, WM_COMMAND(7) already triggers
# the preview update. Do not store mutable message content on foreign threads.
anchor='''    if (msg == WM_COMMAND && concept98_enabled &&
        LOWORD(wParam) == 3 && HIWORD(wParam) == CBN_SELCHANGE &&'''
if s.count(anchor)==1:
 s=s.replace(anchor,'''    if(msg==WM_COMMAND && LOWORD(wParam)==8994 &&
       (HWND)lParam==concept98_reply_cancel_v123){
        SendMessageW(hWnd,WM_COMMAND,MAKEWPARAM(7,0),0);
        return 0;
    }
'''+anchor,1)
else:
 # Fall back to the known topic-command ID; do not silently omit cancel.
 anchor='''    if (msg == WM_APP + 0x390) {'''
 if s.count(anchor)!=1:raise SystemExit("v12.3 cancel insertion missing")
 s=s.replace(anchor,'''    if(msg==WM_COMMAND && LOWORD(wParam)==8994 &&
       (HWND)lParam==concept98_reply_cancel_v123){
        SendMessageW(hWnd,WM_COMMAND,MAKEWPARAM(7,0),0);
        return 0;
    }
'''+anchor,1)
# On a peer switch the original selected ID must not leak into a new dialog.
anchor='''        media_chat_v86_loaded_full_instances.clear();
        concept98_photo_clear_bindings_v111();'''
if s.count(anchor)==1:
 s=s.replace(anchor,anchor+'''
        if(replying_msg_id)
            SendMessageW(hWnd,WM_COMMAND,MAKEWPARAM(7,0),0);
''',1)
p.write_text(s,encoding="latin-1",newline="\r\n")
# Loading card inherits system chat surface rather than a fixed white page.
old='''    FillRect(dc,&all,GetSysColorBrush(COLOR_WINDOW));
    DrawEdge(dc,&all,EDGE_SUNKEN,BF_RECT);'''
if a.count(old)!=1:raise SystemExit("v12.3 photo loading card background missing")
a=a.replace(old,'''    // v123 use Telegacy's user-selected chat surface, not white.
    HBRUSH chatbrush=CreateSolidBrush(colors[1]);
    FillRect(dc,&all,chatbrush);
    DeleteObject(chatbrush);
    DrawEdge(dc,&all,EDGE_SUNKEN,BF_RECT);''',1)
m.write_text(a,encoding="latin-1",newline="\r\n")
print("v12.3: corrected trailing-slash cache path, verified full-JPEG disk persistence, redraw OLE, themed loading card, visible cancellable reply context.")
