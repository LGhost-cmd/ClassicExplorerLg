#!/usr/bin/env python3
"""Concept98 v13.8: attach each locally loaded reply-chain file to the
shared Win98 viewer list with matching local paths; keep the chain in reverse
chronology and never imply remote ancestors' attachments are already cached."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_chain_files_v138.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_chain_files_v138" in s:raise SystemExit(0)
if "concept98_reply_chain_v136" not in s:raise SystemExit("v13.6 required")
def one(a,b,label):
 global s
 n=s.count(a)
 if n!=1:raise SystemExit("v13.8 "+label+" count="+str(n))
 s=s.replace(a,b,1)

one('''    std::wstring content;
    std::set<int> visited;
    int id=concept98_reply_root_v136;''',
r'''    std::wstring content;
    // concept98_chain_files_v138: rebind attachment list to ALL actually
    // loaded chain nodes rather than leaving the clicked row's stale files.
    concept98_forward_paths_v130.clear();
    if(concept98_forward_files_v130)
        SendMessageW(concept98_forward_files_v130,LB_RESETCONTENT,0,0);
    std::set<int> visited;
    int id=concept98_reply_root_v136;''',"reset old file list")
one('''        const Concept98ReplySnapshot136& node=it->second;
        for(int i=0;i<depth;i++)content+=L"    ";''',
r'''        const Concept98ReplySnapshot136& node=it->second;
        // The RichEdit Document positions are authoritative only for
        // messages actually loaded into this same chat, not RPC snapshots.
        for(size_t j=0;j<messages.size();j++){
            const Message& row=messages[j];
            if(row.id!=id)continue;
            for(size_t k=0;k<documents.size();k++){
                const Document& doc=documents[k];
                if(doc.min<row.start_char || doc.max>row.end_char)
                    continue;
                std::wstring file_name=doc.filename?
                    doc.filename:L"Вложение";
                std::wstring line;
                for(int d=0;d<depth;d++)line+=L"  ";
                wchar_t item_id[32]={0};
                swprintf_s(item_id,ARRAYSIZE(item_id),L"%d",id);
                line+=L"[#";line+=item_id;line+=L"] ";
                line+=file_name;
                if(concept98_forward_files_v130)
                    SendMessageW(concept98_forward_files_v130,
                        LB_ADDSTRING,0,(LPARAM)line.c_str());
                std::wstring path;
                if(doc.filename &&
                   GetFileAttributesW(doc.filename)!=INVALID_FILE_ATTRIBUTES)
                    path=doc.filename;
                concept98_forward_paths_v130.push_back(path);
            }
            break;
        }
        for(int i=0;i<depth;i++)content+=L"    ";''',"files for loaded messages")
# Keep graceful empty list after a freshly fetched plain-text source.
one('''    SendMessageW(concept98_forward_rich_v130,WM_SETTEXT,0,
                 (LPARAM)content.c_str());''',
'''    if(concept98_forward_files_v130 &&
       concept98_forward_paths_v130.empty())
        SendMessageW(concept98_forward_files_v130,LB_ADDSTRING,0,
            (LPARAM)L"Нет загруженных вложений");
    SendMessageW(concept98_forward_rich_v130,WM_SETTEXT,0,
                 (LPARAM)content.c_str());''',"empty list")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v13.8: bounded reply-chain file list bound to actually loaded sources.")
