#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_photo_click_download_v78.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
p = root / "src" / "procs.cpp"
r = root / "src" / "response.cpp"

for path in (h, t, p, r):
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
    in_string = False
    in_char = False
    in_line = False
    in_block = False
    escaped = False
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


if "chat_photo_click_download_v78" in read(t):
    print("Chat photo click/download v7.8 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_channel_media_layout_v77", t),
    ("chat_runtime_recovery_v76", t),
    ("chat_interaction_paging_v75", t),
    ("chat_photo_retry_dblclick_proc_v75", p),
    ("chat_media_full_photo_v64", t),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

# ---------------------------------------------------------------------------
# Runtime state + persistent save/open helper.
# ---------------------------------------------------------------------------
s = read(t)

state_anchor = "static DCInfo* media_chat_full_photo_dc = NULL; // chat_media_dc_retry_v66"
if state_anchor not in s:
    raise SystemExit("Could not locate full-photo DC state.")

state_extra = r'''
static bool media_chat_full_photo_open_when_done = false; // chat_photo_click_download_v78
static wchar_t media_chat_full_photo_saved_path[MAX_PATH] = {0};

static bool media_chat_full_photo_save_and_open() {
    if (media_chat_full_photo_bytes.empty())
        return false;

    wchar_t base[MAX_PATH] = {0};
    wchar_t folder[MAX_PATH] = {0};

    HRESULT shell_folder = SHGetFolderPathW(
        NULL,
        CSIDL_MYPICTURES | CSIDL_FLAG_CREATE,
        NULL,
        SHGFP_TYPE_CURRENT,
        base
    );

    if (SUCCEEDED(shell_folder) && base[0]) {
        _snwprintf(
            folder,
            ARRAYSIZE(folder) - 1,
            L"%s\\Telegacy",
            base
        );
    } else {
        _snwprintf(
            folder,
            ARRAYSIZE(folder) - 1,
            L"%s\\TelegacyPhotos",
            appdata_path
        );
    }

    folder[ARRAYSIZE(folder) - 1] = 0;
    CreateDirectoryW(folder, NULL);

    unsigned __int64 photo_id =
        (unsigned __int64)read_le(media_chat_full_photo_id, 8);

    _snwprintf(
        media_chat_full_photo_saved_path,
        ARRAYSIZE(media_chat_full_photo_saved_path) - 1,
        L"%s\\photo_%016I64X.jpg",
        folder,
        photo_id
    );
    media_chat_full_photo_saved_path[
        ARRAYSIZE(media_chat_full_photo_saved_path) - 1
    ] = 0;

    FILE* file = _wfopen(
        media_chat_full_photo_saved_path,
        L"wb"
    );

    if (!file) {
        diag_log(
            "chat v78 photo save failed path=%ls",
            media_chat_full_photo_saved_path
        );
        media_chat_full_photo_saved_path[0] = 0;
        return false;
    }

    size_t written = fwrite(
        &media_chat_full_photo_bytes[0],
        1,
        media_chat_full_photo_bytes.size(),
        file
    );

    fclose(file);

    if (written != media_chat_full_photo_bytes.size()) {
        diag_log(
            "chat v78 photo short write path=%ls wrote=%Iu expected=%Iu",
            media_chat_full_photo_saved_path,
            written,
            media_chat_full_photo_bytes.size()
        );
        return false;
    }

    HINSTANCE opened = ShellExecuteW(
        hMain,
        L"open",
        media_chat_full_photo_saved_path,
        NULL,
        NULL,
        SW_SHOWNORMAL
    );

    diag_log(
        "chat v78 photo saved/opened path=%ls bytes=%Iu shell=%Id",
        media_chat_full_photo_saved_path,
        media_chat_full_photo_bytes.size(),
        (INT_PTR)opened
    );

    return (INT_PTR)opened > 32;
}

'''
s = s.replace(state_anchor, state_anchor + state_extra, 1)

# Reset must never leak the previous click action into the next photo.
reset_sig = "static void media_chat_full_photo_reset(bool allow_retry)"
rs, re_ = function_range(s, reset_sig)
reset_func = s[rs:re_]
reset_close = reset_func.rfind("}")
if reset_close < 0:
    raise SystemExit("Could not locate full-photo reset close.")
reset_insert = r'''
    media_chat_full_photo_open_when_done = false;
    media_chat_full_photo_saved_path[0] = 0;
'''
reset_func = reset_func[:reset_close] + reset_insert + reset_func[reset_close:]
s = s[:rs] + reset_func + s[re_:]

# ---------------------------------------------------------------------------
# A click-targeted transfer is allowed to preempt background work. Double-click
# upgrades an already-running transfer of the same photo into save+open mode.
# ---------------------------------------------------------------------------
video_pos = s.find("bool media_chat_video_handle_chat_mouse(")
if video_pos < 0:
    raise SystemExit("Could not locate video mouse handler insertion point.")

user_helper = r'''
// chat_photo_click_download_v78
static DCInfo* media_chat_photo_preferred_dc(Document* document) {
    if (!document)
        return &dcInfoMain;

    if (
        document->dc <= 0 ||
        document->dc == dcInfoMain.dc
    ) {
        return &dcInfoMain;
    }

    for (
        std::list<DCInfo>::iterator it = active_dcs.begin();
        it != active_dcs.end();
        ++it
    ) {
        if (
            it->dc == document->dc &&
            it->ready
        ) {
            return &(*it);
        }
    }

    // Starting on main is safe: Telegram's FILE_MIGRATE path will establish or
    // reuse the media DC, and v7.8 explicitly resumes this serial request there.
    return &dcInfoMain;
}

static bool media_chat_full_photo_user_action(
    Document* document,
    bool save_and_open
) {
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

    bool same_active =
        media_chat_full_photo_active &&
        memcmp(
            document->id,
            media_chat_full_photo_id,
            8
        ) == 0 &&
        memcmp(
            document->access_hash,
            media_chat_full_photo_access_hash,
            8
        ) == 0;

    if (same_active) {
        if (save_and_open)
            media_chat_full_photo_open_when_done = true;

        diag_log(
            "chat v78 photo action joined active transfer open=%d",
            media_chat_full_photo_open_when_done ? 1 : 0
        );
        return true;
    }

    if (media_chat_full_photo_active) {
        diag_log(
            "chat v78 photo action preempting background transfer"
        );
        media_chat_full_photo_reset(true);
    }

    memset(
        document->photo_msg_id,
        0,
        sizeof(document->photo_msg_id)
    );

    media_chat_full_photo_open_when_done = save_and_open;

    DCInfo* preferred =
        media_chat_photo_preferred_dc(document);

    bool started = media_chat_full_photo_begin(
        document,
        preferred
    );

    if (!started)
        media_chat_full_photo_open_when_done = false;

    diag_log(
        "chat v78 photo action start dc=%d open=%d started=%d",
        preferred ? preferred->dc : -1,
        save_and_open ? 1 : 0,
        started ? 1 : 0
    );

    return started;
}

bool media_chat_full_photo_retry_migrated(
    Document* document,
    DCInfo* target_dc,
    const BYTE* failed_rpc_id
) {
    if (
        !document ||
        !target_dc ||
        !failed_rpc_id ||
        !media_chat_full_photo_active ||
        memcmp(
            failed_rpc_id,
            media_chat_full_photo_rpc_id,
            8
        ) != 0
    ) {
        return false;
    }

    bool restarted =
        media_chat_full_photo_begin(
            document,
            target_dc
        );

    diag_log(
        "chat v78 migrated user photo retry dc=%d restarted=%d",
        target_dc->dc,
        restarted ? 1 : 0
    );

    return restarted;
}


'''
s = s[:video_pos] + user_helper + s[video_pos:]

# Replace v7.5's double-click-only function with single-click upgrade and
# double-click save/open semantics.
photo_sig = "bool media_chat_photo_handle_chat_mouse("
ps, pe = function_range(s, photo_sig)

photo_handler = r'''bool media_chat_photo_handle_chat_mouse(
    HWND hWnd,
    UINT msg,
    WPARAM,
    LPARAM lParam
) {
    if (
        !chat ||
        hWnd != chat ||
        (
            msg != WM_LBUTTONDOWN &&
            msg != WM_LBUTTONDBLCLK
        )
    ) {
        return false;
    }

    POINT point = {
        GET_X_LPARAM(lParam),
        GET_Y_LPARAM(lParam)
    };

    LRESULT raw_hit = SendMessageW(
        chat,
        EM_CHARFROMPOS,
        0,
        (LPARAM)&point
    );

    int hit_char =
        raw_hit >= 0
            ? (int)raw_hit
            : -1;

    for (
        int i = (int)documents.size() - 1;
        i >= 0;
        i--
    ) {
        Document* document = &documents[i];

        if (
            !document->visible ||
            !document->file_reference ||
            document->photo_size == 0 ||
            document->photo_size == 1 ||
            document->photo_size == 3 ||
            document->max <= document->min
        ) {
            continue;
        }

        bool hit = false;

        if (hit_char >= 0) {
            for (int delta = -1; delta <= 1; delta++) {
                int candidate = hit_char + delta;

                if (
                    candidate >= document->min &&
                    candidate <= document->max
                ) {
                    hit = true;
                    break;
                }
            }
        }

        if (!hit) {
            POINTL origin = {0, 0};

            LRESULT pos_result = SendMessageW(
                chat,
                EM_POSFROMCHAR,
                (WPARAM)&origin,
                (LPARAM)document->min
            );

            if (pos_result != -1) {
                int effective_dpi =
                    dpi > 0
                        ? dpi
                        : 96;

                int card_width =
                    MulDiv(288, effective_dpi, 96);

                int card_height =
                    MulDiv(216, effective_dpi, 96);

                RECT card = {
                    (LONG)origin.x,
                    (LONG)origin.y,
                    (LONG)origin.x + card_width,
                    (LONG)origin.y + card_height
                };

                hit =
                    PtInRect(
                        &card,
                        point
                    ) != FALSE;
            }
        }

        if (!hit)
            continue;

        bool save_and_open =
            msg == WM_LBUTTONDBLCLK;

        bool started =
            media_chat_full_photo_user_action(
                document,
                save_and_open
            );

        diag_log(
            "chat v78 photo click index=%d char=%d range=%d..%d double=%d started=%d",
            i,
            hit_char,
            document->min,
            document->max,
            save_and_open ? 1 : 0,
            started ? 1 : 0
        );

        if (!started)
            MessageBeep(MB_ICONASTERISK);

        return true;
    }

    return false;
}'''

s = s[:ps] + photo_handler + s[pe:]

# On successful completion, replace the preview first, then persist/open the
# exact downloaded JPEG when the action came from a double click.
completion_anchor = "    media_chat_full_photo_reset(false);"
completion_pos = s.find(completion_anchor)
if completion_pos < 0:
    raise SystemExit("Could not locate full-photo completion reset.")

completion_extra = r'''    if (media_chat_full_photo_open_when_done) {
        if (!media_chat_full_photo_save_and_open())
            MessageBeep(MB_ICONASTERISK);
    }

'''
s = s[:completion_pos] + completion_extra + s[completion_pos:]

write(t, s)

# ---------------------------------------------------------------------------
# Resume the same serial click request after FILE_MIGRATE even for a public
# channel opened from "All chats". v7.7 deliberately bypasses the serial loader
# for automatic search-channel previews, so the generic get_photo() retry cannot
# be allowed to steal an explicit user-click transfer.
# ---------------------------------------------------------------------------
s = read(r)

response_decl_anchor = "bool media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length); // chat_media_full_photo_v64"
if response_decl_anchor not in s:
    raise SystemExit("Could not locate full-photo response declaration.")

retry_decl = (
    "\nbool media_chat_full_photo_retry_migrated("
    "Document* document, DCInfo* target_dc, const BYTE* failed_rpc_id"
    "); // chat_photo_click_download_v78"
)
s = s.replace(
    response_decl_anchor,
    response_decl_anchor + retry_decl,
    1,
)

rpc_case = s.find("case 0x2144ca19:")
if rpc_case < 0:
    raise SystemExit("Could not locate rpc_error case.")

retry_call = "get_photo(NULL, &documents[j], active_dc);"
retry_pos = s.find(retry_call, rpc_case)
if retry_pos < 0:
    raise SystemExit("Could not locate migrated document get_photo retry.")

retry_new = r'''if (
                                    !media_chat_full_photo_retry_migrated(
                                        &documents[j],
                                        active_dc,
                                        last_rpcresult_msgid
                                    )
                                ) {
                                    get_photo(
                                        NULL,
                                        &documents[j],
                                        active_dc
                                    );
                                }'''
s = s[:retry_pos] + retry_new + s[retry_pos + len(retry_call):]
write(r, s)

# ---------------------------------------------------------------------------
# Direct RichEdit interception: first click requests full quality; the generated
# WM_LBUTTONDBLCLK requests save+open. Photo handler excludes video thumbnails,
# so existing video double-click behavior is unaffected.
# ---------------------------------------------------------------------------
s = read(p)
old = r'''    // chat_photo_retry_dblclick_proc_v75
    if (
        msg == WM_LBUTTONDBLCLK &&
        media_chat_photo_handle_chat_mouse(
'''
new = r'''    // chat_photo_retry_dblclick_proc_v75
    // chat_photo_click_download_proc_v78
    if (
        (
            msg == WM_LBUTTONDOWN ||
            msg == WM_LBUTTONDBLCLK
        ) &&
        media_chat_photo_handle_chat_mouse(
'''
if old not in s:
    raise SystemExit("Could not locate v7.5 photo mouse interception.")
s = s.replace(old, new, 1)
write(p, s)

checks = {
    t: [
        "chat_photo_click_download_v78",
        "media_chat_full_photo_save_and_open()",
        "media_chat_full_photo_user_action(",
        "chat v78 photo click",
        "chat v78 photo saved/opened",
        "media_chat_full_photo_retry_migrated(",
    ],
    r: [
        "media_chat_full_photo_retry_migrated(",
        "last_rpcresult_msgid",
    ],
    p: [
        "chat_photo_click_download_proc_v78",
        "msg == WM_LBUTTONDOWN ||",
        "msg == WM_LBUTTONDBLCLK",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v7.8 verification failed in {path.name}: {token}")

print(
    "Applied chat photo click/download v7.8: a single click force-loads the "
    "full PhotoSize into the existing OLE card, a double click upgrades that "
    "same transfer into a persistent Pictures\\Telegacy JPEG download and opens "
    "it with the system image viewer, and explicit click transfers survive "
    "FILE_MIGRATE even for search-only public channels."
)
