#!/usr/bin/env python3
"""Concept98 v13.9: forwarded replies open the same newest-first chain viewer.
When Telegram has not returned a parent yet, display the embedded original
quote without falsely pretending the full message/media was downloaded."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_forward_chain_v139.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_forward_chain_v139" in s:raise SystemExit(0)
if "concept98_chain_files_v138" not in s:raise SystemExit("v13.8 required")
def one(a,b,label):
 global s
 n=s.count(a)
 if n!=1:raise SystemExit("v13.9 "+label+" matches="+str(n))
 s=s.replace(a,b,1)
one('''            return concept98_open_forward_v130((int)i,false);''',
'''            // concept98_forward_chain_v139: forwarded messages with a
            // real reply_to reference open the reverse nested chain.
            if(messages[i].concept98_reply_target_v134>0 &&
               concept98_reply_chain_open_v136(i))return true;
            return concept98_open_forward_v130((int)i,false);''',
"direct forward click")
one('''            return concept98_open_forward_v130((int)i);
    return false;
}''',
'''            {
                if(messages[i].concept98_reply_target_v134>0 &&
                   concept98_reply_chain_open_v136(i))return true;
                return concept98_open_forward_v130((int)i);
            }
    return false;
}''',
"EN_LINK forward click")
one(r'''            content+=L"\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0438\u0437 Telegram...";
            concept98_reply_request_v136(id);''',
r'''            content+=L"\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0438\u0437 Telegram...";
            // Keep Telegram's embedded text quote visible until a full
            // messages.getMessages result arrives. Do not fake attachments.
            for(size_t j=0;j<messages.size();j++){
                if(messages[j].concept98_reply_target_v134==id &&
                   !messages[j].concept98_reply_quote_v134.empty()){
                    content+=L"\r\n";
                    for(int k=0;k<depth;k++)content+=L"    ";
                    content+=L"\u0426\u0438\u0442\u0430\u0442\u0430: ";
                    content+=messages[j].concept98_reply_quote_v134;
                    break;
                }
            }
            concept98_reply_request_v136(id);''',
"quoted parent while waiting")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v13.9: forwarded replies expose nested reply chains; quoted parent while loading.")
