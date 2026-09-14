#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_layout_v64.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
m = root / "src" / "message.cpp"
hp = root / "src" / "helpers.cpp"
r = root / "src" / "response.cpp"

for path in (t, m, hp, r):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


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


base_t = read(t)
if "chat_media_layout_v64" in base_t:
    print("Chat media layout v6.4 already applied.")
    raise SystemExit(0)
if "chat_media_layout_v60" not in base_t:
    raise SystemExit("Chat media layout v6.0 was not found. Run patch_chat_media_layout.py first.")

# v6.1 layout: larger 288x216 cards, deterministic OLE replacement, and media
# blocks kept separate from message text.
s = read(hp)
start, end = function_range(s, "HBITMAP media_chat_make_photo_card(")
func = s[start:end]
func2 = func.replace("const int card_w = 224;", "const int card_w = 288;", 1)
func2 = func2.replace("const int card_h = 168;", "const int card_h = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_chat_make_photo_card from v6.0.")
s = s[:start] + func2 + s[end:]

start, end = function_range(s, "static HBITMAP media_chat_make_video_preview(")
func = s[start:end]
func2 = func.replace("const int width = 224;", "const int width = 288;", 1)
func2 = func2.replace("const int height = 168;", "const int height = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_chat_make_video_preview from v6.0.")
s = s[:start] + func2 + s[end:]

start, end = function_range(s, "int replace_in_chat(")
func = s[start:end]
old = '''\t\t\tif (media_card)\n\t\t\t\tdisplay_bitmap = media_card;\n\n\t\t\tinsert_image(\n\t\t\t\tchat,\n\t\t\t\tNULL,\n\t\t\t\tdisplay_bitmap\n\t\t\t);\n\n\t\t\tif (media_card)\n\t\t\t\tDeleteObject(media_card);\n\n\t\t\tSendMessage(chat, EM_SETSEL, min, max);\n\t\t\tSendMessage(chat, EM_SETCHARFORMAT, SCF_SELECTION, (LPARAM)&cf);\n\t\t\tdiff = 0;'''
new = '''\t\t\tif (media_card)\n\t\t\t\tdisplay_bitmap = media_card;\n\n\t\t\t// chat_media_layout_v64: replace the selected OLE instead of appending.\n\t\t\tSendMessage(chat, EM_REPLACESEL, FALSE, (LPARAM)L"");\n\n\t\t\tinsert_image(\n\t\t\t\tchat,\n\t\t\t\tNULL,\n\t\t\t\tdisplay_bitmap\n\t\t\t);\n\n\t\t\tif (media_card)\n\t\t\t\tDeleteObject(media_card);\n\n\t\t\tSendMessage(chat, EM_SETSEL, min, min + 1);\n\t\t\tSendMessage(chat, EM_SETCHARFORMAT, SCF_SELECTION, (LPARAM)&cf);\n\t\t\tdiff = 1 - (max - min);'''
if old not in func:
    raise SystemExit("Could not locate v6.0 OLE replacement block in replace_in_chat.")
func = func.replace(old, new, 1)
s = s[:start] + func + s[end:]
write(hp, s)

s = read(m)
start, end = function_range(s, "static HBITMAP media_chat_video_placeholder()")
func = s[start:end]
func2 = func.replace("const int width = 224;", "const int width = 288;", 1)
func2 = func2.replace("const int height = 168;", "const int height = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_chat_video_placeholder from v6.0.")
s = s[:start] + func2 + s[end:]

old = "\t\tif (!to_front && !header && !msghastext) {"
new = "\t\tif (!to_front && !header && !msghastext && !group_media) { // chat_media_block_v64"
if old not in s:
    raise SystemExit("Could not locate grouped-media newline removal block.")
s = s.replace(old, new, 1)

old = '''\t\t\tif (hClone) {\n\t\t\t\tmedia_card =\n\t\t\t\t\tgroup_media\n\t\t\t\t\t\t? media_album_make_tile(hClone)\n\t\t\t\t\t\t: media_chat_make_photo_card(hClone);\n\n\t\t\t\tif (media_card)\n\t\t\t\t\tdisplay_bitmap = media_card;\n\t\t\t}'''
new = '''\t\t\tif (hClone) {\n\t\t\t\tmedia_card = media_chat_make_photo_card(hClone);\n\n\t\t\t\tif (media_card)\n\t\t\t\t\tdisplay_bitmap = media_card;\n\t\t\t}'''
if old not in s:
    raise SystemExit("Could not locate v6.0 initial photo-card selection.")
s = s.replace(old, new, 1)

old = "\tbool addnewline = (editing && added_photo && group_media && editing_index != messages.size() - 1 && messages[editing_index + 1].start_char == messages[editing_index + 1].end_header) ? false : true;"
new = "\tbool addnewline = true; // chat_media_block_v64"
if old not in s:
    raise SystemExit("Could not locate addnewline album rule.")
s = s.replace(old, new, 1)

video_old = '''\t\t\t\t\t\tfree(document.filename);\n\t\t\t\t\t\tfree(document.file_reference);\n\t\t\t\t\t\tdocument.filename = NULL;\n\t\t\t\t\t\tdocument.file_reference = NULL;\n\n\t\t\t\t\t\twritten += riched_write(\n\t\t\t\t\t\t\tchat,\n\t\t\t\t\t\t\tL"\\n"\n\t\t\t\t\t\t);'''
video_new = '''\t\t\t\t\t\tfree(document.filename);\n\t\t\t\t\t\tfree(document.file_reference);\n\t\t\t\t\t\tdocument.filename = NULL;\n\t\t\t\t\t\tdocument.file_reference = NULL;\n\t\t\t\t\t\t// chat_media_block_v64: footer/final separator owns the newline.'''
if video_old not in s:
    raise SystemExit("Could not locate video-card trailing newline.")
s = s.replace(video_old, video_new, 1)
write(m, s)

s = read(r)
old = '''\t\t\t\tif (documents[i].visible) {\n                    HBITMAP chat_bitmap = hClone;\n                    HBITMAP album_tile = NULL;\n\n                    if (\n                        hClone &&\n                        media_album_is_document(\n                            documents[i].id\n                        )\n                    ) {\n                        album_tile =\n                            media_album_make_tile(\n                                hClone\n                            );\n\n                        if (album_tile)\n                            chat_bitmap = album_tile;\n                    }\n\n                    replace_in_chat(\n                        NULL,\n                        &cr,\n                        NULL,\n                        chat_bitmap,\n                        NULL,\n                        NULL,\n                        NULL\n                    );\n\n                    if (album_tile)\n                        DeleteObject(album_tile);\n                }'''
new = '''\t\t\t\tif (documents[i].visible) {\n                    // chat_media_block_v64: one decoded image -> one chat card.\n                    replace_in_chat(\n                        NULL,\n                        &cr,\n                        NULL,\n                        hClone,\n                        NULL,\n                        NULL,\n                        NULL\n                    );\n                }'''
if old not in s:
    raise SystemExit("Could not locate response-side album double-wrap block.")
s = s.replace(old, new, 1)
write(r, s)

s = read(t)
start, end = function_range(s, "HBITMAP media_album_make_tile(")
func = s[start:end]
func2 = func.replace("const int tile_w = 224;", "const int tile_w = 288;", 1)
func2 = func2.replace("const int tile_h = 168;", "const int tile_h = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_album_make_tile from v6.0.")
s = s[:start] + func2 + s[end:]

start, end = function_range(s, "bool media_chat_video_handle_chat_mouse(")
func = s[start:end]
func2 = func.replace("                        224,", "                        288,", 1)
func2 = func2.replace("                        168,", "                        216,", 1)
if func2 == func:
    raise SystemExit("Could not enlarge video-card hit rectangle from v6.0.")
s = s[:start] + func2 + s[end:]
write(t, s)

# Full-photo loader: normal visible chat photos use the same full PhotoSize
# request pattern as Media. The tiny stripped JPEG is only a temporary card.
s = read(t)
insert_pos = s.find("static void media_player_queue_chat_autoplay(")
if insert_pos < 0:
    raise SystemExit("Could not locate chat media helper insertion point.")

full_loader = r'''
// chat_media_full_photo_v64
static bool media_chat_full_photo_active = false;
static BYTE media_chat_full_photo_rpc_id[8] = {0};
static BYTE media_chat_full_photo_id[8] = {0};
static BYTE media_chat_full_photo_access_hash[8] = {0};
static BYTE* media_chat_full_photo_file_reference = NULL;
static char media_chat_full_photo_size = 0;
static LONGLONG media_chat_full_photo_expected_size = 0;
static LONGLONG media_chat_full_photo_offset = 0;
static std::vector<BYTE> media_chat_full_photo_bytes;

static void media_chat_full_photo_reset(bool allow_retry) {
    if (allow_retry) {
        for (int i = 0; i < (int)documents.size(); i++) {
            if (
                memcmp(documents[i].id, media_chat_full_photo_id, 8) == 0 &&
                memcmp(documents[i].access_hash, media_chat_full_photo_access_hash, 8) == 0
            ) {
                memset(documents[i].photo_msg_id, 0, 8);
                break;
            }
        }
    }

    free(media_chat_full_photo_file_reference);
    media_chat_full_photo_file_reference = NULL;
    media_chat_full_photo_active = false;
    media_chat_full_photo_size = 0;
    media_chat_full_photo_expected_size = 0;
    media_chat_full_photo_offset = 0;
    media_chat_full_photo_bytes.clear();
    memset(media_chat_full_photo_rpc_id, 0, 8);
    memset(media_chat_full_photo_id, 0, 8);
    memset(media_chat_full_photo_access_hash, 0, 8);
}

static bool media_chat_full_photo_send_chunk() {
    if (!media_chat_full_photo_active || !media_chat_full_photo_file_reference || !media_chat_full_photo_size)
        return false;

    BYTE unenc_query[192] = {0};
    BYTE enc_query[216] = {0};
    internal_header(unenc_query, true);
    memcpy(media_chat_full_photo_rpc_id, unenc_query + 16, 8);

    write_le(unenc_query + 32, 0xbe5335be, 4);
    write_le(unenc_query + 36, 0, 4);
    write_le(unenc_query + 40, 0x40181ffe, 4);
    memcpy(unenc_query + 44, media_chat_full_photo_id, 8);
    memcpy(unenc_query + 52, media_chat_full_photo_access_hash, 8);

    int file_ref_len = tlstr_len(media_chat_full_photo_file_reference, true);
    if (file_ref_len <= 0 || 60 + file_ref_len + 16 > (int)sizeof(unenc_query))
        return false;

    memcpy(unenc_query + 60, media_chat_full_photo_file_reference, file_ref_len);
    int offset = 60 + file_ref_len;

    memset(unenc_query + offset, 0, 12);
    unenc_query[offset] = 1;
    unenc_query[offset + 1] = (BYTE)media_chat_full_photo_size;
    write_le(unenc_query + offset + 4, media_chat_full_photo_offset, 8);
    offset += 12;

    write_le(unenc_query + offset, 1048576, 4);
    offset += 4;
    write_le(unenc_query + 28, offset - 32, 4);

    int padding_len = get_padding(offset);
    fortuna_read(unenc_query + offset, padding_len, &prng);
    offset += padding_len;

    if (!convert_message(unenc_query, enc_query, offset, 0))
        return false;

    int sent = send_query(enc_query, offset + 24);
    diag_log(
        "chat full photo request size=%c offset=%I64d expected=%I64d sent=%d",
        media_chat_full_photo_size,
        media_chat_full_photo_offset,
        media_chat_full_photo_expected_size,
        sent
    );
    return sent > 0;
}

bool media_chat_full_photo_begin(Document* document) {
    if (
        !document ||
        !document->visible ||
        !document->file_reference ||
        document->photo_size == 0 ||
        document->photo_size == 1 ||
        document->photo_size == 3
    ) {
        return false;
    }

    if (media_chat_full_photo_active)
        return true;

    int file_ref_len = tlstr_len(document->file_reference, true);
    if (file_ref_len <= 0)
        return false;

    media_chat_full_photo_file_reference = (BYTE*)malloc(file_ref_len);
    if (!media_chat_full_photo_file_reference)
        return false;

    memcpy(media_chat_full_photo_file_reference, document->file_reference, file_ref_len);
    memcpy(media_chat_full_photo_id, document->id, 8);
    memcpy(media_chat_full_photo_access_hash, document->access_hash, 8);
    media_chat_full_photo_size = document->photo_size;
    media_chat_full_photo_expected_size = document->size;
    media_chat_full_photo_offset = 0;
    media_chat_full_photo_bytes.clear();
    media_chat_full_photo_active = true;

    if (!media_chat_full_photo_send_chunk()) {
        media_chat_full_photo_reset(false);
        return false;
    }

    memcpy(document->photo_msg_id, media_chat_full_photo_rpc_id, 8);
    return true;
}

bool media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length) {
    if (
        !media_chat_full_photo_active ||
        !rpc_id ||
        !response ||
        length < 13 ||
        memcmp(rpc_id, media_chat_full_photo_rpc_id, 8) != 0
    ) {
        return false;
    }

    int size = tlstr_len(response + 12, false);
    int prefix = size >= 254 ? 4 : 1;
    int data_pos = 12 + prefix;

    if (size < 0 || data_pos < 0 || data_pos + size > length) {
        diag_log("chat full photo malformed upload.file size=%d length=%d", size, length);
        media_chat_full_photo_reset(true);
        return true;
    }

    if (size > 0) {
        media_chat_full_photo_bytes.insert(
            media_chat_full_photo_bytes.end(),
            response + data_pos,
            response + data_pos + size
        );
    }

    media_chat_full_photo_offset += size;
    bool more =
        size >= 1048576 &&
        (media_chat_full_photo_expected_size <= 0 || media_chat_full_photo_offset < media_chat_full_photo_expected_size);

    if (more) {
        if (!media_chat_full_photo_send_chunk()) {
            diag_log("chat full photo next chunk failed");
            media_chat_full_photo_reset(true);
        }
        return true;
    }

    int target = -1;
    for (int i = 0; i < (int)documents.size(); i++) {
        if (
            documents[i].visible &&
            memcmp(documents[i].id, media_chat_full_photo_id, 8) == 0 &&
            memcmp(documents[i].access_hash, media_chat_full_photo_access_hash, 8) == 0
        ) {
            target = i;
            break;
        }
    }

    diag_log(
        "chat full photo complete bytes=%I64d expected=%I64d target=%d",
        media_chat_full_photo_offset,
        media_chat_full_photo_expected_size,
        target
    );

    if (target >= 0 && !media_chat_full_photo_bytes.empty()) {
        HBITMAP full_bitmap = jpg_to_bmp(
            &media_chat_full_photo_bytes[0],
            (int)media_chat_full_photo_bytes.size()
        );

        if (full_bitmap) {
            CHARRANGE cr;
            cr.cpMin = documents[target].min;
            cr.cpMax = documents[target].max;
            replace_in_chat(NULL, &cr, NULL, full_bitmap, NULL, NULL, NULL);
            DeleteObject(full_bitmap);
        } else {
            diag_log("chat full photo JPEG decode failed");
        }
    }

    media_chat_full_photo_reset(false);

    if (IMAGELOADPOLICY != 0) {
        for (int i = (int)documents.size() - 1; i >= 0; i--) {
            if (
                documents[i].visible &&
                documents[i].photo_size != 0 &&
                documents[i].photo_size != 1 &&
                documents[i].photo_size != 3 &&
                documents[i].file_reference &&
                !read_le(documents[i].photo_msg_id, 8)
            ) {
                get_photo(NULL, &documents[i], &dcInfoMain);
                break;
            }
        }
    }

    return true;
}

'''
s = s[:insert_pos] + full_loader + s[insert_pos:]
marker = "// chat_media_layout_v60"
if marker not in s:
    raise SystemExit("Could not locate v6.0 marker in telegacy.cpp.")
s = s.replace(marker, marker + "\n// chat_media_layout_v64", 1)
write(t, s)

# helpers.cpp: route normal chat photos to full-photo loader.
s = read(hp)
get_start, get_end = function_range(s, "void get_photo(")
func = s[get_start:get_end]
brace = func.find("{")
if brace < 0:
    raise SystemExit("Could not locate get_photo opening brace.")
intercept = r'''

    // chat_media_full_photo_v64
    if (
        !rce &&
        document &&
        document->visible &&
        document->photo_size != 0 &&
        document->photo_size != 1 &&
        document->photo_size != 3 &&
        IMAGELOADPOLICY != 0
    ) {
        if (media_chat_full_photo_begin(document))
            return;
    }
'''
func = func[:brace + 1] + intercept + func[brace + 1:]
s = s[:get_start] + func + s[get_end:]
decl_anchor = "void get_photo(RequestedCustomEmoji* rce, Document* document, DCInfo* dcInfo) {"
if decl_anchor not in s:
    raise SystemExit("Could not locate get_photo declaration anchor.")
s = s.replace(
    decl_anchor,
    "bool media_chat_full_photo_begin(Document* document); // chat_media_full_photo_v64\n" + decl_anchor,
    1,
)
write(hp, s)

# response.cpp: claim matching upload.file RPC before Media/legacy handlers.
s = read(r)
anchor = '''        // media_tabs_av_response_v3
        if (
            media_archive_handle_full_photo_upload('''
if anchor not in s:
    raise SystemExit("Could not locate Media full-photo upload handler.")
chat_handler = r'''        // chat_media_full_photo_response_v64
        if (
            media_chat_full_photo_handle_upload(
                last_rpcresult_msgid,
                unenc_response,
                length
            )
        ) {
            break;
        }

'''
s = s.replace(anchor, chat_handler + anchor, 1)
decl_pos = s.find("case 0x96a18d5: { // upload.file")
if decl_pos < 0:
    raise SystemExit("Could not locate upload.file switch case.")
func_candidates = ["void response_handler(", "int response_handler(", "void response_parser(", "int response_parser("]
insert_decl = -1
for sig in func_candidates:
    p = s.find(sig)
    if p >= 0 and p < decl_pos:
        insert_decl = p
        break
if insert_decl < 0:
    insert_decl = s.find("\nvoid ")
    if insert_decl < 0:
        insert_decl = s.find("\nint ")
    if insert_decl < 0:
        raise SystemExit("Could not locate response.cpp declaration insertion point.")
    insert_decl += 1
s = s[:insert_decl] + "bool media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length); // chat_media_full_photo_v64\n" + s[insert_decl:]
write(r, s)

checks = {
    hp: [
        "const int card_w = 288;",
        "const int card_h = 216;",
        "chat_media_layout_v64: replace the selected OLE",
        "media_chat_full_photo_begin(document)",
    ],
    m: [
        "const int width = 288;",
        "!msghastext && !group_media",
        "media_card = media_chat_make_photo_card(hClone);",
        "bool addnewline = true; // chat_media_block_v64",
    ],
    r: [
        "chat_media_block_v64: one decoded image -> one chat card",
        "chat_media_full_photo_response_v64",
        "media_chat_full_photo_handle_upload(",
    ],
    t: [
        "chat_media_layout_v64",
        "chat_media_full_photo_v64",
        "const int tile_w = 288;",
        "const int tile_h = 216;",
        "media_chat_full_photo_send_chunk()",
        "jpg_to_bmp(",
    ],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat media v6.4 verification failed in {path.name}: {token}")

print(
    "Applied self-contained chat media v6.4: 288x216 block cards, deterministic "
    "OLE replacement, double-click video hit area, and full PhotoSize downloads "
    "for normal chat photos using the same request strategy as Media."
)
