#!/usr/bin/env python3
"""Telegacy Concept 98 v9.6: repair avatar cache identity, retries and header.
Does not modify the Telegram decoder, chat document or socket transport.
"""
from pathlib import Path
import sys

if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_integrity_v96.py <Telegacy source>")
root=Path(sys.argv[1]).resolve()
cpp=root/"src"/"telegacy.cpp"
helpers=root/"src"/"helpers.cpp"

def load(p): return p.read_text(encoding="latin-1")
def store(p,s): p.write_text(s,encoding="latin-1",newline="\r\n")
def sub(s,old,new,label):
    if old not in s: raise SystemExit("Concept 98 v9.6 missing: "+label)
    return s.replace(old,new,1)
s=load(helpers)
if "concept98_integrity_v96" in s:
    print("Concept 98 v9.6 already applied")
    raise SystemExit(0)
begin=s.find("// Real Telegram avatar thumbs, separate from profile-gallery requests.")
end=s.find("void get_pfp(DCInfo* dcInfo, Peer* peer) {",begin)
if begin<0 or end<0: raise SystemExit("Could not locate avatar implementation")

replacement=r'''// concept98_integrity_v96
// Live avatars use the exact same MTProto request as get_pfp(), but with
// separate RPC IDs and a cache identity of (peer type, peer id, photo id).
// A failed request does NOT cause a permanent fallback to initials.
struct ConceptAvatar96 {
    HBITMAP bitmap;
    __int64 photo_id;
    DWORD last_use;
    DWORD next_retry;
    unsigned int failed;
    bool loading;
};
typedef std::pair<int, __int64> ConceptAvatar96Key;
static std::map<ConceptAvatar96Key, ConceptAvatar96> concept98_cache_v96;
static ConceptAvatar96Key concept98_pending_key_v96;
static BYTE concept98_pending_rpc_v96[8] = {0};
static bool concept98_pending_v96=false;
static DWORD concept98_pending_tick_v96=0;
static DWORD concept98_request_after_v96=0;

static ConceptAvatar96Key concept98_key_v96(const Peer* p) {
    return ConceptAvatar96Key(
        p ? (int)p->type : -1,
        p ? (__int64)read_le(p->id,8) : 0
    );
}
static DWORD concept98_delay_v96(unsigned int attempts) {
    // Avoid permanent misses and repeated requests to broken DCs.
    if (attempts>8) attempts=8;
    DWORD ms=5000u*(attempts+1);
    return ms>60000u ? 60000u : ms;
}
static void concept98_evict_v96() {
    if (concept98_cache_v96.size()<128) return;
    std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator oldest =
        concept98_cache_v96.end();
    for (std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it =
         concept98_cache_v96.begin(); it!=concept98_cache_v96.end(); ++it) {
        if (it->second.loading) continue;
        if (oldest==concept98_cache_v96.end() ||
            it->second.last_use < oldest->second.last_use)
            oldest=it;
    }
    if (oldest!=concept98_cache_v96.end()) {
        if (oldest->second.bitmap) DeleteObject(oldest->second.bitmap);
        concept98_cache_v96.erase(oldest);
    }
}
static void concept98_avatar_failure_v96(ConceptAvatar96Key key) {
    std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it =
        concept98_cache_v96.find(key);
    if (it==concept98_cache_v96.end()) return;
    it->second.loading=false;
    it->second.failed++;
    it->second.next_retry=GetTickCount()+
        concept98_delay_v96(it->second.failed);
}

bool concept98_dnd_active_v93() {
    int until=GetPrivateProfileIntW(
        L"Concept98",L"dnd_until",0,
        get_path(appdata_path,L"options.ini")
    );
    return until>current_time();
}
void concept98_dnd_set_v93(int minutes) {
    int until=minutes>0 ? current_time()+minutes*60 : 0;
    wchar_t value[32]={0};
    _snwprintf_s(value,ARRAYSIZE(value),_TRUNCATE,L"%d",until);
    WritePrivateProfileStringW(
        L"Concept98",L"dnd_until",value,
        get_path(appdata_path,L"options.ini")
    );
    // Existing toast closes on DND; the unread count remains untouched.
    diag_log("concept98 v96 DND minutes=%d until=%d",minutes,until);
}
void concept98_avatar_clear_v93() {
    for (std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it =
         concept98_cache_v96.begin(); it!=concept98_cache_v96.end(); ++it) {
        if (it->second.bitmap) DeleteObject(it->second.bitmap);
    }
    concept98_cache_v96.clear();
    concept98_pending_v96=false;
    memset(concept98_pending_rpc_v96,0,8);
}
bool concept98_avatar_draw_v93(HDC dc, Peer* peer, RECT dest) {
    if (!peer || !dc || !read_le(peer->id,8)) return false;
    ConceptAvatar96Key key=concept98_key_v96(peer);
    std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it =
        concept98_cache_v96.find(key);
    if (it==concept98_cache_v96.end() || !it->second.bitmap ||
        it->second.photo_id!=(__int64)read_le(peer->photo,8))
        return false;
    BITMAP bm={0};
    if (!GetObjectW(it->second.bitmap,sizeof(bm),&bm) ||
        bm.bmWidth<=0 || bm.bmHeight<=0) return false;
    HDC source=CreateCompatibleDC(dc);
    if (!source) return false;
    HGDIOBJ old=SelectObject(source,it->second.bitmap);
    SetStretchBltMode(dc,HALFTONE);
    bool painted=StretchBlt(dc,dest.left,dest.top,
        dest.right-dest.left,dest.bottom-dest.top,
        source,0,0,bm.bmWidth,bm.bmHeight,SRCCOPY)!=0;
    SelectObject(source,old);
    DeleteDC(source);
    it->second.last_use=GetTickCount();
    return painted;
}
static bool concept98_avatar_request_v96(Peer* peer) {
    if (!peer || !dcInfoMain.ready ||
        !read_le(peer->photo,8) || !read_le(peer->id,8)) return false;
    BYTE query[256]={0};
    BYTE encrypted[280]={0};
    internal_header(query,true);
    write_le(query+32,0xbe5335be,4);
    memset(query+36,0,4);
    write_le(query+40,0x37257e99,4);
    memset(query+44,0,4);
    int placed=place_peer(query+48,peer,true);
    if (placed<=0 || placed>152) return false;
    int offset=48+placed;
    memcpy(query+offset,peer->photo,8); offset+=8;
    memset(query+offset,0,8); offset+=8;
    write_le(query+offset,1048576,4); offset+=4;
    write_le(query+28,offset-32,4);
    int pad=get_padding(offset);
    if (pad<0 || offset+pad>256) return false;
    fortuna_read(query+offset,pad,&prng); offset+=pad;
    convert_message(query,encrypted,offset,0);
    concept98_pending_key_v96=concept98_key_v96(peer);
    memcpy(concept98_pending_rpc_v96,query+16,8);
    concept98_pending_v96=true;
    concept98_pending_tick_v96=GetTickCount();
    concept98_request_after_v96=GetTickCount()+1400;
    send_query(encrypted,offset+24);
    diag_log("concept98 v96 avatar request type=%d",peer->type);
    return true;
}

void concept98_avatar_pump_v93(
    HWND list, const std::vector<int>& mapping, bool global_mode
) {
    if (!concept98_enabled || !list || !IsWindowVisible(list) ||
        !dcInfoMain.ready) return;
    DWORD now=GetTickCount();
    if (concept98_pending_v96) {
        if (now-concept98_pending_tick_v96<12000) return;
        concept98_avatar_failure_v96(concept98_pending_key_v96);
        concept98_pending_v96=false;
        memset(concept98_pending_rpc_v96,0,8);
        diag_log("concept98 v96 avatar request timeout");
    }
    if ((LONG)(now-concept98_request_after_v96)<0) return;
    int count=(int)SendMessageW(list,LB_GETCOUNT,0,0);
    int top=(int)SendMessageW(list,LB_GETTOPINDEX,0,0);
    if (count<=0 || count>50000 || top<0) return;
    RECT box={0}; GetClientRect(list,&box);
    int row=(int)SendMessageW(list,LB_GETITEMHEIGHT,0,0);
    if (row<1) row=50;
    int visible=(box.bottom+row-1)/row+1;
    if (visible>32) visible=32;

    int selection=(int)SendMessageW(list,LB_GETCURSEL,0,0);
    for (int n=-2;n<visible;n++) {
        int slot=n==-2 ? selection : n==-1 ? -1 : top+n;
        Peer* peer=NULL;
        if (slot==-1) peer=current_peer;
        else if (slot>=0 && slot<count) {
            if (global_mode) {
                LRESULT value=SendMessageW(
                    hComboBoxChats,CB_GETITEMDATA,slot,0
                );
                if (value!=CB_ERR && value!=0) peer=(Peer*)value;
            } else if (current_folder && current_folder->peers &&
                       slot<(int)mapping.size()) {
                int folder_idx=mapping[slot];
                if (folder_idx>=0 && folder_idx<current_folder->count) {
                    int id=current_folder->peers[folder_idx];
                    if (id>=0 && id<peers_count) peer=&peers[id];
                }
            }
        }
        if (!peer || !read_le(peer->id,8) ||
            !read_le(peer->photo,8)) continue;
        ConceptAvatar96Key key=concept98_key_v96(peer);
        __int64 photo_id=(__int64)read_le(peer->photo,8);
        std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it =
            concept98_cache_v96.find(key);

        if (it!=concept98_cache_v96.end() &&
            it->second.photo_id!=photo_id) {
            if (it->second.bitmap) DeleteObject(it->second.bitmap);
            concept98_cache_v96.erase(it);
            it=concept98_cache_v96.end();
        }
        if (it==concept98_cache_v96.end()) {
            concept98_evict_v96();
            ConceptAvatar96 entry={0};
            entry.photo_id=photo_id;
            entry.last_use=now;
            concept98_cache_v96[key]=entry;
            it=concept98_cache_v96.find(key);
        }
        if (it->second.bitmap || it->second.loading ||
            (LONG)(now-it->second.next_retry)<0) continue;

        // Never mark an avatar permanently fetched unless the request
        // was sent. Explicit timeout/invalid JPEG results allow retry.
        if (concept98_avatar_request_v96(peer))
            it->second.loading=true;
        else
            it->second.next_retry=now+3000;
        return;
    }
}
bool concept98_avatar_handle_upload_v93(
    const BYTE* request_id, BYTE* response, int length
) {
    if (!concept98_pending_v96 || !request_id ||
        memcmp(request_id,concept98_pending_rpc_v96,8)!=0)
        return false;
    ConceptAvatar96Key key=concept98_pending_key_v96;
    concept98_pending_v96=false;
    memset(concept98_pending_rpc_v96,0,8);
    if (!response || length<17) {
        concept98_avatar_failure_v96(key);
        return true;
    }
    int bytes=(int)tlstr_len(response+12,false);
    int header=bytes>=254 ? 4 : 1;
    if (bytes<4 || bytes>1048576 ||
        bytes>length-12-header) {
        concept98_avatar_failure_v96(key);
        diag_log("concept98 v96 rejected avatar bytes=%d length=%d",
                 bytes,length);
        return true;
    }
    HBITMAP original=jpg_to_bmp(response+12+header,bytes);
    if (!original) {
        concept98_avatar_failure_v96(key);
        return true;
    }
    BITMAP bm={0};
    if (!GetObjectW(original,sizeof(bm),&bm) ||
        bm.bmWidth<1 || bm.bmHeight<1 ||
        bm.bmWidth>8192 || bm.bmHeight>8192) {
        DeleteObject(original);
        concept98_avatar_failure_v96(key);
        return true;
    }
    HDC screen=GetDC(NULL);
    HDC src=screen ? CreateCompatibleDC(screen) : NULL;
    HDC dst=screen ? CreateCompatibleDC(screen) : NULL;
    HBITMAP thumb=screen ? CreateCompatibleBitmap(screen,40,40):NULL;
    bool rendered=false;
    if (src && dst && thumb) {
        HGDIOBJ was_src=SelectObject(src,original);
        HGDIOBJ was_dst=SelectObject(dst,thumb);
        SetStretchBltMode(dst,HALFTONE);
        rendered=StretchBlt(dst,0,0,40,40,
             src,0,0,bm.bmWidth,bm.bmHeight,SRCCOPY)!=0;
        SelectObject(src,was_src);
        SelectObject(dst,was_dst);
    }
    if (src) DeleteDC(src);
    if (dst) DeleteDC(dst);
    if (screen) ReleaseDC(NULL,screen);
    DeleteObject(original);
    if (!rendered) {
        if (thumb) DeleteObject(thumb);
        concept98_avatar_failure_v96(key);
        return true;
    }
    std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it =
         concept98_cache_v96.find(key);
    if (it==concept98_cache_v96.end()) {
        DeleteObject(thumb);
        return true;
    }
    if (it->second.bitmap) DeleteObject(it->second.bitmap);
    it->second.bitmap=thumb;
    it->second.loading=false;
    it->second.failed=0;
    it->second.last_use=GetTickCount();
    HWND list=hMain ? GetDlgItem(hMain,8910) : NULL;
    HWND header=hMain ? GetDlgItem(hMain,8996) : NULL;
    if (list) InvalidateRect(list,NULL,FALSE);
    if (header) InvalidateRect(header,NULL,FALSE);
    diag_log("concept98 v96 avatar ready type=%d bytes=%d",
             key.first,bytes);
    return true;
}

'''
s=s[:begin]+replacement+s[end:]
store(helpers,s)

s=load(cpp)
if "concept98_real_avatars_v93" not in s or \
   "concept98_pixel_icons_v95" not in s:
    raise SystemExit("Concept 98 v9.5 runtime missing")

# Add one owner-draw static to the standard chat header.
needle="static bool concept98_draw_row("
glyph=r'''// concept98_integrity_v96: current chat avatar, with a clean initials fallback.
static bool concept98_draw_header_v96(const DRAWITEMSTRUCT* dis) {
    if (!dis || dis->CtlID!=8996) return false;
    HDC dc=dis->hDC;
    RECT rc=dis->rcItem;
    HBRUSH back=CreateSolidBrush(GetSysColor(COLOR_BTNFACE));
    FillRect(dc,&rc,back);
    DeleteObject(back);
    RECT tile={rc.left+2,rc.top+2,rc.right-2,rc.bottom-2};
    if (!concept98_avatar_draw_v93(dc,current_peer,tile)) {
        HBRUSH face=CreateSolidBrush(RGB(68,104,134));
        FillRect(dc,&tile,face);
        DeleteObject(face);
        if (current_peer && current_peer->name &&
            current_peer->name[0]) {
            wchar_t initials[2]={current_peer->name[0],0};
            int old=SetBkMode(dc,TRANSPARENT);
            SetTextColor(dc,RGB(255,255,255));
            DrawTextW(dc,initials,-1,&tile,
                      DT_SINGLELINE|DT_CENTER|DT_VCENTER);
            SetBkMode(dc,old);
        }
    }
    DrawEdge(dc,&tile,EDGE_SUNKEN,BF_RECT);
    return true;
}

'''
s=sub(s,"static DWORD concept98_previous_badge_hash_v91 = 0;",
      "static HWND concept98_header_avatar_v96=NULL;\nstatic DWORD concept98_previous_badge_hash_v91 = 0;",
      "early chat-avatar declaration")
s=sub(s,needle,glyph+needle,"header render anchor")
old="        concept98_chat_title, concept98_chat_detail,\n"
s=sub(s,old,old+"        concept98_header_avatar_v96,\n","layout controls")
old='    concept98_move_v91(concept98_chat_title, content_x, 30,\n                       title_w, 26);\n    concept98_move_v91(concept98_chat_detail, content_x, 57,\n                       title_w, 17);'
new='    concept98_move_v91(concept98_header_avatar_v96,\n                       content_x,34,38,38);\n    concept98_move_v91(concept98_chat_title, content_x+46, 30,\n                       title_w-46, 26);\n    concept98_move_v91(concept98_chat_detail, content_x+46, 57,\n                       title_w-46, 17);'
s=sub(s,old,new,"chat header layout")
old='    concept98_chat_title = CreateWindowW('
new=r'''    concept98_header_avatar_v96=CreateWindowW(
        L"STATIC",L"",panel | SS_OWNERDRAW,
        250,34,38,38,hwnd,(HMENU)8996,NULL,NULL
    );
    concept98_chat_title = CreateWindowW('''
s=sub(s,old,new,"header creation")
old='if (concept98_enabled && concept98_action_button_v95(lpdis)) return TRUE;'
s=sub(s,old,'if (concept98_enabled && concept98_draw_header_v96(lpdis)) return TRUE;\n\t\t'+old,"header draw routing")
old='    if (current_peer && current_peer->name) {'
s=sub(s,old,'    if (concept98_header_avatar_v96)\n        InvalidateRect(concept98_header_avatar_v96,NULL,FALSE);\n    if (current_peer && current_peer->name) {',
      "header peer synchronization")
store(cpp,s)
for p,tokens in {
    helpers:("concept98_integrity_v96","concept98_avatar_failure_v96",
             "concept98_avatar_request_v96","concept98_avatar_pump_v93",
             "concept98_avatar_handle_upload_v93"),
    cpp:("concept98_integrity_v96","concept98_header_avatar_v96",
         "concept98_draw_header_v96","(HMENU)8996")
}.items():
    generated=load(p)
    for t in tokens:
        if t not in generated: raise SystemExit(f"Missing {t} in {p}")
print("Applied v9.6: avatar cache photo-aware, retries and timeouts, global "
      "results avatars, live chat header photo with initials fallback.")
