#!/usr/bin/env python3
"""Concept98 v12.0: visible forum combobox with latest-active default; exact media clicks.
Patch v11.9 output. Network response posts work to UI thread (no cross-thread
ComboBox mutation). Switch topics with a fresh history and reject old RPCs.
Static WebM/TGS stickers must never be opened as normal video/audio.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_forum_media_v120.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_forum_media_v120" in s:raise SystemExit(0)
if "concept98_forum_topics_v119" not in s:raise SystemExit("requires v11.9")
def one(old,new,name):
    global s
    n=s.count(old)
    if n!=1:raise SystemExit("v12.0 %s: %d matches"%(name,n))
    s=s.replace(old,new,1)

# Keep the informational second line ("Канал") visible. The real topic control
# sits beneath it instead of covering it or hiding behind the More menu.
one('''    if(concept98_chat_detail &&
       IsWindowVisible(concept98_chat_detail)==shown)
        ShowWindow(concept98_chat_detail,shown?SW_HIDE:SW_SHOW);''',
'''    // concept98_forum_media_v120: keep "Канал" as its own label.
    if(concept98_chat_detail && !IsWindowVisible(concept98_chat_detail))
        ShowWindow(concept98_chat_detail,SW_SHOW);
    if(shown) SetWindowPos(concept98_topic_combo_v119,HWND_TOP,
            0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE);''',
"show label and promote dropdown")
# The old 60 s throttle reset the UI on re-entry yet sent no new query.
one('''    if(it!=concept98_forum_attempts_v119.end() &&
       (DWORD)(now-it->second)<60000)return;
    concept98_forum_attempts_v119[id]=now;''',
'''    // v120: no reset-without-request when returning to a forum.
    // Peer changes already limit calls to one request per navigation.
    concept98_forum_attempts_v119[id]=now;''',"forum reopen throttle")

begin=s.index("    HWND combo=concept98_topic_combo_v119;",s.index("bool concept98_forum_receive_v119("))
end=s.index('    diag_log("concept98 v119 forum topics ready count=%d",',begin)
old=s[begin:end]
new='''    // v120: response may execute on the socket worker thread. Never send
    // ComboBox commands or ShowWindow from it; marshal to the UI HWND.
    PostMessageW(hMain,WM_APP+0x391,0,0);
'''
s=s[:begin]+new+s[end:]
# Selection must not page the previous topic's messages.
one('''    message_search_clear_chat_view();
    InterlockedExchange(&history_request_pending,0);
    no_more_msgs=false;
    diag_log("concept98 v119 forum switched topic=%d (read only)",id);
    get_history();''',
'''    message_search_clear_chat_view();
    InterlockedExchange(&history_request_pending,0);
    InterlockedExchange(&history_skip_next,0);
    no_more_msgs=false;
    diag_log("concept98 v120 forum switched topic=%d (read only)",id);
    get_history();''',"topic pagination reset")

anchor="static void concept98_apply_layout(HWND hwnd) {"
insert=r'''
// concept98_forum_media_v120: called ONLY on the window/UI thread.
static void concept98_forum_populate_v120() {
    if(!concept98_topic_combo_v119 || !concept98_forum_loaded_v119 ||
       !current_peer || current_peer->type!=2 ||
       memcmp(current_peer->id,concept98_forum_peer_v119,8)!=0)
        return;
    HWND combo=concept98_topic_combo_v119;
    SendMessageW(combo,CB_RESETCONTENT,0,0);
    // channels.getForumTopics uses last-message ordering by default:
    // first returned topic is the most recently active.
    for(size_t i=0;i<concept98_forum_topics_v119.size();i++) {
        const ConceptForumTopic119& t=concept98_forum_topics_v119[i];
        int row=(int)SendMessageW(combo,CB_ADDSTRING,0,(LPARAM)t.title.c_str());
        if(row>=0) SendMessageW(combo,CB_SETITEMDATA,row,t.id);
    }
    int all=(int)SendMessageW(combo,CB_ADDSTRING,0,
           (LPARAM)L"\x0412\x0441\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x044f");
    if(all>=0) SendMessageW(combo,CB_SETITEMDATA,all,0);
    if(!concept98_forum_topics_v119.empty()){
        SendMessageW(combo,CB_SETCURSEL,0,0);
        concept98_forum_select_v119();
    }
    concept98_forum_visibility_v119();
    diag_log("concept98 v120 visible forum dropdown count=%d default_topic=%d hwnd=%p",
             (int)concept98_forum_topics_v119.size(),
             concept98_forum_selected_v119,combo);
}
'''
one(anchor,insert+"\n"+anchor,"populate entry")
# Show an actual separate row BELOW "Канал": no overlap with search toolbar.
one('''    concept98_move_v91(concept98_topic_combo_v119,
                       content_x+46, 54, title_w-46, 240);
    concept98_forum_visibility_v119();''',
'''    const int topic_row_v120 =
        concept98_forum_loaded_v119 && current_peer &&
        current_peer->type==2 ? 29 : 0;
    concept98_move_v91(concept98_topic_combo_v119,
                       content_x+46, 78, title_w-46, 235);
    concept98_forum_visibility_v119();''',
"topic row geometry")
one('''    concept98_move_v91(hMessageSearch, content_x, 82,
                       search_w, 24);''',
'''    concept98_move_v91(hMessageSearch, content_x, 82+topic_row_v120,
                       search_w, 24);''',"message search row")
one('''    concept98_move_v91(hMessageSearchPrev, nav_x, 82,
                       nav_width, 24);''',
'''    concept98_move_v91(hMessageSearchPrev, nav_x, 82+topic_row_v120,
                       nav_width, 24);''',"search previous row")
one('''    concept98_move_v91(hMessageSearchNext, nav_x+nav_width+1,
                       82, nav_width, 24);''',
'''    concept98_move_v91(hMessageSearchNext, nav_x+nav_width+1,
                       82+topic_row_v120, nav_width, 24);''',"search next row")
one('''    concept98_move_v91(hMediaArchiveButton,
                       content_x+content_w-media_width, 82,
                       media_width, 24);''',
'''    concept98_move_v91(hMediaArchiveButton,
                       content_x+content_w-media_width, 82+topic_row_v120,
                       media_width, 24);''',"media button row")
one('''                           status_x, 85, status_w, 20);''',
'''                           status_x, 85+topic_row_v120, status_w, 20);''',
"search status row")
one('''    concept98_move_v91(concept98_rule, content_x, 112,
                       content_w, 2);
    const int chat_y = 117;''',
'''    concept98_move_v91(concept98_rule, content_x, 112+topic_row_v120,
                       content_w, 2);
    const int chat_y = 117+topic_row_v120;''',"chat and rule shift")
# marshal to UI thread in the outer window procedure, before normal WM_COMMAND.
one('''    if (msg == WM_APP + 0x390) {
        concept98_sync();''',
'''    if (msg == WM_APP + 0x391) { // v120: socket -> UI thread
        concept98_forum_populate_v120();
        if(concept98_enabled)concept98_apply_layout(hWnd);
        return 0;
    }
    if (msg == WM_APP + 0x390) {
        concept98_sync();''',
"UI forum response message")
# Provide visibility diagnostic on native selection and dropdown.
one('''        case 8999: { // concept98 v119 real forum topic choice
            if(HIWORD(wParam)==CBN_SELCHANGE)
                concept98_forum_select_v119();
            break;
        }''',
'''        case 8999: { // concept98 v120 real forum topic choice
            diag_log("concept98 v120 dropdown notify=%d hwnd=%p",
                     HIWORD(wParam),(HWND)lParam);
            if((HWND)lParam==concept98_topic_combo_v119 &&
               HIWORD(wParam)==CBN_SELCHANGE)
                concept98_forum_select_v119();
            break;
        }''',"combobox WM_COMMAND")
# When the chat is not concept mode, ensure dropdown does not persist.
one('''    HWND extras[] = {
        concept98_list, concept98_filter, concept98_caption,''',
'''    HWND extras[] = {
        concept98_list, concept98_filter, concept98_caption,''',
"extras leading marker")
one('''    if (!concept98_enabled) {
        for (int i=0;i<(int)ARRAYSIZE(extras);++i)''',
'''    if (!concept98_enabled) {
        if(concept98_topic_combo_v119)
            ShowWindow(concept98_topic_combo_v119,SW_HIDE);
        for (int i=0;i<(int)ARRAYSIZE(extras);++i)''',
"disable concept layout")
# Media correctness: a sticker .webm is already the decoded static image.
# Old EN_LINK path treated its filename as a *video*, opening the same WebM.
one('''\t\t\t\t\tint media_kind = media_player_kind_from_path(documents[i].filename);''',
'''\t\t\t\t\tif (documents[i].photo_size == 1) {
                        // v120: inline stickers are static; no video autoplay,
                        // no ambiguous link activation and no stray downloads.
                        diag_log("concept98 v120 static sticker click ignored id=%I64d",
                                 (__int64)read_le(documents[i].id,8));
                        break;
                    }
                    int media_kind = media_player_kind_from_path(documents[i].filename);''',
"disable WebM sticker accidental video autoplay")
# Do not choose an unrelated video by guessing 288x216 around its OLE after
# history prepends. Accept only the exact character range.
sig='bool media_chat_video_handle_chat_mouse('
start=s.index(sig);end=s.index("\n}\n",start)+2
f=s[start:end]
a='''        // Fallback for RichEdit builds that return a nearby text character for
        // OLE content: the chat card is deliberately fixed at 112x84 at 96 DPI.'''
b='''        if (!hit)
            continue;'''
if a not in f or b not in f:raise SystemExit("video geometric fallback markers absent")
i=f.index(a);j=f.index(b,i)
f=f[:i]+'''        // concept98 v120: NEVER hit-test a guessed large rectangle for
        // another video. An incorrect match played the same file repeatedly.
        // If RichEdit text geometry is stale, require an exact OLE binding.
'''+f[j:]
s=s[:start]+f+s[end:]
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v12.0: latest forum topic auto-opens, separate visible selector, UI-thread sync; static sticker not auto-played, no geometric video mis-hits.")
