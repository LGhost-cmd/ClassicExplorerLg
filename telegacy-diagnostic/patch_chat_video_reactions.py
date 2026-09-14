#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_chat_video_reactions.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing expected Telegacy file: {t}")


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
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = brace

    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
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
            in_line_comment = True
            i += 2
            continue

        if c == "/" and n == "*":
            in_block_comment = True
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


s = read(t)

if "chat_video_full_download_reactions_v58" in s:
    print("Chat video/reactions v5.8 fix already applied.")
    raise SystemExit(0)

for required in (
    "media_tabs_av_runtime_v56",
    "media_playback_start_runtime_v57",
    "media_player_queue_chat_autoplay(",
    "media_player_try_open_chat_path(",
    "media_player_chat_download_complete(",
    "COleCallback::GetContextMenu(",
):
    if required not in s:
        raise SystemExit(
            f"Required Telegacy runtime token was not found: {required}"
        )

# ---------------------------------------------------------------------------
# Chat video: a photo_size==3 entry is only the JPEG preview sentinel.
# download_file() treats non-zero photo_size as a thumbnail request, so clone
# the Telegram Document with photo_size=0 before starting the full transfer.
# ---------------------------------------------------------------------------

_, completion_end = function_range(
    s,
    "void media_player_chat_download_complete(",
)

video_helper = r'''

// chat_video_full_download_reactions_v58
static bool media_chat_video_start_full_document(
    Document* document
) {
    if (
        !document ||
        document->photo_size != 3 ||
        !document->filename ||
        !document->filename[0] ||
        !document->file_reference
    ) {
        return false;
    }

    // The completion callback uses this exact destination path to autoplay.
    media_player_queue_chat_autoplay(
        document->filename
    );

    // Do not restart or delete a file which is already receiving the full
    // document. The thumbnail request uses photo_size==3; a real video uses 0.
    for (
        int i = 0;
        i < (int)downloading_docs.size();
        i++
    ) {
        if (
            downloading_docs[i].photo_size == 0 &&
            memcmp(
                downloading_docs[i].id,
                document->id,
                8
            ) == 0 &&
            downloading_docs[i].filename &&
            _wcsicmp(
                downloading_docs[i].filename,
                document->filename
            ) == 0
        ) {
            diag_log(
                "chat video full download already active path=%ls",
                document->filename
            );
            return true;
        }
    }

    bool file_exists = false;
    bool file_complete = false;

    HANDLE file =
        CreateFileW(
            document->filename,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            NULL
        );

    if (file != INVALID_HANDLE_VALUE) {
        file_exists = true;

        LARGE_INTEGER size = {0};

        file_complete =
            GetFileSizeEx(
                file,
                &size
            ) &&
            size.QuadPart ==
                document->size;

        CloseHandle(file);
    }

    if (file_complete) {
        diag_log(
            "chat video full file already ready path=%ls",
            document->filename
        );

        return media_player_try_open_chat_path(
            document->filename
        );
    }

    // A completed thumbnail can occupy the same destination used by the card.
    // Never let the full Telegram document append/resume on top of JPEG bytes.
    if (file_exists) {
        if (!DeleteFileW(document->filename)) {
            diag_log(
                "chat video could not clear preview/partial path=%ls error=%lu",
                document->filename,
                (unsigned long)GetLastError()
            );
            return false;
        }
    }

    Document full = {0};

    full.size =
        document->size;

    memcpy(
        full.id,
        document->id,
        8
    );

    memcpy(
        full.access_hash,
        document->access_hash,
        8
    );

    full.dc =
        document->dc;

    // Critical difference from the visible preview sentinel.
    full.photo_size = 0;
    full.visible = false;

    int file_ref_len =
        tlstr_len(
            document->file_reference,
            true
        );

    if (file_ref_len <= 0)
        return false;

    full.file_reference =
        (BYTE*)malloc(
            file_ref_len
        );

    if (!full.file_reference)
        return false;

    memcpy(
        full.file_reference,
        document->file_reference,
        file_ref_len
    );

    full.filename =
        _wcsdup(
            document->filename
        );

    if (!full.filename) {
        free(full.file_reference);
        full.file_reference = NULL;
        return false;
    }

    downloading_docs.push_back(
        full
    );

    diag_log(
        "chat video starting full download size=%I64d path=%ls",
        document->size,
        document->filename
    );

    download_file(
        &dcInfoMain,
        &downloading_docs.back()
    );

    return true;
}
'''

s = s[:completion_end] + video_helper + s[completion_end:]

# EN_LINK normally subtracts one from EM_CHARFROMPOS. That is useful for text
# links but can move a one-character OLE video preview outside its own range.
en_link = s.find(
    "pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK"
)
if en_link < 0:
    raise SystemExit(
        "Could not locate the chat EN_LINK handler for the video-card fix."
    )

sel_pattern = re.compile(
    r"unsigned\s+int\s+sel_char\s*=\s*"
    r"SendMessage\s*\(\s*chat\s*,\s*EM_CHARFROMPOS\s*,\s*0\s*,"
    r"\s*\(LPARAM\)\s*&pt\s*\)\s*-\s*1\s*;"
)

sel_match = sel_pattern.search(
    s,
    en_link,
    min(len(s), en_link + 8000),
)
if not sel_match:
    raise SystemExit(
        "Could not locate chat EN_LINK character hit testing."
    )

sel_replacement = r'''LRESULT media_hit_char =
                        SendMessage(
                            chat,
                            EM_CHARFROMPOS,
                            0,
                            (LPARAM)&pt
                        );

                    unsigned int sel_char =
                        media_hit_char > 0
                            ? (unsigned int)media_hit_char - 1
                            : 0;

                    unsigned int media_raw_sel_char =
                        media_hit_char >= 0
                            ? (unsigned int)media_hit_char
                            : 0;'''

s = (
    s[:sel_match.start()]
    + sel_replacement
    + s[sel_match.end():]
)

condition_start = s.find(
    "if (documents[i].min <= sel_char && documents[i].max >= sel_char) {",
    sel_match.start(),
    min(len(s), sel_match.start() + 10000),
)

if condition_start < 0:
    raise SystemExit(
        "Could not locate chat document hit condition."
    )

old_condition = (
    "if (documents[i].min <= sel_char && "
    "documents[i].max >= sel_char) {"
)

new_condition = r'''if (
                        (
                            documents[i].min <= (int)sel_char &&
                            documents[i].max >= (int)sel_char
                        ) ||
                        (
                            documents[i].photo_size == 3 &&
                            documents[i].min <= (int)media_raw_sel_char &&
                            documents[i].max >= (int)media_raw_sel_char
                        )
                    ) {'''

s = (
    s[:condition_start]
    + new_condition
    + s[condition_start + len(old_condition):]
)

found_pos = s.find(
    "found = true;",
    condition_start,
    min(len(s), condition_start + 2500),
)

if found_pos < 0:
    raise SystemExit(
        "Could not locate the matched chat-document branch."
    )

found_end = found_pos + len("found = true;")

video_branch = r'''

                    // photo_size==3 is the linked JPEG preview. Clicking it
                    // must request/open the underlying full Telegram video.
                    if (documents[i].photo_size == 3) {
                        media_chat_video_start_full_document(
                            &documents[i]
                        );
                        break;
                    }'''

s = s[:found_end] + video_branch + s[found_end:]

# ---------------------------------------------------------------------------
# Reactions: Telegacy already has reactionStatic and the Telegram reaction
# sending logic. Expose that native chooser from the ordinary message context
# menu instead of only from the tiny reaction/footer hit area.
# ---------------------------------------------------------------------------

menu_start, menu_end = function_range(
    s,
    "COleCallback::GetContextMenu(",
)
menu_func = s[menu_start:menu_end]

menu_anchor = "HMENU hMenu = CreatePopupMenu();"
menu_pos = menu_func.find(menu_anchor)

if menu_pos < 0:
    raise SystemExit(
        "Could not locate Telegacy message context menu creation."
    )

menu_insert = r'''HMENU hMenu = CreatePopupMenu();

            const wchar_t* reaction_label =
                (
                    LANG[0] == 'R' &&
                    LANG[1] == 'U'
                )
                    ? L"\u0420\u0435\u0430\u043a\u0446\u0438\u044f..."
                    : L"Reaction...";

            UINT reaction_flags =
                (
                    current_peer &&
                    current_peer->reaction_list &&
                    !current_peer->reaction_list->empty()
                )
                    ? MF_STRING
                    : (MF_STRING | MF_GRAYED);

            AppendMenuW(
                hMenu,
                reaction_flags,
                25,
                reaction_label
            );

            AppendMenuW(
                hMenu,
                MF_SEPARATOR,
                0,
                NULL
            );'''

menu_func = (
    menu_func[:menu_pos]
    + menu_insert
    + menu_func[menu_pos + len(menu_anchor):]
)

s = s[:menu_start] + menu_func + s[menu_end:]

# Command ID 25 is unused in Telegacy 1.0.4. Place it next to the existing
# reply/edit/forward context-menu commands.
forward_case = -1
search_from = 0

while True:
    candidate = s.find("case 24: {", search_from)
    if candidate < 0:
        break

    if "forwarding_msg_id = sel_msg_id" in s[
        candidate:candidate + 700
    ]:
        forward_case = candidate
        break

    search_from = candidate + 1

if forward_case < 0:
    raise SystemExit(
        "Could not locate the message Forward command near case 24."
    )

reaction_case = r'''case 25: {
        if (
            reactionStatic &&
            current_peer &&
            current_peer->reaction_list &&
            !current_peer->reaction_list->empty()
        ) {
            POINT pt;
            GetCursorPos(&pt);

            SetWindowPos(
                reactionStatic,
                NULL,
                pt.x,
                pt.y,
                0,
                0,
                SWP_NOACTIVATE |
                SWP_SHOWWINDOW |
                SWP_NOSIZE
            );
        } else {
            MessageBeep(
                MB_ICONASTERISK
            );
        }
        break;
    }

    '''

s = s[:forward_case] + reaction_case + s[forward_case:]

write(t, s)

check = read(t)

for token in (
    "chat_video_full_download_reactions_v58",
    "media_chat_video_start_full_document(",
    "full.photo_size = 0;",
    "media_raw_sel_char",
    'L"Reaction..."',
    "case 25: {",
):
    if token not in check:
        raise SystemExit(
            f"Chat video/reactions v5.8 verification failed: {token}"
        )

print(
    "Applied chat video/reactions v5.8: video preview clicks now download "
    "the full Telegram Document and autoplay it, and right-click message "
    "menus offer the native reaction chooser."
)
