#!/usr/bin/env python3
"""Concept98 v10.5: never draw low-resolution chat photo previews.

The loading card contains no Telegram image bytes. Stickers only animate
with a fresh RichEdit position, never a scroll-extrapolated one.
"""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_concept98_clean_media_v105.py <Telegacy source>")
root = Path(sys.argv[1]).resolve()
message = root / "src" / "message.cpp"
runtime = root / "src" / "telegacy.cpp"
m = message.read_text(encoding="latin-1")
t = runtime.read_text(encoding="latin-1")
if "concept98_clean_media_v105" in m and "concept98_clean_media_v105" in t:
    print("Concept98 v10.5 already applied")
    raise SystemExit(0)
if "concept98_static_webp_identity_v104" not in t:
    raise SystemExit("Requires complete Concept98 v10.4 patch chain")
if "chat_media_resilience_v71" not in m:
    raise SystemExit("Missing ordinary chat photo renderer")

def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit("v10.5 expected one " + label + ", found " + str(count))
    return text.replace(old, new, 1)

# The v7.1 fallback re-enabled the tiny Telegram stripped JPEG and enlarged it
# to 288x216. Never decode or insert it, even while the network is slow.
m = once(
    m,
    "if (size == 'i' && IMAGELOADPOLICY) { // chat_media_resilience_v71: stripped preview is a fallback",
    "if (size == 'i' && false) { // concept98_clean_media_v105: stripped preview is metadata only",
    "stripped-JPEG gate",
)

# The ordinary photo path must always reserve a neutral card, not a thumbnail
# discovered under another size flag. Its eventual full JPEG still arrives via
# the existing v6.6 loader and v8.7 exact-identity RichEdit replacement.
old = """\t\t\tif (hClone) {
\t\t\t\tmedia_card = media_chat_make_photo_card(hClone);
\t\t\t\tdisplay_bitmap = media_card ? media_card : hClone;
\t\t\t} else {
\t\t\t\tloading_card = media_chat_photo_placeholder();
\t\t\t\tdisplay_bitmap = loading_card;
\t\t\t}"""
new = """\t\t\t// concept98_clean_media_v105: placeholder-only until full decode.
\t\t\t// hClone is deliberately never used as a chat photo preview.
\t\t\tloading_card = media_chat_photo_placeholder();
\t\t\tdisplay_bitmap = loading_card;"""
m = once(m, old, new, "ordinary photo placeholder")

start = m.find("static HBITMAP media_chat_photo_placeholder()")
if start < 0:
    raise SystemExit("Missing v7.0 photo placeholder function")
brace = m.find("{", start)
depth = 0
end = -1
for i in range(brace, len(m)):
    if m[i] == "{": depth += 1
    elif m[i] == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break
if end < 0:
    raise SystemExit("Unclosed photo placeholder function")

# A single, quiet Windows 98-era loading card. It is NOT an approximation of
# the downloaded photo. Only fully decoded media is allowed to replace it.
card = r'''static HBITMAP media_chat_photo_placeholder() {
    // concept98_clean_media_v105
    const int width=288, height=216;
    HDC screen=GetDC(NULL);
    if (!screen) return NULL;
    HBITMAP bitmap=CreateCompatibleBitmap(screen,width,height);
    HDC dc=CreateCompatibleDC(screen);
    ReleaseDC(NULL,screen);
    if (!bitmap || !dc) {
        if (bitmap) DeleteObject(bitmap);
        if (dc) DeleteDC(dc);
        return NULL;
    }
    HGDIOBJ old=SelectObject(dc,bitmap);
    RECT all={0,0,width,height};
    FillRect(dc,&all,GetSysColorBrush(COLOR_WINDOW));
    DrawEdge(dc,&all,EDGE_SUNKEN,BF_RECT);
    RECT title={14,76,width-14,110};
    SetBkMode(dc,TRANSPARENT);
    SetTextColor(dc,GetSysColor(COLOR_WINDOWTEXT));
    DrawTextW(dc,L"Loading image...",-1,&title,
              DT_CENTER|DT_SINGLELINE|DT_VCENTER);
    RECT hint={12,112,width-12,145};
    SetTextColor(dc,GetSysColor(COLOR_GRAYTEXT));
    DrawTextW(dc,L"Full quality  |  Click to retry",-1,&hint,
              DT_CENTER|DT_SINGLELINE|DT_VCENTER);
    SelectObject(dc,old);
    DeleteDC(dc);
    return bitmap;
}'''
m = m[:start] + card + m[end:]

# Fail closed: never extrapolate the WebM/TGS overlay across RichEdit scroll.
# EM_POSFROMCHAR must give the live position of this sticker's own exact OLE.
start = t.find("        bool inferred_geometry = false;")
end = t.find("        if (\n            !direct_geometry &&\n            !inferred_geometry", start)
if start < 0 or end < 0:
    raise SystemExit("Missing v8.8 inferred animated sticker geometry")
legacy = t[start:end]
if "sticker_cp == sticker->last_cp_v88" not in legacy:
    raise SystemExit("Missing v9.4 same-cp sticker geometry guard")
replacement = """        // concept98_clean_media_v105: inferred scroll locations can
        // visibly slice the next media item. Show only confirmed positions.
        // Keeping the matching cp invariant is essential:
        // sticker_cp == sticker->last_cp_v88 after a fresh query.
        bool inferred_geometry = false;
"""
t = t[:start] + replacement + t[end:]
needle = """            sticker->visible = false;
            continue;
        }

        int width =
            media_chat_sticker_card_width();"""
repl = """            sticker->visible = false;
            sticker->have_geometry_v88 = false;
            continue;
        }

        int width =
            media_chat_sticker_card_width();"""
t = once(t, needle, repl, "sticker no-geometry fallback")
if "origin.x -=" in t[t.find("static VOID CALLBACK media_chat_sticker_timer_proc_unsafe("):t.find("static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(")+11000]:
    raise SystemExit("Sticker timer still extrapolates the overlay x-coordinate")

message.write_text(m, encoding="latin-1", newline="\r\n")
runtime.write_text(t, encoding="latin-1", newline="\r\n")
print("Concept98 v10.5: stripped previews disabled, honest loading card, "
      "full-resolution only via verified OLE, animated overlays require a "
      "fresh exact RichEdit geometry.")
