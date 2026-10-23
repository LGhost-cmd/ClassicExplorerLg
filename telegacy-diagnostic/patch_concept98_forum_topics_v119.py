#!/usr/bin/env python3
"""Concept98 v11.9: functional read-only forum topic navigation.
Only display the Win98 dropdown after channels.getForumTopics returns real topic
IDs/titles. Request messages.getReplies for selected topic, keep same peer,
disable composer while viewing a topic so outgoing messages cannot land in
the wrong thread. All-messages view remains fully functional.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_forum_topics_v119.py <src>")
root=Path(sys.argv[1]).resolve()
cpp=root/"src"/"telegacy.cpp"
helpers=root/"src"/"helpers.cpp"
response=root/"src"/"response.cpp"
s=cpp.read_text(encoding="latin-1")
h=helpers.read_text(encoding="latin-1")
r=response.read_text(encoding="latin-1")
if "concept98_forum_topics_v119" in s:
    print("v11.9 already applied");raise SystemExit(0)
if "concept98_sticker_size_alpha_v117" not in s:raise SystemExit("requires v11.7")
def one(source,old,new,name):
    n=source.count(old)
    if n!=1:raise SystemExit("v11.9 expected one %s, found %d"%(name,n))
    return source.replace(old,new,1)
# Peer-driven control, never a fake selector in non-forum channels.
s=one(s,
    "static HWND concept98_chat_detail = NULL;",
    "static HWND concept98_chat_detail = NULL;\nstatic HWND concept98_topic_combo_v119 = NULL; // concept98_forum_topics_v119",
    "topic combo declaration")
anchor="static void concept98_apply_layout(HWND hwnd) {"
network=r'''
// concept98_forum_topics_v119: layer-196 forum topics and real topic replies.
struct ConceptForumTopic119 {
    int id;
    std::wstring title;
};
static std::vector<ConceptForumTopic119> concept98_forum_topics_v119;
static BYTE concept98_forum_rpc_v119[8]={0};
static BYTE concept98_forum_peer_v119[8]={0};
static bool concept98_forum_pending_v119=false;
static bool concept98_forum_loaded_v119=false;
static int concept98_forum_selected_v119=0;
static BYTE concept98_forum_history_rpc_v119[8]={0};
static bool concept98_forum_history_pending_v119=false;
static std::map<__int64,DWORD> concept98_forum_attempts_v119;
int concept98_current_topic_v119(){return concept98_forum_selected_v119;}
void concept98_note_topic_history_rpc_v119(const BYTE* id) {
    if(!id)return;
    memcpy(concept98_forum_history_rpc_v119,id,8);
    concept98_forum_history_pending_v119=true;
}
bool concept98_accept_topic_history_v119(const BYTE* id) {
    if(!concept98_forum_selected_v119)return true;
    return id && concept98_forum_history_pending_v119 &&
        memcmp(concept98_forum_history_rpc_v119,id,8)==0;
}
static void concept98_forum_visibility_v119(){
    if(!concept98_topic_combo_v119 || !IsWindow(concept98_topic_combo_v119))
        return;
    bool shown=concept98_enabled && current_peer &&
        current_peer->type==2 && concept98_forum_loaded_v119 &&
        !concept98_forum_topics_v119.empty();
    if(IsWindowVisible(concept98_topic_combo_v119)!=shown)
        ShowWindow(concept98_topic_combo_v119,shown?SW_SHOW:SW_HIDE);
    if(concept98_chat_detail &&
       IsWindowVisible(concept98_chat_detail)==shown)
        ShowWindow(concept98_chat_detail,shown?SW_HIDE:SW_SHOW);
}
static void concept98_forum_reset_v119(){
    concept98_forum_selected_v119=0;
    concept98_forum_loaded_v119=false;
    concept98_forum_pending_v119=false;
    concept98_forum_topics_v119.clear();
    memset(concept98_forum_rpc_v119,0,8);
    memset(concept98_forum_history_rpc_v119,0,8);
    concept98_forum_history_pending_v119=false;
    if(concept98_topic_combo_v119)
        SendMessageW(concept98_topic_combo_v119,CB_RESETCONTENT,0,0);
    if(msgInput && current_peer)
        EnableWindow(msgInput,current_peer->perm.cansendmsg);
    concept98_forum_visibility_v119();
}
static void concept98_forum_request_v119(){
    concept98_forum_reset_v119();
    if(!concept98_enabled || !current_peer || current_peer->type!=2 ||
       !dcInfoMain.ready || !read_le(current_peer->access_hash,8))return;
    __int64 id=(__int64)read_le(current_peer->id,8);
    DWORD now=GetTickCount();
    std::map<__int64,DWORD>::iterator it=concept98_forum_attempts_v119.find(id);
    if(it!=concept98_forum_attempts_v119.end() &&
       (DWORD)(now-it->second)<60000)return;
    concept98_forum_attempts_v119[id]=now;
    BYTE query[160]={0},encrypted[184]={0};
    internal_header(query,true);
    int pos=32;
    write_le(query+pos,0x0de560d1,4);pos+=4; // channels.getForumTopics
    memset(query+pos,0,4);pos+=4;            // flags (no search query)
    write_le(query+pos,0xf35aec28,4);pos+=4; // inputChannel
    memcpy(query+pos,current_peer->id,8);pos+=8;
    memcpy(query+pos,current_peer->access_hash,8);pos+=8;
    memset(query+pos,0,12);pos+=12; // offset_date/id/topic
    write_le(query+pos,100,4);pos+=4; // bounded server page
    write_le(query+28,pos-32,4);
    int padding=get_padding(pos);
    if(padding<0||pos+padding>160)return;
    fortuna_read(query+pos,padding,&prng);pos+=padding;
    memcpy(concept98_forum_rpc_v119,query+16,8);
    memcpy(concept98_forum_peer_v119,current_peer->id,8);
    if(!convert_message(query,encrypted,pos,0))return;
    int sent=send_query(encrypted,pos+24);
    concept98_forum_pending_v119=sent>0;
    diag_log("concept98 v119 topics request sent=%d peer=%I64d",
             sent,id);
}
bool concept98_forum_receive_v119(
    const BYTE* rpc,BYTE* data,int length
){
    if(!rpc||!data||!concept98_forum_pending_v119||
       memcmp(rpc,concept98_forum_rpc_v119,8)!=0)return false;
    concept98_forum_pending_v119=false;
    if(!current_peer || current_peer->type!=2 ||
       memcmp(current_peer->id,concept98_forum_peer_v119,8)!=0)
        return true;
    // messages.forumTopics#367617d3:
    // flags, count, vector signature, number of topics, topics[].
    if(length<24 || read_le(data,4)!=0x367617d3 ||
       read_le(data+12,4)!=0x1cb5c415) {
        diag_log("concept98 v119 unsupported forumTopics reply length=%d",
                 length);
        return true;
    }
    int count=(int)read_le(data+16,4);
    if(count<1 || count>1000)return true;
    // At API layer 196 the stable topic constructor is #71701da9.
    // Find only 4-byte aligned constructors after the vector header,
    // checking every string bound, never trusting unknown topic fields.
    std::vector<ConceptForumTopic119> discovered;
    for(int at=20;at+24<length && (int)discovered.size()<count;at+=4){
        if(read_le(data+at,4)!=0x71701da9)continue;
        int id=(int)read_le(data+at+8,4);
        int date=(int)read_le(data+at+12,4);
        int sp=at+16;
        if(id<1||date<1300000000||sp+4>=length)continue;
        int len=(unsigned char)data[sp];
        int prefix=1;
        if(len==254){
            len=(int)data[sp+1]|((int)data[sp+2]<<8)|
                ((int)data[sp+3]<<16);
            prefix=4;
        }
        if(len<1||len>256||sp+prefix+len>length)continue;
        wchar_t title[260]={0};
        int written=MultiByteToWideChar(
            CP_UTF8,MB_ERR_INVALID_CHARS,
            (LPCCH)(data+sp+prefix),len,title,259);
        if(written<=0)continue;
        title[written]=0;
        bool exists=false;
        for(size_t i=0;i<discovered.size();i++)
            if(discovered[i].id==id)exists=true;
        if(exists)continue;
        ConceptForumTopic119 topic;
        topic.id=id;topic.title=title;
        discovered.push_back(topic);
    }
    if(discovered.empty()){
        diag_log("concept98 v119 no parseable topic records count=%d",count);
        return true;
    }
    concept98_forum_topics_v119.swap(discovered);
    concept98_forum_loaded_v119=true;
    HWND combo=concept98_topic_combo_v119;
    if(combo){
        SendMessageW(combo,CB_RESETCONTENT,0,0);
        int ix=(int)SendMessageW(combo,CB_ADDSTRING,0,
                                 (LPARAM)L"\x0412\x0441\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x044f");
        if(ix>=0)SendMessageW(combo,CB_SETITEMDATA,ix,0);
        for(size_t i=0;i<concept98_forum_topics_v119.size();i++){
            const ConceptForumTopic119& item=concept98_forum_topics_v119[i];
            int row=(int)SendMessageW(combo,CB_ADDSTRING,0,
                                     (LPARAM)item.title.c_str());
            if(row>=0)SendMessageW(combo,CB_SETITEMDATA,row,item.id);
        }
        SendMessageW(combo,CB_SETCURSEL,0,0);
    }
    concept98_forum_visibility_v119();
    diag_log("concept98 v119 forum topics ready count=%d",
             (int)concept98_forum_topics_v119.size());
    return true;
}
static void concept98_forum_select_v119(){
    if(!concept98_forum_loaded_v119 || !current_peer ||
       !concept98_topic_combo_v119)return;
    int index=(int)SendMessageW(concept98_topic_combo_v119,
                                CB_GETCURSEL,0,0);
    if(index<0)return;
    LRESULT value=SendMessageW(concept98_topic_combo_v119,
                               CB_GETITEMDATA,index,0);
    if(value==CB_ERR)return;
    int id=(int)value;
    if(concept98_forum_selected_v119==id)return;
    concept98_forum_selected_v119=id;
    // Selecting a topic shows only that server thread. Sending requires
    // inputReplyToMessage.top_msg_id, not implemented in this release.
    // Disable composer rather than silently writing to the wrong thread.
    if(msgInput)
        EnableWindow(msgInput,id==0 && current_peer->perm.cansendmsg);
    if(media_chat_full_photo_active)media_chat_full_photo_reset(true);
    message_search_clear_chat_view();
    InterlockedExchange(&history_request_pending,0);
    no_more_msgs=false;
    diag_log("concept98 v119 forum switched topic=%d (read only)",id);
    get_history();
}
'''
s=one(s,anchor,network+"\n"+anchor,"forum helper placement")
# native combo exactly over the existing static "Канал" label
s=one(s,
'''    concept98_move_v91(concept98_chat_detail, content_x+46, 57,
                       title_w-46, 17);''',
'''    concept98_move_v91(concept98_chat_detail, content_x+46, 57,
                       title_w-46, 17);
    concept98_move_v91(concept98_topic_combo_v119,
                       content_x+46, 54, title_w-46, 240);''',
"forum layout")
s=one(s,
'''    concept98_chat_detail = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT,
        250,57,220,17,hwnd,NULL,NULL,NULL
    );''',
'''    concept98_chat_detail = CreateWindowW(
        L"STATIC", L"", panel | SS_LEFT,
        250,57,220,17,hwnd,NULL,NULL,NULL
    );
    concept98_topic_combo_v119=CreateWindowExW(
        WS_EX_CLIENTEDGE,L"COMBOBOX",L"",
        WS_CHILD|WS_VSCROLL|WS_TABSTOP|CBS_DROPDOWNLIST,
        250,54,220,240,hwnd,(HMENU)8999,NULL,NULL
    );''',
"create forum combo")
s=one(s,'''        concept98_chat_title, concept98_chat_detail,
        concept98_search_button, concept98_profile_button,''',
'''        concept98_chat_title, concept98_chat_detail,
        concept98_topic_combo_v119,
        concept98_search_button, concept98_profile_button,''',
"forum native fonts")
s=one(s,
'''    if (current_peer && current_peer->name) {
        wchar_t oldname[256] = {0};''',
'''    concept98_forum_visibility_v119();
    if (current_peer && current_peer->name) {
        wchar_t oldname[256] = {0};''',
"sidebar topic visibility synchronization")
# Peer change fetches forum topics once; nonforum peers keep ordinary label.
s=one(s,'''            current_peer = selected_peer;
            media_archive_clear();''',
'''            current_peer = selected_peer;
            concept98_forum_request_v119();
            media_archive_clear();''',
"forum peer change")
s=one(s,'''        case 3004: { // media archive''',
'''        case 8999: { // concept98 v119 real forum topic choice
            if(HIWORD(wParam)==CBN_SELCHANGE)
                concept98_forum_select_v119();
            break;
        }
        case 3004: { // media archive''',
"forum native command")
# Do not add per-timer network spam: use the existing on-peer-change hook.
cpp.write_text(s,encoding="latin-1",newline="\r\n")
# messages.getReplies#22ddd30c shares the messages.Messages return parser with
# getHistory; note the RPC ID for stale-response checks.
h=one(h,'''    write_le(unenc_query + 32, 0x4423e6c5, 4);''',
'''    int forum_topic_id=concept98_current_topic_v119();
    write_le(unenc_query+32,
             forum_topic_id>0 ? 0x22ddd30c : 0x4423e6c5,4);''',
"getHistory constructor")
h=one(h,'''    int oldest_id = messages.size() ? messages.front().id : 0;''',
'''    if(forum_topic_id>0){
        write_le(unenc_query+36+offset,forum_topic_id,4);
        offset+=4;
    }
    int oldest_id = messages.size() ? messages.front().id : 0;''',
"getReplies topic ID")
h=one(h,'''    convert_message(
        unenc_query,
        enc_query,
        len,
        0
    );''',
'''    concept98_note_topic_history_rpc_v119(unenc_query+16);
    convert_message(
        unenc_query,
        enc_query,
        len,
        0
    );''',
"forum history RPC identity")
h=h.replace("#include <telegacy.h>","#include <telegacy.h>\nextern int concept98_current_topic_v119();\nextern void concept98_note_topic_history_rpc_v119(const BYTE*);",1)
helpers.write_text(h,encoding="latin-1",newline="\r\n")
r=r.replace("#include <telegacy.h>","#include <telegacy.h>\nextern bool concept98_forum_receive_v119(const BYTE*,BYTE*,int);\nextern bool concept98_accept_topic_history_v119(const BYTE*);",1)
r=one(r,'''    case 0x5f206716: // messages.messagesSlice (newer)''',
'''    case 0x367617d3: { // concept98 v119: messages.forumTopics
        concept98_forum_receive_v119(last_rpcresult_msgid,
                                     unenc_response,length);
        break;
    }
    case 0x5f206716: // messages.messagesSlice (newer)''',
"forumTopics response")
r=one(r,'''        int offset_msg = 12;
        if (constructor != 0x8c718e87) {''',
'''        if(!concept98_accept_topic_history_v119(last_rpcresult_msgid)){
            diag_log("concept98 v119 rejected unrelated topic history response");
            break;
        }
        int offset_msg = 12;
        if (constructor != 0x8c718e87) {''',
"history thread response isolation")
response.write_text(r,encoding="latin-1",newline="\r\n")
print("Concept98 v11.9: real forum topics query/dropdown and read-only thread histories; global chat remains unchanged.")
