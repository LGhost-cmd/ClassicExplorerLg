#!/usr/bin/env python3
"""Concept98 v13.0: Win98 forwarded-message label opens full rich-text and
attachment window. The actual chat/OLE objects and char offsets are untouched."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_forward_view_v130.py <src>")
root=Path(sys.argv[1]).resolve();m=root/"src"/"message.cpp";t=root/"src"/"telegacy.cpp"
a=m.read_text(encoding="latin-1");s=t.read_text(encoding="latin-1")
if "concept98_forward_view_v130" in s:raise SystemExit(0)
if "concept98_chat_polish_v128" not in a:raise SystemExit("v12.8 missing")
def one(v,old,new,label):
 n=v.count(old)
 if n!=1:raise SystemExit("v13.0 "+label+" occurrences="+str(n))
 return v.replace(old,new,1)
# Make only the short "Пересланное сообщение" heading a LINK.
marker="    // concept98_readable_ui_v127: distinguish reply/forward context from"
style=r'''    // concept98_forward_view_v130: a native link only on the exact
    // forwarded-message heading, not the whole quote or author line.
    if(msgfwd && !context_v128.empty() && header){
        std::wstring tag=L"\x041f\x0435\x0440\x0435\x0441\x043b\x0430\x043d\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
        size_t where=context_v128.find(tag);
        if(where!=std::wstring::npos){
            int a=message.start_char+ordinary_header_len_v128+(int)where;
            int z=a+(int)tag.size();
            if(a>=message.start_char && z<=message.end_header){
                SendMessageW(chat,EM_SETSEL,a,z);
                CHARFORMAT2 f;ZeroMemory(&f,sizeof(f));f.cbSize=sizeof(f);
                f.dwMask=CFM_LINK|CFM_UNDERLINE|CFM_COLOR;
                f.dwEffects=CFE_LINK|CFE_UNDERLINE;
                f.crTextColor=GetSysColor(COLOR_HOTLIGHT);
                SendMessageW(chat,EM_SETCHARFORMAT,SCF_SELECTION,(LPARAM)&f);
            }
        }
    }
'''
a=one(a,marker,style+marker,"style forwarded exact label")
# Top-level classic Win98 window, reusable; RTF stream preserves formatting
# and currently rendered OLE objects. Attachment filenames are also listed.
global_anchor="static bool concept98_split_drag_v128=false;"
viewer=r'''// concept98_forward_view_v130: view a forwarded message without touching chat
// text, media OLE anchors, scroll position or downloads.
static HWND concept98_forward_win_v130=NULL;
static HWND concept98_forward_rich_v130=NULL;
static HWND concept98_forward_files_v130=NULL;
static std::vector<std::wstring> concept98_forward_paths_v130;
static const wchar_t* concept98_forward_label_v130=
 L"\x041f\x0435\x0440\x0435\x0441\x043b\x0430\x043d\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";

static LRESULT CALLBACK concept98_forward_proc_v130(HWND h,UINT msg,WPARAM w,LPARAM l){
    if(msg==WM_CREATE){
        concept98_forward_rich_v130=CreateWindowExW(
            WS_EX_CLIENTEDGE,L"RichEdit20W",L"",
            WS_CHILD|WS_VISIBLE|WS_VSCROLL|ES_MULTILINE|ES_READONLY|
            ES_AUTOVSCROLL|WS_CLIPSIBLINGS,8,8,490,420,h,
            (HMENU)1301,NULL,NULL);
        concept98_forward_files_v130=CreateWindowExW(
            WS_EX_CLIENTEDGE,L"LISTBOX",L"",
            WS_CHILD|WS_VISIBLE|WS_VSCROLL|LBS_NOTIFY,
            505,8,195,420,h,(HMENU)1302,NULL,NULL);
        if(concept98_forward_rich_v130){
            SendMessageW(concept98_forward_rich_v130,WM_SETFONT,
                         (WPARAM)hFonts[0],TRUE);
            SendMessageW(concept98_forward_rich_v130,EM_SETBKGNDCOLOR,0,
                         (LPARAM)colors[1]);
            COleCallback* ole=new COleCallback(concept98_forward_rich_v130);
            SendMessageW(concept98_forward_rich_v130,EM_SETOLECALLBACK,0,
                         (LPARAM)ole);
            ole->Release();
        }
        if(concept98_forward_files_v130)
            SendMessageW(concept98_forward_files_v130,WM_SETFONT,
                         (WPARAM)hFonts[2],TRUE);
        return 0;
    }
    if(msg==WM_SIZE){
        int wid=LOWORD(l),hei=HIWORD(l);
        int files=wid>=630?195:150;
        if(concept98_forward_rich_v130)MoveWindow(concept98_forward_rich_v130,
            8,8,wid-files-24,hei-16,TRUE);
        if(concept98_forward_files_v130)MoveWindow(concept98_forward_files_v130,
            wid-files-8,8,files,hei-16,TRUE);
        return 0;
    }
    if(msg==WM_COMMAND && LOWORD(w)==1302 &&
       HIWORD(w)==LBN_DBLCLK && concept98_forward_files_v130){
        int k=(int)SendMessageW(concept98_forward_files_v130,LB_GETCURSEL,0,0);
        if(k>=0 && k<(int)concept98_forward_paths_v130.size() &&
           !concept98_forward_paths_v130[k].empty()){
            const wchar_t* path=concept98_forward_paths_v130[k].c_str();
            if(GetFileAttributesW(path)!=INVALID_FILE_ATTRIBUTES)
                ShellExecuteW(h,L"open",path,NULL,NULL,SW_SHOWNORMAL);
        }
        return 0;
    }
    if(msg==WM_CLOSE){DestroyWindow(h);return 0;}
    if(msg==WM_DESTROY){
        concept98_forward_win_v130=NULL;
        concept98_forward_rich_v130=NULL;
        concept98_forward_files_v130=NULL;
        concept98_forward_paths_v130.clear();
        return 0;
    }
    return DefWindowProcW(h,msg,w,l);
}

static bool concept98_open_forward_v130(int index){
    if(!chat||index<0||index>=(int)messages.size())return false;
    const Message& row=messages[index];
    if(row.end_char<=row.start_char)return false;
    static bool registered=false;
    if(!registered){
        WNDCLASSW wc;ZeroMemory(&wc,sizeof(wc));
        wc.lpfnWndProc=concept98_forward_proc_v130;
        wc.hInstance=GetModuleHandleW(NULL);
        wc.lpszClassName=L"TelegacyForwardConcept98V130";
        wc.hCursor=LoadCursor(NULL,IDC_ARROW);
        wc.hbrBackground=GetSysColorBrush(COLOR_BTNFACE);
        if(!RegisterClassW(&wc)&&GetLastError()!=ERROR_CLASS_ALREADY_EXISTS)
            return false;
        registered=true;
    }
    if(!concept98_forward_win_v130){
        concept98_forward_win_v130=CreateWindowExW(
            WS_EX_APPWINDOW|WS_EX_DLGMODALFRAME,
            L"TelegacyForwardConcept98V130",
            L"\x041f\x0435\x0440\x0435\x0441\x043b\x0430\x043d\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435 | Telegacy",
            WS_OVERLAPPEDWINDOW|WS_VISIBLE,CW_USEDEFAULT,CW_USEDEFAULT,
            780,570,hMain,NULL,GetModuleHandleW(NULL),NULL);
    }
    if(!concept98_forward_rich_v130)return false;
    // Export one message as formatted RTF, including embedded photo/sticker
    // objects where supported by the installed RichEdit version.
    CHARRANGE original;SendMessageW(chat,EM_EXGETSEL,0,(LPARAM)&original);
    POINT scroll={0,0};SendMessageW(chat,EM_GETSCROLLPOS,0,(LPARAM)&scroll);
    SendMessageW(chat,EM_SETSEL,row.start_char,row.end_char);
    StreamData data={0};
    EDITSTREAM out={0};out.dwCookie=(DWORD_PTR)&data;
    out.pfnCallback=StreamOutCallback;
    SendMessageW(chat,EM_STREAMOUT,SF_RTF|SFF_SELECTION,(LPARAM)&out);
    SendMessageW(chat,EM_EXSETSEL,0,(LPARAM)&original);
    SendMessageW(chat,EM_SETSCROLLPOS,0,(LPARAM)&scroll);
    SendMessageW(concept98_forward_rich_v130,WM_SETTEXT,0,(LPARAM)L"");
    if(data.buf && data.length>0 && out.dwError==0){
        EDITSTREAM in={0};in.dwCookie=(DWORD_PTR)&data;
        in.pfnCallback=StreamInCallback;
        SendMessageW(concept98_forward_rich_v130,EM_STREAMIN,SF_RTF,(LPARAM)&in);
    } else {
        wchar_t text[170]={0};
        SendMessageW(concept98_forward_rich_v130,WM_SETTEXT,0,
          (LPARAM)L"\x041d\x0435 \x0443\x0434\x0430\x043b\x043e\x0441\x044c \x043e\x0442\x043e\x0431\x0440\x0430\x0437\x0438\x0442\x044c \x0444\x043e\x0440\x043c\x0430\x0442\x0438\x0440\x043e\x0432\x0430\x043d\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435.");
    }
    free(data.buf);
    SendMessageW(concept98_forward_rich_v130,EM_SETSEL,0,0);
    concept98_forward_paths_v130.clear();
    SendMessageW(concept98_forward_files_v130,LB_RESETCONTENT,0,0);
    int files=0;
    for(size_t k=0;k<documents.size();k++){
        const Document& d=documents[k];
        if(d.min<row.start_char || d.max>row.end_char)continue;
        files++;
        wchar_t filename[256]={0};
        if(d.filename)wcsncpy_s(filename,ARRAYSIZE(filename),d.filename,_TRUNCATE);
        else wcscpy_s(filename,ARRAYSIZE(filename),L"\x0412\x043b\x043e\x0436\x0435\x043d\x0438\x0435");
        SendMessageW(concept98_forward_files_v130,LB_ADDSTRING,0,(LPARAM)filename);
        wchar_t local[MAX_PATH]={0};
        bool cached=d.photo_size &&
                    concept98_full_photo_path_v101(d.id,d.access_hash,
                                                   local,ARRAYSIZE(local)) &&
                    GetFileAttributesW(local)!=INVALID_FILE_ATTRIBUTES;
        concept98_forward_paths_v130.push_back(cached?local:L"");
    }
    if(files==0)
        SendMessageW(concept98_forward_files_v130,LB_ADDSTRING,0,
          (LPARAM)L"\x041d\x0435\x0442 \x0432\x043b\x043e\x0436\x0435\x043d\x0438\x0439");
    ShowWindow(concept98_forward_win_v130,SW_SHOWNORMAL);
    SetForegroundWindow(concept98_forward_win_v130);
    diag_log("concept98 v130 forward window id=%d attachments=%d RTF_bytes=%d",
             row.id,files,data.length);
    return true;
}
static bool concept98_forward_hit_v130(const ENLINK* event){
    if(!event || event->chrg.cpMax<=event->chrg.cpMin)return false;
    const int len=event->chrg.cpMax-event->chrg.cpMin;
    const int expected=(int)wcslen(concept98_forward_label_v130);
    if(len!=expected)return false;
    wchar_t got[70]={0};
    TEXTRANGEW tr={0};tr.chrg=event->chrg;tr.lpstrText=got;
    SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
    if(wcscmp(got,concept98_forward_label_v130)!=0)return false;
    for(size_t i=0;i<messages.size();i++)
        if(event->chrg.cpMin>=messages[i].start_char &&
           event->chrg.cpMax<=messages[i].end_header)
            return concept98_open_forward_v130((int)i);
    return false;
}
'''
s=one(s,global_anchor,viewer+"\n"+global_anchor,"viewer implementation")
anchor='''        if (pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK && (pENLink->msg == WM_LBUTTONDOWN)) {
			bool found = false;'''
repl='''        if (pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK && (pENLink->msg == WM_LBUTTONDOWN)) {
            if(concept98_enabled && concept98_forward_hit_v130(pENLink))return 0;
			bool found = false;'''
s=one(s,anchor,repl,"forward link event handler")
m.write_text(a,encoding="latin-1",newline="\r\n")
t.write_text(s,encoding="latin-1",newline="\r\n")
print("v13.0: clickable forwarded header, Win98 native full RTF + attachment list window.")
