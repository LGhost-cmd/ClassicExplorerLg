#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_layout.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
p = root / "src" / "procs.cpp"
m = root / "src" / "message.cpp"
hp = root / "src" / "helpers.cpp"

for path in (h, t, p, m, hp):
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


# The patch intentionally runs after v5.9.
for path, token in ((t, "chat_video_direct_mouse_v59"), (p, "chat_video_direct_mouse_proc_v59")):
    if token not in read(path):
        raise SystemExit(f"Required v5.9 token was not found in {path.name}: {token}")

if "chat_media_layout_v60" in read(t):
    print("Chat media layout v6.0 already applied.")
    raise SystemExit(0)

# Header declaration for the shared photo-card helper.
s = read(h)
anchor = "HBITMAP media_album_make_tile(HBITMAP source);"
if anchor not in s:
    raise SystemExit("Could not locate media_album_make_tile declaration.")
if "media_chat_make_photo_card" not in s:
    s = s.replace(
        anchor,
        anchor + "\nHBITMAP media_chat_make_photo_card(HBITMAP source); // chat_media_layout_v60",
        1,
    )
write(h, s)

# helpers.cpp: normalize tiny stripped previews and large downloaded photos.
s = read(hp)
insert_at = s.find("int replace_in_chat(")
if insert_at < 0:
    raise SystemExit("Could not locate replace_in_chat in helpers.cpp.")

photo_card = r'''
// chat_media_layout_v60
HBITMAP media_chat_make_photo_card(
    HBITMAP source
) {
    if (!source)
        return NULL;

    BITMAP bm = {0};
    if (!GetObject(source, sizeof(bm), &bm))
        return NULL;

    int src_w = bm.bmWidth;
    int src_h = bm.bmHeight < 0 ? -bm.bmHeight : bm.bmHeight;
    if (src_w <= 0 || src_h <= 0)
        return NULL;

    const int card_w = 224;
    const int card_h = 168;
    const int pad = 5;

    HDC screen = GetDC(NULL);
    if (!screen)
        return NULL;

    HBITMAP card = CreateCompatibleBitmap(screen, card_w, card_h);
    ReleaseDC(NULL, screen);
    if (!card)
        return NULL;

    HDC src_dc = CreateCompatibleDC(NULL);
    HDC dst_dc = CreateCompatibleDC(NULL);
    if (!src_dc || !dst_dc) {
        if (src_dc) DeleteDC(src_dc);
        if (dst_dc) DeleteDC(dst_dc);
        DeleteObject(card);
        return NULL;
    }

    HGDIOBJ old_src = SelectObject(src_dc, source);
    HGDIOBJ old_dst = SelectObject(dst_dc, card);

    RECT all = {0, 0, card_w, card_h};
    FillRect(dst_dc, &all, GetSysColorBrush(COLOR_WINDOW));
    RECT frame = {0, 0, card_w, card_h};
    DrawEdge(dst_dc, &frame, EDGE_SUNKEN, BF_RECT);

    int area_w = card_w - pad * 2;
    int area_h = card_h - pad * 2;
    double scale_x = (double)area_w / (double)src_w;
    double scale_y = (double)area_h / (double)src_h;
    double scale = scale_x < scale_y ? scale_x : scale_y;

    int draw_w = (int)(src_w * scale + 0.5);
    int draw_h = (int)(src_h * scale + 0.5);
    if (draw_w < 1) draw_w = 1;
    if (draw_h < 1) draw_h = 1;

    int draw_x = (card_w - draw_w) / 2;
    int draw_y = (card_h - draw_h) / 2;

    SetStretchBltMode(dst_dc, HALFTONE);
    SetBrushOrgEx(dst_dc, 0, 0, NULL);
    StretchBlt(
        dst_dc,
        draw_x,
        draw_y,
        draw_w,
        draw_h,
        src_dc,
        0,
        0,
        src_w,
        src_h,
        SRCCOPY
    );

    SelectObject(src_dc, old_src);
    SelectObject(dst_dc, old_dst);
    DeleteDC(src_dc);
    DeleteDC(dst_dc);
    return card;
}

'''
if "HBITMAP media_chat_make_photo_card(" not in s:
    s = s[:insert_at] + photo_card + s[insert_at:]

vs, ve = function_range(s, "static HBITMAP media_chat_make_video_preview(")
vfunc = s[vs:ve]
vfunc2 = vfunc.replace("const int width = 112;", "const int width = 224;", 1).replace("const int height = 84;", "const int height = 168;", 1)
if vfunc2 == vfunc:
    raise SystemExit("Could not resize media_chat_make_video_preview.")
s = s[:vs] + vfunc2 + s[ve:]

block_start = s.find("\t\t\tHBITMAP display_bitmap = hBitmap;", insert_at)
if block_start < 0:
    raise SystemExit("Could not locate replace_in_chat media bitmap block start.")
block_end = s.find("\n\n\t\t\tSendMessage(chat, EM_SETSEL", block_start)
if block_end < 0:
    raise SystemExit("Could not locate replace_in_chat media bitmap block end.")
new = r'''\t\t\tHBITMAP display_bitmap = hBitmap;
\t\t\tHBITMAP media_card = NULL;
\t\t\tbool video_card = false;

\t\t\tfor (
\t\t\t\tint k = 0;
\t\t\t\tk < (int)documents.size();
\t\t\t\tk++
\t\t\t) {
\t\t\t\tif (
\t\t\t\t\tdocuments[k].photo_size == 3 &&
\t\t\t\t\tdocuments[k].visible &&
\t\t\t\t\tdocuments[k].min == min &&
\t\t\t\t\tdocuments[k].max == max
\t\t\t\t) {
\t\t\t\t\tvideo_card = true;
\t\t\t\t\tbreak;
\t\t\t\t}
\t\t\t}

\t\t\tmedia_card =
\t\t\t\tvideo_card
\t\t\t\t\t? media_chat_make_video_preview(hBitmap)
\t\t\t\t\t: media_chat_make_photo_card(hBitmap);

\t\t\tif (media_card)
\t\t\t\tdisplay_bitmap = media_card;

\t\t\tinsert_image(
\t\t\t\tchat,
\t\t\t\tNULL,
\t\t\t\tdisplay_bitmap
\t\t\t);

\t\t\tif (media_card)
\t\t\t\tDeleteObject(media_card);'''.replace('\\t', '\t')
s = s[:block_start] + new + s[block_end:]
write(hp, s)

# message.cpp: normalize initial stripped previews and video placeholders.
s = read(m)
ps, pe = function_range(s, "static HBITMAP media_chat_video_placeholder()")
pfunc = s[ps:pe]
pfunc2 = pfunc.replace("const int width = 112;", "const int width = 224;", 1).replace("const int height = 84;", "const int height = 168;", 1)
if pfunc2 == pfunc:
    raise SystemExit("Could not resize media_chat_video_placeholder.")
s = s[:ps] + pfunc2 + s[pe:]

block_start = s.find("\t\t\tHBITMAP display_bitmap = hClone;")
if block_start < 0:
    raise SystemExit("Could not locate initial chat-photo insertion block start.")
block_end = s.find("\n\n\t\t\tDeleteObject(hClone);", block_start)
if block_end < 0:
    raise SystemExit("Could not locate initial chat-photo insertion block end.")
new = r'''\t\t\tHBITMAP display_bitmap = hClone;
\t\t\tHBITMAP media_card = NULL;

\t\t\tif (hClone) {
\t\t\t\tmedia_card =
\t\t\t\t\tgroup_media
\t\t\t\t\t\t? media_album_make_tile(hClone)
\t\t\t\t\t\t: media_chat_make_photo_card(hClone);

\t\t\t\tif (media_card)
\t\t\t\t\tdisplay_bitmap = media_card;
\t\t\t}

\t\t\tinsert_image(chat, NULL, display_bitmap);

\t\t\tif (media_card)
\t\t\t\tDeleteObject(media_card);'''.replace('\\t', '\t')
s = s[:block_start] + new + s[block_end:]
write(m, s)

# telegacy.cpp: group albums same size; video only on double-click.
s = read(t)
as_, ae = function_range(s, "HBITMAP media_album_make_tile(")
afunc = s[as_:ae]
afunc2 = afunc.replace("const int tile_w = 132;", "const int tile_w = 224;", 1).replace("const int tile_h = 104;", "const int tile_h = 168;", 1)
if afunc2 == afunc:
    raise SystemExit("Could not resize media_album_make_tile.")
s = s[:as_] + afunc2 + s[ae:]

hs, he = function_range(s, "bool media_chat_video_handle_chat_mouse(")
handler = s[hs:he]
handler_new = handler.replace(
    "        (\n            msg != WM_LBUTTONDOWN &&\n            msg != WM_LBUTTONDBLCLK\n        )",
    "        msg != WM_LBUTTONDBLCLK",
    1,
)
handler_new = handler_new.replace("                        112,", "                        224,", 1).replace("                        84,", "                        168,", 1)
old_single = r'''        // WM_LBUTTONDOWN already performs the action. Consume the subsequent
        // WM_LBUTTONDBLCLK notification so a fast double click cannot cancel,
        // restart, or open the same video twice.
        if (msg == WM_LBUTTONDBLCLK) {
            diag_log(
                "chat video direct mouse swallowed double click index=%d",
                i
            );
            return true;
        }

        bool started ='''
new_single = r'''        // v6.0: a video card is deliberately activated only by double-click.
        bool started ='''
if old_single not in handler_new:
    raise SystemExit("Could not switch direct video handler to double-click.")
handler_new = handler_new.replace(old_single, new_single, 1)
handler_new = handler_new.replace("chat video direct mouse hit", "chat video direct double-click hit", 1)
s = s[:hs] + handler_new + s[he:]

old_branch = r'''                    if (documents[i].photo_size == 3) {
                        media_chat_video_start_full_document(
                            &documents[i]
                        );
                        break;
                    }'''
new_branch = r'''                    if (documents[i].photo_size == 3) {
                        if (media_double_click) {
                            media_chat_video_start_full_document(
                                &documents[i]
                            );
                        }
                        break;
                    }'''
if old_branch not in s:
    raise SystemExit("Could not locate EN_LINK video branch.")
s = s.replace(old_branch, new_branch, 1)
marker = "// chat_video_direct_mouse_v59"
s = s.replace(marker, marker + "\n// chat_media_layout_v60", 1)
write(t, s)

# procs.cpp: only consume a real double-click for video cards.
s = read(p)
old = r'''    if (
        (
            msg == WM_LBUTTONDOWN ||
            msg == WM_LBUTTONDBLCLK
        ) &&
        media_chat_video_handle_chat_mouse('''
new = r'''    if (
        msg == WM_LBUTTONDBLCLK &&
        media_chat_video_handle_chat_mouse('''
if old not in s:
    raise SystemExit("Could not locate v5.9 WndProcChat mouse interception.")
s = s.replace(old, new, 1)
write(p, s)

checks = {
    h: ["media_chat_make_photo_card(HBITMAP source)"],
    hp: ["chat_media_layout_v60", "const int card_w = 224;", "media_chat_make_photo_card(hBitmap)"],
    m: ["const int width = 224;", "media_chat_make_photo_card(hClone)"],
    t: ["chat_media_layout_v60", "msg != WM_LBUTTONDBLCLK", "const int tile_w = 224;", "if (media_double_click)"],
    p: ["msg == WM_LBUTTONDBLCLK &&", "media_chat_video_handle_chat_mouse("],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat media v6.0 verification failed in {path.name}: {token}")

print(
    "Applied chat media v6.0: video cards open only on double-click; all chat "
    "photo/video previews use a consistent 224x168 framed card with preserved aspect ratio."
)
