#!/usr/bin/env python3
"""Concept98 v12.1: restore forum search and retry cached full-JPEG OLE upgrades.
Also align the Win98 search line below the currently selected topic.
No network/photo transport changes; retry only verified exact-identity local JPEGs.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_forum_search_cached_photo_v121.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_forum_search_cached_photo_v121" in s:raise SystemExit(0)
if "concept98_forum_media_v120" not in s:raise SystemExit("v12.0 missing")
def one(old,new,where):
    global s
    n=s.count(old)
    if n!=1:raise SystemExit("v12.1 %s expected 1 got %d"%(where,n))
    s=s.replace(old,new,1)

# The previous topic selector intentionally DISABLED search, making it white
# and noninteractive. This restores the existing working server search by peer.
one('''    if(hMessageSearch)EnableWindow(hMessageSearch,TRUE);
    concept98_forum_visibility_v119();''',
'''    if(hMessageSearch)EnableWindow(hMessageSearch,TRUE);
    concept98_forum_visibility_v119();''',"reset search guard") if False else None
one('''    if(hMessageSearch)EnableWindow(hMessageSearch,id==0);''',
'''    // concept98_forum_search_cached_photo_v121:
    // Keep channel-wide Telegram server search available in every topic.
    // Search results are channel-wide; clearing the query returns to topic.
    if(hMessageSearch)EnableWindow(hMessageSearch,TRUE);''',
"topic search enable")

# Set a precise, honest scope hint, preserve the edit HWND and its events.
one('''    concept98_forum_visibility_v119();
    diag_log("concept98 v120 visible forum dropdown count=%d default_topic=%d hwnd=%p",''',
'''    concept98_forum_visibility_v119();
    if(hMessageSearch) SendMessageW(hMessageSearch,0x1501,TRUE,
         (LPARAM)L"\x041f\x043e\x0438\x0441\x043a \x043f\x043e \x043a\x0430\x043d\x0430\x043b\x0443...");
    diag_log("concept98 v120 visible forum dropdown count=%d default_topic=%d hwnd=%p",''',
"forum search cue")
one('''    if(hMessageSearch)EnableWindow(hMessageSearch,TRUE);
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
"restore search hint") if False else None

# The edit is physically left-aligned at the edge of conversation while
# topic selection is indented by the avatar. Use that common 46px text grid.
one('''    concept98_move_v91(hMessageSearch, content_x, 82+topic_row_v120,
                       search_w, 24);''',
'''    const int search_left_v121 = content_x+46;
    int aligned_search_width_v121 = search_w-46;
    if(aligned_search_width_v121<138)
        aligned_search_width_v121=138;
    concept98_move_v91(hMessageSearch,
                       search_left_v121, 82+topic_row_v120,
                       aligned_search_width_v121, 24);''',
"search alignment")
# Avoid drawing a phantom tiny status control between search and navigation.
one('''    if (hMessageSearchStatus) {
        int status_x = content_x + search_w + 8;''',
'''    if (hMessageSearchStatus) {
        int status_x = content_x + search_w + 8;''',
"keep status geometry") if False else None

# Cache rehydration: response may save bytes but fail exact OLE swap while
# getReplies is still modifying the same rich text. A later timer retries once
# after layout using ONLY verified cached full JPEG and exact COM identity.
needle="static void concept98_auto_full_photo_pump_v106() {"
if s.count(needle)!=1:raise SystemExit("No v10.6 photo pump")
recovery=r'''
// concept98_forum_search_cached_photo_v121
// A successfully downloaded full JPEG is sometimes cached before its RichEdit
// OLE anchor settles on a getReplies page. Do not leave Loading image forever.
// Reuse the v10.1 cache and the same v8.7 transaction-safe OLE replacement;
// never display degraded thumbnail data or insert a second standalone OLE.
static bool concept98_retry_cached_photo_v121() {
    if(!concept98_enabled || !chat || media_chat_full_photo_active ||
       !IsWindowVisible(chat) || documents.empty()) return false;
    static std::map<unsigned __int64,DWORD> failed_until;
    if(failed_until.size()>256)failed_until.clear();
    DWORD now=GetTickCount();
    for(size_t i=0;i<documents.size();i++){
        Document* d=&documents[i];
        if(!d->visible || !d->file_reference ||
           !d->photo_size || d->photo_size==1 || d->photo_size==3 ||
           media_chat_v81_photo_is_full(d))continue;
        unsigned __int64 id=(unsigned __int64)read_le(d->id,8);
        unsigned __int64 hash=(unsigned __int64)read_le(d->access_hash,8);
        unsigned __int64 key=id^(hash<<1);
        if(!key)continue;
        std::map<unsigned __int64,DWORD>::iterator delay=failed_until.find(key);
        if(delay!=failed_until.end()&&(LONG)(now-delay->second)<0)continue;
        std::vector<BYTE> jpeg;
        if(!concept98_full_photo_load_v101(d,&jpeg))continue;
        // Mark short retry cooldown in advance to prevent endless redraw.
        failed_until[key]=now+1800;
        IUnknown* bound=concept98_photo_lookup_v111(d->id,d->access_hash);
        if(!bound)continue;
        int cp=media_chat_v87_find_identity_cp(bound);
        bound->Release();
        if(cp<0)continue;
        d->min=cp;d->max=cp+1;
        if(!media_chat_v87_exact_bitmap_at_cp(cp))continue;
        // The action uses cache first and calls the transactional
        // media_chat_upgrade_photo_in_place; it will not request new bytes
        // when the local cached JPEG commits successfully.
        bool success=media_chat_full_photo_user_action(d,false);
        if(success && media_chat_v81_photo_is_full(d)){
            failed_until.erase(key);
            diag_log("concept98 v121 late cached JPEG OLE recovered id=%I64u cp=%d",
                     id,cp);
            return true;
        }
        diag_log("concept98 v121 cached JPEG retry not committed id=%I64u cp=%d",
                 id,cp);
        return false;
    }
    return false;
}
'''
s=s.replace(needle,recovery+"\n"+needle,1)
# Tick before requests: cache is already complete, no download necessary.
one('''            concept98_auto_full_photo_pump_v106();
        }
        return 0;
    }''',
'''            if (!concept98_retry_cached_photo_v121())
                concept98_auto_full_photo_pump_v106();
        }
        return 0;
    }''',
"avatar/photo tick")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v12.1: forum search reenabled and aligned, late exact cached full-JPEG retries after getReplies.")
