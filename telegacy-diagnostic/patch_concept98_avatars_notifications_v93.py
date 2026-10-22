#!/usr/bin/env python3
"""Telegacy Concept 98 v9.3: bounded real avatar cache and notification controls."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_concept98_avatars_notifications_v93.py <Telegacy src>")

root=Path(sys.argv[1]).resolve()
t=root/"src"/"telegacy.cpp"
h=root/"src"/"helpers.cpp"
r=root/"src"/"response.cpp"
header=root/"include"/"telegacy.h"

def read(p): return p.read_text(encoding="latin-1")
def save(p,s): p.write_text(s,encoding="latin-1",newline="\r\n")
def one(s,old,new,label):
    if old not in s: raise SystemExit("v9.3 missing "+label)
    return s.replace(old,new,1)

s=read(t)
if "concept98_real_avatars_v93" in s:
    print("Concept 98 v9.3 already applied"); raise SystemExit(0)
if "concept98_interactions_v92" not in s:
    raise SystemExit("v9.2 prerequisite missing")

api=r'''
// concept98_real_avatars_v93
void concept98_avatar_pump_v93(HWND list, const std::vector<int>& mapping, bool global_mode);
bool concept98_avatar_draw_v93(HDC dc, Peer* peer, RECT bounds);
bool concept98_avatar_handle_upload_v93(
    const BYTE* msgid, BYTE* response, int length
);
void concept98_avatar_clear_v93();
bool concept98_dnd_active_v93();
void concept98_dnd_set_v93(int minutes);
'''

hs=read(header)
hs=one(hs,"extern bool concept98_enabled; // concept98_shell_v90",
       "extern bool concept98_enabled; // concept98_shell_v90\n"+api,
       "header concept state")
save(header,hs)

helpers=read(h)
helpers=one(helpers,"#include <telegacy.h>\n",
            "#include <telegacy.h>\n#include <map>\n",
            "helper include")
at=helpers.index("void get_pfp(DCInfo* dcInfo, Peer* peer) {")
code=r'''// Real Telegram avatar thumbs, separate from profile-gallery requests.
struct ConceptAvatar93 {
    HBITMAP image;
    DWORD last_use;
    bool unavailable;
};
static std::map<__int64, ConceptAvatar93> concept98_avatars_v93;
static BYTE concept98_avatar_msgid_v93[8] = {0};
static __int64 concept98_avatar_pending_id_v93 = 0;
static DWORD concept98_avatar_pending_tick_v93 = 0;
static DWORD concept98_avatar_next_request_v93 = 0;

bool concept98_dnd_active_v93() {
    int until=GetPrivateProfileIntW(
        L"Concept98", L"dnd_until", 0,
        get_path(appdata_path,L"options.ini")
    );
    return until > current_time();
}

void concept98_dnd_set_v93(int minutes) {
    int until = minutes > 0 ? current_time()+minutes*60 : 0;
    wchar_t value[32] = {0};
    _snwprintf_s(value, ARRAYSIZE(value), _TRUNCATE, L"%d", until);
    WritePrivateProfileStringW(
        L"Concept98", L"dnd_until", value,
        get_path(appdata_path,L"options.ini")
    );
    diag_log("concept98 v93 DND minutes=%d", minutes);
}

void concept98_avatar_clear_v93() {
    for (std::map<__int64,ConceptAvatar93>::iterator it =
        concept98_avatars_v93.begin();
        it != concept98_avatars_v93.end(); ++it) {
        if (it->second.image) DeleteObject(it->second.image);
    }
    concept98_avatars_v93.clear();
    concept98_avatar_pending_id_v93 = 0;
    memset(concept98_avatar_msgid_v93,0,sizeof(concept98_avatar_msgid_v93));
}

bool concept98_avatar_draw_v93(
    HDC dc, Peer* peer, RECT dest
) {
    if (!peer || !dc) return false;
    __int64 id = (__int64)read_le(peer->id,8);
    std::map<__int64,ConceptAvatar93>::iterator it =
        concept98_avatars_v93.find(id);
    if (it == concept98_avatars_v93.end() || !it->second.image)
        return false;

    HDC src = CreateCompatibleDC(dc);
    if (!src) return false;
    HGDIOBJ old = SelectObject(src,it->second.image);
    BITMAP bm = {0};
    bool drawn=false;
    if (GetObjectW(it->second.image,sizeof(bm),&bm) &&
        bm.bmWidth>0 && bm.bmHeight>0) {
        SetStretchBltMode(dc,HALFTONE);
        drawn = StretchBlt(
            dc,dest.left,dest.top,
            dest.right-dest.left,dest.bottom-dest.top,
            src,0,0,bm.bmWidth,bm.bmHeight,SRCCOPY
        ) != 0;
    }
    SelectObject(src,old);
    DeleteDC(src);
    it->second.last_use=GetTickCount();
    return drawn;
}

static void concept98_avatar_request_v93(Peer* peer) {
    if (!peer || !dcInfoMain.ready ||
        !read_le(peer->photo,8) || !read_le(peer->id,8))
        return;

    BYTE unenc_query[256]={0};
    BYTE enc_query[280]={0};
    internal_header(unenc_query,true);
    write_le(unenc_query+32,0xbe5335be,4);
    memset(unenc_query+36,0,4);
    write_le(unenc_query+40,0x37257e99,4);
    memset(unenc_query+44,0,4);
    int offset=48+place_peer(unenc_query+48,(Peer*)peer,true);
    if (offset>210 || offset<48) return;
    memcpy(unenc_query+offset,peer->photo,8);
    offset+=8;
    memset(unenc_query+offset,0,8);
    offset+=8;
    write_le(unenc_query+offset,1048576,4);
    offset+=4;
    write_le(unenc_query+28,offset-32,4);
    int pad=get_padding(offset);
    if (pad<0 || offset+pad>256) return;
    fortuna_read(unenc_query+offset,pad,&prng);
    offset+=pad;
    convert_message(unenc_query,enc_query,offset,0);
    concept98_avatar_pending_id_v93 = (__int64)read_le(peer->id,8);
    memcpy(concept98_avatar_msgid_v93,unenc_query+16,8);
    concept98_avatar_pending_tick_v93=GetTickCount();
    concept98_avatar_next_request_v93=GetTickCount()+1700;
    send_query(enc_query,offset+24);
}

void concept98_avatar_pump_v93(HWND list, const std::vector<int>& mapping, bool global_mode) {
    if (!concept98_enabled || global_mode || !list ||
        !IsWindowVisible(list) || !current_folder ||
        !current_folder->peers || !peers)
        return;

    DWORD now=GetTickCount();
    if (concept98_avatar_pending_id_v93) {
        if (now-concept98_avatar_pending_tick_v93<11000)
            return;
        // Abandon this request id; a delayed RPC can no longer poison a
        // newer profile request or another chat avatar.
        concept98_avatar_pending_id_v93=0;
        memset(concept98_avatar_msgid_v93,0,8);
    }
    if ((LONG)(now-concept98_avatar_next_request_v93)<0)
        return;

    int top=(int)SendMessageW(list,LB_GETTOPINDEX,0,0);
    int count=(int)SendMessageW(list,LB_GETCOUNT,0,0);
    if (top<0 || count<=0 || count>50000) return;
    RECT box={0};
    GetClientRect(list,&box);
    int row=(int)SendMessageW(list,LB_GETITEMHEIGHT,0,0);
    if (row<=0) row=50;
    int visible=(box.bottom+row-1)/row+1;
    if (visible>32) visible=32;

    // Selection is important even if offscreen; most-recent visible rows
    // are requested first. This code intentionally does not fetch 381
    // avatars en masse.
    int selection=(int)SendMessageW(list,LB_GETCURSEL,0,0);
    for (int n=-1;n<visible;n++) {
        int slot=(n<0) ? selection : top+n;
        if (slot<0 || slot>=count) continue;
        // Local owner-draw rows keep a mapping to the source folder.
        Peer* peer = NULL;
        if (n<0) {
            peer=current_peer;
        } else if (slot<(int)mapping.size()) {
            int folder_slot=mapping[slot];
            if (folder_slot>=0 &&
                folder_slot<current_folder->count) {
                int id=current_folder->peers[folder_slot];
                if (id>=0 && id<peers_count) peer=&peers[id];
            }
        }
        if (!peer) continue;
        __int64 id=(__int64)read_le(peer->id,8);
        if (!id || !read_le(peer->photo,8)) continue;
        if (concept98_avatars_v93.count(id)) continue;
        if (concept98_avatars_v93.size()>96) {
            std::map<__int64,ConceptAvatar93>::iterator old =
                concept98_avatars_v93.begin();
            if (old->second.image) DeleteObject(old->second.image);
            concept98_avatars_v93.erase(old);
        }
        ConceptAvatar93 state={0};
        state.last_use=now;
        state.unavailable=false;
        concept98_avatars_v93[id]=state;
        concept98_avatar_request_v93(peer);
        return;
    }
}

// Called from upload.file before the document parser. It consumes ONLY the
// request id generated by concept98_avatar_request_v93.
bool concept98_avatar_handle_upload_v93(
    const BYTE* request_id, BYTE* response, int length
) {
    if (!concept98_avatar_pending_id_v93 || !request_id ||
        memcmp(request_id,concept98_avatar_msgid_v93,8)!=0)
        return false;

    __int64 id=concept98_avatar_pending_id_v93;
    concept98_avatar_pending_id_v93=0;
    memset(concept98_avatar_msgid_v93,0,8);
    if (!response || length<17) return true;

    int bytes=(int)tlstr_len(response+12,false);
    int header_bytes=bytes>=254 ? 4 : 1;
    if (bytes<4 || bytes>1048576 ||
        bytes+12+header_bytes>length) {
        diag_log("concept98 v93 avatar discarded malformed bytes=%d",bytes);
        return true;
    }

    HBITMAP original=jpg_to_bmp(
        response+12+header_bytes,bytes
    );
    if (!original) return true;

    BITMAP bm={0};
    if (!GetObjectW(original,sizeof(bm),&bm) ||
        bm.bmWidth<=0 || bm.bmHeight<=0 ||
        bm.bmWidth>8192 || bm.bmHeight>8192) {
        DeleteObject(original);
        return true;
    }

    HDC screen=GetDC(NULL);
    if (!screen) { DeleteObject(original); return true; }
    HDC src=CreateCompatibleDC(screen);
    HDC dst=CreateCompatibleDC(screen);
    HBITMAP small=CreateCompatibleBitmap(screen,40,40);
    HGDIOBJ oldsrc=NULL;
    HGDIOBJ olddst=NULL;
    bool rendered=false;
    if (src && dst && small) {
        oldsrc=SelectObject(src,original);
        olddst=SelectObject(dst,small);
        SetStretchBltMode(dst,HALFTONE);
        rendered = StretchBlt(dst,0,0,40,40,src,
                              0,0,bm.bmWidth,bm.bmHeight,SRCCOPY)!=0;
    }
    if (oldsrc) SelectObject(src,oldsrc);
    if (olddst) SelectObject(dst,olddst);
    if (src) DeleteDC(src);
    if (dst) DeleteDC(dst);
    ReleaseDC(NULL,screen);
    DeleteObject(original);
    if (!rendered) {
        if (small) DeleteObject(small);
        return true;
    }

    std::map<__int64,ConceptAvatar93>::iterator it =
        concept98_avatars_v93.find(id);
    if (it==concept98_avatars_v93.end()) {
        DeleteObject(small);
        return true;
    }
    if (it->second.image) DeleteObject(it->second.image);
    it->second.image=small;
    it->second.last_use=GetTickCount();
    if (concept98_list && IsWindow(concept98_list))
        InvalidateRect(concept98_list,NULL,FALSE);
    diag_log("concept98 v93 avatar loaded id=%I64d bytes=%d",
             id,bytes);
    return true;
}

'''
# change references to concept98_list, global mode which are static telegacy.cpp
# via list HWND passed from caller; handle upload repaints using exported HWND.
code=code.replace("    if (global_chat_search_mode) continue;","    if (SendMessageW(hChatScopeTabs,TCM_GETCURSEL,0,0)==1) continue;")
code=code.replace("    if (concept98_list && IsWindow(concept98_list))\n        InvalidateRect(concept98_list,NULL,FALSE);",
                  "    if (hMain && IsWindow(hMain))\n        PostMessageW(hMain,WM_APP+0x390,0,0);")
helpers=helpers[:at]+code+helpers[at:]
save(h,helpers)

# The explicit response RPC binding avoids grabbing other user-photo/gallery
# responses; the peer profile pipeline is unchanged.
resp=read(r)
resp=one(resp,"case 0x96a18d5: { // upload.file",
              "case 0x96a18d5: { // upload.file\n"
              "\t\tif (concept98_avatar_handle_upload_v93("
              "last_rpcresult_msgid,unenc_response,length)) break;",
              "upload.file avatar callback")
save(r,resp)

# A visual avatar is preferred; initials remain a genuine fallback.
old=r'''    HBRUSH tile_brush = CreateSolidBrush(category_color);
    FillRect(dc, &avatar, tile_brush);
    DeleteObject(tile_brush);
    DrawEdge(dc, &avatar, EDGE_SUNKEN, BF_RECT);

    HFONT oldfont = (HFONT)SelectObject(dc, hFonts[2]);'''
new=r'''    bool avatar_found = concept98_avatar_draw_v93(
        dc,peer,avatar
    );
    if (!avatar_found) {
        HBRUSH tile_brush = CreateSolidBrush(category_color);
        FillRect(dc, &avatar, tile_brush);
        DeleteObject(tile_brush);
    }
    DrawEdge(dc, &avatar, EDGE_SUNKEN, BF_RECT);

    HFONT oldfont = (HFONT)SelectObject(dc, hFonts[2]);'''
s=one(s,old,new,"owner draw avatar")
s=one(s,'    DrawTextW(dc, initials, -1, &avatar,\n              DT_SINGLELINE | DT_CENTER | DT_VCENTER);',
        '    if (!avatar_found)\n        DrawTextW(dc, initials, -1, &avatar,\n                  DT_SINGLELINE | DT_CENTER | DT_VCENTER);',
        "avatar fallback initials")
s=one(s,'        concept98_sync();\n        if (concept98_enabled &&',
        '        concept98_sync();\n        concept98_avatar_pump_v93(concept98_list,concept98_folder_indices,global_chat_search_mode);\n        if (concept98_enabled &&',
        "avatar pump timer")
s=one(s,'\t\tKillTimer(hWnd, CONCEPT98_TIMER);',
        '\t\tKillTimer(hWnd, CONCEPT98_TIMER);\n'
        '\t\tconcept98_avatar_clear_v93();',
        "avatar cleanup")
# Create a useful system icon for the sidebar: use the Windows shell's
# own icon; no Microsoft icon binaries are copied into this repository.
s=one(s,
    '''    SendMessageW(
        concept98_brand_icon_v91, STM_SETICON,
        (WPARAM)LoadIconW(
            GetModuleHandleW(NULL), MAKEINTRESOURCEW(IDI_ICON)
        ), 0
    );''',
    '''    SendMessageW(
        concept98_brand_icon_v91, STM_SETICON,
        (WPARAM)LoadIconW(NULL, IDI_APPLICATION), 0
    );''',
    "native icon")
# Timer keeps a cached DND status without triggering a repaint every frame.
s=one(s,
    '    diag_log("concept98 v91 created split-pane classic shell");',
    '    diag_log("concept98 v91 created split-pane classic shell");\n'
    '    diag_log("concept98 v93 avatar caching and DND available");',
    "v93 creation log")
# Menu command to toggle DND locally without disabling unread counters.
s=one(s,
   '    if (msg == WM_COMMAND && LOWORD(wParam) == 8915) {',
   r'''    if (msg == WM_COMMAND && LOWORD(wParam) == 8991) {
        concept98_dnd_set_v93(
            concept98_dnd_active_v93() ? 0 : 60
        );
        return 0;
    }
    if (msg == WM_COMMAND && LOWORD(wParam) == 8915) {''',
   "DND command")
s=one(s,
    '    SetTimer(hwnd, CONCEPT98_TIMER, 1800, NULL);',
    r'''    HMENU notify_tools = GetSubMenu(hMenuBar,2);
    if (notify_tools) {
        AppendMenuW(notify_tools,MF_STRING,8991,
                    L"\x041d\x0435 \x0431\x0435\x0441\x043f\x043e\x043a\x043e\x0438\x0442\x044c (60 \x043c\x0438\x043d.)");
    }
    SetTimer(hwnd, CONCEPT98_TIMER, 1800, NULL);''',
    "DND tools menu")

save(t,s)

# Distinct Hide/Close and DND controls in actual popup.
notif=read(h)
notif=one(notif,
    '''void remove_notification() {
	if (balloon_notifications) {''',
    '''void remove_notification() {
	if (current_notification && IsWindow(current_notification)) {
		DestroyWindow(current_notification);
		current_notification = NULL;
	} else if (balloon_notifications) {''',
    "always destroy concept popup before system balloon")
notif=one(notif,
    '''    if (concept98_enabled && msg == WM_COMMAND) {
        if (LOWORD(wParam) == 1 || LOWORD(wParam) == 2) {''',
    r'''    if (concept98_enabled && msg == WM_COMMAND) {
        if (LOWORD(wParam) == 3) {
            remove_notification();
            return TRUE;
        }
        if (LOWORD(wParam) == 4) {
            concept98_dnd_set_v93(60);
            remove_notification();
            return TRUE;
        }
        if (LOWORD(wParam) == 1 || LOWORD(wParam) == 2) {''',
    "notification command")
notif=one(notif,
    '''        HWND text_controls[] = {
            title, body, button_reply, button_open
        };''',
    r'''        HWND hide = CreateWindowW(
            L"BUTTON", L"\x0421\x043a\x0440\x044b\x0442\x044c",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            54, 150, 110, 24, hDlg,(HMENU)3,NULL,NULL
        );
        HWND dnd = CreateWindowW(
            L"BUTTON", L"\x041d\x0435 \x0431\x0435\x0441\x043f\x043e\x043a\x043e\x0438\x0442\x044c",
            WS_VISIBLE | WS_CHILD | BS_PUSHBUTTON,
            172,150,186,24,hDlg,(HMENU)4,NULL,NULL
        );
        HWND text_controls[] = {
            title, body, button_reply, button_open, hide, dnd
        };''',
    "hide and DND buttons")
notif=one(notif,"        const int h = 182;","        const int h = 214;",
    "popup height")
notif=one(notif,
    '''    if (concept98_enabled && msg == WM_CLOSE) {
        remove_notification();
        return TRUE;
    }''',
    '''    if (concept98_enabled && msg == WM_CLOSE) {
        remove_notification();
        return TRUE;
    }''',
    "notification close verification") if False else notif

# Suppress toast + sound during DND without dropping unread counters.
anchor="void new_msg_notification(Peer* peer, BYTE* msg_bytes, bool groupmed) {\n"
if anchor not in notif:raise SystemExit("new_msg_notification missing")
notif=notif.replace(anchor,anchor+r'''    if (concept98_enabled && concept98_dnd_active_v93()) {
        if (!peer || memcmp(peer->id,myself.id,8)==0) return;
        if (!peer->mute_until && !muted_types[peer->type])
            update_total_unread_msgs_count(1);
        peer->unread_msgs_count++;
        return;
    }
''',1)
save(h,notif)

for path,markers in {
    t:["concept98_real_avatars_v93","concept98_avatar_pump_v93","concept98_avatar_draw_v93","concept98_dnd_set_v93"],
    h:["concept98_avatar_handle_upload_v93","concept98_dnd_active_v93"],
    r:["concept98_avatar_handle_upload_v93"],
    header:["concept98_avatar_draw_v93"]
}.items():
    s=read(path)
    for marker in markers:
        if marker not in s:raise SystemExit("Missing v93 marker %s in %s"%(marker,path.name))

print("Concept 98 v9.3 applied: bounded avatars, native system icon, "
      "close/hide DND notifications with preserved unread counts.")
