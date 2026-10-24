#!/usr/bin/env python3
"""Concept98 v14.0: real nested Win98 reply branch cards.
Each available message is streamed as its original RTF/OLE into its own
read-only native RichEdit; absent messages get their actual Telegram text
while the real source is fetched. No bracketed [Message] placeholders,
no artificial attachment-only sidebar for branch mode."""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_nested_cards_v140.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_nested_cards_v140" in s: raise SystemExit(0)
if "concept98_forward_chain_v139" not in s: raise SystemExit("v13.9 prerequisite missing")
def one(a,b,label):
 global s
 n=s.count(a)
 if n!=1: raise SystemExit("v14.0 "+label+" matches="+str(n))
 s=s.replace(a,b,1)

# Branch mode is a client-only presentation. Reuse the existing top-level
# Windows 98 viewer rather than creating a second competing popup.
anchor="static const wchar_t* concept98_forward_label_v130="
state=r'''// concept98_nested_cards_v140
static HWND concept98_branch_host_v140=NULL;
static bool concept98_branch_active_v140=false;
struct Concept98BranchCard140 {
    HWND panel;
    HWND rich;
    int id,depth,y,height;
    Concept98BranchCard140():panel(NULL),rich(NULL),id(0),depth(0),y(0),height(0){}
};
static std::vector<Concept98BranchCard140> concept98_branch_cards_v140;
static int concept98_branch_total_v140=0;
static int concept98_branch_scroll_v140=0;
static void concept98_branch_layout_v140();
static bool concept98_branch_render_v140();
static void concept98_branch_clear_v140();
'''
one(anchor,state+anchor,"viewer global branch state")
# Forward-only windows keep their original useful single-message viewer.
one("static bool concept98_open_forward_v130(int index,bool reply_view_v132=false){",
"""static bool concept98_open_forward_v130(int index,bool reply_view_v132=false){
    concept98_branch_active_v140=false;
    if(concept98_branch_host_v140)
        ShowWindow(concept98_branch_host_v140,SW_HIDE);
    if(concept98_forward_rich_v130)
        ShowWindow(concept98_forward_rich_v130,SW_SHOW);
    if(concept98_forward_files_v130)
        ShowWindow(concept98_forward_files_v130,SW_SHOW);""",
"restore forward-only viewer")
one('''    if(msg==WM_SIZE){
        int wid=LOWORD(l),hei=HIWORD(l);''',
'''    if(msg==WM_SIZE){
        if(concept98_branch_host_v140 && concept98_branch_active_v140){
            MoveWindow(concept98_branch_host_v140,8,8,
                (int)LOWORD(l)-16,(int)HIWORD(l)-16,TRUE);
            concept98_branch_layout_v140();
            return 0;
        }
        int wid=LOWORD(l),hei=HIWORD(l);''',
"nested pane window resize")
one('''    if(msg==WM_DESTROY){
        concept98_forward_win_v130=NULL;''',
'''    if(msg==WM_DESTROY){
        concept98_branch_active_v140=false;
        concept98_branch_clear_v140();
        concept98_branch_host_v140=NULL;
        concept98_forward_win_v130=NULL;''',
"viewer children cleanup")
one('''static void concept98_reply_refresh_v136(){
    if(!concept98_reply_root_v136''',
'''static void concept98_reply_refresh_v136(){
    if(concept98_branch_render_v140()) return;
    if(!concept98_reply_root_v136''',
"replace plain chain text view")
# Append definitions after all snapshot/node/RPC code but before the next
# v13.4 reply click handler (which calls the popup).
anchor="static bool concept98_reply_activate_v134(size_t index){"
impl=r'''// concept98_nested_cards_v140: classic inset blocks with L-shaped rails.
static void concept98_branch_clear_v140(){
    for(size_t i=0;i<concept98_branch_cards_v140.size();i++)
        if(concept98_branch_cards_v140[i].panel &&
           IsWindow(concept98_branch_cards_v140[i].panel))
            DestroyWindow(concept98_branch_cards_v140[i].panel);
    concept98_branch_cards_v140.clear();
    concept98_branch_total_v140=0;
}
static void concept98_branch_layout_v140(){
    if(!concept98_branch_host_v140 ||
       !IsWindow(concept98_branch_host_v140))return;
    RECT area={0};GetClientRect(concept98_branch_host_v140,&area);
    const int width=area.right-area.left;
    const int height=area.bottom-area.top;
    concept98_branch_scroll_v140=
        max(0,min(concept98_branch_scroll_v140,
                  max(0,concept98_branch_total_v140-height)));
    for(size_t i=0;i<concept98_branch_cards_v140.size();i++){
        Concept98BranchCard140& c=concept98_branch_cards_v140[i];
        int x=18+min(c.depth,10)*23;
        int w=max(220,width-x-18);
        if(c.panel && IsWindow(c.panel)){
            MoveWindow(c.panel,x,c.y-concept98_branch_scroll_v140,
                       w,c.height,TRUE);
            if(c.rich)
                MoveWindow(c.rich,9,29,max(80,w-18),
                           max(38,c.height-36),TRUE);
        }
    }
    SCROLLINFO si={0};si.cbSize=sizeof(si);
    si.fMask=SIF_PAGE|SIF_RANGE|SIF_POS;
    si.nMin=0;si.nMax=max(0,concept98_branch_total_v140);
    si.nPage=max(1,height);si.nPos=concept98_branch_scroll_v140;
    SetScrollInfo(concept98_branch_host_v140,SB_VERT,&si,TRUE);
    InvalidateRect(concept98_branch_host_v140,NULL,FALSE);
}
static LRESULT CALLBACK concept98_branch_proc_v140(
    HWND wnd,UINT msg,WPARAM w,LPARAM l){
    switch(msg){
    case WM_ERASEBKGND:{
        RECT r={0};GetClientRect(wnd,&r);
        FillRect((HDC)w,&r,GetSysColorBrush(COLOR_BTNFACE));
        return 1;
    }
    case WM_PAINT:{
        PAINTSTRUCT ps={0};HDC dc=BeginPaint(wnd,&ps);
        HPEN pen=CreatePen(PS_SOLID,2,GetSysColor(COLOR_3DSHADOW));
        HGDIOBJ old=SelectObject(dc,pen);
        for(size_t i=0;i<concept98_branch_cards_v140.size();i++){
            const Concept98BranchCard140& c=concept98_branch_cards_v140[i];
            if(!c.depth)continue;
            const int x=18+min(c.depth,10)*23;
            const int y=c.y-concept98_branch_scroll_v140;
            MoveToEx(dc,x-12,y-6,NULL);
            LineTo(dc,x-12,y+22);
            LineTo(dc,x-3,y+22);
        }
        SelectObject(dc,old);DeleteObject(pen);
        EndPaint(wnd,&ps);return 0;
    }
    case WM_SIZE:
        concept98_branch_layout_v140();return 0;
    case WM_VSCROLL:{
        SCROLLINFO si={0};si.cbSize=sizeof(si);
        si.fMask=SIF_ALL;GetScrollInfo(wnd,SB_VERT,&si);
        int next=concept98_branch_scroll_v140;
        switch(LOWORD(w)){
            case SB_TOP:next=0;break;
            case SB_BOTTOM:next=concept98_branch_total_v140;break;
            case SB_LINEUP:next-=35;break;
            case SB_LINEDOWN:next+=35;break;
            case SB_PAGEUP:next-=(int)si.nPage;break;
            case SB_PAGEDOWN:next+=(int)si.nPage;break;
            case SB_THUMBTRACK:next=si.nTrackPos;break;
            default:break;
        }
        concept98_branch_scroll_v140=next;
        concept98_branch_layout_v140();return 0;
    }
    case WM_MOUSEWHEEL:
        concept98_branch_scroll_v140-=
           (short)HIWORD(w)/WHEEL_DELTA*65;
        concept98_branch_layout_v140();return 0;
    }
    return DefWindowProcW(wnd,msg,w,l);
}
static bool concept98_branch_ensure_v140(){
    if(!concept98_forward_win_v130 ||
       !IsWindow(concept98_forward_win_v130))return false;
    if(!concept98_branch_host_v140 ||
       !IsWindow(concept98_branch_host_v140)){
        static bool registered=false;
        if(!registered){
            WNDCLASSW wc={0};
            wc.lpfnWndProc=concept98_branch_proc_v140;
            wc.hInstance=GetModuleHandleW(NULL);
            wc.lpszClassName=L"TelegacyReplyBranchesV140";
            wc.hCursor=LoadCursor(NULL,IDC_ARROW);
            wc.hbrBackground=GetSysColorBrush(COLOR_BTNFACE);
            if(!RegisterClassW(&wc) &&
               GetLastError()!=ERROR_CLASS_ALREADY_EXISTS)return false;
            registered=true;
        }
        RECT area={0};GetClientRect(concept98_forward_win_v130,&area);
        concept98_branch_host_v140=CreateWindowExW(
            WS_EX_CLIENTEDGE,L"TelegacyReplyBranchesV140",L"",
            WS_CHILD|WS_VISIBLE|WS_VSCROLL|WS_CLIPCHILDREN,
            8,8,max(260,area.right-16),max(200,area.bottom-16),
            concept98_forward_win_v130,(HMENU)1410,
            GetModuleHandleW(NULL),NULL);
    }
    if(!concept98_branch_host_v140)return false;
    ShowWindow(concept98_forward_rich_v130,SW_HIDE);
    ShowWindow(concept98_forward_files_v130,SW_HIDE);
    ShowWindow(concept98_branch_host_v140,SW_SHOW);
    concept98_branch_active_v140=true;
    return true;
}
static bool concept98_branch_copy_rtf_v140(HWND destination,
                                           const Message& row){
    if(!chat || !destination || row.end_char<=row.start_char ||
       row.end_char-row.start_char>32000)return false;
    CHARRANGE original={0};
    SendMessageW(chat,EM_EXGETSEL,0,(LPARAM)&original);
    POINT scroll={0,0};
    SendMessageW(chat,EM_GETSCROLLPOS,0,(LPARAM)&scroll);
    SendMessageW(chat,EM_SETSEL,row.start_char,row.end_char);
    StreamData data={0};EDITSTREAM out={0};
    out.dwCookie=(DWORD_PTR)&data;out.pfnCallback=StreamOutCallback;
    SendMessageW(chat,EM_STREAMOUT,SF_RTF|SFF_SELECTION,(LPARAM)&out);
    SendMessageW(chat,EM_EXSETSEL,0,(LPARAM)&original);
    SendMessageW(chat,EM_SETSCROLLPOS,0,(LPARAM)&scroll);
    bool okay=false;
    if(data.buf && data.length>0 && out.dwError==0){
        EDITSTREAM in={0};in.dwCookie=(DWORD_PTR)&data;
        in.pfnCallback=StreamInCallback;
        SendMessageW(destination,EM_STREAMIN,SF_RTF,(LPARAM)&in);
        okay=in.dwError==0;
    }
    free(data.buf);
    return okay;
}
static bool concept98_branch_render_v140(){
    if(!concept98_reply_root_v136 ||
       !concept98_forward_win_v130 ||
       !concept98_reply_peer_check_v136())return false;
    if(!concept98_branch_ensure_v140())return false;
    concept98_branch_clear_v140();
    std::set<int> visited;
    int id=concept98_reply_root_v136;
    int y=12;
    for(int depth=0;id>0 && depth<12;depth++){
        if(!visited.insert(id).second)break;
        const Message* row=NULL;
        for(size_t j=0;j<messages.size();j++)
            if(messages[j].id==id){row=&messages[j];break;}
        std::map<int,Concept98ReplySnapshot136>::iterator it=
            concept98_reply_nodes_v136.find(id);
        const bool ready=it!=concept98_reply_nodes_v136.end();
        const bool has_media=ready&&it->second.media;
        const std::wstring plain=ready?it->second.body:L"";
        // Enough room for native embedded OLE stickers/photos; long messages
        // remain scrollable within their own card, not visually clipped.
        int content_height=has_media?310:115;
        if(plain.size()>100)
            content_height+=min(150,(int)plain.size()/50*18);
        content_height=min(450,content_height);
        Concept98BranchCard140 c;
        c.id=id;c.depth=depth;c.y=y;
        c.height=content_height+36;
        c.panel=CreateWindowExW(WS_EX_CLIENTEDGE,L"STATIC",L"",
            WS_CHILD|WS_VISIBLE|WS_CLIPCHILDREN,
            0,0,300,c.height,concept98_branch_host_v140,
            NULL,GetModuleHandleW(NULL),NULL);
        if(!c.panel)break;
        const wchar_t* heading=depth?
            L"\x0412 \x043e\x0442\x0432\x0435\x0442 \x043d\x0430":
            L"\x0422\x0435\x043a\x0443\x0449\x0435\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
        HWND hTitle=CreateWindowExW(0,L"STATIC",heading,
            WS_CHILD|WS_VISIBLE|SS_LEFT,
            9,6,360,19,c.panel,NULL,GetModuleHandleW(NULL),NULL);
        if(hTitle)SendMessageW(hTitle,WM_SETFONT,(WPARAM)hFonts[2],TRUE);
        c.rich=CreateWindowExW(0,L"RichEdit20W",L"",
            WS_CHILD|WS_VISIBLE|WS_VSCROLL|ES_MULTILINE|
            ES_READONLY|ES_AUTOVSCROLL|WS_TABSTOP,
            9,29,280,content_height,c.panel,
            NULL,GetModuleHandleW(NULL),NULL);
        if(c.rich){
            SendMessageW(c.rich,WM_SETFONT,(WPARAM)hFonts[0],FALSE);
            SendMessageW(c.rich,EM_SETBKGNDCOLOR,0,
                (LPARAM)colors[1]);
            COleCallback* cb=new COleCallback(c.rich);
            SendMessageW(c.rich,EM_SETOLECALLBACK,0,(LPARAM)cb);
            cb->Release();
            bool copied=row&&concept98_branch_copy_rtf_v140(c.rich,*row);
            if(!copied){
                std::wstring body;
                if(ready){
                    body=plain;
                    if(body.empty() && !has_media)
                        body=L"\x0422\x0435\x043a\x0441\x0442 \x043e\x0442\x0441\x0443\x0442\x0441\x0442\x0432\x0443\x0435\x0442";
                    if(has_media){
                        if(!body.empty())body+=L"\r\n";
                        body+=L"\x0412\x043b\x043e\x0436\x0435\x043d\x0438\x0435 \x043f\x043e\x043b\x0443\x0447\x0435\x043d\x043e \x0438\x0437 Telegram";
                    }
                }else{
                    body=L"\x041f\x043e\x043b\x0443\x0447\x0430\x0435\x043c \x0438\x0441\x0445\x043e\x0434\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435...";
                    for(size_t j=0;j<messages.size();j++)
                        if(messages[j].concept98_reply_target_v134==id &&
                            !messages[j].concept98_reply_quote_v134.empty()){
                            body=L"\x0426\x0438\x0442\x0430\x0442\x0430: "+
                                 messages[j].concept98_reply_quote_v134;
                            break;
                        }
                    concept98_reply_request_v136(id);
                }
                SendMessageW(c.rich,WM_SETTEXT,0,(LPARAM)body.c_str());
            }
            SendMessageW(c.rich,EM_SETSEL,0,0);
        }
        concept98_branch_cards_v140.push_back(c);
        y+=c.height+13;
        if(!ready)break;
        id=it->second.parent;
    }
    concept98_branch_total_v140=y+12;
    concept98_branch_layout_v140();
    SetWindowTextW(concept98_forward_win_v130,
        L"\x0426\x0435\x043f\x043e\x0447\x043a\x0430 \x043e\x0442\x0432\x0435\x0442\x043e\x0432 | Telegacy");
    return true;
}
'''
one(anchor,impl+anchor,"insert branch renderer after reply snapshot helpers")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("Concept98 v14.0: classic linked reply cards; source RTF including inline OLE media; on-demand missing replies.")
