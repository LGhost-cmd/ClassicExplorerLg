#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_preview_v70.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
m = root / "src" / "message.cpp"
h = root / "src" / "helpers.cpp"
t = root / "src" / "telegacy.cpp"

for p in (m, h, t):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


def function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")
    depth = 0
    in_string = in_char = in_line = in_block = escaped = False
    i = brace
    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""
        if in_line:
            if c == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            if c == "*" and n == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "'":
                in_char = False
            i += 1
            continue
        if c == "/" and n == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and n == "*":
            in_block = True
            i += 2
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "'":
            in_char = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
        i += 1
    raise SystemExit(f"Could not locate closing brace: {signature}")


if "chat_media_preview_v70" in read(m):
    print("Chat media preview v7.0 already applied.")
    raise SystemExit(0)

# Photo UI: never upscale Telegram's tiny stripped JPEG. Reserve a clean framed
# block while the real server preview is requested.
s = read(m)
video_sig = "static HBITMAP media_chat_video_placeholder() {"
pos = s.find(video_sig)
if pos < 0:
    raise SystemExit("Could not locate video placeholder insertion point.")

photo_placeholder = r'''// chat_media_preview_v70
static HBITMAP media_chat_photo_placeholder() {
    const int width = 288;
    const int height = 216;

    HDC screen = GetDC(NULL);
    if (!screen)
        return NULL;

    HBITMAP bitmap = CreateCompatibleBitmap(screen, width, height);
    ReleaseDC(NULL, screen);
    if (!bitmap)
        return NULL;

    HDC dc = CreateCompatibleDC(NULL);
    if (!dc) {
        DeleteObject(bitmap);
        return NULL;
    }

    HGDIOBJ old_bitmap = SelectObject(dc, bitmap);
    RECT all = {0, 0, width, height};
    FillRect(dc, &all, GetSysColorBrush(COLOR_3DFACE));
    DrawEdge(dc, &all, EDGE_SUNKEN, BF_RECT);
    SelectObject(dc, old_bitmap);
    DeleteDC(dc);
    return bitmap;
}


'''
s = s[:pos] + photo_placeholder + s[pos:]

photo_ctor = "} else if (doc != NULL && read_le(doc, 4) == 0x695150d7 && (read_le(doc + 4, 4) & (1 << 0))) {"
photo_start = s.find(photo_ctor)
if photo_start < 0:
    raise SystemExit("Could not locate ordinary photo branch.")
photo_end = s.find("\n\tbool addnewline =", photo_start)
if photo_end < 0:
    raise SystemExit("Could not locate end of ordinary photo branch.")
photo = s[photo_start:photo_end]

if "\t\tHBITMAP hClone;" not in photo:
    raise SystemExit("Could not locate ordinary photo hClone declaration.")
photo = photo.replace("\t\tHBITMAP hClone;", "\t\tHBITMAP hClone = NULL;", 1)

old_strip = "if (size == 'i' && IMAGELOADPOLICY) {"
if old_strip not in photo:
    raise SystemExit("Could not locate stripped-preview decode branch.")
photo = photo.replace(
    old_strip,
    "if (size == 'i' && false) { // chat_media_preview_v70: stripped preview is metadata only",
    1,
)

old_render = '''\t\t} else if (IMAGELOADPOLICY) {\n\t\t\tHBITMAP display_bitmap = hClone;\n\t\t\tHBITMAP media_card = NULL;\n\n\t\t\tif (hClone) {\n\t\t\t\tmedia_card = media_chat_make_photo_card(hClone);\n\n\t\t\t\tif (media_card)\n\t\t\t\t\tdisplay_bitmap = media_card;\n\t\t\t}\n\n\t\t\tinsert_image(chat, NULL, display_bitmap);\n\n\t\t\tif (media_card)\n\t\t\t\tDeleteObject(media_card);\n\n\t\t\tDeleteObject(hClone);\n\t\t} else {'''
new_render = '''\t\t} else if (IMAGELOADPOLICY) {\n\t\t\t// chat_media_preview_v70: do not show/upscale Telegram's tiny stripped JPEG.\n\t\t\t// The real preview is already requested through get_photo(), exactly like\n\t\t\t// the Media window. Until upload.file arrives, reserve one clean card.\n\t\t\tHBITMAP display_bitmap = NULL;\n\t\t\tHBITMAP media_card = NULL;\n\t\t\tHBITMAP loading_card = NULL;\n\n\t\t\tif (hClone) {\n\t\t\t\tmedia_card = media_chat_make_photo_card(hClone);\n\t\t\t\tdisplay_bitmap = media_card ? media_card : hClone;\n\t\t\t} else {\n\t\t\t\tloading_card = media_chat_photo_placeholder();\n\t\t\t\tdisplay_bitmap = loading_card;\n\t\t\t}\n\n\t\t\tif (display_bitmap)\n\t\t\t\tinsert_image(chat, NULL, display_bitmap);\n\t\t\telse {\n\t\t\t\twchar_t placeholder[] = {0xFE0F, 0};\n\t\t\t\triched_write(chat, placeholder);\n\t\t\t}\n\n\t\t\tif (media_card)\n\t\t\t\tDeleteObject(media_card);\n\t\t\tif (loading_card)\n\t\t\t\tDeleteObject(loading_card);\n\t\t\tif (hClone)\n\t\t\t\tDeleteObject(hClone);\n\t\t} else {'''
if old_render not in photo:
    raise SystemExit("Could not locate v6.4 ordinary-photo render block.")
photo = photo.replace(old_render, new_render, 1)

old_end = '''\t\twritten++;\n\t\tdocument.max = cr_startmsg.cpMin + written;\n\t\tif (to_front && !footer && messages[0].end_char - messages[0].end_header <= 2) {'''
new_end = '''\t\twritten++;\n\t\tdocument.max = cr_startmsg.cpMin + written;\n\t\t// Every media item is a block. If this grouped/intermediate message has no\n\t\t// footer of its own, terminate the OLE line here so the next text cannot\n\t\t// continue beside the image. The newline is deliberately outside max.\n\t\tif (!footer)\n\t\t\twritten += riched_write(chat, L"\\n");\n\t\tif (to_front && !footer && messages[0].end_char - messages[0].end_header <= 2) {'''
if old_end not in photo:
    raise SystemExit("Could not locate ordinary-photo range finalization.")
photo = photo.replace(old_end, new_end, 1)
s = s[:photo_start] + photo + s[photo_end:]

# Video UI: request the real Telegram Document preview for every enabled image
# policy, and always keep the card on its own line.
old_gate = "if (!to_front && IMAGELOADPOLICY == 2) {"
new_gate = "if (!to_front && IMAGELOADPOLICY != 0) { // chat_media_preview_v70"
if s.count(old_gate) != 1:
    raise SystemExit(f"Expected one initial video-preview gate, found {s.count(old_gate)}.")
s = s.replace(old_gate, new_gate, 1)

old_video_tail = '''\t\t\t\t\t\tdocument.filename = NULL;\n\t\t\t\t\t\tdocument.file_reference = NULL;\n\t\t\t\t\t\t// chat_media_block_v64: footer/final separator owns the newline.'''
new_video_tail = '''\t\t\t\t\t\tdocument.filename = NULL;\n\t\t\t\t\t\tdocument.file_reference = NULL;\n\n\t\t\t\t\t\t// chat_media_preview_v70: video is a block, never inline with the\n\t\t\t\t\t\t// following message text. A normal footer already starts on a new\n\t\t\t\t\t\t// line; grouped/intermediate media needs its own separator here.\n\t\t\t\t\t\tif (!footer)\n\t\t\t\t\t\t\twritten += riched_write(chat, L"\\n");'''
if old_video_tail not in s:
    raise SystemExit("Could not locate v6.4 video-card trailing newline marker.")
s = s.replace(old_video_tail, new_video_tail, 1)
write(m, s)

# Transport: stop intercepting visible chat photos with the experimental full
# photo loader. Use Telegacy's native get_photo path — the same upload.getFile
# path Media uses — but make its legacy fixed buffers safe for modern Telegram
# file_reference lengths.
s = read(h)
start, end = function_range(s, "void get_photo(RequestedCustomEmoji* rce, Document* document, DCInfo* dcInfo)")
func = s[start:end]

intercept = '''\n    // chat_media_full_photo_v64\n    if (\n        !rce &&\n        document &&\n        document->visible &&\n        document->photo_size != 0 &&\n        document->photo_size != 1 &&\n        document->photo_size != 3 &&\n        IMAGELOADPOLICY != 0\n    ) {\n        if (media_chat_full_photo_begin(document, dcInfo))\n            return;\n    }\n'''
if intercept not in func:
    raise SystemExit("Could not locate v6.4 full-photo get_photo interceptor.")
func = func.replace(
    intercept,
    '''\n    // chat_media_preview_v70: visible chat photos intentionally use the native\n    // get_photo/upload.file transport below, exactly like Media previews. The\n    // old v6.4 full-photo interceptor remains compiled only for compatibility\n    // with already-patched response code, but it is no longer entered here.\n''',
    1,
)

if "\tBYTE unenc_query[144];\n\tBYTE enc_query[168];" not in func:
    raise SystemExit("Could not locate legacy get_photo request buffers.")
func = func.replace(
    "\tBYTE unenc_query[144];\n\tBYTE enc_query[168];",
    "\tBYTE unenc_query[1024] = {0};\n\tBYTE enc_query[1048] = {0}; // chat_media_preview_v70",
    1,
)

old_ref = '''\tint fileref_len = tlstr_len(rce ? rce->file_reference : document->file_reference, true);\n\tmemcpy(unenc_query + 60, rce ? rce->file_reference : document->file_reference, fileref_len);\n\tint offset_query = 60 + fileref_len;'''
new_ref = '''\tBYTE* request_file_reference = rce ? rce->file_reference : (document ? document->file_reference : NULL);\n\tif (!request_file_reference) {\n\t\tif (rce) memset(rce->msg_id, 0, 8);\n\t\telse if (document) memset(document->photo_msg_id, 0, 8);\n\t\treturn;\n\t}\n\n\tint fileref_len = tlstr_len(request_file_reference, true);\n\tif (fileref_len <= 0 || 60 + fileref_len + 16 >= (int)sizeof(unenc_query)) {\n\t\tdiag_log("get_photo v70 rejected file_reference len=%d", fileref_len);\n\t\tif (rce) memset(rce->msg_id, 0, 8);\n\t\telse if (document) memset(document->photo_msg_id, 0, 8);\n\t\treturn;\n\t}\n\n\tmemcpy(unenc_query + 60, request_file_reference, fileref_len);\n\tint offset_query = 60 + fileref_len;'''
if old_ref not in func:
    raise SystemExit("Could not locate get_photo file_reference copy.")
func = func.replace(old_ref, new_ref, 1)

old_padding = '''\tint padding_len = get_padding(offset_query);\n\tfortuna_read(unenc_query + offset_query, padding_len, &prng);\n\toffset_query += padding_len;\n\tconvert_message(dcInfo, unenc_query, enc_query, offset_query, 0);\n\tsend_query(dcInfo, enc_query, offset_query + 24);'''
new_padding = '''\tint padding_len = get_padding(offset_query);\n\tif (\n\t\tpadding_len < 0 ||\n\t\toffset_query + padding_len > (int)sizeof(unenc_query) ||\n\t\toffset_query + padding_len + 24 > (int)sizeof(enc_query)\n\t) {\n\t\tdiag_log("get_photo v70 rejected request size=%d padding=%d", offset_query, padding_len);\n\t\tif (rce) memset(rce->msg_id, 0, 8);\n\t\telse if (document) memset(document->photo_msg_id, 0, 8);\n\t\treturn;\n\t}\n\n\tfortuna_read(unenc_query + offset_query, padding_len, &prng);\n\toffset_query += padding_len;\n\tconvert_message(dcInfo, unenc_query, enc_query, offset_query, 0);\n\tsend_query(dcInfo, enc_query, offset_query + 24);'''
if old_padding not in func:
    raise SystemExit("Could not locate get_photo padding/send tail.")
func = func.replace(old_padding, new_padding, 1)
s = s[:start] + func + s[end:]
write(h, s)

# Audit marker. The v6.4 custom loader remains compiled, but no normal visible
# chat-photo request is routed into it after this patch.
s = read(t)
marker_anchor = "// chat_media_layout_v64"
if marker_anchor not in s:
    raise SystemExit("Could not locate v6.4 audit marker in telegacy.cpp.")
s = s.replace(marker_anchor, marker_anchor + "\n// chat_media_preview_v70", 1)
write(t, s)

checks = {
    m: [
        "chat_media_preview_v70",
        "static HBITMAP media_chat_photo_placeholder()",
        "if (size == 'i' && false)",
        "IMAGELOADPOLICY != 0) { // chat_media_preview_v70",
    ],
    h: [
        "BYTE unenc_query[1024] = {0};",
        "get_photo v70 rejected file_reference",
        "visible chat photos intentionally use the native",
    ],
    t: ["chat_media_preview_v70"],
}
for p, tokens in checks.items():
    data = read(p)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat media preview v7.0 verification failed in {p.name}: {token}")

print(
    "Applied chat media preview v7.0: stripped thumbnails are never rendered; "
    "photos use the same native server-preview path as Media with safe modern "
    "file_reference buffers; video previews load for every enabled image policy; "
    "photo/video cards remain separate blocks."
)
