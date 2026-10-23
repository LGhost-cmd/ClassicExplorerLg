#!/usr/bin/env python3
"""Concept98 v13.2: unified left-aligned dialog, gaps only on speaker switch,
compact system-framed reply/forward labels; clicking reply shows the referenced
message (full rich text and its available attachments) in existing viewer.
Avoid editing original chat media and their OLE CP ranges after rendering."""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_single_flow_reply_v132.py <src>")
root=Path(sys.argv[1]).resolve()
m=root/"src"/"message.cpp"
t=root/"src"/"telegacy.cpp"
s=m.read_text(encoding="latin-1")
u=t.read_text(encoding="latin-1")
if "concept98_single_flow_reply_v132" in s:raise SystemExit(0)
if "concept98_forward_view_v130" not in s or "concept98_chat_polish_v128" not in s:
    raise SystemExit("v13.0 context renderer is required")
def once(v,old,new,label):
 n=v.count(old)
 if n!=1:raise SystemExit("v13.2 "+label+" count="+str(n))
 return v.replace(old,new,1)
# Layout. Header and body are single-flow like ICQ/mIRC, author name colors
# remain. The only larger vertical gap is between different speakers; for
# historical pages compare to the neighbour in the correct prepend direction.
old='''    const int cw=inner.right-inner.left;
    int inner_edge=cw*12/100;
    if(inner_edge<16)inner_edge=16;
    if(inner_edge>140)inner_edge=140;
    int opposite=cw*10/100;
    if(opposite<28)opposite=28;
    if(opposite>135)opposite=135;
    if(inner_edge*2+opposite>cw-230){
        inner_edge=16;
        opposite=28;
    }
    pf.wAlignment=service?PFA_CENTER:(message.outgoing?PFA_RIGHT:PFA_LEFT);
    pf.dxStartIndent=service?0:
        MulDiv(inner_edge+(message.outgoing?opposite:0),1440,dpi);
    pf.dxRightIndent=service?0:
        MulDiv(inner_edge+(message.outgoing?0:opposite),1440,dpi);
    pf.dwMask|=PFM_SPACEBEFORE;
    pf.dySpaceBefore=(!service && header)?75:0;'''
new='''    // concept98_single_flow_reply_v132: traditional single text column.
    const int cw=inner.right-inner.left;
    const int inset=cw<400?8:16;
    pf.wAlignment=service?PFA_CENTER:PFA_LEFT;
    pf.dxStartIndent=service?0:MulDiv(inset,1440,dpi);
    pf.dxRightIndent=service?0:MulDiv(12,1440,dpi);
    pf.dwMask|=PFM_SPACEBEFORE|PFM_SPACEAFTER;
    const bool author_changed_v132=!service && header &&
        !messages.empty() &&
        message.outgoing!=(to_front?messages.front().outgoing:
                                    messages.back().outgoing);
    pf.dySpaceBefore=author_changed_v132?150:(!service&&header?35:0);
    pf.dySpaceAfter=0;'''
s=once(s,old,new,"traditional left alignment")

# v12.8 packs an optional name/excerpt into the heading.  Keep the actual
# target ID, but show only the compact label to avoid unbalanced header CPs
# and the date line running into a neighbouring message.
start=s.find('''        if(msgrpl){
            int reply_flags=read_le(msgrpl+4,4);''')
end=s.find('''        if(msgfwd){
            if(!context_v128.empty())''',start)
if start<0 or end<0 or end<=start:
 raise SystemExit("v13.2 could not find reply context construction")
reply=r'''        if(msgrpl){
            int reply_flags=read_le(msgrpl+4,4);
            if(reply_flags & (1<<4))
                reply_target_v128=(int)read_le(msgrpl+8,4);
            // concept98_single_flow_reply_v132: short clickable header.
            // The source body and attachments open in the full viewer.
            context_v128=L"\x041e\x0442\x0432\x0435\x0442 \x043d\x0430 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
        }
'''
s=s[:start]+reply+s[end:]
# Ensure the date is a true new paragraph by avoiding rich formatting
# leaking from a header selection into timestamp and later messages.
# We only adjust the selection style of the quote heading, not the body.
marker='''    // concept98_readable_ui_v127: distinguish reply/forward context from'''
style=r'''    // concept98_single_flow_reply_v132: reply link on exact header label.
    if(msgrpl && !context_v128.empty() && header){
        const std::wstring label=
            L"\x041e\x0442\x0432\x0435\x0442 \x043d\x0430 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
        size_t where=context_v128.find(label);
        if(where!=std::wstring::npos){
            int a=message.start_char+ordinary_header_len_v128+(int)where;
            int b=a+(int)label.size();
            if(a>=message.start_char && b<=message.end_header){
                SendMessageW(chat,EM_SETSEL,a,b);
                CHARFORMAT2 f;ZeroMemory(&f,sizeof(f));
                f.cbSize=sizeof(f);
                f.dwMask=CFM_LINK|CFM_UNDERLINE|CFM_COLOR;
                f.dwEffects=CFE_LINK|CFE_UNDERLINE;
                f.crTextColor=GetSysColor(COLOR_BTNTEXT);
                SendMessageW(chat,EM_SETCHARFORMAT,SCF_SELECTION,(LPARAM)&f);
            }
        }
    }
'''
s=once(s,marker,style+marker,"clickable reply heading")
# Tone down forwarded link, match reply in the gray system-color framed area.
s=once(s,"f.crTextColor=GetSysColor(COLOR_HOTLIGHT);",
          "f.crTextColor=GetSysColor(COLOR_BTNTEXT);",
          "system-colored forward heading")
# Important: do not alter the footer's timestamp serialization (which also
# carries seen status and reactions). Instead stop paragraph border state from
# propagating into the timestamp by restoring the paragraph after selection.
needle='''            SendMessage(chat,EM_SETPARAFORMAT,0,(LPARAM)&quote_border);
        }
    }
    // concept98_forward_view_v130'''
# v13.0 forward block comes AFTER v12.8 style before v12.7 comment,
# so match only known complete paragraph border end.
needle2='''            SendMessage(chat,EM_SETPARAFORMAT,0,(LPARAM)&quote_border);
        }
    }
    // concept98_forward_view_v130'''
if needle2 in s:
    s=s.replace(needle2,'''            SendMessage(chat,EM_SETPARAFORMAT,0,(LPARAM)&quote_border);
        }
    }
    // concept98_forward_view_v130''',1)

# Use the existing full RTF viewer for the referenced reply source. If the
# source isn't among loaded messages, trigger Telegram retrieval and tell the
# user it must be opened after the message arrives (no fake preview).
anchor='''static bool concept98_forward_hit_v130(const ENLINK* event){'''
helper=r'''// concept98_single_flow_reply_v132: same popup as a forwarded message,
 // but previews the referenced message, not the replying message.
static bool concept98_reply_hit_v132(const ENLINK* event){
    if(!event || !chat || !current_peer || event->chrg.cpMin<0)
        return false;
    const wchar_t* label=
        L"\x041e\x0442\x0432\x0435\x0442 \x043d\x0430 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
    const int length=(int)wcslen(label);
    if(event->chrg.cpMax-event->chrg.cpMin!=length)return false;
    wchar_t actual[72]={0};
    TEXTRANGEW tr;ZeroMemory(&tr,sizeof(tr));
    tr.chrg=event->chrg;tr.lpstrText=actual;
    LRESULT n=SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
    if(n!=length || wcscmp(actual,label)!=0)return false;
    for(size_t k=0;k<messages.size();k++){
        const Message& current=messages[k];
        if(event->chrg.cpMin<current.start_char ||
           event->chrg.cpMax>current.end_header)continue;
        const int reply=current.reply_needed;
        if(reply>0){
            for(size_t j=0;j<messages.size();j++){
                if(messages[j].id==reply)
                    return concept98_open_forward_v130((int)j);
            }
            get_message(reply,current_peer);
            MessageBoxW(hMain,
                L"\x0418\x0441\x0445\x043e\x0434\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435 \x0435\x0449\x0451 \x043d\x0435 \x0437\x0430\x0433\x0440\x0443\x0436\x0435\x043d\x043e. \x0417\x0430\x043f\x0440\x043e\x0448\x0435\x043d\x0430 \x0435\x0433\x043e \x0437\x0430\x0433\x0440\x0443\x0437\x043a\x0430; \x043f\x043e\x0432\x0442\x043e\x0440\x0438\x0442\x0435 \x043d\x0430\x0436\x0430\x0442\x0438\x0435 \x043f\x043e\x0437\x0436\x0435.",
                L"Telegacy | \x041e\x0442\x0432\x0435\x0442",MB_OK|MB_ICONINFORMATION);
        }else{
            MessageBoxW(hMain,
                L"\x0418\x0441\x0445\x043e\x0434\x043d\x043e\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435 \x043d\x0435 \x0443\x043a\x0430\x0437\x0430\x043d\x043e \x0432 \x0434\x0430\x043d\x043d\x044b\x0445 Telegram.",
                L"Telegacy | \x041e\x0442\x0432\x0435\x0442",MB_OK|MB_ICONINFORMATION);
        }
        return true;
    }
    return false;
}
'''
u=once(u,anchor,helper+anchor,"reply link handler")
u=once(u,
'''            if(concept98_enabled && pENLink->msg==WM_LBUTTONDOWN &&
               concept98_forward_hit_v130(pENLink))return 0;''',
'''            if(concept98_enabled && pENLink->msg==WM_LBUTTONDOWN &&
               (concept98_reply_hit_v132(pENLink) ||
                concept98_forward_hit_v130(pENLink)))return 0;''',
"link dispatch")
m.write_text(s,encoding="latin-1",newline="\r\n")
t.write_text(u,encoding="latin-1",newline="\r\n")
print("v13.2: one left-aligned message flow; author-switch only spacing; uniform system-gray click-to-open reply/forward frames.")
