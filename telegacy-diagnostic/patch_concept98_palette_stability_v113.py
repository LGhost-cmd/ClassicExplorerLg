#!/usr/bin/env python3
"""Concept98 v11.3: restore the active Telegacy palette, original Chats icon,
and avoid repeated RichEdit background resets / redundant header paints.
No photo transport, message indexing, or OLE replacement changes.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_palette_stability_v113.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_palette_stability_v113" in s:
    print("v11.3 already applied");raise SystemExit(0)
if "concept98_shell_polish_v110" not in s:raise SystemExit("requires shell v11.0")
def once(a,b,why):
    global s
    n=s.count(a)
    if n!=1:raise SystemExit("v11.3 expected one %s, got %d"%(why,n))
    s=s.replace(a,b,1)
old=r'''    // concept98_shell_polish_v110
    // The chat and editor are kept on a warm, high-contrast Windows paper
    // background. No gradients, glass effects, rounded cards or custom scrollbars.
    if (chat) SendMessageW(chat,EM_SETBKGNDCOLOR,0,
                           (LPARAM)RGB(247,246,242));
    if (msgInput) SendMessageW(msgInput,EM_SETBKGNDCOLOR,0,
                               (LPARAM)RGB(250,249,245));'''
new=r'''    // concept98_palette_stability_v113
    // Restore Telegacy's actual theme paper color. Applying it on EVERY
    // layout call invalidated both RichEdit controls and caused white flashes.
    // Cache per-HWND/color so resize, chat switches and 1.8s sync are no-ops.
    static HWND styled_chat=NULL,styled_editor=NULL;
    static COLORREF previous_chat=(COLORREF)-1,previous_editor=(COLORREF)-1;
    if (concept98_enabled && chat && IsWindow(chat) &&
        (chat!=styled_chat || colors[1]!=previous_chat)) {
        SendMessageW(chat,EM_SETBKGNDCOLOR,0,(LPARAM)colors[1]);
        styled_chat=chat;previous_chat=colors[1];
    }
    if (concept98_enabled && msgInput && IsWindow(msgInput) &&
        (msgInput!=styled_editor || colors[1]!=previous_editor)) {
        SendMessageW(msgInput,EM_SETBKGNDCOLOR,0,(LPARAM)colors[1]);
        styled_editor=msgInput;previous_editor=colors[1];
    }'''
once(old,new,"theme color block")
# Respect Win98 icon package that ALREADY ships chats.ico.
old='''        {8914,L"options.ico",NULL,false}
'''
new='''        {8914,L"options.ico",NULL,false},
        {8915,L"chats.ico",NULL,false}
'''
once(old,new,"icons98 slot")
once('''        (WPARAM)LoadIconW(NULL, IDI_APPLICATION), 0
''','''        (WPARAM)(concept98_asset_icon_v107(8915)
            ? concept98_asset_icon_v107(8915)
            : LoadIconW(NULL, IDI_APPLICATION)), 0
''',"sidebar chats icon")
# Frequent conceptual sync used to invalidate header even though selection did not
# change. The existing avatar cache invalidates the header WHEN an image arrives.
old='''    if (concept98_header_avatar_v96)
        InvalidateRect(concept98_header_avatar_v96,NULL,FALSE);
    if (current_peer && current_peer->name) {'''
new='''    static int avatar_peer_type_v113=-1;
    static __int64 avatar_peer_id_v113=0;
    static __int64 avatar_photo_id_v113=0;
    int active_type=current_peer ? current_peer->type : -1;
    __int64 active_id=current_peer ?
        (__int64)read_le(current_peer->id,8) : 0;
    __int64 photo_id=current_peer ?
        (__int64)read_le(current_peer->photo,8) : 0;
    if (active_type!=avatar_peer_type_v113 ||
        active_id!=avatar_peer_id_v113 ||
        photo_id!=avatar_photo_id_v113) {
        avatar_peer_type_v113=active_type;
        avatar_peer_id_v113=active_id;
        avatar_photo_id_v113=photo_id;
        if (concept98_header_avatar_v96)
            InvalidateRect(concept98_header_avatar_v96,NULL,FALSE);
    }
    if (current_peer && current_peer->name) {'''
once(old,new,"header invalidation")
# Don't repaint the app's entire client area while moving its RichEdit child.
# This is a parent-only style; it doesn't affect clipping between the controls.
old='''    SetTimer(hwnd, CONCEPT98_TIMER, 1800, NULL);
    SetTimer(hwnd, 8998, 240, NULL);'''
new='''    SetWindowLongPtrW(hwnd,GWL_STYLE,
        GetWindowLongPtrW(hwnd,GWL_STYLE)|WS_CLIPCHILDREN);
    SetTimer(hwnd, CONCEPT98_TIMER, 1800, NULL);
    SetTimer(hwnd, 8998, 240, NULL);'''
once(old,new,"clip child redraw")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("Concept98 v11.3: theme-colored chat, no per-layout RichEdit erase, bundled chats.ico, stable avatar paints.")
