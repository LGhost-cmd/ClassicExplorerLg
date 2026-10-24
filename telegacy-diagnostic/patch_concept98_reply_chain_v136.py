#!/usr/bin/env python3
"""Concept98 v13.6: read-only chained reply popup, newest to oldest.
Fetched originals are cached from real messages.getMessages responses and
never inserted into the chat RichEdit merely to construct a reply preview.
Network lookups are bounded (12 ancestors) and scoped to current peer."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_reply_chain_v136.py <src>")
root=Path(sys.argv[1]).resolve()
m=root/"src"/"message.cpp";t=root/"src"/"telegacy.cpp";r=root/"src"/"response.cpp"
d={p:p.read_text(encoding="latin-1") for p in (m,t,r)}
if "concept98_reply_chain_v136" in d[t]:raise SystemExit(0)
if "concept98_reply_links_v134" not in d[t]:raise SystemExit("v13.4 required")
def one(path,old,new,label):
 n=d[path].count(old)
 if n!=1:raise SystemExit("v13.6 "+label+" occurrences="+str(n))
 d[path]=d[path].replace(old,new,1)
# Reduce needless network activity and prevent old set_reply_tofront()
# from writing a second quote into an already formatted Concept98 header.
one(m,"message.reply_needed = context_v128.empty()?0:reply_target_v128;",
"""message.reply_needed = concept98_enabled ? 0 :
        (context_v128.empty()?0:reply_target_v128); // concept98_reply_chain_v136""",
"disable legacy footer updates")
# Cache the text while decoding legitimate messages normally. No raw pointer
# escapes, and only a short bounded excerpt enters the chain cache.
one(m,"message.seen = ((to_front && !message.outgoing)",
r'''    if(concept98_enabled && message.id>0 && msg_bytes){
        const int length_v136=tlstr_to_str_len(msg_bytes);
        if(length_v136>=0 && length_v136<=4096){
            wchar_t* txt_v136=read_string(msg_bytes,NULL);
            if(txt_v136){
                extern void concept98_reply_note_v136(int,int,const wchar_t*,bool);
                concept98_reply_note_v136(message.id,
                    message.concept98_reply_target_v134,txt_v136,
                    (flags&(1<<9))!=0);
                free(txt_v136);
            }
        }
    }
    message.seen = ((to_front && !message.outgoing)''',
"record loaded replies")
# Hook the response BEFORE the legacy reply enrichment branch can discard a
# single message. For incomplete/foreign content, the snapshot parser fails
# closed without affecting normal message processing.
one(r,'''			int id = read_le(unenc_response + offset_msg + 12, 4);
			for (int i = 0; i < messages.size(); i++) {''',
'''            if(concept98_enabled){
                extern void concept98_reply_capture_rpc_v136(const BYTE*,int);
                if(offset_msg>=0 && offset_msg<length)
                    concept98_reply_capture_rpc_v136(
                        unenc_response+offset_msg,length-offset_msg);
            }
			int id = read_le(unenc_response + offset_msg + 12, 4);
			for (int i = 0; i < messages.size(); i++) {''',
"capture single message response")

# Prevent the legacy reply patch-up from mutating the Concept98 RichEdit.
one(r,'''					messages[i].reply_needed = 0;
					if (messages[i].end_char == messages[i].end_footer) break;''',
'''					messages[i].reply_needed = 0;
                    if(concept98_enabled) { neworrep=true; break; }
					if (messages[i].end_char == messages[i].end_footer) break;''',
"skip duplicate quote mutation")
one(r,'''				else set_reply_tofront(i, NULL, j);''',
'''                else if(!concept98_enabled) set_reply_tofront(i,NULL,j);''',
"skip historical duplicate quote")

# Inject helper near native viewer. Use account-/peer-scoped keys and short
# text copies; no borrowed RPC buffers survive the callback.
anchor="static HWND concept98_forward_win_v130=NULL;"
helper=r'''// concept98_reply_chain_v136: bounded peer-local cached reply snapshots.
#include <map>
#include <set>
struct Concept98ReplySnapshot136 {
    int parent;
    std::wstring body;
    bool media;
    Concept98ReplySnapshot136():parent(0),media(false){}
};
static std::map<int,Concept98ReplySnapshot136> concept98_reply_nodes_v136;
static std::set<int> concept98_reply_requested_v136;
static BYTE concept98_reply_peer_v136[8]={0};
static int concept98_reply_root_v136=0;

static bool concept98_reply_peer_check_v136(){
    if(!current_peer)return false;
    if(memcmp(concept98_reply_peer_v136,current_peer->id,8)){
        concept98_reply_nodes_v136.clear();
        concept98_reply_requested_v136.clear();
        concept98_reply_root_v136=0;
        memcpy(concept98_reply_peer_v136,current_peer->id,8);
    }
    return true;
}
void concept98_reply_note_v136(int id,int parent,const wchar_t* body,bool media){
    if(!concept98_enabled || !concept98_reply_peer_check_v136() ||
       id<=0 || !body)return;
    if(concept98_reply_nodes_v136.size()>256){
        concept98_reply_nodes_v136.clear();
        concept98_reply_requested_v136.clear();
    }
    Concept98ReplySnapshot136& n=concept98_reply_nodes_v136[id];
    n.parent=parent>0?parent:0;
    n.body.assign(body,body+wcsnlen_s(body,4096));
    n.media=media;
}
static void concept98_reply_request_v136(int id){
    if(id<=0 || !concept98_reply_peer_check_v136() ||
       concept98_reply_requested_v136.size()>=12 ||
       !concept98_reply_requested_v136.insert(id).second)return;
    get_message(id,current_peer);
}
// Read only normal Telegram messages; verify boundaries before TL reads.
void concept98_reply_capture_rpc_v136(const BYTE* raw,int len){
    if(!concept98_enabled || !concept98_reply_peer_check_v136() ||
       !raw || len<40)return;
    const unsigned int cons=(unsigned int)read_le((BYTE*)raw,4);
    if(cons!=0x96fdbbe9)return;
    const unsigned int flags=(unsigned int)read_le((BYTE*)raw+4,4);
    const unsigned int flags2=(unsigned int)read_le((BYTE*)raw+8,4);
    const int id=(int)read_le((BYTE*)raw+12,4);
    if(id<=0)return;
    int at=16;
    if(flags&(1u<<8))at+=12;
    if(flags&(1u<<29))at+=4;
    if(at+12>len)return;
    at+=4; // peer constructor
    if(memcmp(raw+at,current_peer->id,8)!=0)return;
    at+=8;
    if(flags&(1u<<28))at+=12;
    if(at+16>len)return;
    if(flags&(1u<<2)){int n=msgfwd_offset((BYTE*)raw+at);
        if(n<=0 || n>len-at)return;at+=n;}
    if(flags&(1u<<11))at+=8;
    if(flags2&1u)at+=8;
    if(at+16>len)return;
    int parent=0;
    if(flags&(1u<<3)){
        unsigned int rf=(unsigned int)read_le((BYTE*)raw+at+4,4);
        if(rf&(1u<<4))parent=(int)read_le((BYTE*)raw+at+8,4);
        int n=msgrpl_offset((BYTE*)raw+at);
        if(n<=0 || n>len-at)return;at+=n;
    }
    at+=4; // date
    if(at+4>len)return;
    int encoded=0;
    if(raw[at]<254)encoded=(raw[at]+1+3)&~3;
    else {
        int bytes=(int)raw[at+1] | ((int)raw[at+2]<<8) |
                 ((int)raw[at+3]<<16);
        if(bytes<0 || bytes>16384)return;
        encoded=(bytes+4+3)&~3;
    }
    if(encoded<=0 || encoded>len-at)return;
    int decoded=tlstr_to_str_len((BYTE*)raw+at);
    if(decoded<0 || decoded>4096)return;
    wchar_t* text=read_string((BYTE*)raw+at,NULL);
    if(!text)return;
    concept98_reply_note_v136(id,parent,text,(flags&(1u<<9))!=0);
    free(text);
    if(concept98_reply_root_v136 && concept98_forward_win_v130 &&
       IsWindow(concept98_forward_win_v130))
        PostMessageW(hMain,WM_APP+0x4A6,0,0);
}
// Reuse the native Concept98 viewer; only its copy is replaced.
// Parent links never rewrite chat RichEdit, Document CP or cached OLE.
static void concept98_reply_refresh_v136(){
    if(!concept98_reply_root_v136 || !concept98_forward_rich_v130 ||
       !IsWindow(concept98_forward_rich_v130) ||
       !concept98_reply_peer_check_v136())return;
    std::wstring content;
    std::set<int> visited;
    int id=concept98_reply_root_v136;
    for(int depth=0;id>0 && depth<12;depth++){
        if(!visited.insert(id).second){
            content+=L"\r\n[Циклическая ссылка на сообщение]\r\n";
            break;
        }
        if(depth)content+=L"\r\n";
        for(int i=0;i<depth;i++)content+=L"    ";
        if(depth)content+=L"[ ";
        wchar_t number[44]={0};
        swprintf_s(number,ARRAYSIZE(number),L"Сообщение #%d",id);
        content+=number;
        content+=L"\r\n";
        std::map<int,Concept98ReplySnapshot136>::iterator it=
            concept98_reply_nodes_v136.find(id);
        if(it==concept98_reply_nodes_v136.end()){
            for(int i=0;i<depth;i++)content+=L"    ";
            content+=L"Загрузка из Telegram...";
            concept98_reply_request_v136(id);
            if(depth)content+=L" ]\r\n";
            break;
        }
        const Concept98ReplySnapshot136& node=it->second;
        for(int i=0;i<depth;i++)content+=L"    ";
        content+=node.body.empty()?L"[Сообщение без текста]":node.body;
        if(node.media)content+=L"\r\n[Медиавложение]";
        if(depth)content+=L" ]";
        id=node.parent;
        if(content.size()>32000){content.resize(32000);break;}
    }
    SendMessageW(concept98_forward_rich_v130,WM_SETTEXT,0,
                 (LPARAM)content.c_str());
    SendMessageW(concept98_forward_rich_v130,EM_SETSEL,0,0);
    SetWindowTextW(concept98_forward_win_v130,
        L"Цепочка ответов | Telegacy");
}
static bool concept98_reply_chain_open_v136(size_t index){
    if(!concept98_reply_peer_check_v136() || index>=messages.size())
        return false;
    // The currently displayed row always exists. The immutable ID and
    // reply_to are saved on Message, even if Telegram reply_needed cleared.
    Message row=messages[index];
    if(row.id<=0)return false;
    concept98_reply_root_v136=row.id;
    std::map<int,Concept98ReplySnapshot136>::iterator it=
        concept98_reply_nodes_v136.find(row.id);
    if(it==concept98_reply_nodes_v136.end()){
        std::wstring body;
        const int a=row.end_header,b=row.end_char;
        if(b>a && b-a<4096){
            std::vector<wchar_t> buffer(b-a+1,0);
            TEXTRANGEW tr={0};tr.chrg.cpMin=a;tr.chrg.cpMax=b;
            tr.lpstrText=&buffer[0];
            SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
            body=&buffer[0];
        }
        concept98_reply_note_v136(row.id,row.concept98_reply_target_v134,
                                  body.c_str(),false);
    }else if(row.concept98_reply_target_v134>0){
        it->second.parent=row.concept98_reply_target_v134;
    }
    if(!concept98_open_forward_v130((int)index,true))return false;
    concept98_reply_refresh_v136();
    return true;
}
'''
# The viewer static HWND variables must be declared before the reply capture
# hook uses them, so move the helper immediately AFTER the four HWND declarations.
v=d[t]; loc=v.find("static std::vector<std::wstring> concept98_forward_paths_v130;")
if loc<0:raise SystemExit("Missing viewer state")
loc+=len("static std::vector<std::wstring> concept98_forward_paths_v130;")
# Do not insert definitions before actual concept98_open_forward_v130 function:
# forward declarations for existing popup helpers suffice.
protos=r'''
static bool concept98_open_forward_v130(int index,bool reply_view_v132);
static void concept98_reply_refresh_v136();
'''
v=v[:loc]+"\n"+protos+v[loc:]
# Insert helpers after definition of concept98_open_forward_v130, before hit test.
loc=v.find("static bool concept98_reply_activate_v134(size_t index){")
if loc<0:raise SystemExit("v13.4 reply activation missing")
# Remove include from local function insertion and place it at TU root.
helper=helper.replace("#include <map>\n#include <set>\n","")
if "#include <set>" not in v:v="#include <set>\n"+v
if "#include <map>" not in v:v="#include <map>\n"+v
v=v[:v.find("static bool concept98_reply_activate_v134(size_t index){")]+helper+v[v.find("static bool concept98_reply_activate_v134(size_t index){"):]
d[t]=v
one(t,"""static bool concept98_reply_activate_v134(size_t index){
    if(!current_peer || index>=messages.size())return false;""",
"""static bool concept98_reply_activate_v134(size_t index){
    if(!current_peer || index>=messages.size())return false;
    if(concept98_reply_chain_open_v136(index))return true;""",
"enable chain popup")
# Main window is where response notifications are queued.
one(t,"""    if (msg==WM_APP+0x397) {""",
"""    if (msg==WM_APP+0x4A6) {
        concept98_reply_refresh_v136();
        return 0;
    }
    if (msg==WM_APP+0x397) {""",
"UI thread refresh")
for p,body in d.items():
 p.write_text(body,encoding="latin-1",newline="\r\n")
print("v13.6: newest-to-oldest nested read-only reply chain; on-demand fetch; never modify chat footer.")
