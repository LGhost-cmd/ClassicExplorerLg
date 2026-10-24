#!/usr/bin/env python3
"""Concept98 v13.4: preserve reply targets and quoted text independently of
Telegacy's ephemeral reply_needed field; robust native click hit testing on
real reply-label glyphs even when RichEdit fails to emit EN_LINK.
Never mutate the original RichEdit document or OLE character positions."""
from pathlib import Path
import sys

if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_reply_links_v134.py <src>")
root=Path(sys.argv[1]).resolve()
h=root/"include"/"telegacy.h"
m=root/"src"/"message.cpp"
t=root/"src"/"telegacy.cpp"
p=root/"src"/"procs.cpp"
src={path:path.read_text(encoding="latin-1") for path in (h,m,t,p)}
if "concept98_reply_links_v134" in src[t]:
    print("v13.4 already applied")
    raise SystemExit(0)
if "concept98_reply_hit_v132" not in src[t]:
    raise SystemExit("v13.4 requires v13.2")
def one(path,old,new,label):
    original=src[path]
    count=original.count(old)
    if count!=1:
        raise SystemExit("v13.4 "+label+": matches="+str(count))
    src[path]=original.replace(old,new,1)

one(h,
    "int start_char, end_header, end_char, start_reactions, end_footer, reply_needed, id;",
    """int start_char, end_header, end_char, start_reactions, end_footer, reply_needed, id;
    // concept98_reply_links_v134: stable, never cleared by the reply RPC.
    int concept98_reply_target_v134;
    std::wstring concept98_reply_quote_v134;""",
    "persist reply identity in Message")
if "#include <string>" not in src[h]:
    one(h,"#include <vector>","#include <string>\n#include <vector>",
        "std::wstring include")

# Keep the immutable reply-to ID even for grouped messages where the visual
# message header is temporarily suppressed. Cache only the bounded TL quote
# stored with the original Telegram reply header.
one(m,
    "message.concept98_author_id_v132=identity_v132;",
    r'''message.concept98_author_id_v132=identity_v132;
    // concept98_reply_links_v134: reply_needed can later be reset by
    // set_reply_tofront() and Telegram RPC handling. This field cannot.
    message.concept98_reply_target_v134=0;
    if(msgrpl){
        const int rf_v134=(int)read_le(msgrpl+4,4);
        if(rf_v134&(1<<4))
            message.concept98_reply_target_v134=(int)read_le(msgrpl+8,4);
        if(rf_v134&(1<<6)){
            int off_v134=8;
            if(rf_v134&(1<<4))off_v134+=4;
            if(rf_v134&(1<<0))off_v134+=12;
            if(rf_v134&(1<<5))
                off_v134+=msgfwd_offset(msgrpl+off_v134);
            if(rf_v134&(1<<8))
                off_v134+=messagemedia_offset(msgrpl+off_v134);
            if(rf_v134&(1<<1))off_v134+=4;
            const int n_v134=tlstr_to_str_len(msgrpl+off_v134);
            if(n_v134>0 && n_v134<=4096){
                wchar_t* txt_v134=read_string(msgrpl+off_v134,NULL);
                if(txt_v134){
                    message.concept98_reply_quote_v134=txt_v134;
                    free(txt_v134);
                }
            }
        }
    }''',
    "capture reply id and TL quoted text")

# The existing v13.2 callback assumes EN_LINK's chrg always covers exactly
# the label. In RichEdit it can be a smaller run. Unify hit handling for the
# native notification AND the mouse click, with a pixel-bound label test.
start=src[t].find("static bool concept98_reply_hit_v132(const ENLINK* event){")
end=src[t].find("static bool concept98_forward_hit_v130(const ENLINK* event){",start)
if start<0 or end<=start:
    raise SystemExit("v13.4 could not find v13.2 reply handler boundaries")
new_handler=r'''// concept98_reply_links_v134: compare the visible label glyph bounds, never
// the entire header, whitespace, media box or sender nickname.
static bool concept98_context_label_range_v134(
    const Message& row,const wchar_t* label,int* first,int* last)
{
    if(row.end_header<=row.start_char)return false;
    const int size=row.end_header-row.start_char;
    if(size<=0 || size>4096)return false;
    std::vector<wchar_t> body(size+1,0);
    TEXTRANGEW tr={0};
    tr.chrg.cpMin=row.start_char;
    tr.chrg.cpMax=row.end_header;
    tr.lpstrText=&body[0];
    LRESULT copied=SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
    if(copied<=0 || copied>size)return false;
    const wchar_t* located=wcsstr(&body[0],label);
    if(!located)return false;
    *first=row.start_char+(int)(located-&body[0]);
    *last=*first+(int)wcslen(label);
    return *first>=row.start_char && *last<=row.end_header;
}
static const wchar_t* concept98_reply_tag_v134=
    L"\x041e\x0442\x0432\x0435\x0442 \x043d\x0430 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
static const wchar_t* concept98_forward_tag_v134=
    L"\x041f\x0435\x0440\x0435\x0441\x043b\x0430\x043d\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
static bool concept98_reply_activate_v134(size_t index){
    if(!current_peer || index>=messages.size())return false;
    const int target=messages[index].concept98_reply_target_v134;
    // Make a copy before entering nested Win32 message loops.
    const std::wstring quote=messages[index].concept98_reply_quote_v134;
    if(target>0){
        for(size_t j=0;j<messages.size();j++)
            if(messages[j].id==target && messages[j].end_char>messages[j].start_char)
                return concept98_open_forward_v130((int)j,true);
        // The historical message may not be loaded yet. Existing Telegram
        // fetch is asynchronous; do not claim that it is already present.
        get_message(target,current_peer);
    }
    // Use the existing Win98 native RTF popup for an available embedded
    // Telegram quote. Never copy the replying message as the original.
    if(!concept98_open_forward_v130((int)index,true))return false;
    concept98_forward_paths_v130.clear();
    SendMessageW(concept98_forward_files_v130,LB_RESETCONTENT,0,0);
    SendMessageW(concept98_forward_rich_v130,WM_SETTEXT,0,
        (LPARAM)(quote.empty()?
         (target>0?
          L"\x0418\x0441\x0445\x043e\x0434\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435 \x0437\x0430\x043f\x0440\x043e\x0448\x0435\x043d\x043e \x0438\x0437 Telegram. \x041e\x043d\x043e \x0435\x0449\x0451 \x043d\x0435 \x0437\x0430\x0433\x0440\x0443\x0436\x0435\x043d\x043e; \x043f\x043e\x0432\x0442\x043e\x0440\x0438\x0442\x0435 \x043d\x0430\x0436\x0430\x0442\x0438\x0435 \x043f\x043e\x0437\x0436\x0435.":
          L"\x0412 \x0434\x0430\x043d\x043d\x044b\x0445 Telegram \x043d\x0435\x0442 ID \x0438\x043b\x0438 \x0442\x0435\x043a\x0441\x0442\x0430 \x0438\x0441\x0445\x043e\x0434\x043d\x043e\x0433\x043e \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x044f.") :
         quote.c_str()));
    if(concept98_forward_files_v130)
        SendMessageW(concept98_forward_files_v130,LB_ADDSTRING,0,
         (LPARAM)L"\x0412\x043b\x043e\x0436\x0435\x043d\x0438\x044f \x0438\x0441\x0445\x043e\x0434\x043d\x0438\x043a\x0430 \x043d\x0435 \x0437\x0430\x0433\x0440\x0443\x0436\x0435\x043d\x044b");
    return true;
}
static bool concept98_reply_hit_v132(const ENLINK* event){
    if(!concept98_enabled || !event || !chat)return false;
    for(size_t i=0;i<messages.size();i++){
        int a=0,b=0;
        if(!concept98_context_label_range_v134(messages[i],concept98_reply_tag_v134,&a,&b))continue;
        if(event->chrg.cpMin>=a && event->chrg.cpMin<b &&
           event->chrg.cpMax<=b+1)
            return concept98_reply_activate_v134(i);
    }
    return false;
}
// RichEdit 2.0 sometimes does not emit EN_LINK for a mixed-format header.
// Hit-test the actual label rectangle directly, before the inherited
// WndProcChat handler can consume its WM_LBUTTONDOWN.
bool concept98_reply_click_v134(POINT point){
    if(!concept98_enabled || !chat || !current_peer)return false;
    for(size_t i=0;i<messages.size();i++){
        for(int type=0;type<2;type++){
            const wchar_t* tag=type==0?concept98_reply_tag_v134:
                                         concept98_forward_tag_v134;
            int a=0,b=0;
            if(!concept98_context_label_range_v134(messages[i],tag,&a,&b))
                continue;
            POINTL start={0},stop={0};
            SendMessageW(chat,EM_POSFROMCHAR,(WPARAM)&start,(LPARAM)a);
            SendMessageW(chat,EM_POSFROMCHAR,(WPARAM)&stop,(LPARAM)b);
            if(start.y!=stop.y || stop.x<=start.x)continue;
            HDC dc=GetDC(chat);
            int h=19;
            if(dc){
                HGDIOBJ old=SelectObject(dc,hFonts[0]);
                TEXTMETRICW tm={0};
                if(GetTextMetricsW(dc,&tm))h=tm.tmHeight+tm.tmExternalLeading;
                SelectObject(dc,old);
                ReleaseDC(chat,dc);
            }
            // Only the actual glyph run, not the remainder of the line.
            if(point.x<(int)start.x || point.y<(int)start.y ||
               point.x>=(int)stop.x || point.y>=(int)start.y+h)
                continue;
            if(type==0)return concept98_reply_activate_v134(i);
            return concept98_open_forward_v130((int)i,false);
        }
    }
    return false;
}
'''
src[t]=src[t][:start]+new_handler+src[t][end:]
one(p,
    "LRESULT CALLBACK WndProcChat(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {",
    """extern bool concept98_reply_click_v134(POINT);
LRESULT CALLBACK WndProcChat(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if(concept98_enabled && hWnd==chat && msg==WM_LBUTTONDOWN){
        POINT pt={GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam)};
        if(concept98_reply_click_v134(pt))return 0;
    }""",
    "exact direct click before legacy profile handler")
for path,body in src.items():
    path.write_text(body,encoding="latin-1",newline="\r\n")
print("v13.4: persistent reply reference and TL quote; exact clickable glyphs for native and fallback mouse events.")
