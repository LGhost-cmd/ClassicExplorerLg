#!/usr/bin/env python3
"""Concept98 v12.4: page media staging, cache-first rendering, reliable click.
All message-photo cache readers use the same normalized path. New history pages
are masked behind a native loading surface until photos finish or bounded
timeout; the existing serial Telegram fetcher remains asynchronous.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_page_stage_v124.py <src>")
root=Path(sys.argv[1]).resolve()
t=root/"src"/"telegacy.cpp"
m=root/"src"/"message.cpp"
r=root/"src"/"response.cpp"
s=t.read_text(encoding="latin-1")
a=m.read_text(encoding="latin-1")
b=r.read_text(encoding="latin-1")
if "concept98_page_stage_v124" in s: raise SystemExit(0)
if "concept98_photo_reply_v123" not in s: raise SystemExit("v12.3 required")
def rep(v,old,new,label):
 n=v.count(old)
 if n!=1: raise SystemExit("v12.4 %s: count=%d"%(label,n))
 return v.replace(old,new,1)

# The old v10.8 loader silently searches APPDATA\Telegacy\\photo_cache98
# while v12.3 WRITES to APPDATA\Telegacy\photo_cache98.
a=rep(a,r'''        L"%s\\photo_cache98\\%016I64X-%016I64X-%016I64X.jpg",''',
        r'''        L"%sphoto_cache98\\%016I64X-%016I64X-%016I64X.jpg",''',
        "cache-first path")

# Register a full JPEG injected directly during message rendering.  The image
# is already present; there is no reason to run the asynchronous OLE swap.
a=rep(a,'#include <telegacy.h>',
'''#include <telegacy.h>
extern void concept98_note_cached_rendered_v124(const Document*);''',
"cache-first note declaration")
a=rep(a,'bool added_doc = false, added_photo = false;',
'''bool added_doc = false, added_photo = false;
    bool concept98_cached_rendered_v124=false;''',
"cache-first local")
a=rep(a,'''			if (cached_card) {
				display_bitmap=cached_card;
			} else {''',
'''			if (cached_card) {
				display_bitmap=cached_card;
                concept98_cached_rendered_v124=true;
			} else {''',
"cached full bitmap tracking")
a=rep(a,'''		if (added_doc) {
			if (to_front) documents.push_front(document);
			else documents.push_back(document);
		}
		if (added_video_thumb) {''',
'''		if (added_doc) {
			if (to_front) documents.push_front(document);
			else documents.push_back(document);
            if (concept98_cached_rendered_v124) {
                const Document* inserted = to_front ?
                    &documents.front() : &documents.back();
                concept98_note_cached_rendered_v124(inserted);
            }
		}
		if (added_video_thumb) {''',
"cache-first full registration")

# Media double-click may open the already downloaded local original directly.
# A single click must never be a no-op just because its previous OLE full flag
# is set; that flag does not prove what RichEdit currently displays.
s=rep(s,'''    if (
        already_full &&
        !save_and_open
    ) {
        diag_log(
            "chat v81 full photo already loaded; single click ignored"
        );
        return true;
    }



    media_chat_v87_capture_photo_ole(document);
    if (!save_and_open && !media_chat_v81_photo_is_full(document)) {''',
'''    // concept98_page_stage_v124: cached JPEG means instant local open or
    // a verified exact-OLE refresh. Never suppress a user click merely
    // because a previous Document pointer was marked full.
    if(save_and_open){
        std::vector<BYTE> local;
        if(concept98_full_photo_load_v101(document,&local)){
            wchar_t path[MAX_PATH]={0};
            if(concept98_full_photo_path_v101(document->id,
                document->access_hash,path,ARRAYSIZE(path))){
                HINSTANCE opened=ShellExecuteW(hMain,L"open",path,
                                              NULL,NULL,SW_SHOWNORMAL);
                if((INT_PTR)opened>32){
                    diag_log("concept98 v124 double-click opened cached JPEG");
                    return true;
                }
            }
        }
    }
    media_chat_v87_capture_photo_ole(document);
    if (!save_and_open) {''',
"remove stale full-click suppression")
# The page scanner uses a one-request-at-a-time transfer. It must not be
# stopped just because we mask the RichEdit with a separate sibling control.
decl='''static void media_chat_v81_mark_photo_full(
    const Document* document
) {'''
pos=s.find(decl)
if pos<0:raise SystemExit("v12.4 missing instance-full marker")
brace=s.index("{",pos);depth=0;end=-1
for i in range(brace,len(s)):
 if s[i]=="{":depth+=1
 elif s[i]=="}":
  depth-=1
  if depth==0:end=i+1;break
if end<0:raise SystemExit("v12.4 unclosed instance-full marker")
s=s[:end]+'''
// concept98_page_stage_v124: only the successfully decoded cache-first
// rendering path may declare a just-inserted Document visually full.
void concept98_note_cached_rendered_v124(const Document* document){
    media_chat_v81_mark_photo_full(document);
}
'''+s[end:]

# A native Win98 loading veil prevents revealing an unfinished page.
# This deliberately does NOT block the UI thread or the underlying RichEdit:
# loading proceeds via existing one-at-a-time upload.file requests. Timeout
# never holds the chat hostage when Telegram rejects a file reference.
stage=r'''
// concept98_page_stage_v124: media-first reveal for history pages.
static HWND concept98_page_veil_v124=NULL;
static std::vector<ConceptPhotoKey111> concept98_page_keys_v124;
static DWORD concept98_page_started_v124=0;
static BYTE concept98_page_peer_v124[8]={0};

static void concept98_page_unveil_v124(const char* why){
    if(concept98_page_veil_v124 && IsWindow(concept98_page_veil_v124))
        ShowWindow(concept98_page_veil_v124,SW_HIDE);
    if(!concept98_page_keys_v124.empty())
        diag_log("concept98 v124 staged history revealed cause=%s count=%d",
                 why,(int)concept98_page_keys_v124.size());
    concept98_page_keys_v124.clear();
}

void concept98_page_stage_v124(int newly_added_docs){
    if(!concept98_enabled || !hMain || !chat || !current_peer ||
       newly_added_docs<=0 || !IMAGELOADPOLICY)return;
    concept98_page_unveil_v124("superseded");
    if(newly_added_docs>(int)documents.size())
        newly_added_docs=(int)documents.size();
    for(int i=0;i<newly_added_docs;i++){
        const Document* d=&documents[i];
        if(!d->visible || !d->file_reference || !d->photo_size ||
           d->photo_size==1 || d->photo_size==3 ||
           media_chat_v81_photo_is_full(d))continue;
        ConceptPhotoKey111 key=concept98_photo_key_v111(d->id,d->access_hash);
        if(!key.first)continue;
        if(std::find(concept98_page_keys_v124.begin(),
                     concept98_page_keys_v124.end(),key)==
                     concept98_page_keys_v124.end())
            concept98_page_keys_v124.push_back(key);
    }
    if(concept98_page_keys_v124.empty())return;
    if(!concept98_page_veil_v124){
        concept98_page_veil_v124=CreateWindowExW(
            WS_EX_CLIENTEDGE,L"STATIC",
            L"\x0417\x0430\x0433\x0440\x0443\x0437\x043a\x0430 \x043c\x0435\x0434\x0438\x0430...",
            WS_CHILD|WS_CLIPSIBLINGS|SS_CENTER|SS_CENTERIMAGE,
            0,0,200,100,hMain,(HMENU)8992,NULL,NULL);
        if(concept98_page_veil_v124)
            SendMessageW(concept98_page_veil_v124,WM_SETFONT,
                         (WPARAM)hFonts[2],FALSE);
    }
    memcpy(concept98_page_peer_v124,current_peer->id,8);
    concept98_page_started_v124=GetTickCount();
    diag_log("concept98 v124 staged history started pending=%d",
             (int)concept98_page_keys_v124.size());
    if(concept98_page_veil_v124){
        RECT rc={0};GetWindowRect(chat,&rc);
        POINT p={rc.left,rc.top};
        ScreenToClient(hMain,&p);
        SetWindowPos(concept98_page_veil_v124,HWND_TOP,p.x,p.y,
            rc.right-rc.left,rc.bottom-rc.top,
            SWP_SHOWWINDOW|SWP_NOACTIVATE);
        InvalidateRect(concept98_page_veil_v124,NULL,TRUE);
    }
}

static void concept98_page_tick_v124(){
    if(concept98_page_keys_v124.empty())return;
    if(!current_peer || memcmp(current_peer->id,concept98_page_peer_v124,8)){
        concept98_page_unveil_v124("peer switched");
        return;
    }
    int ready=0;
    for(size_t i=0;i<concept98_page_keys_v124.size();i++){
        bool found=false;
        for(size_t k=0;k<documents.size();k++){
            const Document* d=&documents[k];
            if(concept98_photo_key_v111(d->id,d->access_hash)!=
               concept98_page_keys_v124[i])continue;
            found=true;
            if(media_chat_v81_photo_is_full(d))ready++;
            break;
        }
        if(!found)ready++; // deleted message must not block the page.
    }
    if(ready==(int)concept98_page_keys_v124.size()){
        concept98_page_unveil_v124("all media ready");
        return;
    }
    // Never lock out chat history for more than 12 seconds on an unreachable
    // photo. Existing placeholder supports another user-initiated attempt.
    if(GetTickCount()-concept98_page_started_v124>=12000){
        diag_log("concept98 v124 staging timeout ready=%d total=%d",
                  ready,(int)concept98_page_keys_v124.size());
        concept98_page_unveil_v124("12s timeout");
        return;
    }
    if(concept98_page_veil_v124 && IsWindowVisible(concept98_page_veil_v124)){
        wchar_t label[110]={0};
        _snwprintf_s(label,ARRAYSIZE(label),_TRUNCATE,
           L"\x0417\x0430\x0433\x0440\x0443\x0437\x043a\x0430 \x043c\x0435\x0434\x0438\x0430: %d / %d",
           ready,(int)concept98_page_keys_v124.size());
        SetWindowTextW(concept98_page_veil_v124,label);
        RECT rc={0};GetWindowRect(chat,&rc);
        POINT p={rc.left,rc.top};ScreenToClient(hMain,&p);
        SetWindowPos(concept98_page_veil_v124,HWND_TOP,p.x,p.y,
            rc.right-rc.left,rc.bottom-rc.top,
            SWP_NOACTIVATE);
    }
}
'''
needle='static void concept98_auto_full_photo_pump_v106() {'
if s.count(needle)!=1:raise SystemExit("missing photo pump")
s=s.replace(needle,stage+"\n"+needle,1)
# The v12.3 independent avatar timer already calls both local cache retry
# and network prefetch, so assess page readiness after those operations.
s=rep(s,'''            if (!concept98_retry_cached_photo_v121())
                concept98_auto_full_photo_pump_v106();
        }
        return 0;
    }''',
'''            if (!concept98_retry_cached_photo_v121())
                concept98_auto_full_photo_pump_v106();
            concept98_page_tick_v124();
        }
        return 0;
    }''',"page staging timer")
# Prevent an overlay lingering when the Concept98 shell is switched off.
s=rep(s,'''    if (!concept98_enabled) {
        if(concept98_topic_combo_v119)''',
'''    if (!concept98_enabled) {
        concept98_page_unveil_v124("classic shell disabled");
        if(concept98_topic_combo_v119)''',"classic shell overlay cleanup")
# Begin staging at the end of getHistory's single UI-thread render transaction.
# It records only the newly inserted documents, not the entire chat.
b=rep(b,'''		diag_log("history v76 page raw=%d rendered=%d limit=%d",''',
'''        concept98_page_stage_v124((int)documents.size()-documents_count_old);
		diag_log("history v76 page raw=%d rendered=%d limit=%d",''',
"start history staging")
b=rep(b,'#include <telegacy.h>',
'''#include <telegacy.h>
extern void concept98_page_stage_v124(int);''',"history staging declaration")
t.write_text(s,encoding="latin-1",newline="\r\n")
m.write_text(a,encoding="latin-1",newline="\r\n")
r.write_text(b,encoding="latin-1",newline="\r\n")
print("v12.4: normalized full JPEG read path, cache-rendered instance flag, restored single/double click and bounded staged history reveal.")
