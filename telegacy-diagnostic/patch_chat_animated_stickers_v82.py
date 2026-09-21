#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_animated_stickers_v82.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
m = root / "src" / "message.cpp"
r = root / "src" / "response.cpp"
t = root / "src" / "telegacy.cpp"
cmake = root / "CMakeLists.txt"
manifest = root / "vcpkg.json"

for path in (h, m, r, t, cmake, manifest):
    if not path.exists():
        raise SystemExit(f"Missing expected file: {path}")


def read(path):
    encoding = "utf-8" if path.suffix in (".json", ".txt") or path.name == "CMakeLists.txt" else "latin-1"
    return path.read_text(encoding=encoding)


def write(path, data):
    encoding = "utf-8" if path.suffix in (".json", ".txt") or path.name == "CMakeLists.txt" else "latin-1"
    newline = "\n" if encoding == "utf-8" else "\r\n"
    path.write_text(data, encoding=encoding, newline=newline)


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


if "chat_animated_stickers_v82" in read(t):
    print("Animated stickers v8.2 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_photo_open_sticker_viewport_v81", t),
    ("chat_media_ole_rebind_v80", t),
    ("media_tabs_av_runtime_v2", t),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

if "rlottie::rlottie" not in read(cmake):
    raise SystemExit("CMakeLists.txt does not link rlottie::rlottie.")
if '"rlottie"' not in read(manifest):
    raise SystemExit("vcpkg.json does not contain rlottie.")

# ---------------------------------------------------------------------------
# Shared declarations / rlottie include.
# ---------------------------------------------------------------------------
s = read(h)

if "#include <rlottie.h>" not in s:
    anchor = "#include <mfplay.h>"
    if anchor not in s:
        raise SystemExit("Could not locate mfplay include for rlottie insertion.")
    s = s.replace(anchor, anchor + "\n#include <rlottie.h>", 1)

decl_anchor = "bool media_chat_photo_handle_chat_mouse("
decl_pos = s.find(decl_anchor)
if decl_pos < 0:
    raise SystemExit("Could not locate chat photo declaration section.")

line_end = s.find("\n", decl_pos)
if line_end < 0:
    raise SystemExit("Could not locate declaration line end.")

decls = r'''
void media_chat_animated_sticker_queue(
    Document* document
); // chat_animated_stickers_v82
void media_chat_animated_sticker_download_complete(
    Document* document
); // chat_animated_stickers_v82
void media_chat_animated_sticker_clear(); // chat_animated_stickers_v82
'''

if "media_chat_animated_sticker_queue(" not in s:
    s = s[:line_end + 1] + decls + s[line_end + 1:]

write(h, s)

# ---------------------------------------------------------------------------
# Runtime: TGS via rlottie + WebM via MFPlay, rendered as child overlays above
# the existing RichEdit sticker placeholder. No RichEdit content is replaced
# every frame, so animation itself cannot move the chat viewport.
# ---------------------------------------------------------------------------
s = read(t)

marker = "// chat_photo_open_sticker_viewport_v81"
insert_at = s.find(marker)
if insert_at < 0:
    raise SystemExit("Could not locate v8.1 runtime marker.")

insert_at = s.find("\n", insert_at)
if insert_at < 0:
    raise SystemExit("Could not locate v8.1 marker line end.")
insert_at += 1

runtime = r'''
// chat_animated_stickers_v82
struct ChatAnimatedSticker {
    BYTE id[8];
    BYTE access_hash[8];
    int anchor_min;
    int kind; // 1 = TGS/Lottie, 2 = WebM/video sticker
    wchar_t path[MAX_PATH];

    HWND window;
    rlottie::Animation* lottie;
    IMFPMediaPlayer* video;

    std::vector<unsigned int> pixels;
    size_t frame;
    size_t total_frames;
    double fps;
    DWORD next_frame_tick;

    bool visible;
    bool video_paused_for_visibility;
};

static std::vector<ChatAnimatedSticker*> media_chat_animated_stickers;
static UINT_PTR media_chat_sticker_timer = 0;
static bool media_chat_sticker_class_registered = false;
static const wchar_t* MEDIA_CHAT_STICKER_CLASS =
    L"TelegacyAnimatedSticker82";

static int media_chat_sticker_kind_from_filename(
    const wchar_t* filename
) {
    if (!filename || !filename[0])
        return 0;

    const wchar_t* dot =
        wcsrchr(filename, L'.');

    if (!dot)
        return 0;

    if (_wcsicmp(dot, L".webm") == 0)
        return 2;

    if (
        _wcsicmp(dot, L".tgs") == 0 ||
        _wcsicmp(dot, L".x-tgsticker") == 0
    ) {
        return 1;
    }

    return 0;
}

static bool media_chat_sticker_same_document(
    const Document* document,
    const ChatAnimatedSticker* sticker
) {
    return
        document &&
        sticker &&
        document->visible &&
        document->photo_size == 1 &&
        memcmp(document->id, sticker->id, 8) == 0 &&
        memcmp(document->access_hash, sticker->access_hash, 8) == 0;
}

static Document* media_chat_sticker_find_document(
    ChatAnimatedSticker* sticker
) {
    if (!sticker)
        return NULL;

    Document* best = NULL;
    int best_distance = INT_MAX;

    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        if (
            !media_chat_sticker_same_document(
                &documents[i],
                sticker
            )
        ) {
            continue;
        }

        int distance =
            documents[i].min >= sticker->anchor_min
                ? documents[i].min - sticker->anchor_min
                : sticker->anchor_min - documents[i].min;

        if (distance < best_distance) {
            best_distance = distance;
            best = &documents[i];
        }
    }

    if (best)
        sticker->anchor_min = best->min;

    return best;
}

static int media_chat_sticker_card_width() {
    int effective_dpi =
        dpi > 0
            ? dpi
            : 96;

    return MulDiv(
        288,
        effective_dpi,
        96
    );
}

static int media_chat_sticker_card_height() {
    int effective_dpi =
        dpi > 0
            ? dpi
            : 96;

    return MulDiv(
        216,
        effective_dpi,
        96
    );
}

static LRESULT CALLBACK media_chat_sticker_window_proc(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    ChatAnimatedSticker* sticker =
        (ChatAnimatedSticker*)GetWindowLongPtrW(
            hwnd,
            GWLP_USERDATA
        );

    if (msg == WM_NCCREATE) {
        CREATESTRUCTW* create =
            (CREATESTRUCTW*)lParam;

        sticker =
            (ChatAnimatedSticker*)create->lpCreateParams;

        SetWindowLongPtrW(
            hwnd,
            GWLP_USERDATA,
            (LONG_PTR)sticker
        );
    }

    if (msg == WM_NCHITTEST)
        return HTTRANSPARENT;

    if (msg == WM_ERASEBKGND)
        return 1;

    if (msg == WM_PAINT) {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hwnd, &ps);

        RECT rc = {0};
        GetClientRect(hwnd, &rc);

        if (
            sticker &&
            sticker->kind == 1 &&
            !sticker->pixels.empty()
        ) {
            BITMAPINFO info;
            memset(
                &info,
                0,
                sizeof(info)
            );

            info.bmiHeader.biSize =
                sizeof(BITMAPINFOHEADER);
            info.bmiHeader.biWidth =
                media_chat_sticker_card_width();
            info.bmiHeader.biHeight =
                -media_chat_sticker_card_height();
            info.bmiHeader.biPlanes = 1;
            info.bmiHeader.biBitCount = 32;
            info.bmiHeader.biCompression = BI_RGB;

            StretchDIBits(
                dc,
                0,
                0,
                rc.right - rc.left,
                rc.bottom - rc.top,
                0,
                0,
                media_chat_sticker_card_width(),
                media_chat_sticker_card_height(),
                &sticker->pixels[0],
                &info,
                DIB_RGB_COLORS,
                SRCCOPY
            );
        } else if (
            !sticker ||
            sticker->kind != 2 ||
            !sticker->video
        ) {
            FillRect(
                dc,
                &rc,
                GetSysColorBrush(COLOR_WINDOW)
            );
        }

        EndPaint(hwnd, &ps);
        return 0;
    }

    return DefWindowProcW(
        hwnd,
        msg,
        wParam,
        lParam
    );
}

static bool media_chat_sticker_register_class() {
    if (media_chat_sticker_class_registered)
        return true;

    WNDCLASSEXW wc;
    memset(&wc, 0, sizeof(wc));

    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc =
        media_chat_sticker_window_proc;
    wc.hInstance =
        GetModuleHandleW(NULL);
    wc.hCursor =
        LoadCursorW(NULL, IDC_ARROW);
    wc.hbrBackground =
        GetSysColorBrush(COLOR_WINDOW);
    wc.lpszClassName =
        MEDIA_CHAT_STICKER_CLASS;

    ATOM atom =
        RegisterClassExW(&wc);

    if (
        !atom &&
        GetLastError() !=
            ERROR_CLASS_ALREADY_EXISTS
    ) {
        diag_log(
            "chat v82 sticker window class registration failed error=%u",
            (unsigned int)GetLastError()
        );
        return false;
    }

    media_chat_sticker_class_registered = true;
    return true;
}

static bool media_chat_sticker_read_file(
    const wchar_t* path,
    std::vector<BYTE>* bytes
) {
    if (!path || !bytes)
        return false;

    bytes->clear();

    FILE* file =
        _wfopen(path, L"rb");

    if (!file)
        return false;

    _fseeki64(file, 0, SEEK_END);
    __int64 size = _ftelli64(file);
    _fseeki64(file, 0, SEEK_SET);

    if (
        size <= 0 ||
        size > 16 * 1024 * 1024
    ) {
        fclose(file);
        return false;
    }

    bytes->resize((size_t)size);

    size_t got =
        fread(
            &(*bytes)[0],
            1,
            (size_t)size,
            file
        );

    fclose(file);

    if (got != (size_t)size) {
        bytes->clear();
        return false;
    }

    return true;
}

static bool media_chat_sticker_gzip_json(
    const wchar_t* path,
    std::string* json
) {
    if (!json)
        return false;

    json->clear();

    std::vector<BYTE> compressed;

    if (
        !media_chat_sticker_read_file(
            path,
            &compressed
        )
    ) {
        return false;
    }

    if (
        compressed.size() >= 2 &&
        compressed[0] == '{'
    ) {
        json->assign(
            (const char*)&compressed[0],
            compressed.size()
        );
        return true;
    }

    if (
        compressed.size() < 18 ||
        compressed[0] != 0x1F ||
        compressed[1] != 0x8B ||
        compressed[2] != 8
    ) {
        return false;
    }

    int flags = compressed[3];
    size_t pos = 10;

    if (flags & 0x04) {
        if (pos + 2 > compressed.size())
            return false;

        size_t extra =
            compressed[pos] |
            ((size_t)compressed[pos + 1] << 8);

        pos += 2 + extra;
    }

    if (flags & 0x08) {
        while (
            pos < compressed.size() &&
            compressed[pos] != 0
        ) {
            pos++;
        }
        pos++;
    }

    if (flags & 0x10) {
        while (
            pos < compressed.size() &&
            compressed[pos] != 0
        ) {
            pos++;
        }
        pos++;
    }

    if (flags & 0x02)
        pos += 2;

    if (
        pos >= compressed.size() ||
        compressed.size() < pos + 8
    ) {
        return false;
    }

    size_t deflate_size =
        compressed.size() -
        pos -
        8;

    size_t out_size = 0;

    void* out =
        tinfl_decompress_mem_to_heap(
            &compressed[pos],
            deflate_size,
            &out_size,
            0
        );

    if (!out || out_size == 0) {
        if (out)
            mz_free(out);
        return false;
    }

    json->assign(
        (const char*)out,
        out_size
    );

    mz_free(out);
    return true;
}

static bool media_chat_sticker_create_window(
    ChatAnimatedSticker* sticker
) {
    if (
        !sticker ||
        !chat ||
        !media_chat_sticker_register_class()
    ) {
        return false;
    }

    if (sticker->window)
        return true;

    sticker->window =
        CreateWindowExW(
            WS_EX_NOPARENTNOTIFY,
            MEDIA_CHAT_STICKER_CLASS,
            L"",
            WS_CHILD |
                WS_CLIPSIBLINGS |
                WS_CLIPCHILDREN,
            0,
            0,
            media_chat_sticker_card_width(),
            media_chat_sticker_card_height(),
            chat,
            NULL,
            GetModuleHandleW(NULL),
            sticker
        );

    return sticker->window != NULL;
}

static bool media_chat_sticker_load_lottie(
    ChatAnimatedSticker* sticker
) {
    if (
        !sticker ||
        sticker->kind != 1
    ) {
        return false;
    }

    if (sticker->lottie)
        return true;

    std::string json;

    if (
        !media_chat_sticker_gzip_json(
            sticker->path,
            &json
        )
    ) {
        diag_log(
            "chat v82 TGS gzip decode failed path=%ls",
            sticker->path
        );
        return false;
    }

    char key[80] = {0};

    _snprintf(
        key,
        sizeof(key) - 1,
        "telegacy-%016I64X-%d",
        (unsigned __int64)read_le(sticker->id, 8),
        sticker->anchor_min
    );

    std::unique_ptr<rlottie::Animation> animation =
        rlottie::Animation::loadFromData(
            json,
            key
        );

    if (!animation) {
        diag_log(
            "chat v82 rlottie load failed path=%ls",
            sticker->path
        );
        return false;
    }

    sticker->lottie =
        animation.release();

    sticker->total_frames =
        sticker->lottie->totalFrame();

    sticker->fps =
        sticker->lottie->frameRate();

    if (
        sticker->total_frames == 0 ||
        sticker->fps <= 0.0
    ) {
        delete sticker->lottie;
        sticker->lottie = NULL;
        return false;
    }

    if (sticker->fps > 30.0)
        sticker->fps = 30.0;

    sticker->frame = 0;
    sticker->next_frame_tick = 0;

    sticker->pixels.assign(
        media_chat_sticker_card_width() *
            media_chat_sticker_card_height(),
        0
    );

    diag_log(
        "chat v82 TGS ready frames=%Iu fps=%.2f path=%ls",
        sticker->total_frames,
        sticker->fps,
        sticker->path
    );

    return true;
}

static bool media_chat_sticker_load_video(
    ChatAnimatedSticker* sticker
) {
    if (
        !sticker ||
        sticker->kind != 2 ||
        !sticker->window
    ) {
        return false;
    }

    if (sticker->video)
        return true;

    CoInitialize(NULL);

    HRESULT hr =
        MFPCreateMediaPlayer(
            NULL,
            FALSE,
            MFP_OPTION_NONE,
            NULL,
            sticker->window,
            &sticker->video
        );

    if (
        FAILED(hr) ||
        !sticker->video
    ) {
        sticker->video = NULL;

        diag_log(
            "chat v82 WebM player create failed hr=0x%08X path=%ls",
            (unsigned int)hr,
            sticker->path
        );
        return false;
    }

    IMFPMediaItem* item = NULL;

    hr =
        sticker->video->CreateMediaItemFromURL(
            sticker->path,
            TRUE,
            0,
            &item
        );

    if (
        SUCCEEDED(hr) &&
        item
    ) {
        hr =
            sticker->video->SetMediaItem(item);
    }

    if (item)
        item->Release();

    if (FAILED(hr)) {
        sticker->video->Shutdown();
        sticker->video->Release();
        sticker->video = NULL;

        diag_log(
            "chat v82 WebM media item failed hr=0x%08X path=%ls",
            (unsigned int)hr,
            sticker->path
        );
        return false;
    }

    sticker->video->SetVolume(0.0f);
    hr = sticker->video->Play();

    diag_log(
        "chat v82 WebM inline play hr=0x%08X path=%ls",
        (unsigned int)hr,
        sticker->path
    );

    return SUCCEEDED(hr);
}

static void media_chat_sticker_render_lottie(
    ChatAnimatedSticker* sticker,
    DWORD now
) {
    if (
        !sticker ||
        !sticker->lottie ||
        !sticker->window ||
        sticker->pixels.empty()
    ) {
        return;
    }

    if (
        sticker->next_frame_tick &&
        (LONG)(now - sticker->next_frame_tick) < 0
    ) {
        return;
    }

    int width =
        media_chat_sticker_card_width();

    int height =
        media_chat_sticker_card_height();

    rlottie::Surface surface(
        &sticker->pixels[0],
        width,
        height,
        width * 4
    );

    sticker->lottie->renderSync(
        sticker->frame,
        surface,
        true
    );

    COLORREF background =
        GetSysColor(COLOR_WINDOW);

    unsigned int bg_r =
        GetRValue(background);
    unsigned int bg_g =
        GetGValue(background);
    unsigned int bg_b =
        GetBValue(background);

    for (
        size_t i = 0;
        i < sticker->pixels.size();
        i++
    ) {
        unsigned int pixel =
            sticker->pixels[i];

        unsigned int alpha =
            (pixel >> 24) & 0xFF;
        unsigned int red =
            (pixel >> 16) & 0xFF;
        unsigned int green =
            (pixel >> 8) & 0xFF;
        unsigned int blue =
            pixel & 0xFF;

        unsigned int inv =
            255 - alpha;

        red +=
            bg_r * inv / 255;
        green +=
            bg_g * inv / 255;
        blue +=
            bg_b * inv / 255;

        if (red > 255) red = 255;
        if (green > 255) green = 255;
        if (blue > 255) blue = 255;

        sticker->pixels[i] =
            (red << 16) |
            (green << 8) |
            blue;
    }

    sticker->frame =
        (sticker->frame + 1) %
        sticker->total_frames;

    int interval =
        (int)(1000.0 / sticker->fps);

    if (interval < 16)
        interval = 16;

    sticker->next_frame_tick =
        now + interval;

    InvalidateRect(
        sticker->window,
        NULL,
        FALSE
    );
}

static void media_chat_sticker_loop_video(
    ChatAnimatedSticker* sticker
) {
    if (
        !sticker ||
        !sticker->video
    ) {
        return;
    }

    MFP_MEDIAPLAYER_STATE state =
        MFP_MEDIAPLAYER_STATE_EMPTY;

    if (
        FAILED(
            sticker->video->GetState(
                &state
            )
        )
    ) {
        return;
    }

    PROPVARIANT position = {0};
    PROPVARIANT duration = {0};

    bool have_position =
        SUCCEEDED(
            sticker->video->GetPosition(
                MFP_POSITIONTYPE_100NS,
                &position
            )
        ) &&
        position.vt == VT_I8;

    bool have_duration =
        SUCCEEDED(
            sticker->video->GetDuration(
                MFP_POSITIONTYPE_100NS,
                &duration
            )
        ) &&
        duration.vt == VT_I8 &&
        duration.hVal.QuadPart > 0;

    bool at_end =
        have_position &&
        have_duration &&
        position.hVal.QuadPart >=
            duration.hVal.QuadPart -
            150000LL;

    if (
        state == MFP_MEDIAPLAYER_STATE_STOPPED ||
        at_end
    ) {
        PROPVARIANT zero = {0};
        zero.vt = VT_I8;
        zero.hVal.QuadPart = 0;

        sticker->video->SetPosition(
            MFP_POSITIONTYPE_100NS,
            &zero
        );

        sticker->video->Play();
    }
}

static VOID CALLBACK media_chat_sticker_timer_proc(
    HWND,
    UINT,
    UINT_PTR,
    DWORD
) {
    if (
        !chat ||
        media_chat_animated_stickers.empty()
    ) {
        return;
    }

    RECT client = {0};
    GetClientRect(chat, &client);

    DWORD now =
        GetTickCount();

    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {
        ChatAnimatedSticker* sticker =
            media_chat_animated_stickers[i];

        if (!sticker)
            continue;

        Document* document =
            media_chat_sticker_find_document(
                sticker
            );

        if (
            !document ||
            document->max <= document->min
        ) {
            if (sticker->window)
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );

            sticker->visible = false;
            continue;
        }

        POINTL origin = {0, 0};

        LRESULT result =
            SendMessageW(
                chat,
                EM_POSFROMCHAR,
                (WPARAM)&origin,
                (LPARAM)document->min
            );

        int width =
            media_chat_sticker_card_width();

        int height =
            media_chat_sticker_card_height();

        bool in_view =
            result != -1 &&
            origin.y < client.bottom &&
            origin.y + height > client.top &&
            origin.x < client.right &&
            origin.x + width > client.left;

        if (!in_view) {
            if (sticker->window)
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );

            if (
                sticker->video &&
                !sticker->video_paused_for_visibility
            ) {
                MFP_MEDIAPLAYER_STATE state =
                    MFP_MEDIAPLAYER_STATE_EMPTY;

                if (
                    SUCCEEDED(
                        sticker->video->GetState(
                            &state
                        )
                    ) &&
                    state ==
                        MFP_MEDIAPLAYER_STATE_PLAYING
                ) {
                    sticker->video->Pause();
                    sticker->video_paused_for_visibility = true;
                }
            }

            sticker->visible = false;
            continue;
        }

        if (
            !media_chat_sticker_create_window(
                sticker
            )
        ) {
            continue;
        }

        SetWindowPos(
            sticker->window,
            HWND_TOP,
            origin.x,
            origin.y,
            width,
            height,
            SWP_NOACTIVATE |
                SWP_SHOWWINDOW
        );

        sticker->visible = true;

        if (sticker->kind == 1) {
            if (
                media_chat_sticker_load_lottie(
                    sticker
                )
            ) {
                media_chat_sticker_render_lottie(
                    sticker,
                    now
                );
            }
        } else if (sticker->kind == 2) {
            if (
                media_chat_sticker_load_video(
                    sticker
                )
            ) {
                if (
                    sticker->video_paused_for_visibility
                ) {
                    sticker->video->Play();
                    sticker->video_paused_for_visibility = false;
                }

                media_chat_sticker_loop_video(
                    sticker
                );
            }
        }
    }
}

static void media_chat_sticker_start_timer() {
    if (media_chat_sticker_timer)
        return;

    media_chat_sticker_timer =
        SetTimer(
            NULL,
            0,
            33,
            media_chat_sticker_timer_proc
        );
}

static void media_chat_sticker_destroy(
    ChatAnimatedSticker* sticker
) {
    if (!sticker)
        return;

    if (sticker->video) {
        sticker->video->Stop();
        sticker->video->Shutdown();
        sticker->video->Release();
        sticker->video = NULL;
    }

    if (sticker->window) {
        DestroyWindow(
            sticker->window
        );
        sticker->window = NULL;
    }

    if (sticker->lottie) {
        delete sticker->lottie;
        sticker->lottie = NULL;
    }

    delete sticker;
}

void media_chat_animated_sticker_clear() {
    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {
        media_chat_sticker_destroy(
            media_chat_animated_stickers[i]
        );
    }

    media_chat_animated_stickers.clear();

    if (media_chat_sticker_timer) {
        KillTimer(
            NULL,
            media_chat_sticker_timer
        );
        media_chat_sticker_timer = 0;
    }

    diag_log(
        "chat v82 animated sticker runtime cleared"
    );
}

static bool media_chat_sticker_runtime_exists(
    const Document* document
) {
    if (!document)
        return true;

    for (
        int i = 0;
        i < (int)media_chat_animated_stickers.size();
        i++
    ) {
        ChatAnimatedSticker* sticker =
            media_chat_animated_stickers[i];

        if (
            sticker &&
            memcmp(
                sticker->id,
                document->id,
                8
            ) == 0 &&
            memcmp(
                sticker->access_hash,
                document->access_hash,
                8
            ) == 0 &&
            (
                sticker->anchor_min ==
                    document->min ||
                abs(
                    sticker->anchor_min -
                    document->min
                ) <= 2
            )
        ) {
            return true;
        }
    }

    return false;
}

static void media_chat_sticker_activate(
    Document* document,
    const wchar_t* path
) {
    if (
        !document ||
        !path ||
        !path[0] ||
        document->photo_size != 1 ||
        media_chat_sticker_runtime_exists(
            document
        )
    ) {
        return;
    }

    int kind =
        media_chat_sticker_kind_from_filename(
            path
        );

    if (!kind)
        return;

    ChatAnimatedSticker* sticker =
        new ChatAnimatedSticker();

    memset(
        sticker,
        0,
        sizeof(ChatAnimatedSticker)
    );

    memcpy(
        sticker->id,
        document->id,
        8
    );

    memcpy(
        sticker->access_hash,
        document->access_hash,
        8
    );

    sticker->anchor_min =
        document->min;

    sticker->kind = kind;

    wcsncpy(
        sticker->path,
        path,
        ARRAYSIZE(sticker->path) - 1
    );

    sticker->path[
        ARRAYSIZE(sticker->path) - 1
    ] = 0;

    media_chat_animated_stickers.push_back(
        sticker
    );

    media_chat_sticker_start_timer();

    diag_log(
        "chat v82 animated sticker activated kind=%d min=%d path=%ls",
        kind,
        document->min,
        path
    );
}

static void media_chat_sticker_activate_matching_documents(
    const Document* downloaded
) {
    if (!downloaded || !downloaded->filename)
        return;

    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        if (
            documents[i].visible &&
            documents[i].photo_size == 1 &&
            memcmp(
                documents[i].id,
                downloaded->id,
                8
            ) == 0 &&
            memcmp(
                documents[i].access_hash,
                downloaded->access_hash,
                8
            ) == 0
        ) {
            media_chat_sticker_activate(
                &documents[i],
                downloaded->filename
            );
        }
    }
}

static bool media_chat_sticker_cache_path(
    const Document* document,
    int kind,
    wchar_t* out,
    int out_count
) {
    if (
        !document ||
        !out ||
        out_count < 32 ||
        !appdata_path[0]
    ) {
        return false;
    }

    wchar_t folder[MAX_PATH] = {0};

    _snwprintf(
        folder,
        ARRAYSIZE(folder) - 1,
        L"%s\\animated_stickers",
        appdata_path
    );

    folder[
        ARRAYSIZE(folder) - 1
    ] = 0;

    CreateDirectoryW(
        folder,
        NULL
    );

    const wchar_t* extension =
        kind == 2
            ? L".webm"
            : L".tgs";

    _snwprintf(
        out,
        out_count - 1,
        L"%s\\%016I64X%s",
        folder,
        (unsigned __int64)read_le(
            (BYTE*)document->id,
            8
        ),
        extension
    );

    out[out_count - 1] = 0;
    return true;
}

static bool media_chat_sticker_file_complete(
    const wchar_t* path,
    __int64 expected
) {
    if (!path || !path[0])
        return false;

    WIN32_FILE_ATTRIBUTE_DATA data;

    if (
        !GetFileAttributesExW(
            path,
            GetFileExInfoStandard,
            &data
        )
    ) {
        return false;
    }

    ULARGE_INTEGER size;
    size.LowPart =
        data.nFileSizeLow;
    size.HighPart =
        data.nFileSizeHigh;

    return
        size.QuadPart > 0 &&
        (
            expected <= 0 ||
            size.QuadPart ==
                (unsigned __int64)expected
        );
}

void media_chat_animated_sticker_queue(
    Document* document
) {
    if (
        !document ||
        !document->visible ||
        document->photo_size != 1 ||
        !document->filename ||
        !document->file_reference
    ) {
        return;
    }

    int kind =
        media_chat_sticker_kind_from_filename(
            document->filename
        );

    if (!kind)
        return;

    wchar_t cache_path[MAX_PATH] = {0};

    if (
        !media_chat_sticker_cache_path(
            document,
            kind,
            cache_path,
            ARRAYSIZE(cache_path)
        )
    ) {
        return;
    }

    if (
        media_chat_sticker_file_complete(
            cache_path,
            document->size
        )
    ) {
        media_chat_sticker_activate(
            document,
            cache_path
        );
        return;
    }

    for (
        int i = 0;
        i < (int)downloading_docs.size();
        i++
    ) {
        if (
            memcmp(
                downloading_docs[i].id,
                document->id,
                8
            ) == 0 &&
            downloading_docs[i].filename &&
            _wcsicmp(
                downloading_docs[i].filename,
                cache_path
            ) == 0
        ) {
            return;
        }
    }

    DeleteFileW(cache_path);

    Document copy =
        *document;

    copy.min = 0;
    copy.max = 0;
    copy.photo_size = 0;
    copy.visible = false;

    copy.filename =
        _wcsdup(cache_path);

    int file_reference_length =
        tlstr_len(
            document->file_reference,
            true
        );

    copy.file_reference = NULL;

    if (file_reference_length > 0) {
        copy.file_reference =
            (BYTE*)malloc(
                file_reference_length
            );

        if (copy.file_reference) {
            memcpy(
                copy.file_reference,
                document->file_reference,
                file_reference_length
            );
        }
    }

    if (
        !copy.filename ||
        !copy.file_reference
    ) {
        free(copy.filename);
        free(copy.file_reference);
        return;
    }

    downloading_docs.push_back(copy);

    download_file(
        &dcInfoMain,
        &downloading_docs.back()
    );

    diag_log(
        "chat v82 animated sticker download queued kind=%d bytes=%I64d path=%ls",
        kind,
        document->size,
        cache_path
    );
}

void media_chat_animated_sticker_download_complete(
    Document* document
) {
    if (
        !document ||
        !document->filename
    ) {
        return;
    }

    int kind =
        media_chat_sticker_kind_from_filename(
            document->filename
        );

    if (!kind)
        return;

    bool matching_sticker = false;

    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        if (
            documents[i].photo_size == 1 &&
            memcmp(
                documents[i].id,
                document->id,
                8
            ) == 0 &&
            memcmp(
                documents[i].access_hash,
                document->access_hash,
                8
            ) == 0
        ) {
            matching_sticker = true;
            break;
        }
    }

    if (!matching_sticker)
        return;

    diag_log(
        "chat v82 animated sticker download complete kind=%d path=%ls",
        kind,
        document->filename
    );

    media_chat_sticker_activate_matching_documents(
        document
    );
}

'''

s = s[:insert_at] + runtime + s[insert_at:]

# Clear overlays immediately on a peer switch.
peer_assign = "\t\t\tcurrent_peer = selected_peer;"
if peer_assign not in s:
    raise SystemExit("Could not locate selected_peer assignment for sticker cleanup.")

peer_cleanup = r'''			if (
				current_peer != selected_peer
			) {
				media_chat_animated_sticker_clear();
			}

			current_peer = selected_peer;'''.replace("\\t", "\t")

s = s.replace(peer_assign, peer_cleanup, 1)

# Context/media jumps also clear and rebuild the chat.
clear_sig = "void message_search_clear_chat_view()"
if clear_sig in s:
    cs, ce = function_range(s, clear_sig)
    clear_func = s[cs:ce]
    brace = clear_func.find("{")
    if brace >= 0 and "media_chat_animated_sticker_clear();" not in clear_func:
        clear_func = (
            clear_func[:brace + 1] +
            "\n    media_chat_animated_sticker_clear();\n" +
            clear_func[brace + 1:]
        )
        s = s[:cs] + clear_func + s[ce:]

write(t, s)

# ---------------------------------------------------------------------------
# Queue animated sticker original documents after the message Document has been
# committed into the global deque. Static WebP stickers are ignored.
# ---------------------------------------------------------------------------
s = read(m)

tail_anchor = "\tif (!chat_member_found && msg_bytes - chat_member_id != 16) free(sender);"
if tail_anchor not in s:
    raise SystemExit("Could not locate message_handler tail for sticker queue.")

queue_call = r'''	if (
		added_doc &&
		document.visible &&
		document.photo_size == 1
	) {
		media_chat_animated_sticker_queue(
			&document
		);
	}

'''.replace("\\t", "\t")

s = s.replace(
    tail_anchor,
    queue_call + tail_anchor,
    1
)

write(m, s)

# ---------------------------------------------------------------------------
# Generic document download completion already routes Media/video callbacks.
# Add animated-sticker activation while the completed DownloadingDocument still
# owns its filename/id/access_hash fields.
# ---------------------------------------------------------------------------
s = read(r)

completion_anchor = "media_player_chat_download_complete(downloading_docs[i].filename);"
if completion_anchor not in s:
    raise SystemExit("Could not locate chat document download completion callback.")

if "media_chat_animated_sticker_download_complete(&downloading_docs[i]);" not in s:
    pos = s.find(completion_anchor)
    line_start = s.rfind("\n", 0, pos) + 1
    indent = s[line_start:pos]

    insertion = (
        completion_anchor +
        "\n" +
        indent +
        "media_chat_animated_sticker_download_complete(&downloading_docs[i]);"
    )

    s = (
        s[:pos] +
        insertion +
        s[pos + len(completion_anchor):]
    )

write(r, s)

checks = {
    h: [
        "#include <rlottie.h>",
        "media_chat_animated_sticker_queue(",
        "media_chat_animated_sticker_download_complete(",
        "media_chat_animated_sticker_clear()",
    ],
    m: [
        "media_chat_animated_sticker_queue(",
        "document.photo_size == 1",
    ],
    r: [
        "media_chat_animated_sticker_download_complete(&downloading_docs[i])",
    ],
    t: [
        "chat_animated_stickers_v82",
        "rlottie::Animation::loadFromData",
        "MFPCreateMediaPlayer(",
        "chat v82 TGS ready",
        "chat v82 WebM inline play",
        "chat v82 animated sticker download queued",
        "media_chat_sticker_timer_proc",
        "HTTRANSPARENT",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v8.2 verification failed in {path.name}: {token}")

print(
    "Applied animated stickers v8.2: TGS stickers render inline through rlottie, "
    "WebM video stickers play inline through MFPlay, both loop in child overlays "
    "anchored to the RichEdit sticker object without replacing chat text each "
    "frame, originals are cached/downloaded automatically, and off-screen "
    "animations are hidden/paused."
)
