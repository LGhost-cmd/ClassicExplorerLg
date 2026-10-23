#!/usr/bin/env python3
"""v11.1: bind each chat photo to its ORIGINAL RichEdit OLE COM identity at
insertion time. Async JPEG completion uses this stable pointer, not guessed
char offsets, media ordinal, or currently hovered picture."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_photo_ole_identity_v111.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
m=root/"src"/"message.cpp"
s=p.read_text(encoding="latin-1")
a=m.read_text(encoding="latin-1")
if "concept98_photo_ole_identity_v111" in s:
    print("v11.1 already applied");raise SystemExit(0)
if "concept98_shell_polish_v110" not in s:
    raise SystemExit("v11.0 prerequisite missing")
needle="static bool media_chat_v87_capture_photo_ole(\n    Document* document\n) {"
if s.count(needle)!=1: raise SystemExit("Missing v8.7 OLE capture")
registry=r'''
// concept98_photo_ole_identity_v111
// Each full photo has an immutable Telegram media identity. The RichEdit
// object itself is captured at insertion, before forwarded headers and
// pagination can cause Document::min to drift.
typedef std::pair<unsigned __int64,unsigned __int64> ConceptPhotoKey111;
static std::map<ConceptPhotoKey111,IUnknown*> concept98_photo_oles_v111;
static ConceptPhotoKey111 concept98_photo_key_v111(
    const BYTE* id,const BYTE* hash
){
    return ConceptPhotoKey111(
        (unsigned __int64)read_le((BYTE*)id,8),
        (unsigned __int64)read_le((BYTE*)hash,8));
}
void concept98_photo_clear_bindings_v111(){
    for(std::map<ConceptPhotoKey111,IUnknown*>::iterator it=
        concept98_photo_oles_v111.begin();
        it!=concept98_photo_oles_v111.end();++it)
        if(it->second)it->second->Release();
    concept98_photo_oles_v111.clear();
}
bool concept98_photo_bind_v111(
    const BYTE* id,const BYTE* hash,int cp
){
    if(!chat||!id||!hash||cp<0)return false;
    IRichEditOle* ole=NULL;
    SendMessageW(chat,EM_GETOLEINTERFACE,0,(LPARAM)&ole);
    if(!ole)return false;
    IUnknown* captured=NULL;
    LONG count=ole->GetObjectCount();
    for(LONG i=0;i<count;i++){
        REOBJECT obj={0};
        obj.cbStruct=sizeof(obj);
        if(FAILED(ole->GetObject(i,&obj,REO_GETOBJ_POLEOBJ))||
           !obj.poleobj)continue;
        if((int)obj.cp==cp){
            media_chat_v87_query_bitmap_identity(obj.poleobj,&captured);
            obj.poleobj->Release();
            break;
        }
        obj.poleobj->Release();
    }
    ole->Release();
    if(!captured) return false;
    ConceptPhotoKey111 key=concept98_photo_key_v111(id,hash);
    std::map<ConceptPhotoKey111,IUnknown*>::iterator old=
        concept98_photo_oles_v111.find(key);
    if(old!=concept98_photo_oles_v111.end() && old->second)
        old->second->Release();
    concept98_photo_oles_v111[key]=captured;
    if(concept98_photo_oles_v111.size()>1024)
        concept98_photo_clear_bindings_v111();
    diag_log("concept98 v111 bound photo OLE cp=%d",cp);
    return true;
}
static IUnknown* concept98_photo_lookup_v111(
    const BYTE* id,const BYTE* hash
){
    std::map<ConceptPhotoKey111,IUnknown*>::iterator it=
        concept98_photo_oles_v111.find(concept98_photo_key_v111(id,hash));
    if(it==concept98_photo_oles_v111.end()||!it->second)return NULL;
    it->second->AddRef();
    return it->second;
}
'''
s=s.replace(needle,registry+"\n"+needle,1)
expected='''    if (!chat || !document || document->min < 0)
        return false;

    IRichEditOle* ole = NULL;'''
repl=r'''    if (!chat || !document || document->min < 0)
        return false;

    IUnknown* bound=concept98_photo_lookup_v111(
        document->id,document->access_hash);
    if(bound) {
        int resolved=media_chat_v87_find_identity_cp(bound);
        if(resolved>=0){
            media_chat_full_photo_ole_identity_v87=bound;
            media_chat_full_photo_clicked_cp_v87=resolved;
            document->min=resolved;
            document->max=resolved+1;
            diag_log("concept98 v111 captured bound photo cp=%d",resolved);
            return true;
        }
        bound->Release();
        diag_log("concept98 v111 stale photo binding; trying strict cp");
    }

    IRichEditOle* ole = NULL;'''
# Limit to the capture function, not every occurrence in generated file.
start=s.find(needle)
end=s.find("static bool media_chat_upgrade_photo_in_place(",start)
part=s[start:end]
if part.count(expected)!=1:raise SystemExit("Original capture guard missing")
s=s[:start]+part.replace(expected,repl,1)+s[end:]
# After a successful OLE replacement, refresh key -> new canonical identity.
start=s.find("static bool media_chat_upgrade_photo_in_place(")
end=s.find("bool media_chat_full_photo_handle_upload(",start)
part=s[start:end]
old='''    if (replaced) {
        diag_log(
            "chat v87 full photo replaced exact captured=%d old=%d new=%d",'''
new='''    if (replaced) {
        concept98_photo_bind_v111(
            document->id,document->access_hash,actual_cp);
        diag_log(
            "chat v87 full photo replaced exact captured=%d old=%d new=%d",'''
if part.count(old)!=1:raise SystemExit("Replacement completion missing")
s=s[:start]+part.replace(old,new,1)+s[end:]
hook='        media_chat_v86_loaded_full_instances.clear();'
if s.count(hook)!=1:raise SystemExit("No chat-switch bindings cleanup")
s=s.replace(hook,hook+'\n        concept98_photo_clear_bindings_v111();',1)
# The declaration is visible in message.cpp before any new photo OLE is created.
prefix="#include <telegacy.h>"
if a.count(prefix)!=1:raise SystemExit("message.cpp header absent")
a=a.replace(prefix,prefix+'\nextern bool concept98_photo_bind_v111(const BYTE*,const BYTE*,int);',1)
target='''			if (display_bitmap)
				insert_image(chat, NULL, display_bitmap);
			if (cached_card)'''
replacement='''			if (display_bitmap) {
				insert_image(chat, NULL, display_bitmap);
				concept98_photo_bind_v111(
					document.id, document.access_hash, document.min);
			}
			if (cached_card)'''
if a.count(target)!=1:raise SystemExit("cache-first image insertion changed")
a=a.replace(target,replacement,1)
p.write_text(s,encoding="latin-1",newline="\r\n")
m.write_text(a,encoding="latin-1",newline="\r\n")
print("v11.1: bound per-photo COM identity on insertion; async JPEG upgrades replace its original OLE.")
