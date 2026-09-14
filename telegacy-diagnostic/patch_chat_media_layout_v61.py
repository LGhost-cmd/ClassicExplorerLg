#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_layout_v61.py <Telegacy source directory>")

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


if "chat_media_layout_v60" not in read(t):
    raise SystemExit("Chat media layout v6.0 was not found. Run patch_chat_media_layout.py first.")
if "chat_media_layout_v61" in read(t):
    print("Chat media layout v6.1 already applied.")
    raise SystemExit(0)

# Larger framed cards: 288x216 logical pixels.
s = read(hp)
start, end = function_range(s, "HBITMAP media_chat_make_photo_card(")
func = s[start:end]
func2 = func.replace("const int card_w = 224;", "const int card_w = 288;", 1)
func2 = func2.replace("const int card_h = 168;", "const int card_h = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_chat_make_photo_card.")
s = s[:start] + func2 + s[end:]

start, end = function_range(s, "static HBITMAP media_chat_make_video_preview(")
func = s[start:end]
func2 = func.replace("const int width = 224;", "const int width = 288;", 1)
func2 = func2.replace("const int height = 168;", "const int height = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_chat_make_video_preview.")
s = s[:start] + func2 + s[end:]

# Deterministic OLE replacement: delete the selected preview first. RichEdit
# can otherwise insert the new OLE beside the selected one and show both.
start, end = function_range(s, "int replace_in_chat(")
func = s[start:end]
old = '''\t\t\tif (media_card)\n\t\t\t\tdisplay_bitmap = media_card;\n\n\t\t\tinsert_image(\n\t\t\t\tchat,\n\t\t\t\tNULL,\n\t\t\t\tdisplay_bitmap\n\t\t\t);\n\n\t\t\tif (media_card)\n\t\t\t\tDeleteObject(media_card);\n\n\t\t\tSendMessage(chat, EM_SETSEL, min, max);\n\t\t\tSendMessage(chat, EM_SETCHARFORMAT, SCF_SELECTION, (LPARAM)&cf);\n\t\t\tdiff = 0;'''
new = '''\t\t\tif (media_card)\n\t\t\t\tdisplay_bitmap = media_card;\n\n\t\t\t// chat_media_layout_v61: replace, never append beside old OLE.\n\t\t\tSendMessage(chat, EM_REPLACESEL, FALSE, (LPARAM)L"");\n\n\t\t\tinsert_image(\n\t\t\t\tchat,\n\t\t\t\tNULL,\n\t\t\t\tdisplay_bitmap\n\t\t\t);\n\n\t\t\tif (media_card)\n\t\t\t\tDeleteObject(media_card);\n\n\t\t\tSendMessage(chat, EM_SETSEL, min, min + 1);\n\t\t\tSendMessage(chat, EM_SETCHARFORMAT, SCF_SELECTION, (LPARAM)&cf);\n\t\t\tdiff = 1 - (max - min);'''
if old not in func:
    raise SystemExit("Could not locate v6.0 OLE replacement block in replace_in_chat.")
func = func.replace(old, new, 1)
s = s[:start] + func + s[end:]
write(hp, s)

# message.cpp: larger video placeholder and strict media-block layout.
s = read(m)
start, end = function_range(s, "static HBITMAP media_chat_video_placeholder()")
func = s[start:end]
func2 = func.replace("const int width = 224;", "const int width = 288;", 1)
func2 = func2.replace("const int height = 168;", "const int height = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_chat_video_placeholder.")
s = s[:start] + func2 + s[end:]

# Grouped media used to delete the separator before the next image, allowing
# a following image/text fragment to continue on the same line. Disable that.
old = "\t\tif (!to_front && !header && !msghastext) {"
new = "\t\tif (!to_front && !header && !msghastext && !group_media) { // chat_media_block_v61"
if old not in s:
    raise SystemExit("Could not locate grouped-media newline removal block.")
s = s.replace(old, new, 1)

# Inline chat always uses one common photo-card renderer. Album tiles remain
# available for the Media archive only.
old = '''\t\t\tif (hClone) {\n\t\t\t\tmedia_card =\n\t\t\t\t\tgroup_media\n\t\t\t\t\t\t? media_album_make_tile(hClone)\n\t\t\t\t\t\t: media_chat_make_photo_card(hClone);\n\n\t\t\t\tif (media_card)\n\t\t\t\t\tdisplay_bitmap = media_card;\n\t\t\t}'''
new = '''\t\t\tif (hClone) {\n\t\t\t\tmedia_card = media_chat_make_photo_card(hClone);\n\n\t\t\t\tif (media_card)\n\t\t\t\t\tdisplay_bitmap = media_card;\n\t\t\t}'''
if old not in s:
    raise SystemExit("Could not locate v6.0 initial photo-card selection.")
s = s.replace(old, new, 1)

# Do not suppress the final message separator for edited albums. This keeps
# every media item as a block after message text.
old = "\tbool addnewline = (editing && added_photo && group_media && editing_index != messages.size() - 1 && messages[editing_index + 1].start_char == messages[editing_index + 1].end_header) ? false : true;"
new = "\tbool addnewline = true; // chat_media_block_v61"
if old not in s:
    raise SystemExit("Could not locate addnewline album rule.")
s = s.replace(old, new, 1)

# Video cards already get a newline from the footer/final message separator.
# Remove the extra immediate newline created by v5.6 to match photo spacing.
video_old = '''\t\t\t\t\t\tfree(document.filename);\n\t\t\t\t\t\tfree(document.file_reference);\n\t\t\t\t\t\tdocument.filename = NULL;\n\t\t\t\t\t\tdocument.file_reference = NULL;\n\n\t\t\t\t\t\twritten += riched_write(\n\t\t\t\t\t\t\tchat,\n\t\t\t\t\t\t\tL"\\n"\n\t\t\t\t\t\t);'''
video_new = '''\t\t\t\t\t\tfree(document.filename);\n\t\t\t\t\t\tfree(document.file_reference);\n\t\t\t\t\t\tdocument.filename = NULL;\n\t\t\t\t\t\tdocument.file_reference = NULL;\n\t\t\t\t\t\t// chat_media_block_v61: footer/final separator owns the newline.'''
if video_old not in s:
    raise SystemExit("Could not locate video-card trailing newline.")
s = s.replace(video_old, video_new, 1)
write(m, s)

# response.cpp: remove the pre-wrapped album tile. replace_in_chat now receives
# the real decoded bitmap and creates exactly one chat card from it.
s = read(r)
old = '''\t\t\t\tif (documents[i].visible) {\n                    HBITMAP chat_bitmap = hClone;\n                    HBITMAP album_tile = NULL;\n\n                    if (\n                        hClone &&\n                        media_album_is_document(\n                            documents[i].id\n                        )\n                    ) {\n                        album_tile =\n                            media_album_make_tile(\n                                hClone\n                            );\n\n                        if (album_tile)\n                            chat_bitmap = album_tile;\n                    }\n\n                    replace_in_chat(\n                        NULL,\n                        &cr,\n                        NULL,\n                        chat_bitmap,\n                        NULL,\n                        NULL,\n                        NULL\n                    );\n\n                    if (album_tile)\n                        DeleteObject(album_tile);\n                }'''
new = '''\t\t\t\tif (documents[i].visible) {\n                    // chat_media_block_v61: one decoded image -> one chat card.\n                    replace_in_chat(\n                        NULL,\n                        &cr,\n                        NULL,\n                        hClone,\n                        NULL,\n                        NULL,\n                        NULL\n                    );\n                }'''
if old not in s:
    raise SystemExit("Could not locate response-side album double-wrap block.")
s = s.replace(old, new, 1)
write(r, s)

# telegacy.cpp: archive tiles and video hit rectangle match the larger card.
s = read(t)
start, end = function_range(s, "HBITMAP media_album_make_tile(")
func = s[start:end]
func2 = func.replace("const int tile_w = 224;", "const int tile_w = 288;", 1)
func2 = func2.replace("const int tile_h = 168;", "const int tile_h = 216;", 1)
if func2 == func:
    raise SystemExit("Could not enlarge media_album_make_tile.")
s = s[:start] + func2 + s[end:]

start, end = function_range(s, "bool media_chat_video_handle_chat_mouse(")
func = s[start:end]
func2 = func.replace("                        224,", "                        288,", 1)
func2 = func2.replace("                        168,", "                        216,", 1)
if func2 == func:
    raise SystemExit("Could not enlarge video-card hit rectangle.")
s = s[:start] + func2 + s[end:]

marker = "// chat_media_layout_v60"
if marker not in s:
    raise SystemExit("Could not locate v6.0 marker in telegacy.cpp.")
s = s.replace(marker, marker + "\n// chat_media_layout_v61", 1)
write(t, s)

checks = {
    hp: [
        "const int card_w = 288;",
        "const int card_h = 216;",
        "chat_media_layout_v61: replace, never append beside old OLE",
        "diff = 1 - (max - min);",
    ],
    m: [
        "const int width = 288;",
        "!msghastext && !group_media",
        "media_card = media_chat_make_photo_card(hClone);",
        "bool addnewline = true; // chat_media_block_v61",
        "footer/final separator owns the newline",
    ],
    r: [
        "chat_media_block_v61: one decoded image -> one chat card",
        "                        hClone,",
    ],
    t: [
        "chat_media_layout_v61",
        "const int tile_w = 288;",
        "const int tile_h = 216;",
        "                        288,",
        "                        216,",
    ],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat media v6.1 verification failed in {path.name}: {token}")

print(
    "Applied chat media v6.1: 288x216 previews, no duplicate OLE insertion, "
    "single-pass full-photo replacement, and media stays in a separate block after text."
)
