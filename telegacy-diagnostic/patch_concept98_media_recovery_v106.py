#!/usr/bin/env python3
"""Concept98 v10.6: safe WebM fallback, bounded avatar retention, automatic full photos.

The native RichEdit OLE picture remains the only visible WebM poster while
the old MFPlay child overlay is quarantined. No new OLE is inserted by timers.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_media_recovery_v106.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
h=root/"src"/"helpers.cpp"
m=root/"src"/"message.cpp"
t=p.read_text(encoding="latin-1")
s=h.read_text(encoding="latin-1")
a=m.read_text(encoding="latin-1")
if "concept98_media_recovery_v106" in t:
    print("v10.6 already applied");raise SystemExit(0)
if "concept98_clean_media_v105" not in t or "concept98_fast_avatars_v99" not in s:
    raise SystemExit("Requires Concept98 v10.5 and avatar v9.9")

def one(source,old,new,what):
    if source.count(old)!=1:
        raise SystemExit(f"v10.6 expected exactly one {what}, found {source.count(old)}")
    return source.replace(old,new,1)

# The screenshot contains a partly transparent/shifting WebM *window* over
# the static RichEdit poster. The poster loads through v8.1/v8.4 already.
# Until we have a compositor without child windows, NEVER overlap it with
# an MFP child window; TGS overlays retain their exact-cp guards.
timer_start=t.find("static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(")
timer_end=t.find("static VOID CALLBACK media_chat_sticker_timer_proc(",timer_start+20)
if timer_end<0:
    timer_end=t.find("static void media_chat_sticker_",timer_start+20)
if timer_start<0 or timer_end<0:
    raise SystemExit("Missing stable animated sticker timer")
timer=t[timer_start:timer_end]
old="""        if (!sticker)
            continue;

        Document* document ="""
new="""        if (!sticker)
            continue;

        // concept98_media_recovery_v106: MFP draws to a child HWND and can
        // leave a sliced/offset frame over chat text or a neighbouring photo.
        // The verified RichEdit sticker poster is the safe fallback.
        if (sticker->kind == 2) {
            if (sticker->window) ShowWindow(sticker->window,SW_HIDE);
            if (sticker->video && !sticker->video_paused_for_visibility) {
                sticker->video->Pause();
                sticker->video_paused_for_visibility=true;
            }
            sticker->visible=false;
            sticker->have_geometry_v88=false;
            continue;
        }

        Document* document ="""
timer=one(timer,old,new,"WebM child-window quarantine")
t=t[:timer_start]+timer+t[timer_end:]

# Keep avatars for an entire large dialog roster rather than thrashing a
# tiny 128-item cache every time the user scrolls through their chat list.
s=one(s,"if (concept98_cache_v96.size()<128) return;",
      "if (concept98_cache_v96.size()<1024) return; // concept98_media_recovery_v106",
      "avatar cache capacity")

# Automatic full-quality image upgrades, in small increments, reuse the
# exact OLE capture/identity-verified photo click path. No native preview,
# no speculative cp/ordinal mapping and no new bitmap insertion on failure.
# Cooldowns avoid retry storms when access references have expired.
proto="static void concept98_auto_full_photo_pump_v106(); // concept98_media_recovery_v106\n"
anchor="static UINT_PTR media_chat_sticker_timer = 0;"
t=one(t,anchor,proto+anchor,"photo scanner forward declaration")
defn="static bool media_chat_full_photo_user_action(\n    Document* document,\n    bool save_and_open\n) {"
start=t.find(defn)
if start<0: raise SystemExit("Missing v10.1 photo user action")
brace=t.find("{",start)
depth=0
end=-1
for i in range(brace,len(t)):
    if t[i]=="{":depth+=1
    elif t[i]=="}":
        depth-=1
        if depth==0:
            end=i+1
            break
if end<0:raise SystemExit("Unclosed photo user action")
scanner=r'''

// concept98_media_recovery_v106
// Prefer the full JPEG automatically instead of indefinitely presenting
// 'Loading image...'. The same one-at-a-time transport used by clicks is
// deliberately retained, and only a verified exact OLE can be committed.
static void concept98_auto_full_photo_pump_v106() {
    if (!concept98_enabled || !chat || !IsWindowVisible(chat) ||
        !dcInfoMain.ready || !IMAGELOADPOLICY ||
        media_chat_full_photo_active || documents.empty()) return;

    static std::map<unsigned __int64,DWORD> next_attempt;
    DWORD now=GetTickCount();
    if (next_attempt.size()>512) next_attempt.clear();

    RECT view={0};
    SendMessageW(chat,EM_GETRECT,0,(LPARAM)&view);
    if (view.right<=view.left || view.bottom<=view.top) return;

    for (size_t i=0;i<documents.size();++i) {
        Document* d=&documents[i];
        if (!d->visible || !d->file_reference ||
            d->photo_size==0 || d->photo_size==1 ||
            d->photo_size==3 || d->min<0 ||
            d->max!=d->min+1 ||
            media_chat_v81_photo_is_full(d)) continue;
        // Do not use v8.0 proportional rebind. An image may only
        // auto-upgrade its *own* one-character OLE.
        if (!media_chat_v87_exact_bitmap_at_cp(d->min)) continue;
        POINTL pos={0,0};
        if (SendMessageW(chat,EM_POSFROMCHAR,
                         (WPARAM)&pos,(LPARAM)d->min)==-1) continue;
        if (pos.y>view.bottom || pos.y+216<view.top) continue;

        unsigned __int64 key=
            (unsigned __int64)read_le(d->id,8) ^
            ((unsigned __int64)read_le(d->access_hash,8)<<1);
        if (!key) continue;
        std::map<unsigned __int64,DWORD>::iterator it=
            next_attempt.find(key);
        if (it!=next_attempt.end() &&
            (LONG)(now-it->second)<0) continue;
        // Errors and expired references must never flood the network.
        next_attempt[key]=now+30000;
        bool started=media_chat_full_photo_user_action(d,false);
        diag_log("concept98 v106 auto full photo started=%d type=%d",
                 started?1:0,(int)d->photo_size);
        return;
    }
}
'''
t=t[:end]+scanner+t[end:]
# This 240ms timer was introduced in v9.9 for avatar scheduling.
tick="""    if (msg == WM_TIMER && wParam == 8998) {
        if (concept98_enabled && dcInfoMain.ready)
            concept98_avatar_pump_v93(
                concept98_list,concept98_folder_indices,
                global_chat_search_mode
            );
        return 0;
    }"""
new_tick="""    if (msg == WM_TIMER && wParam == 8998) {
        if (concept98_enabled && dcInfoMain.ready) {
            concept98_avatar_pump_v93(
                concept98_list,concept98_folder_indices,
                global_chat_search_mode
            );
            concept98_auto_full_photo_pump_v106();
        }
        return 0;
    }"""
t=one(t,tick,new_tick,"v9.9 independent avatar timer")
# Honest placeholder: one can still click to retry, but fetch is automatic.
a=one(a,'L"Full quality  |  Click to retry"',
      'L"Full quality  |  Loading..."',"loading card copy")
h.write_text(s,encoding="latin-1",newline="\r\n")
p.write_text(t,encoding="latin-1",newline="\r\n")
m.write_text(a,encoding="latin-1",newline="\r\n")
print("v10.6 safe WebM poster fallback; 1024 avatar cache; "
      "automatic exact-OLE full-quality photo fetch with cooldown.")
