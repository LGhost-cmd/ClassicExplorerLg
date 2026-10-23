#!/usr/bin/env python3
"""Concept98 v11.4: retry channel/group avatar FILE_MIGRATE through its media DC.
The old avatar upload.getFile always used dcInfoMain and silently timed out on
FILE_MIGRATE_4. Re-encrypt queries against a ready target DC; no auth changes.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_avatar_dc_v114.py <src>")
root=Path(sys.argv[1]).resolve()
h=root/"src"/"helpers.cpp"
r=root/"src"/"response.cpp"
s=h.read_text(encoding="latin-1")
t=r.read_text(encoding="latin-1")
if "concept98_avatar_dc_v114" in s:
    print("v11.4 already applied");raise SystemExit(0)
if "concept98_pending_v99" not in s:raise SystemExit("avatar v9.9 missing")
old='''static std::map<__int64,ConceptAvatarPending99> concept98_pending_v99;'''
new=r'''static std::map<__int64,ConceptAvatarPending99> concept98_pending_v99;
// concept98_avatar_dc_v114: media DC by stable avatar/chat identity.
static std::map<ConceptAvatar96Key,int> concept98_avatar_dc_v114;
void concept98_avatar_migrated_v114(const BYTE* rpc_id,int dc) {
    if (!rpc_id || dc<=0 || dc>5) return;
    std::lock_guard<std::recursive_mutex> guard(concept98_avatar_mutex_v98);
    __int64 rpc=(__int64)read_le((BYTE*)rpc_id,8);
    std::map<__int64,ConceptAvatarPending99>::iterator pending=
        concept98_pending_v99.find(rpc);
    if (pending==concept98_pending_v99.end()) return;
    ConceptAvatar96Key key=pending->second.key;
    concept98_pending_v99.erase(pending);
    concept98_avatar_dc_v114[key]=dc;
    std::map<ConceptAvatar96Key,ConceptAvatar96>::iterator it=
        concept98_cache_v96.find(key);
    if (it!=concept98_cache_v96.end()) {
        it->second.loading=false;
        it->second.next_retry=GetTickCount()+600;
    }
    diag_log("concept98 v114 avatar FILE_MIGRATE to dc=%d",dc);
}
'''
if s.count(old)!=1:raise SystemExit("pending map missing")
s=s.replace(old,new,1)
old='''    send_query(encrypted,offset+24);
    diag_log("concept98 v96 avatar request type=%d",peer->type);'''
# Must select DC BEFORE internal_header, not just send different encrypted bits.
# Restructure function via its definition's entire C++ text.
start=s.find("static bool concept98_avatar_request_v96(Peer* peer) {")
end=s.find("\nvoid concept98_avatar_pump_v93(",start)
if start<0 or end<0:raise SystemExit("avatar request bounds missing")
f=s[start:end]
anchor='''    BYTE query[256]={0};
    BYTE encrypted[280]={0};
    internal_header(query,true);'''
replacement=r'''    DCInfo* target=&dcInfoMain;
    ConceptAvatar96Key key=concept98_key_v96(peer);
    std::map<ConceptAvatar96Key,int>::iterator hint=
        concept98_avatar_dc_v114.find(key);
    if (hint!=concept98_avatar_dc_v114.end() &&
        hint->second!=dcInfoMain.dc) {
        target=NULL;
        for(std::list<DCInfo>::iterator it=active_dcs.begin();
            it!=active_dcs.end();++it) {
            if(it->dc==hint->second && it->ready) {
                target=&(*it);break;
            }
        }
        if (!target) return false; // wait for DC authentication, no main-DC flood
    }
    BYTE query[256]={0};
    BYTE encrypted[280]={0};
    internal_header(target,query,true);'''
if f.count(anchor)!=1:raise SystemExit("avatar internal_header missing")
f=f.replace(anchor,replacement,1)
if f.count("convert_message(query,encrypted,offset,0);")!=1 or f.count(old)!=1:
    raise SystemExit("avatar encryption/send patterns missing")
f=f.replace("convert_message(query,encrypted,offset,0);","convert_message(target,query,encrypted,offset,0);",1)
f=f.replace(old,'''    send_query(target,encrypted,offset+24);
    diag_log("concept98 v114 avatar request type=%d dc=%d",
             peer->type,target->dc);''',1)
s=s[:start]+f+s[end:]
# Avatar cache must not retain obsolete DC hints after logout.
old='''    concept98_pending_v99.clear();
    memset(concept98_pending_rpc_v96,0,8);'''
new='''    concept98_pending_v99.clear();
    concept98_avatar_dc_v114.clear();
    memset(concept98_pending_rpc_v96,0,8);'''
if s.count(old)!=1:raise SystemExit("logout clear map missing")
s=s.replace(old,new,1)
# Propagate FILE_MIGRATE to the avatar pending request table before legacy
# migration code creates/connects the target DC. Never alter photo retries.
old="int dc = error_message[13] - L'0';"
if t.count(old)!=1:raise SystemExit("response FILE_MIGRATE branch changed")
t=t.replace(old,old+'''
                concept98_avatar_migrated_v114(last_rpcresult_msgid,dc);''',1)
header="#include <telegacy.h>"
if t.count(header)!=1:raise SystemExit("response.cpp header missing")
t=t.replace(header,header+"\nextern void concept98_avatar_migrated_v114(const BYTE*,int);",1)
h.write_text(s,encoding="latin-1",newline="\r\n")
r.write_text(t,encoding="latin-1",newline="\r\n")
print("v11.4: avatar downloads follow FILE_MIGRATE media DC; encrypted RPC per target; safe delayed retries.")
