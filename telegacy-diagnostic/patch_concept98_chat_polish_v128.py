#!/usr/bin/env python3
"""Concept98 v12.8: readable compact chat, top-mounted framed reply/forward
context, and stable native splitter drag. Preserves photo/OLE message identity.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_chat_polish_v128.py <src>")
root=Path(sys.argv[1]).resolve()
paths={name:root/"src"/(name+".cpp") for name in ("message","telegacy","procs")}
src={name:path.read_text(encoding="latin-1") for name,path in paths.items()}
if "concept98_chat_polish_v128" in src["message"]:
    print("v12.8 already applied");raise SystemExit(0)
if "concept98_readable_ui_v127" not in src["message"]:
    raise SystemExit("v12.7 paragraph style required")

def one(name,old,new,why):
    v=src[name]
    n=v.count(old)
    if n!=1: raise SystemExit("v12.8 %s: expected 1, found %d"%(why,n))
    src[name]=v.replace(old,new,1)

# 1) More readable 11pt main body. Preserve existing small timestamps.
one("message",
    "cf.yHeight = MulDiv(-lf.lfHeight, 144, dpi) * 10;",
    """cf.yHeight = MulDiv(-lf.lfHeight, 144, dpi) * 10;
    // concept98_chat_polish_v128: 11pt floor; never reduce a larger system font.
    if(concept98_enabled && cf.yHeight<220)cf.yHeight=220;""",
    "body font floor")
# 2) Give both speakers an inward 12%-of-pane inset rather than sending
# each message to the far window edge. Opposite indents reserve readability.
old='''    int gutter=(inner.right-inner.left)*19/100;
    if(gutter<46)gutter=46;
    if(gutter>220)gutter=220;
    pf.wAlignment=service?PFA_CENTER:(message.outgoing?PFA_RIGHT:PFA_LEFT);
    pf.dxStartIndent=service?0:MulDiv(message.outgoing?gutter:8,1440,dpi);
    pf.dxRightIndent=service?0:MulDiv(message.outgoing?8:gutter,1440,dpi);'''
new='''    const int cw=inner.right-inner.left;
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
one("message",old,new,"compact conversation paragraph columns")

# 3) Create a safe, actual header prefix from message metadata. Crucial:
# the extra text is accounted for in header_len BEFORE RichEdit message
# insertion, so every tracked OLE Document and subsequent Message CP shifts
# by the proper amount and no separate controls overlap media.
begin='''\tint sender_len = header ? wcslen(sender) : 0;
	int header_len = header ? (sender_len + ((current_peer->perm.cansendmsg || msg_len == 0) ? 2 : 3)) : 0;
	bool msghastext'''
replacement='''    int sender_len = header ? wcslen(sender) : 0;
	int header_len = header ? (sender_len + ((current_peer->perm.cansendmsg || msg_len == 0) ? 2 : 3)) : 0;
    // concept98_chat_polish_v128: context is an additional header paragraph,
    // never an OLE overlay, never appended behind the timestamp.
    const int ordinary_header_len_v128=header_len;
    std::wstring context_v128;
    int reply_target_v128=0;
    if(concept98_enabled && !service && !editing && !es && header &&
       !group_media && (msgrpl || msgfwd)) {
        if(msgrpl){
            int reply_flags=read_le(msgrpl+4,4);
            if(reply_flags & (1<<4))
                reply_target_v128=(int)read_le(msgrpl+8,4);
            context_v128=L"\\\\x041e\\\\x0442\\\\x0432\\\\x0435\\\\x0442 \\\\x043d\\\\x0430 ";
            bool matched=false;
            if(reply_target_v128>0){
                for(int j=(int)messages.size()-1;j>=0;j--){
                    if(messages[j].id!=reply_target_v128)continue;
                    matched=true;
                    if(current_peer->type==0)
                        context_v128+=messages[j].outgoing?myself.name:current_peer->name;
                    else context_v128+=L"\\\\x0441\\\\x043e\\\\x043e\\\\x0431\\\\x0449\\\\x0435\\\\x043d\\\\x0438\\\\x0435";
                    int a=messages[j].end_header;
                    int b=messages[j].end_char;
                    if(b>a && b-a<=16000){
                        if(b-a>88)b=a+88;
                        wchar_t excerpt[96]={0};
                        TEXTRANGEW tr={0};
                        tr.chrg.cpMin=a;tr.chrg.cpMax=b;tr.lpstrText=excerpt;
                        LRESULT copied=SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
                        if(copied>0 && copied<95){
                            excerpt[copied]=0;
                            for(int k=0;k<copied;k++)
                                if(excerpt[k]==L'\\\\n'||excerpt[k]==L'\\\\r'||
                                   excerpt[k]==0xFFFC||excerpt[k]==0xFE0F)
                                   excerpt[k]=L' ';
                            if(wcslen(excerpt)){
                                context_v128+=L": ";
                                context_v128+=excerpt;
                            }
                        }
                    }
                    break;
                }
            }
            if(!matched)
                context_v128+=L"\\\\x0441\\\\x043e\\\\x043e\\\\x0431\\\\x0449\\\\x0435\\\\x043d\\\\x0438\\\\x0435";
        }
        if(msgfwd){
            if(!context_v128.empty())context_v128+=L" / ";
            context_v128+=L"\\\\x041f\\\\x0435\\\\x0440\\\\x0435\\\\x0441\\\\x043b\\\\x0430\\\\x043d\\\\x043d\\\\x043e\\\\x0435 \\\\x0441\\\\x043e\\\\x043e\\\\x0431\\\\x0449\\\\x0435\\\\x043d\\\\x0438\\\\x0435";
        }
        if(!context_v128.empty()){
            // The visible system-color framed block is always above body.
            context_v128+=L"\\\\n";
            header_len+=(int)context_v128.size();
        }
    }
	bool msghastext'''
# The Python raw script intentionally uses double-backslash C++ unicode
# escapes above only in its string literal; normalize them before writing.
replacement=replacement.replace(r"\\x",r"\x")
replacement=replacement.replace(r"\\n",r"\n")
replacement=replacement.replace(r"\\r",r"\r")
one("message",begin,replacement,"construct reply prefix before media")
one("message",
'''			msg[sender_len+1] = ' ';
			if (header_len == sender_len + 3) msg[sender_len+2] = '\\n';
		}
		int offset = header_len;''',
'''            msg[sender_len+1] = context_v128.empty() ? ' ' : '\\n';
            if (ordinary_header_len_v128 == sender_len + 3)
                msg[sender_len+2] = '\\n';
        }
        if(!context_v128.empty()){
            memcpy(msg+ordinary_header_len_v128,context_v128.c_str(),
                   context_v128.size()*sizeof(wchar_t));
        }
		int offset = header_len;''',
"write upper reply header and preserve TL body offsets")
# Old Telegacy footer creates the reply and forward context AFTER the body.
# Suppress that branch only for messages that received a top context.
one("message",
'''		get_lang_string("c_rep", lang_str, NULL);
		wcscat(lang_str, L" ");''',
'''        if(context_v128.empty()){ // v128 old footer only in fallback modes
		get_lang_string("c_rep", lang_str, NULL);
		wcscat(lang_str, L" ");''',
"begin original footer guard")
one("message",
'''		if (msgfwd) {
			get_lang_string("c_fwd", lang_str, NULL);
			wcscat(lang_str, L" ");
			written_info += riched_write(chat, lang_str);
			written_info += msgfwd_addname(msg_bytes, msgfwd, cr_startmsg.cpMin + written + written_info, msg_bytes - msg_id == 12);
			written_info += riched_write(chat, L"\\n");
		}

		get_date(info + wcslen(info), date, false);''',
'''		if (msgfwd) {
			get_lang_string("c_fwd", lang_str, NULL);
			wcscat(lang_str, L" ");
			written_info += riched_write(chat, lang_str);
			written_info += msgfwd_addname(msg_bytes, msgfwd, cr_startmsg.cpMin + written + written_info, msg_bytes - msg_id == 12);
			written_info += riched_write(chat, L"\\n");
		}
        } // v128 header context already rendered above the message

		get_date(info + wcslen(info), date, false);''',
"end original footer guard")
one("message",
'''	message.reply_needed = 0;
	int written_info = 0;''',
'''	message.reply_needed = context_v128.empty()?0:reply_target_v128;
	int written_info = 0;''',
"preserve semantic reply target")
# Remove old v12.7 italic footer patch when context is above.
one("message",
'''    if(!service && (msgrpl || msgfwd) &&
       message.end_footer>message.end_char+2){''',
'''    if(!service && context_v128.empty() && (msgrpl || msgfwd) &&
       message.end_footer>message.end_char+2){''',
"don't highlight timestamp in reply messages")
# Decorative frame: RichEdit2 paragraph border when supported; backup
# CHARFORMAT2 background/italic always renders on both 2.0 and 4.1.
needle='''	message.end_footer = message.end_char + written_info;
    // concept98_readable_ui_v127'''
if src["message"].count(needle)!=1:raise SystemExit("v12.8 can't find header style position")
style=r'''	message.end_footer = message.end_char + written_info;
    if(!context_v128.empty() && header && header_len>ordinary_header_len_v128){
        const int context_start=message.start_char+ordinary_header_len_v128;
        const int context_end=message.start_char+header_len-1;
        if(context_start>=0 && context_end>context_start &&
           context_end<=message.end_char){
            SendMessage(chat,EM_SETSEL,context_start,context_end);
            CHARFORMAT2 context_style;ZeroMemory(&context_style,sizeof(context_style));
            context_style.cbSize=sizeof(context_style);
            context_style.dwMask=CFM_BACKCOLOR|CFM_COLOR|CFM_ITALIC|CFM_SIZE;
            context_style.dwEffects=CFE_ITALIC;
            context_style.crBackColor=GetSysColor(COLOR_BTNFACE);
            context_style.crTextColor=GetSysColor(COLOR_BTNTEXT);
            context_style.yHeight=180; // 9pt context, 11pt main text
            SendMessage(chat,EM_SETCHARFORMAT,SCF_SELECTION,(LPARAM)&context_style);
            PARAFORMAT2 quote_border;ZeroMemory(&quote_border,sizeof(quote_border));
            quote_border.cbSize=sizeof(quote_border);
            quote_border.dwMask=PFM_BORDER|PFM_SPACEBEFORE|PFM_SPACEAFTER;
            quote_border.wBorders=(WORD)(1|2|4|8|64|(1<<8));
            quote_border.wBorderWidth=15;
            quote_border.wBorderSpace=45;
            quote_border.dySpaceBefore=65;
            quote_border.dySpaceAfter=70;
            SendMessage(chat,EM_SETPARAFORMAT,0,(LPARAM)&quote_border);
        }
    }
    // concept98_readable_ui_v127'''
one("message",needle,style,"system-color framed quote above message")

# 4) Native splitter originally overwrites Concept98 positions with old
# legacy coordinates for every pixel of drag. Apply only the Concept98
# geometry at most every 24ms, and one complete repaint upon release.
one("telegacy",
'''static void concept98_move_v91(
    HWND control, int x, int y, int w, int h
) {''',
'''static bool concept98_split_drag_v128=false;
static void concept98_move_v91(
    HWND control, int x, int y, int w, int h
) {''',
"add native drag draw state")
one("telegacy","    MoveWindow(control, x, y, w, h, TRUE);",
    "    MoveWindow(control, x, y, w, h, concept98_split_drag_v128 ? FALSE : TRUE);",
    "suppress expensive paints during drag")
# Wrapper after the full apply_layout definition; don't touch any photo paths.
s=src["telegacy"];start=s.find("static void concept98_apply_layout(HWND hwnd) {")
if start<0:raise SystemExit("v12.8 missing layout")
brace=s.find("{",start);depth=0;end=-1
for pos in range(brace,len(s)):
    if s[pos]=="{":depth+=1
    elif s[pos]=="}":
        depth-=1
        if depth==0:end=pos+1;break
if end<0:raise SystemExit("v12.8 unmatched layout braces")
wrapper=r'''
// concept98_chat_polish_v128: call from native splitter's window proc.
void concept98_drag_relayout_v128(bool done){
    if(!concept98_enabled || !hMain)return;
    if(!done){
        static DWORD last=0;
        DWORD now=GetTickCount();
        if((DWORD)(now-last)<24)return;
        last=now;
    }
    concept98_split_drag_v128=!done;
    concept98_apply_layout(hMain);
    concept98_split_drag_v128=false;
    if(done){
        if(chat && IsWindow(chat))
            RedrawWindow(chat,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);
        if(msgInput && IsWindow(msgInput))
            RedrawWindow(msgInput,NULL,NULL,RDW_INVALIDATE|RDW_UPDATENOW);
        if(hToolbar && IsWindow(hToolbar))
            RedrawWindow(hToolbar,NULL,NULL,RDW_INVALIDATE);
        // exactly one refresh, no whole-window ERASEBKGND flashing
    }
}
'''
src["telegacy"]=s[:end]+wrapper+s[end:]
one("procs",
'''LRESULT CALLBACK WndProcSplitter(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {''',
'''extern void concept98_drag_relayout_v128(bool);
LRESULT CALLBACK WndProcSplitter(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {''',
"splitter wrapper declaration")
one("procs",
'''			edits_border_offset = pt.y - (height - 123);
			bool cantwrite = current_peer && !current_peer->perm.cansendmsg;''',
'''			edits_border_offset = pt.y - (height - 123);
            if(concept98_enabled){
                concept98_drag_relayout_v128(false);
                return 0;
            }
			bool cantwrite = current_peer && !current_peer->perm.cansendmsg;''',
"keep legacy geometry out of Concept98")
one("procs",
'''			dragging = false;
			ReleaseCapture();
		}
		break;
	}
	return CallWindowProc(oldSplitterProc, hWnd, msg, wParam, lParam);''',
'''			dragging = false;
			ReleaseCapture();
            if(concept98_enabled){
                concept98_drag_relayout_v128(true);
                return 0;
            }
		}
		break;
    case WM_CAPTURECHANGED:
        if(dragging){
            dragging=false;
            if(concept98_enabled)concept98_drag_relayout_v128(true);
        }
        break;
	}
	return CallWindowProc(oldSplitterProc, hWnd, msg, wParam, lParam);''',
"one final clean layout after drag")
for name,path in paths.items():
    path.write_text(src[name],encoding="latin-1",newline="\r\n")
print("v12.8: 11pt chat, 12pct inner inset, boxed upper reply/forward, one Win98 drag-layout pass, photo path untouched.")
