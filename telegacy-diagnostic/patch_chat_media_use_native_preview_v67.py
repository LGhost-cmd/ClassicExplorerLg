#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_use_native_preview_v67.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
hp = root / "src" / "helpers.cpp"
t = root / "src" / "telegacy.cpp"

for path in (hp, t):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


telegacy = read(t)
if "chat_media_layout_v64" not in telegacy:
    raise SystemExit("Chat media layout v6.4 was not found. Run patch_chat_media_layout_v64.py first.")
if "chat_media_native_preview_v67" in telegacy:
    print("Chat Media-native preview v6.7 already applied.")
    raise SystemExit(0)

s = read(hp)
old = '''    // chat_media_full_photo_v64
    if (
        !rce &&
        document &&
        document->visible &&
        document->photo_size != 0 &&
        document->photo_size != 1 &&
        document->photo_size != 3 &&
        IMAGELOADPOLICY != 0
    ) {
        if (media_chat_full_photo_begin(document, dcInfo))
            return;
    }
'''
new = '''    // chat_media_native_preview_v67
    // Ordinary visible chat photos deliberately fall through to Telegacy's
    // native get_photo()/upload.file path. This is the same server-thumbnail
    // path used by Media and retains Telegacy's proven serial queue, media-DC
    // migration, retry and OLE replacement behaviour. The stripped JPEG that
    // message_handler inserts is therefore only a temporary placeholder.
'''
count = s.count(old)
if count != 1:
    raise SystemExit(
        f"Expected exactly one v6.4 full-photo get_photo interception block, found {count}."
    )
s = s.replace(old, new, 1)

# Keep Media's native server-preview request unchanged. For normal photos this
# is inputPhotoFileLocation + thumb_size 'm': a real Telegram server image,
# rather than the tiny stripped thumbnail embedded in the message object.
if "unenc_query[offset_query + 1] = 'm';" not in s:
    raise SystemExit("Native Telegacy/Media 'm' server-preview request was not found in get_photo().")
if "media_chat_full_photo_begin(document, dcInfo)" in s:
    raise SystemExit("Custom full-photo interception call is still present after v6.7 patch.")
write(hp, s)

s = read(t)
anchor = "// chat_media_full_photo_v64"
if anchor not in s:
    raise SystemExit("Could not locate v6.4 marker for v6.7 audit marker.")
s = s.replace(anchor, anchor + "\n// chat_media_native_preview_v67", 1)
write(t, s)

checks = {
    hp: [
        "chat_media_native_preview_v67",
        "unenc_query[offset_query + 1] = 'm';",
        "internal_header(dcInfo, unenc_query, true);",
        "send_query(dcInfo, enc_query, offset_query + 24);",
    ],
    t: ["chat_media_native_preview_v67"],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat Media-native preview v6.7 verification failed in {path.name}: {token}")

print(
    "Applied chat Media-native preview v6.7: normal chat photos no longer use "
    "the custom full-photo interceptor; they now fall through to Telegacy's "
    "native Media/get_photo server-preview queue and replace stripped placeholders."
)
