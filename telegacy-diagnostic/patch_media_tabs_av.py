#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_media_tabs_av.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for p in (h, t, r):
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


def replace_function(source, signature, replacement):
    start, end = function_range(source, signature)
    return source[:start] + replacement + source[end:]


# =============================================================================
# include/telegacy.h - DirectShow + cross-file Media hooks
# =============================================================================

s = read(h)

if "media_tabs_av_v1" not in s:
    include_anchor = "#include <ddeml.h>"
    if include_anchor not in s:
        raise SystemExit("Could not locate ddeml.h include in telegacy.h")

    s = s.replace(
        include_anchor,
        include_anchor
        + "\n#include <dshow.h>"
        + "\n#pragma comment(lib, \"strmiids.lib\")"
        + "\n// media_tabs_av_v1",
        1
    )

    decl_anchor = "void media_archive_start_next_download();"
    if decl_anchor not in s:
        raise SystemExit(
            "Could not locate Media declarations. "
            "Run the existing Media patches first."
        )

    decls = r'''

// Three-tab Media browser / built-in A/V player.
extern int media_archive_kind; // 0 images, 1 video, 2 music

void media_archive_add_av_document(
    Document* document,
    int message_id,
    int kind,
    const wchar_t* display_name,
    int duration
);

void media_archive_av_download_complete(
    const wchar_t* path
);

void media_archive_finish_av_page();
'''

    s = s.replace(decl_anchor, decl_anchor + decls, 1)

write(h, s)

# Make the DirectShow GUID library explicit for CMake-based diagnostic builds.
cmake = root / "CMakeLists.txt"
if cmake.exists():
    cm = cmake.read_text(encoding="utf-8")

    if "strmiids" not in cm.lower():
        link_anchor = "    ole32\\n"

        if link_anchor in cm:
            cm = cm.replace(
                link_anchor,
                link_anchor + "    strmiids\\n",
                1
            )

            cmake.write_text(
                cm,
                encoding="utf-8",
                newline="\\n"
            )


# =============================================================================
# src/telegacy.cpp - tabs, filter selection, A/V items and DirectShow player
# =============================================================================

s = read(t)

if "media_tabs_av_runtime_v1" in s:
    print("Media tabs/A-V runtime patch already applied.")
    raise SystemExit(0)

if "media_archive_direct_photo_parser_v1" not in s:
    raise SystemExit(
        "Direct safe photo parser is not present. "
        "Run patch_media_direct_photo_parser.py before this patch."
    )

old_struct = r'''struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    int page_index;
    HBITMAP bitmap;
    wchar_t file_path[MAX_PATH];
};'''

new_struct = r'''struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    int page_index;
    HBITMAP bitmap;
    wchar_t file_path[MAX_PATH];

    // media_tabs_av_runtime_v1
    int media_kind;        // 0 image, 1 video, 2 music
    int duration;
    bool has_document;
    Document av_document;
    wchar_t display_name[260];
};'''

if old_struct not in s:
    raise SystemExit("Could not locate MediaArchiveItem layout.")

s = s.replace(old_struct, new_struct, 1)

add_start, add_end = function_range(s, "void media_archive_add_document(")
add_func = s[add_start:add_end]

if "MediaArchiveItem item = {0};" not in add_func:
    if "MediaArchiveItem item;" not in add_func:
        raise SystemExit("Could not locate MediaArchiveItem construction.")
    add_func = add_func.replace(
        "MediaArchiveItem item;",
        "MediaArchiveItem item = {0};",
        1
    )

needle = "    item.document_id =\n        document_id;"
if needle in add_func and "item.media_kind = 0;" not in add_func:
    add_func = add_func.replace(
        needle,
        needle + "\n\n    item.media_kind = 0;",
        1
    )

s = s[:add_start] + add_func + s[add_end:]

anchor = "static void media_archive_update_nav()"
pos = s.find(anchor)

if pos < 0:
    raise SystemExit("Could not locate media_archive_update_nav().")

runtime = r'''
// ======================================================================================
// Three-tab Media browser + Windows 98 / ActiveMovie-style DirectShow player
// ======================================================================================

int media_archive_kind = 0;

static HWND hMediaArchiveTabs = NULL;

static HWND hMediaPlayerWindow = NULL;
static HWND hMediaPlayerVideoHost = NULL;
static HWND hMediaPlayerInfo = NULL;
static HWND hMediaPlayerPlay = NULL;
static HWND hMediaPlayerPause = NULL;
static HWND hMediaPlayerStop = NULL;
static HWND hMediaPlayerSeek = NULL;
static HWND hMediaPlayerVolume = NULL;
static HWND hMediaPlayerTime = NULL;

static IGraphBuilder* media_player_graph = NULL;
static IMediaControl* media_player_control = NULL;
static IMediaSeeking* media_player_seeking = NULL;
static IBasicAudio* media_player_audio = NULL;
static IVideoWindow* media_player_video = NULL;

static bool media_player_is_video = false;
static bool media_player_user_seeking = false;
static const UINT_PTR MEDIA_PLAYER_TIMER = 93;

static int media_av_pending_item = -1;
static wchar_t media_av_pending_path[MAX_PATH] = {0};

static bool media_archive_request_server_page(
    int offset_id
);

static unsigned int media_archive_filter_constructor() {
    if (media_archive_kind == 1)
        return 0x9fc00e65; // inputMessagesFilterVideo

    if (media_archive_kind == 2)
        return 0x3751b49e; // inputMessagesFilterMusic

    return 0x9609a51c; // inputMessagesFilterPhotos
}

static void media_player_release_graph() {
    if (media_player_control)
        media_player_control->Stop();

    if (media_player_video) {
        media_player_video->put_Visible(OAFALSE);
        media_player_video->put_Owner((OAHWND)NULL);
        media_player_video->Release();
        media_player_video = NULL;
    }

    if (media_player_audio) {
        media_player_audio->Release();
        media_player_audio = NULL;
    }

    if (media_player_seeking) {
        media_player_seeking->Release();
        media_player_seeking = NULL;
    }

    if (media_player_control) {
        media_player_control->Release();
        media_player_control = NULL;
    }

    if (media_player_graph) {
        media_player_graph->Release();
        media_player_graph = NULL;
    }
}

static void media_player_format_time(
    LONGLONG value,
    wchar_t* out,
    int out_count
) {
    if (!out || out_count < 8)
        return;

    LONGLONG seconds =
        value / 10000000LL;

    int hours =
        (int)(seconds / 3600);

    int minutes =
        (int)((seconds / 60) % 60);

    int secs =
        (int)(seconds % 60);

    if (hours > 0) {
        _snwprintf(
            out,
            out_count - 1,
            L"%d:%02d:%02d",
            hours,
            minutes,
            secs
        );
    } else {
        _snwprintf(
            out,
            out_count - 1,
            L"%02d:%02d",
            minutes,
            secs
        );
    }

    out[out_count - 1] = 0;
}

static void media_player_update_controls() {
    if (
        !media_player_seeking ||
        !hMediaPlayerSeek
    ) {
        return;
    }

    LONGLONG position = 0;
    LONGLONG duration = 0;

    if (
        FAILED(
            media_player_seeking->GetCurrentPosition(
                &position
            )
        ) ||
        FAILED(
            media_player_seeking->GetDuration(
                &duration
            )
        ) ||
        duration <= 0
    ) {
        return;
    }

    if (!media_player_user_seeking) {
        int slider =
            (int)(
                position * 1000LL /
                duration
            );

        SendMessageW(
            hMediaPlayerSeek,
            TBM_SETPOS,
            TRUE,
            slider
        );
    }

    if (hMediaPlayerTime) {
        wchar_t now_text[32] = {0};
        wchar_t total_text[32] = {0};
        wchar_t combined[80] = {0};

        media_player_format_time(
            position,
            now_text,
            ARRAYSIZE(now_text)
        );

        media_player_format_time(
            duration,
            total_text,
            ARRAYSIZE(total_text)
        );

        _snwprintf(
            combined,
            ARRAYSIZE(combined) - 1,
            L"%s / %s",
            now_text,
            total_text
        );

        combined[
            ARRAYSIZE(combined) - 1
        ] = 0;

        SetWindowTextW(
            hMediaPlayerTime,
            combined
        );
    }
}

static void media_player_layout_video() {
    if (
        !media_player_video ||
        !hMediaPlayerVideoHost
    ) {
        return;
    }

    RECT rc;
    GetClientRect(
        hMediaPlayerVideoHost,
        &rc
    );

    media_player_video->SetWindowPosition(
        0,
        0,
        rc.right,
        rc.bottom
    );
}

static LRESULT CALLBACK TelegacyMediaPlayerWindow(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    switch (msg) {
        case WM_CREATE: {
            HFONT font =
                (HFONT)GetStockObject(
                    DEFAULT_GUI_FONT
                );

            hMediaPlayerVideoHost =
                CreateWindowExW(
                    WS_EX_CLIENTEDGE,
                    L"STATIC",
                    L"",
                    WS_CHILD |
                    WS_VISIBLE |
                    SS_BLACKRECT,
                    8,
                    8,
                    544,
                    306,
                    hwnd,
                    (HMENU)1,
                    NULL,
                    NULL
                );

            hMediaPlayerInfo =
                CreateWindowExW(
                    WS_EX_CLIENTEDGE,
                    L"STATIC",
                    L"",
                    WS_CHILD |
                    SS_LEFT |
                    SS_CENTERIMAGE,
                    8,
                    8,
                    544,
                    70,
                    hwnd,
                    (HMENU)2,
                    NULL,
                    NULL
                );

            hMediaPlayerPlay =
                CreateWindowW(
                    L"BUTTON",
                    L">",
                    WS_CHILD |
                    WS_VISIBLE |
                    BS_PUSHBUTTON,
                    8,
                    324,
                    42,
                    24,
                    hwnd,
                    (HMENU)10,
                    NULL,
                    NULL
                );

            hMediaPlayerPause =
                CreateWindowW(
                    L"BUTTON",
                    L"||",
                    WS_CHILD |
                    WS_VISIBLE |
                    BS_PUSHBUTTON,
                    55,
                    324,
                    42,
                    24,
                    hwnd,
                    (HMENU)11,
                    NULL,
                    NULL
                );

            hMediaPlayerStop =
                CreateWindowW(
                    L"BUTTON",
                    L"[]",
                    WS_CHILD |
                    WS_VISIBLE |
                    BS_PUSHBUTTON,
                    102,
                    324,
                    42,
                    24,
                    hwnd,
                    (HMENU)12,
                    NULL,
                    NULL
                );

            hMediaPlayerTime =
                CreateWindowW(
                    L"STATIC",
                    L"00:00 / 00:00",
                    WS_CHILD |
                    WS_VISIBLE |
                    SS_RIGHT |
                    SS_CENTERIMAGE,
                    398,
                    324,
                    154,
                    24,
                    hwnd,
                    (HMENU)13,
                    NULL,
                    NULL
                );

            hMediaPlayerSeek =
                CreateWindowExW(
                    0,
                    TRACKBAR_CLASSW,
                    L"",
                    WS_CHILD |
                    WS_VISIBLE |
                    TBS_HORZ |
                    TBS_NOTICKS,
                    8,
                    354,
                    544,
                    28,
                    hwnd,
                    (HMENU)14,
                    NULL,
                    NULL
                );

            hMediaPlayerVolume =
                CreateWindowExW(
                    0,
                    TRACKBAR_CLASSW,
                    L"",
                    WS_CHILD |
                    WS_VISIBLE |
                    TBS_HORZ |
                    TBS_NOTICKS,
                    152,
                    324,
                    160,
                    24,
                    hwnd,
                    (HMENU)15,
                    NULL,
                    NULL
                );

            SendMessageW(
                hMediaPlayerSeek,
                TBM_SETRANGE,
                TRUE,
                MAKELPARAM(0, 1000)
            );

            SendMessageW(
                hMediaPlayerVolume,
                TBM_SETRANGE,
                TRUE,
                MAKELPARAM(0, 100)
            );

            SendMessageW(
                hMediaPlayerVolume,
                TBM_SETPOS,
                TRUE,
                85
            );

            HWND controls[] = {
                hMediaPlayerInfo,
                hMediaPlayerPlay,
                hMediaPlayerPause,
                hMediaPlayerStop,
                hMediaPlayerTime
            };

            for (
                int i = 0;
                i < ARRAYSIZE(controls);
                i++
            ) {
                if (controls[i]) {
                    SendMessageW(
                        controls[i],
                        WM_SETFONT,
                        (WPARAM)font,
                        TRUE
                    );
                }
            }

            SetTimer(
                hwnd,
                MEDIA_PLAYER_TIMER,
                250,
                NULL
            );

            return 0;
        }

        case WM_SIZE: {
            RECT rc;
            GetClientRect(hwnd, &rc);

            int client_w =
                rc.right - rc.left;

            int client_h =
                rc.bottom - rc.top;

            int bottom_y =
                client_h - 84;

            int seek_y =
                client_h - 48;

            if (media_player_is_video) {
                ShowWindow(
                    hMediaPlayerVideoHost,
                    SW_SHOW
                );

                ShowWindow(
                    hMediaPlayerInfo,
                    SW_HIDE
                );

                MoveWindow(
                    hMediaPlayerVideoHost,
                    8,
                    8,
                    client_w - 16,
                    bottom_y - 16,
                    TRUE
                );

                media_player_layout_video();
            } else {
                ShowWindow(
                    hMediaPlayerVideoHost,
                    SW_HIDE
                );

                ShowWindow(
                    hMediaPlayerInfo,
                    SW_SHOW
                );

                MoveWindow(
                    hMediaPlayerInfo,
                    8,
                    8,
                    client_w - 16,
                    bottom_y - 16,
                    TRUE
                );
            }

            MoveWindow(
                hMediaPlayerPlay,
                8,
                bottom_y,
                42,
                24,
                TRUE
            );

            MoveWindow(
                hMediaPlayerPause,
                55,
                bottom_y,
                42,
                24,
                TRUE
            );

            MoveWindow(
                hMediaPlayerStop,
                102,
                bottom_y,
                42,
                24,
                TRUE
            );

            MoveWindow(
                hMediaPlayerVolume,
                152,
                bottom_y,
                160,
                24,
                TRUE
            );

            MoveWindow(
                hMediaPlayerTime,
                client_w - 162,
                bottom_y,
                154,
                24,
                TRUE
            );

            MoveWindow(
                hMediaPlayerSeek,
                8,
                seek_y,
                client_w - 16,
                28,
                TRUE
            );

            return 0;
        }

        case WM_COMMAND: {
            switch (LOWORD(wParam)) {
                case 10:
                    if (media_player_control)
                        media_player_control->Run();
                    return 0;

                case 11:
                    if (media_player_control)
                        media_player_control->Pause();
                    return 0;

                case 12:
                    if (media_player_control) {
                        media_player_control->Stop();

                        if (media_player_seeking) {
                            LONGLONG zero = 0;

                            media_player_seeking->SetPositions(
                                &zero,
                                AM_SEEKING_AbsolutePositioning,
                                NULL,
                                AM_SEEKING_NoPositioning
                            );
                        }

                        media_player_update_controls();
                    }
                    return 0;
            }

            break;
        }

        case WM_HSCROLL: {
            HWND source =
                (HWND)lParam;

            if (
                source ==
                hMediaPlayerSeek &&
                media_player_seeking
            ) {
                int code =
                    LOWORD(wParam);

                if (
                    code == TB_THUMBTRACK ||
                    code == TB_THUMBPOSITION ||
                    code == TB_ENDTRACK
                ) {
                    media_player_user_seeking = true;

                    int slider =
                        (int)SendMessageW(
                            hMediaPlayerSeek,
                            TBM_GETPOS,
                            0,
                            0
                        );

                    LONGLONG duration = 0;

                    if (
                        SUCCEEDED(
                            media_player_seeking->GetDuration(
                                &duration
                            )
                        ) &&
                        duration > 0
                    ) {
                        LONGLONG target =
                            duration *
                            slider /
                            1000LL;

                        media_player_seeking->SetPositions(
                            &target,
                            AM_SEEKING_AbsolutePositioning,
                            NULL,
                            AM_SEEKING_NoPositioning
                        );
                    }

                    if (
                        code == TB_ENDTRACK ||
                        code == TB_THUMBPOSITION
                    ) {
                        media_player_user_seeking =
                            false;
                    }

                    media_player_update_controls();
                }

                return 0;
            }

            if (
                source ==
                hMediaPlayerVolume &&
                media_player_audio
            ) {
                int value =
                    (int)SendMessageW(
                        hMediaPlayerVolume,
                        TBM_GETPOS,
                        0,
                        0
                    );

                long volume =
                    value <= 0
                        ? -10000
                        : -5000 + value * 50;

                if (volume > 0)
                    volume = 0;

                media_player_audio->put_Volume(
                    volume
                );

                return 0;
            }

            break;
        }

        case WM_TIMER:
            if (wParam == MEDIA_PLAYER_TIMER) {
                media_player_update_controls();
                return 0;
            }
            break;

        case WM_CLOSE:
            DestroyWindow(hwnd);
            return 0;

        case WM_DESTROY:
            KillTimer(
                hwnd,
                MEDIA_PLAYER_TIMER
            );

            media_player_release_graph();

            hMediaPlayerWindow = NULL;
            hMediaPlayerVideoHost = NULL;
            hMediaPlayerInfo = NULL;
            hMediaPlayerPlay = NULL;
            hMediaPlayerPause = NULL;
            hMediaPlayerStop = NULL;
            hMediaPlayerSeek = NULL;
            hMediaPlayerVolume = NULL;
            hMediaPlayerTime = NULL;

            return 0;
    }

    return DefWindowProcW(
        hwnd,
        msg,
        wParam,
        lParam
    );
}

static bool media_player_open(
    const wchar_t* path,
    bool video
) {
    if (!path || !path[0])
        return false;

    if (
        hMediaPlayerWindow &&
        IsWindow(hMediaPlayerWindow)
    ) {
        DestroyWindow(
            hMediaPlayerWindow
        );
    }

    media_player_release_graph();

    media_player_is_video =
        video;

    HINSTANCE instance =
        GetModuleHandleW(NULL);

    WNDCLASSEXW wc = {0};

    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc =
        TelegacyMediaPlayerWindow;
    wc.hInstance = instance;
    wc.hCursor =
        LoadCursor(
            NULL,
            IDC_ARROW
        );
    wc.hbrBackground =
        (HBRUSH)(
            COLOR_BTNFACE + 1
        );
    wc.lpszClassName =
        L"TelegacyMediaPlayer98";

    WNDCLASSEXW existing = {0};
    existing.cbSize = sizeof(existing);

    if (!GetClassInfoExW(
        instance,
        wc.lpszClassName,
        &existing
    )) {
        if (!RegisterClassExW(&wc))
            return false;
    }

    const wchar_t* leaf =
        wcsrchr(
            path,
            L'\\'
        );

    leaf =
        leaf
            ? leaf + 1
            : path;

    wchar_t title[360] = {0};

    _snwprintf(
        title,
        ARRAYSIZE(title) - 1,
        L"%s - Telegacy Media Player",
        leaf
    );

    int window_h =
        video
            ? 445
            : 210;

    hMediaPlayerWindow =
        CreateWindowExW(
            WS_EX_TOOLWINDOW,
            wc.lpszClassName,
            title,
            WS_OVERLAPPEDWINDOW |
            WS_VISIBLE,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            580,
            window_h,
            hMain,
            NULL,
            instance,
            NULL
        );

    if (!hMediaPlayerWindow)
        return false;

    if (
        !video &&
        hMediaPlayerInfo
    ) {
        wchar_t info[420] = {0};

        _snwprintf(
            info,
            ARRAYSIZE(info) - 1,
            L"Playing:\r\n%s",
            leaf
        );

        SetWindowTextW(
            hMediaPlayerInfo,
            info
        );
    }

    // Telegacy already uses COM/OLE, but initialize defensively for DirectShow.
    CoInitialize(NULL);

    HRESULT hr =
        CoCreateInstance(
            CLSID_FilterGraph,
            NULL,
            CLSCTX_INPROC_SERVER,
            IID_IGraphBuilder,
            (void**)&media_player_graph
        );

    if (FAILED(hr)) {
        MessageBoxW(
            hMediaPlayerWindow,
            L"Could not create the DirectShow filter graph.",
            L"Telegacy Media Player",
            MB_OK |
            MB_ICONERROR
        );

        DestroyWindow(
            hMediaPlayerWindow
        );

        return false;
    }

    hr =
        media_player_graph->RenderFile(
            path,
            NULL
        );

    if (FAILED(hr)) {
        wchar_t error[260];

        _snwprintf(
            error,
            ARRAYSIZE(error) - 1,
            L"Windows could not decode this media file.\r\n\r\nDirectShow error: 0x%08X\r\n\r\nInstall a compatible DirectShow codec/filter if needed.",
            (unsigned int)hr
        );

        error[
            ARRAYSIZE(error) - 1
        ] = 0;

        MessageBoxW(
            hMediaPlayerWindow,
            error,
            L"Telegacy Media Player",
            MB_OK |
            MB_ICONERROR
        );

        DestroyWindow(
            hMediaPlayerWindow
        );

        return false;
    }

    media_player_graph->QueryInterface(
        IID_IMediaControl,
        (void**)&media_player_control
    );

    media_player_graph->QueryInterface(
        IID_IMediaSeeking,
        (void**)&media_player_seeking
    );

    media_player_graph->QueryInterface(
        IID_IBasicAudio,
        (void**)&media_player_audio
    );

    if (video) {
        media_player_graph->QueryInterface(
            IID_IVideoWindow,
            (void**)&media_player_video
        );

        if (
            media_player_video &&
            hMediaPlayerVideoHost
        ) {
            media_player_video->put_Owner(
                (OAHWND)hMediaPlayerVideoHost
            );

            media_player_video->put_WindowStyle(
                WS_CHILD |
                WS_CLIPSIBLINGS |
                WS_CLIPCHILDREN
            );

            media_player_video->put_Visible(
                OATRUE
            );

            media_player_layout_video();
        }
    }

    if (media_player_audio)
        media_player_audio->put_Volume(-750);

    if (media_player_control)
        media_player_control->Run();

    ShowWindow(
        hMediaPlayerWindow,
        SW_SHOW
    );

    SetForegroundWindow(
        hMediaPlayerWindow
    );

    media_player_update_controls();

    return true;
}

static const wchar_t* media_archive_safe_extension(
    MediaArchiveItem* item
) {
    if (!item)
        return L".bin";

    if (
        item->av_document.filename &&
        item->av_document.filename[0]
    ) {
        const wchar_t* dot =
            wcsrchr(
                item->av_document.filename,
                L'.'
            );

        if (
            dot &&
            wcslen(dot) >= 2 &&
            wcslen(dot) <= 8
        ) {
            bool valid = true;

            for (
                const wchar_t* p = dot + 1;
                *p;
                p++
            ) {
                if (
                    !(
                        (*p >= L'0' && *p <= L'9') ||
                        (*p >= L'A' && *p <= L'Z') ||
                        (*p >= L'a' && *p <= L'z')
                    )
                ) {
                    valid = false;
                    break;
                }
            }

            if (valid)
                return dot;
        }
    }

    return
        item->media_kind == 1
            ? L".mp4"
            : L".mp3";
}

static bool media_archive_begin_av_download(
    int item_index
) {
    if (
        item_index < 0 ||
        item_index >=
            (int)media_archive_items.size()
    ) {
        return false;
    }

    MediaArchiveItem* item =
        &media_archive_items[
            item_index
        ];

    if (
        item->media_kind == 0 ||
        !item->has_document
    ) {
        return false;
    }

    if (
        item->file_path[0] &&
        GetFileAttributesW(
            item->file_path
        ) != INVALID_FILE_ATTRIBUTES
    ) {
        return media_player_open(
            item->file_path,
            item->media_kind == 1
        );
    }

    if (media_av_pending_item >= 0) {
        MessageBeep(
            MB_ICONASTERISK
        );
        return false;
    }

    wchar_t temp_dir[MAX_PATH] = {0};

    DWORD temp_len =
        GetTempPathW(
            ARRAYSIZE(temp_dir),
            temp_dir
        );

    if (
        !temp_len ||
        temp_len >=
            ARRAYSIZE(temp_dir)
    ) {
        return false;
    }

    if (
        wcslen(temp_dir) + 16 >=
            ARRAYSIZE(temp_dir)
    ) {
        return false;
    }

    wcscat(
        temp_dir,
        L"TelegacyMedia"
    );

    CreateDirectoryW(
        temp_dir,
        NULL
    );

    const wchar_t* extension =
        media_archive_safe_extension(
            item
        );

    _snwprintf(
        media_av_pending_path,
        ARRAYSIZE(media_av_pending_path) - 1,
        L"%s\\av_%016I64X%s",
        temp_dir,
        item->document_id,
        extension
    );

    media_av_pending_path[
        ARRAYSIZE(media_av_pending_path) - 1
    ] = 0;

    DeleteFileW(
        media_av_pending_path
    );

    Document copy = {0};

    copy.size =
        item->av_document.size;

    memcpy(
        copy.id,
        item->av_document.id,
        8
    );

    memcpy(
        copy.access_hash,
        item->av_document.access_hash,
        8
    );

    copy.dc =
        item->av_document.dc;

    copy.photo_size = 0;
    copy.visible = false;

    if (!item->av_document.file_reference) {
        return false;
    }

    int file_ref_len =
        tlstr_len(
            item->av_document.file_reference,
            true
        );

    if (file_ref_len <= 0)
        return false;

    copy.file_reference =
        (BYTE*)malloc(
            file_ref_len
        );

    if (!copy.file_reference)
        return false;

    memcpy(
        copy.file_reference,
        item->av_document.file_reference,
        file_ref_len
    );

    copy.filename =
        _wcsdup(
            media_av_pending_path
        );

    if (!copy.filename) {
        free(
            copy.file_reference
        );
        return false;
    }

    downloading_docs.push_back(
        copy
    );

    media_av_pending_item =
        item_index;

    diag_log(
        "media av download begin kind=%d item=%d size=%I64d",
        item->media_kind,
        item_index,
        item->av_document.size
    );

    download_file(
        &dcInfoMain,
        &downloading_docs.back()
    );

    return true;
}

void media_archive_av_download_complete(
    const wchar_t* path
) {
    if (
        media_av_pending_item < 0 ||
        !path ||
        !path[0] ||
        wcscmp(
            path,
            media_av_pending_path
        ) != 0
    ) {
        return;
    }

    int item_index =
        media_av_pending_item;

    media_av_pending_item = -1;

    if (
        item_index >= 0 &&
        item_index <
            (int)media_archive_items.size()
    ) {
        wcsncpy(
            media_archive_items[
                item_index
            ].file_path,
            path,
            ARRAYSIZE(
                media_archive_items[
                    item_index
                ].file_path
            ) - 1
        );

        media_archive_items[
            item_index
        ].file_path[
            ARRAYSIZE(
                media_archive_items[
                    item_index
                ].file_path
            ) - 1
        ] = 0;
    }

    diag_log(
        "media av download complete item=%d",
        item_index
    );

    if (
        hMediaArchiveWindow &&
        IsWindow(
            hMediaArchiveWindow
        )
    ) {
        PostMessageW(
            hMediaArchiveWindow,
            WM_APP + 91,
            (WPARAM)item_index,
            0
        );
    }
}

void media_archive_add_av_document(
    Document* document,
    int message_id,
    int kind,
    const wchar_t* display_name,
    int duration
) {
    if (
        !document ||
        message_id <= 0 ||
        (kind != 1 && kind != 2)
    ) {
        return;
    }

    __int64 document_id = 0;

    memcpy(
        &document_id,
        document->id,
        8
    );

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].document_id ==
                document_id &&
            media_archive_items[i].media_kind ==
                kind
        ) {
            return;
        }
    }

    MediaArchiveItem item = {0};

    item.document_id =
        document_id;

    item.message_id =
        message_id;

    item.page_index =
        media_archive_request_page;

    item.media_kind = kind;
    item.duration = duration;
    item.has_document = true;

    item.av_document =
        *document;

    item.av_document.filename =
        document->filename
            ? _wcsdup(
                document->filename
            )
            : NULL;

    int file_ref_len =
        document->file_reference
            ? tlstr_len(
                document->file_reference,
                true
            )
            : 0;

    item.av_document.file_reference = NULL;

    if (file_ref_len > 0) {
        item.av_document.file_reference =
            (BYTE*)malloc(
                file_ref_len
            );

        if (
            item.av_document.file_reference
        ) {
            memcpy(
                item.av_document.file_reference,
                document->file_reference,
                file_ref_len
            );
        }
    }

    if (
        display_name &&
        display_name[0]
    ) {
        wcsncpy(
            item.display_name,
            display_name,
            ARRAYSIZE(
                item.display_name
            ) - 1
        );
    } else if (
        document->filename &&
        document->filename[0]
    ) {
        wcsncpy(
            item.display_name,
            document->filename,
            ARRAYSIZE(
                item.display_name
            ) - 1
        );
    } else {
        _snwprintf(
            item.display_name,
            ARRAYSIZE(
                item.display_name
            ) - 1,
            kind == 1
                ? L"Video #%d"
                : L"Audio #%d",
            message_id
        );
    }

    item.display_name[
        ARRAYSIZE(
            item.display_name
        ) - 1
    ] = 0;

    media_archive_items.push_back(
        item
    );
}

void media_archive_finish_av_page() {
    media_archive_page_loading = false;
    media_archive_refresh();
}

static void media_archive_reset_for_kind(
    int kind
) {
    if (
        kind < 0 ||
        kind > 2
    ) {
        return;
    }

    media_archive_clear();

    media_archive_kind =
        kind;

    media_archive_server_active = true;
    media_archive_search_pending = false;
    media_archive_page_loading = false;

    media_archive_next_offset_id = 0;
    media_archive_loaded_count = 0;
    media_archive_total = 0;
    media_archive_no_more = false;

    media_archive_current_page = 0;
    media_archive_request_page = 0;
    media_archive_previous_page = 0;
    media_archive_highest_page = 0;

    media_archive_page_offsets.clear();
    media_archive_page_offsets.push_back(0);

    media_archive_loaded_pages.clear();

    media_archive_refresh();

    media_archive_request_server_page(
        0
    );
}

'''

s = s[:pos] + runtime + s[pos:]

request_sig = "static bool media_archive_request_server_page_ex("
req_start, req_end = function_range(s, request_sig)
req_func = s[req_start:req_end]

old_filter = r'''    // inputMessagesFilterPhotos#9609a51c
    write_le(
        unenc_query + offset,
        0x9609a51c,
        4
    );'''

new_filter = r'''    // Filter is selected by the active Media tab.
    write_le(
        unenc_query + offset,
        media_archive_filter_constructor(),
        4
    );'''

if old_filter not in req_func:
    old_filter = r'''    write_le(
        unenc_query + offset,
        0x9609a51c,
        4
    );'''

if old_filter not in req_func:
    raise SystemExit(
        "Could not locate Photos filter in Media request function."
    )

req_func = req_func.replace(
    old_filter,
    new_filter,
    1
)

s = s[:req_start] + req_func + s[req_end:]

refresh = r'''static void media_archive_refresh() {
    if (!hMediaArchiveList)
        return;

    ListView_DeleteAllItems(
        hMediaArchiveList
    );

    LONG_PTR style =
        GetWindowLongPtrW(
            hMediaArchiveList,
            GWL_STYLE
        );

    style &= ~LVS_TYPEMASK;

    style |=
        media_archive_kind == 0
            ? LVS_ICON
            : LVS_LIST;

    SetWindowLongPtrW(
        hMediaArchiveList,
        GWL_STYLE,
        style
    );

    SetWindowPos(
        hMediaArchiveList,
        NULL,
        0,
        0,
        0,
        0,
        SWP_NOMOVE |
        SWP_NOSIZE |
        SWP_NOZORDER |
        SWP_NOACTIVATE |
        SWP_FRAMECHANGED
    );

    if (hMediaArchiveImages) {
        ListView_SetImageList(
            hMediaArchiveList,
            NULL,
            LVSIL_NORMAL
        );

        ListView_SetImageList(
            hMediaArchiveList,
            NULL,
            LVSIL_SMALL
        );

        ImageList_Destroy(
            hMediaArchiveImages
        );

        hMediaArchiveImages = NULL;
    }

    if (media_archive_kind == 0) {
        hMediaArchiveImages =
            ImageList_Create(
                96,
                96,
                ILC_COLOR32,
                20,
                16
            );

        if (hMediaArchiveImages) {
            ListView_SetImageList(
                hMediaArchiveList,
                hMediaArchiveImages,
                LVSIL_NORMAL
            );

            SendMessage(
                hMediaArchiveList,
                LVM_SETICONSPACING,
                0,
                MAKELPARAM(112, 118)
            );
        }
    }

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        MediaArchiveItem* archive_item =
            &media_archive_items[i];

        if (
            archive_item->media_kind !=
                media_archive_kind ||
            archive_item->page_index !=
                media_archive_current_page
        ) {
            continue;
        }

        LVITEMW item = {0};

        item.iItem =
            ListView_GetItemCount(
                hMediaArchiveList
            );

        item.lParam = i;

        wchar_t label[340] = {0};

        if (media_archive_kind == 0) {
            HBITMAP thumb =
                media_archive_make_thumbnail(
                    archive_item->bitmap,
                    96
                );

            if (!thumb || !hMediaArchiveImages) {
                if (thumb)
                    DeleteObject(thumb);
                continue;
            }

            int image_index =
                ImageList_Add(
                    hMediaArchiveImages,
                    thumb,
                    NULL
                );

            DeleteObject(thumb);

            if (image_index < 0)
                continue;

            if (archive_item->message_id) {
                _snwprintf(
                    label,
                    ARRAYSIZE(label) - 1,
                    L"#%d",
                    archive_item->message_id
                );
            }

            item.mask =
                LVIF_IMAGE |
                LVIF_PARAM |
                LVIF_TEXT;

            item.iImage =
                image_index;
        } else {
            if (archive_item->duration > 0) {
                _snwprintf(
                    label,
                    ARRAYSIZE(label) - 1,
                    L"%s   [%02d:%02d]",
                    archive_item->display_name,
                    archive_item->duration / 60,
                    archive_item->duration % 60
                );
            } else {
                wcsncpy(
                    label,
                    archive_item->display_name,
                    ARRAYSIZE(label) - 1
                );
            }

            item.mask =
                LVIF_PARAM |
                LVIF_TEXT;
        }

        label[
            ARRAYSIZE(label) - 1
        ] = 0;

        item.pszText =
            label;

        SendMessageW(
            hMediaArchiveList,
            LVM_INSERTITEMW,
            0,
            (LPARAM)&item
        );
    }

    media_archive_update_nav();
}'''

s = replace_function(
    s,
    "static void media_archive_refresh() {",
    refresh
)

open_item = r'''static void media_archive_open_item(
    int item_index
) {
    if (
        item_index < 0 ||
        item_index >=
            (int)media_archive_items.size()
    ) {
        return;
    }

    MediaArchiveItem* item =
        &media_archive_items[
            item_index
        ];

    if (item->media_kind != 0) {
        media_archive_begin_av_download(
            item_index
        );

        return;
    }

    const wchar_t* path =
        item->file_path;

    if (!path || !path[0]) {
        MessageBeep(
            MB_ICONASTERISK
        );
        return;
    }

    typedef HINSTANCE (
        WINAPI *ShellExecuteWProc
    )(
        HWND,
        LPCWSTR,
        LPCWSTR,
        LPCWSTR,
        LPCWSTR,
        INT
    );

    HMODULE shell =
        LoadLibraryW(
            L"shell32.dll"
        );

    if (!shell) {
        MessageBeep(
            MB_ICONASTERISK
        );
        return;
    }

    ShellExecuteWProc proc =
        (ShellExecuteWProc)GetProcAddress(
            shell,
            "ShellExecuteW"
        );

    if (proc) {
        HINSTANCE result =
            proc(
                hMediaArchiveWindow,
                L"open",
                path,
                NULL,
                NULL,
                SW_SHOWNORMAL
            );

        if ((INT_PTR)result <= 32)
            MessageBeep(MB_ICONASTERISK);
    }

    FreeLibrary(shell);
}'''

s = replace_function(
    s,
    "static void media_archive_open_item(",
    open_item
)

clear_start, clear_end = function_range(
    s,
    "void media_archive_clear()"
)
clear_func = s[clear_start:clear_end]

cleanup_anchor = r'''        if (
            media_archive_items[i].bitmap
        ) {'''

cleanup_new = r'''        if (
            media_archive_items[i].has_document
        ) {
            free(
                media_archive_items[i].av_document.filename
            );

            free(
                media_archive_items[i].av_document.file_reference
            );

            media_archive_items[i].av_document.filename = NULL;
            media_archive_items[i].av_document.file_reference = NULL;
        }

        if (
            media_archive_items[i].bitmap
        ) {'''

if cleanup_anchor not in clear_func:
    raise SystemExit(
        "Could not locate bitmap cleanup in media_archive_clear()."
    )

clear_func = clear_func.replace(
    cleanup_anchor,
    cleanup_new,
    1
)

delete_block = r'''        if (
            media_archive_items[i].file_path[0]
        ) {
            DeleteFileW(
                media_archive_items[i].file_path
            );
        }'''

delete_new = r'''        if (
            media_archive_items[i].media_kind == 0 &&
            media_archive_items[i].file_path[0]
        ) {
            DeleteFileW(
                media_archive_items[i].file_path
            );
        }'''

if delete_block in clear_func:
    clear_func = clear_func.replace(
        delete_block,
        delete_new,
        1
    )

s = s[:clear_start] + clear_func + s[clear_end:]

window_proc = r'''static LRESULT CALLBACK TelegacyMediaArchiveWindow(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    switch (msg) {
        case WM_CREATE: {
            HFONT font =
                (HFONT)GetStockObject(
                    DEFAULT_GUI_FONT
                );

            hMediaArchiveTabs =
                CreateWindowExW(
                    0,
                    WC_TABCONTROLW,
                    L"",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_TABSTOP |
                    TCS_TABS,
                    8,
                    7,
                    360,
                    27,
                    hwnd,
                    (HMENU)20,
                    NULL,
                    NULL
                );

            TCITEMW tab = {0};
            tab.mask = TCIF_TEXT;

            tab.pszText =
                (LPWSTR)L"\u0418\u0437\u043E\u0431\u0440\u0430\u0436\u0435\u043D\u0438\u044F";
            TabCtrl_InsertItem(
                hMediaArchiveTabs,
                0,
                &tab
            );

            tab.pszText =
                (LPWSTR)L"\u0412\u0438\u0434\u0435\u043E";
            TabCtrl_InsertItem(
                hMediaArchiveTabs,
                1,
                &tab
            );

            tab.pszText =
                (LPWSTR)L"\u041C\u0443\u0437\u044B\u043A\u0430";
            TabCtrl_InsertItem(
                hMediaArchiveTabs,
                2,
                &tab
            );

            TabCtrl_SetCurSel(
                hMediaArchiveTabs,
                media_archive_kind
            );

            hMediaArchiveNewer =
                CreateWindowW(
                    L"BUTTON",
                    L"<-",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                    8, 40, 44, 24,
                    hwnd,
                    (HMENU)1,
                    NULL,
                    NULL
                );

            hMediaArchivePageEdit =
                CreateWindowExW(
                    WS_EX_CLIENTEDGE,
                    L"EDIT",
                    L"1",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_TABSTOP |
                    ES_NUMBER |
                    ES_CENTER |
                    ES_AUTOHSCROLL,
                    57, 40, 48, 24,
                    hwnd,
                    (HMENU)3,
                    NULL,
                    NULL
                );

            hMediaArchivePageTotal =
                CreateWindowW(
                    L"STATIC",
                    L"/ ?",
                    WS_CHILD |
                    WS_VISIBLE |
                    SS_LEFT |
                    SS_CENTERIMAGE,
                    111, 40, 65, 24,
                    hwnd,
                    (HMENU)4,
                    NULL,
                    NULL
                );

            hMediaArchivePageGo =
                CreateWindowW(
                    L"BUTTON",
                    L"\u041E\u041A",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_TABSTOP |
                    BS_PUSHBUTTON,
                    181, 40, 42, 24,
                    hwnd,
                    (HMENU)5,
                    NULL,
                    NULL
                );

            hMediaArchiveOlder =
                CreateWindowW(
                    L"BUTTON",
                    L"->",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                    228, 40, 44, 24,
                    hwnd,
                    (HMENU)2,
                    NULL,
                    NULL
                );

            hMediaArchiveList =
                CreateWindowExW(
                    WS_EX_CLIENTEDGE,
                    WC_LISTVIEWW,
                    L"",
                    WS_CHILD |
                    WS_VISIBLE |
                    WS_VSCROLL |
                    LVS_ICON |
                    LVS_SINGLESEL |
                    LVS_NOLABELWRAP,
                    8, 70, 580, 378,
                    hwnd,
                    (HMENU)6,
                    NULL,
                    NULL
                );

            HWND controls[] = {
                hMediaArchiveTabs,
                hMediaArchiveNewer,
                hMediaArchiveOlder,
                hMediaArchivePageEdit,
                hMediaArchivePageTotal,
                hMediaArchivePageGo
            };

            for (
                int i = 0;
                i < ARRAYSIZE(controls);
                i++
            ) {
                if (controls[i]) {
                    SendMessageW(
                        controls[i],
                        WM_SETFONT,
                        (WPARAM)font,
                        TRUE
                    );
                }
            }

            SendMessageW(
                hMediaArchivePageEdit,
                EM_SETLIMITTEXT,
                7,
                0
            );

            media_archive_page_edit_original_proc =
                (WNDPROC)SetWindowLongPtrW(
                    hMediaArchivePageEdit,
                    GWLP_WNDPROC,
                    (LONG_PTR)TelegacyMediaPageEditProc
                );

            ListView_SetExtendedListViewStyle(
                hMediaArchiveList,
                LVS_EX_BORDERSELECT |
                LVS_EX_FULLROWSELECT
            );

            media_archive_refresh();
            media_archive_update_nav();

            return 0;
        }

        case WM_SIZE: {
            RECT rc;
            GetClientRect(hwnd, &rc);

            MoveWindow(
                hMediaArchiveTabs,
                8, 7,
                rc.right - 16,
                27,
                TRUE
            );

            MoveWindow(hMediaArchiveNewer, 8, 40, 44, 24, TRUE);
            MoveWindow(hMediaArchivePageEdit, 57, 40, 48, 24, TRUE);
            MoveWindow(hMediaArchivePageTotal, 111, 40, 65, 24, TRUE);
            MoveWindow(hMediaArchivePageGo, 181, 40, 42, 24, TRUE);
            MoveWindow(hMediaArchiveOlder, 228, 40, 44, 24, TRUE);

            MoveWindow(
                hMediaArchiveList,
                8, 70,
                rc.right - 16,
                rc.bottom - 78,
                TRUE
            );

            return 0;
        }

        case WM_COMMAND: {
            int command = LOWORD(wParam);

            if (command == 1) {
                media_archive_navigate_to_page(
                    media_archive_current_page - 1
                );
                return 0;
            }

            if (command == 2) {
                media_archive_navigate_to_page(
                    media_archive_current_page + 1
                );
                return 0;
            }

            if (command == 5) {
                wchar_t page_text[32] = {0};

                GetWindowTextW(
                    hMediaArchivePageEdit,
                    page_text,
                    ARRAYSIZE(page_text)
                );

                int requested =
                    _wtoi(page_text);

                int total_pages =
                    media_archive_total_pages();

                if (
                    requested < 1 ||
                    total_pages <= 0 ||
                    requested > total_pages
                ) {
                    MessageBeep(
                        MB_ICONASTERISK
                    );

                    media_archive_update_nav();
                    return 0;
                }

                media_archive_navigate_to_page(
                    requested - 1
                );

                return 0;
            }

            break;
        }

        case WM_NOTIFY: {
            LPNMHDR hdr =
                (LPNMHDR)lParam;

            if (
                hdr &&
                hdr->hwndFrom ==
                    hMediaArchiveTabs &&
                hdr->code ==
                    TCN_SELCHANGE
            ) {
                int selected =
                    TabCtrl_GetCurSel(
                        hMediaArchiveTabs
                    );

                if (
                    selected >= 0 &&
                    selected <= 2 &&
                    selected != media_archive_kind
                ) {
                    media_archive_reset_for_kind(
                        selected
                    );
                }

                return 0;
            }

            if (
                hdr &&
                hdr->hwndFrom ==
                    hMediaArchiveList &&
                hdr->code ==
                    NM_CLICK
            ) {
                LPNMITEMACTIVATE activate =
                    (LPNMITEMACTIVATE)lParam;

                if (
                    activate &&
                    activate->iItem >= 0
                ) {
                    LVITEMW item = {0};
                    item.mask = LVIF_PARAM;
                    item.iItem = activate->iItem;

                    if (
                        SendMessageW(
                            hMediaArchiveList,
                            LVM_GETITEMW,
                            0,
                            (LPARAM)&item
                        )
                    ) {
                        media_archive_pending_click_item =
                            (int)item.lParam;

                        KillTimer(
                            hwnd,
                            MEDIA_ARCHIVE_CLICK_TIMER
                        );

                        SetTimer(
                            hwnd,
                            MEDIA_ARCHIVE_CLICK_TIMER,
                            GetDoubleClickTime() + 20,
                            NULL
                        );
                    }
                }

                return 0;
            }

            if (
                hdr &&
                hdr->hwndFrom ==
                    hMediaArchiveList &&
                hdr->code ==
                    NM_DBLCLK
            ) {
                KillTimer(
                    hwnd,
                    MEDIA_ARCHIVE_CLICK_TIMER
                );

                media_archive_pending_click_item =
                    -1;

                LPNMITEMACTIVATE activate =
                    (LPNMITEMACTIVATE)lParam;

                if (
                    activate &&
                    activate->iItem >= 0
                ) {
                    LVITEMW item = {0};
                    item.mask = LVIF_PARAM;
                    item.iItem = activate->iItem;

                    if (
                        SendMessageW(
                            hMediaArchiveList,
                            LVM_GETITEMW,
                            0,
                            (LPARAM)&item
                        )
                    ) {
                        media_archive_open_item(
                            (int)item.lParam
                        );
                    }
                }

                return 0;
            }

            break;
        }

        case WM_TIMER:
            if (
                wParam ==
                MEDIA_ARCHIVE_CLICK_TIMER
            ) {
                KillTimer(
                    hwnd,
                    MEDIA_ARCHIVE_CLICK_TIMER
                );

                int item_index =
                    media_archive_pending_click_item;

                media_archive_pending_click_item =
                    -1;

                if (
                    item_index >= 0 &&
                    item_index <
                        (int)media_archive_items.size()
                ) {
                    media_archive_jump_to_message(
                        media_archive_items[
                            item_index
                        ].message_id
                    );
                }

                return 0;
            }
            break;

        case WM_APP + 91: {
            int item_index =
                (int)wParam;

            if (
                item_index >= 0 &&
                item_index <
                    (int)media_archive_items.size()
            ) {
                MediaArchiveItem* item =
                    &media_archive_items[
                        item_index
                    ];

                if (
                    item->media_kind != 0 &&
                    item->file_path[0]
                ) {
                    media_player_open(
                        item->file_path,
                        item->media_kind == 1
                    );
                }
            }

            return 0;
        }

        case WM_DESTROY: {
            KillTimer(
                hwnd,
                MEDIA_ARCHIVE_CLICK_TIMER
            );

            media_archive_pending_click_item =
                -1;

            if (hMediaArchiveImages) {
                ImageList_Destroy(
                    hMediaArchiveImages
                );

                hMediaArchiveImages = NULL;
            }

            hMediaArchiveList = NULL;
            hMediaArchiveTabs = NULL;
            hMediaArchiveNewer = NULL;
            hMediaArchiveOlder = NULL;
            hMediaArchivePageEdit = NULL;
            hMediaArchivePageTotal = NULL;
            hMediaArchivePageGo = NULL;
            hMediaArchiveWindow = NULL;
            media_archive_page_edit_original_proc = NULL;

            return 0;
        }
    }

    return DefWindowProcW(
        hwnd,
        msg,
        wParam,
        lParam
    );
}'''

s = replace_function(
    s,
    "static LRESULT CALLBACK TelegacyMediaArchiveWindow(",
    window_proc
)

show_start, show_end = function_range(
    s,
    "void media_archive_show()"
)
show_func = s[show_start:show_end]

if "media_archive_kind = 0;" not in show_func:
    activation = "        media_archive_server_active = true;"
    if activation not in show_func:
        raise SystemExit(
            "Could not locate Media activation in media_archive_show()."
        )

    show_func = show_func.replace(
        activation,
        "        media_archive_kind = 0;\n"
        + activation,
        1
    )

s = s[:show_start] + show_func + s[show_end:]

write(t, s)


# =============================================================================
# src/response.cpp - safe Document parser + route download completion
# =============================================================================

s = read(r)

if "media_tabs_av_document_parser_v1" not in s:
    anchor = "static void media_archive_handle_server_response("
    pos = s.find(anchor)

    if pos < 0:
        raise SystemExit(
            "Could not locate direct Media server response handler."
        )

    doc_parser = r'''
// ======================================================================================
// Safe A/V Document parser (no message_handler / RichEdit rendering)
// ======================================================================================

// media_tabs_av_document_parser_v1

static void media_tabs_free_document(
    Document* document
) {
    if (!document)
        return;

    free(document->filename);
    free(document->file_reference);

    document->filename = NULL;
    document->file_reference = NULL;
}

static bool media_tabs_extract_document(
    BYTE* media,
    int media_length,
    int message_id,
    int kind,
    Document* document,
    wchar_t* display_name,
    int display_count,
    int* duration_out
) {
    if (
        !media ||
        !document ||
        !display_name ||
        display_count < 8 ||
        !duration_out ||
        message_id <= 0 ||
        media_length < 48
    ) {
        return false;
    }

    memset(
        document,
        0,
        sizeof(Document)
    );

    display_name[0] = 0;
    *duration_out = 0;

    if (
        read_le(media, 4) !=
        0xdd570bd5
    ) {
        return false;
    }

    int media_flags =
        read_le(
            media + 4,
            4
        );

    if (!(media_flags & (1 << 0)))
        return false;

    if (
        read_le(media + 8, 4) !=
        0x8fd4c4d8
    ) {
        return false;
    }

    int doc_flags =
        read_le(
            media + 12,
            4
        );

    memcpy(
        document->id,
        media + 16,
        8
    );

    memcpy(
        document->access_hash,
        media + 24,
        8
    );

    int file_ref_len =
        tlstr_len(
            media + 32,
            true
        );

    if (
        file_ref_len <= 0 ||
        file_ref_len >
            media_length - 32
    ) {
        return false;
    }

    document->file_reference =
        (BYTE*)malloc(
            file_ref_len
        );

    if (!document->file_reference)
        return false;

    memcpy(
        document->file_reference,
        media + 32,
        file_ref_len
    );

    int offset =
        32 +
        file_ref_len;

    if (offset + 4 > media_length) {
        media_tabs_free_document(document);
        return false;
    }

    offset += 4; // date

    if (offset >= media_length) {
        media_tabs_free_document(document);
        return false;
    }

    int mime_len =
        tlstr_len(
            media + offset,
            true
        );

    if (
        mime_len <= 0 ||
        mime_len >
            media_length - offset
    ) {
        media_tabs_free_document(document);
        return false;
    }

    offset += mime_len;

    if (offset + 8 > media_length) {
        media_tabs_free_document(document);
        return false;
    }

    document->size =
        read_le(
            media + offset,
            8
        );

    offset += 8;

    if (
        doc_flags & (1 << 0) ||
        doc_flags & (1 << 1)
    ) {
        int n =
            photo_video_size_offset(
                media + offset,
                (doc_flags & (1 << 0))
                    ? true
                    : false,
                true,
                (doc_flags & (1 << 1))
                    ? true
                    : false
            );

        if (
            n <= 0 ||
            n >
                media_length - offset
        ) {
            media_tabs_free_document(document);
            return false;
        }

        offset += n;
    }

    if (offset + 12 > media_length) {
        media_tabs_free_document(document);
        return false;
    }

    document->dc =
        read_le(
            media + offset,
            4
        );

    offset += 4;

    if (
        read_le(
            media + offset,
            4
        ) != 0x1cb5c415
    ) {
        media_tabs_free_document(document);
        return false;
    }

    int attribute_count =
        read_le(
            media + offset + 4,
            4
        );

    if (
        attribute_count < 0 ||
        attribute_count > 256
    ) {
        media_tabs_free_document(document);
        return false;
    }

    offset += 8;

    wchar_t title[160] = {0};
    wchar_t performer[160] = {0};
    wchar_t filename[260] = {0};

    bool saw_video = false;
    bool saw_audio = false;

    for (
        int i = 0;
        i < attribute_count;
        i++
    ) {
        if (offset + 4 > media_length) {
            media_tabs_free_document(document);
            return false;
        }

        int attr_cons =
            read_le(
                media + offset,
                4
            );

        if (attr_cons == 0x15590068) {
            read_string(
                media + offset + 4,
                filename
            );
        }

        if (attr_cons == 0x9852f9c6) {
            saw_audio = true;

            int flags =
                read_le(
                    media + offset + 4,
                    4
                );

            *duration_out =
                read_le(
                    media + offset + 8,
                    4
                );

            int p =
                offset + 12;

            if (flags & (1 << 0)) {
                read_string(
                    media + p,
                    title
                );

                p +=
                    tlstr_len(
                        media + p,
                        true
                    );
            }

            if (flags & (1 << 1)) {
                read_string(
                    media + p,
                    performer
                );
            }
        }

        if (attr_cons == 0x43c57c48) {
            saw_video = true;

            double duration_double = 0.0;

            memcpy(
                &duration_double,
                media + offset + 8,
                8
            );

            if (
                duration_double > 0.0 &&
                duration_double < 2147483647.0
            ) {
                *duration_out =
                    (int)duration_double;
            }
        }

        int n =
            docatt_offset(
                media + offset
            );

        if (
            n <= 0 ||
            n >
                media_length - offset
        ) {
            media_tabs_free_document(document);
            return false;
        }

        offset += n;
    }

    if (
        kind == 1 &&
        !saw_video
    ) {
        media_tabs_free_document(document);
        return false;
    }

    if (
        kind == 2 &&
        !saw_audio
    ) {
        media_tabs_free_document(document);
        return false;
    }

    if (filename[0]) {
        document->filename =
            _wcsdup(
                filename
            );
    } else {
        wchar_t fallback[80];

        _snwprintf(
            fallback,
            ARRAYSIZE(fallback) - 1,
            kind == 1
                ? L"video_%08X.mp4"
                : L"audio_%08X.mp3",
            (unsigned int)read_le(
                document->access_hash + 4,
                4
            )
        );

        fallback[
            ARRAYSIZE(fallback) - 1
        ] = 0;

        document->filename =
            _wcsdup(
                fallback
            );
    }

    if (!document->filename) {
        media_tabs_free_document(document);
        return false;
    }

    document->photo_size = 0;
    document->visible = false;
    document->min = -message_id;
    document->max = -message_id;

    if (
        kind == 2 &&
        (title[0] || performer[0])
    ) {
        if (
            performer[0] &&
            title[0]
        ) {
            _snwprintf(
                display_name,
                display_count - 1,
                L"%s - %s",
                performer,
                title
            );
        } else if (title[0]) {
            wcsncpy(
                display_name,
                title,
                display_count - 1
            );
        } else {
            wcsncpy(
                display_name,
                performer,
                display_count - 1
            );
        }
    } else {
        wcsncpy(
            display_name,
            document->filename,
            display_count - 1
        );
    }

    display_name[
        display_count - 1
    ] = 0;

    return true;
}

'''

    s = s[:pos] + doc_parser + s[pos:]

handler = r'''static void media_archive_handle_server_response(
    unsigned int constructor,
    BYTE* response,
    int length
) {
    if (!media_archive_accept_response())
        return;

    int offset = 0;
    int total = 0;

    if (!message_search_get_vector(
        constructor,
        response,
        length,
        &offset,
        &total
    )) {
        diag_log(
            "media tabs response vector failed ctor=0x%08X length=%d kind=%d",
            constructor,
            length,
            media_archive_kind
        );

        media_archive_finish_server_page(
            0,
            0,
            0
        );

        return;
    }

    int vector_header =
        offset - 8;

    if (
        vector_header < 0 ||
        vector_header + 8 >
            length
    ) {
        media_archive_finish_server_page(
            0,
            0,
            total
        );

        return;
    }

    int count =
        read_le(
            response +
            vector_header +
            4,
            4
        );

    if (
        count < 0 ||
        count > 1000
    ) {
        media_archive_finish_server_page(
            0,
            0,
            total
        );

        return;
    }

    int last_id = 0;
    int parsed_count = 0;
    int added_count = 0;

    for (
        int i = 0;
        i < count;
        i++
    ) {
        if (
            offset < 0 ||
            offset >= length
        ) {
            break;
        }

        int consumed = 0;
        int message_id = 0;
        BYTE* media = NULL;
        int media_length = 0;

        if (!media_archive_message_envelope(
            response + offset,
            length - offset,
            &consumed,
            &message_id,
            &media,
            &media_length
        )) {
            diag_log(
                "media tabs envelope failed kind=%d item=%d offset=%d ctor=0x%08X",
                media_archive_kind,
                i,
                offset,
                (unsigned int)read_le(
                    response + offset,
                    4
                )
            );

            break;
        }

        if (
            consumed <= 0 ||
            consumed >
                length -
                offset
        ) {
            break;
        }

        if (message_id > 0)
            last_id = message_id;

        if (
            media &&
            media_archive_kind == 0
        ) {
            Document document;

            if (
                media_archive_extract_photo_document(
                    media,
                    media_length,
                    message_id,
                    &document
                )
            ) {
                if (!media_archive_saved_has_document(
                    documents,
                    document.id
                )) {
                    documents.push_front(
                        document
                    );

                    added_count++;
                } else {
                    media_archive_free_document_fields(
                        &document
                    );
                }
            }
        }

        if (
            media &&
            media_archive_kind != 0
        ) {
            Document document;
            wchar_t display_name[260] = {0};
            int duration = 0;

            if (
                media_tabs_extract_document(
                    media,
                    media_length,
                    message_id,
                    media_archive_kind,
                    &document,
                    display_name,
                    ARRAYSIZE(display_name),
                    &duration
                )
            ) {
                media_archive_add_av_document(
                    &document,
                    message_id,
                    media_archive_kind,
                    display_name,
                    duration
                );

                media_tabs_free_document(
                    &document
                );

                added_count++;
            } else {
                diag_log(
                    "media tabs document skipped kind=%d item=%d id=%d media_ctor=0x%08X",
                    media_archive_kind,
                    i,
                    message_id,
                    (unsigned int)read_le(
                        media,
                        4
                    )
                );
            }
        }

        parsed_count++;
        offset += consumed;
    }

    diag_log(
        "media tabs page complete kind=%d raw=%d parsed=%d added=%d total=%d last_id=%d",
        media_archive_kind,
        count,
        parsed_count,
        added_count,
        total,
        last_id
    );

    media_archive_finish_server_page(
        last_id,
        parsed_count,
        total
    );

    if (
        media_archive_kind == 0 &&
        added_count > 0
    ) {
        media_archive_start_next_download();
    } else {
        media_archive_finish_av_page();
    }
}'''

s = replace_function(
    s,
    "static void media_archive_handle_server_response(",
    handler
)

if "media_archive_av_download_complete(downloading_docs[i].filename);" not in s:
    # Locate the completion branch in upload.file by using two stable nearby strings.
    upload_pos = s.find("case 0x96a18d5: { // upload.file")
    if upload_pos < 0:
        raise SystemExit("Could not locate upload.file handler.")

    complete_pos = s.find(
        "if (size < 1048576)",
        upload_pos
    )
    if complete_pos < 0:
        raise SystemExit(
            "Could not locate upload.file completion condition."
        )

    decl_pos = s.find(
        "wchar_t status_str[100];",
        complete_pos
    )
    if decl_pos < 0 or decl_pos - complete_pos > 1000:
        raise SystemExit(
            "Could not locate upload.file completion status declaration."
        )

    line_start = s.rfind("\n", 0, decl_pos) + 1
    indent = s[line_start:decl_pos]

    insert = (
        indent
        + "media_archive_av_download_complete("
        + "downloading_docs[i].filename"
        + ");\n"
    )

    s = s[:line_start] + insert + s[line_start:]

write(r, s)

checks = {
    h: [
        "media_tabs_av_v1",
        "#include <dshow.h>",
        "strmiids.lib",
        "media_archive_add_av_document",
        "media_archive_finish_av_page",
    ],
    t: [
        "media_tabs_av_runtime_v1",
        "WC_TABCONTROLW",
        "media_archive_filter_constructor",
        "TelegacyMediaPlayerWindow",
        "CLSID_FilterGraph",
        "media_archive_begin_av_download",
        "void media_archive_finish_av_page()",
    ],
    r: [
        "media_tabs_av_document_parser_v1",
        "media_tabs_extract_document",
        "media tabs page complete",
        "media_archive_finish_av_page();",
        "media_archive_av_download_complete(downloading_docs[i].filename);",
    ],
}

for p, tokens in checks.items():
    text = read(p)
    for token in tokens:
        if token not in text:
            raise SystemExit(
                f"Internal verification failed in {p.name}: {token}"
            )

print(
    "Applied 3-tab Media browser (Images / Video / Music), "
    "safe server-side A/V metadata parsing, Telegram document download, "
    "and classic DirectShow player."
)
