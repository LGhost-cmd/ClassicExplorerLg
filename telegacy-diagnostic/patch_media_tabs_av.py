#!/usr/bin/env python3
from pathlib import Path
import sys
import base64
import json
import subprocess
import urllib.request

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_media_tabs_av.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"
m = root / "src" / "message.cpp"

for p in (h, t, r, m):
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


# -----------------------------------------------------------------------------
# Single-file replacement mode.
#
# This file replaces the old patch_media_tabs_av.py in the repository.  It
# first applies the exact previous v1 patch, then immediately applies v2.
# Therefore the workflow continues to contain ONE command only:
#
#   python "telegacy-diagnostic\patch_media_tabs_av.py" "telegacy-src"
#
# The previous v1 patch is pinned by Git blob SHA so replacing this file on
# master cannot make the bootstrap download itself recursively.
# -----------------------------------------------------------------------------

V1_BLOB_SHA = "b54ddc7af64c5a43143254c00d566c187aa609fb"
V1_BLOB_API = (
    "https://api.github.com/repos/LGhost-cmd/ClassicExplorerLg/git/blobs/"
    + V1_BLOB_SHA
)


def load_previous_v1_patch():
    # Fast/offline path: the old blob may already be present in the local
    # checkout's object database.
    try:
        repo_root = Path(__file__).resolve().parent.parent

        data = subprocess.check_output(
            ["git", "cat-file", "blob", V1_BLOB_SHA],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
        )

        if data:
            return data.decode("utf-8")
    except Exception:
        pass

    # GitHub Actions has network access because the workflow already clones
    # Telegacy and restores dependencies.  Fetch the immutable old blob rather
    # than the current file path.
    try:
        request = urllib.request.Request(
            V1_BLOB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ClassicExplorerLg-Telegacy-patcher",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        encoded = payload.get("content", "")
        encoding = payload.get("encoding", "")

        if encoding != "base64" or not encoded:
            raise RuntimeError("GitHub returned an unexpected blob representation")

        return base64.b64decode(encoded).decode("utf-8")

    except Exception as exc:
        raise SystemExit(
            "Could not obtain the pinned Media A/V v1 patch "
            f"({V1_BLOB_SHA}). Error: {exc}"
        )


def apply_previous_v1_if_needed():
    if "media_tabs_av_runtime_v1" in read(t):
        return

    print(
        "Media A/V v1 is not present; applying the pinned previous "
        "patch_media_tabs_av.py first..."
    )

    source = load_previous_v1_patch()

    namespace = {
        "__name__": "__main__",
        "__file__": "patch_media_tabs_av_v1_pinned.py",
    }

    try:
        exec(
            compile(
                source,
                "patch_media_tabs_av_v1_pinned.py",
                "exec",
            ),
            namespace,
            namespace,
        )
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise

    if "media_tabs_av_runtime_v1" not in read(t):
        raise SystemExit(
            "Pinned Media A/V v1 patch finished, but its runtime marker "
            "was not found in telegacy.cpp."
        )


apply_previous_v1_if_needed()

s = read(t)
if "media_tabs_av_runtime_v2" in s:
    print("Media A/V v2 already applied.")
    raise SystemExit(0)


# -----------------------------------------------------------------------------
# telegacy.h: MFPlay / cross-file declarations
# -----------------------------------------------------------------------------

s = read(h)

s = s.replace("#define _WIN32_WINNT 0x0400", "#define _WIN32_WINNT 0x0601", 1)
s = s.replace("#define WINVER 0x0500", "#define WINVER 0x0601", 1)

if "#include <mfplay.h>" not in s:
    anchor = "#include <dshow.h>"
    if anchor not in s:
        raise SystemExit("Could not locate #include <dshow.h> in telegacy.h")
    s = s.replace(
        anchor,
        anchor + "\n#include <mfplay.h>\n#pragma comment(lib, \"mfplay.lib\")",
        1,
    )

if "media_archive_preserve_on_chat_clear" not in s:
    anchor = "void media_player_chat_download_complete(\n    const wchar_t* path\n);"
    if anchor not in s:
        raise SystemExit("Could not locate media_player_chat_download_complete declaration")
    s = s.replace(
        anchor,
        anchor
        + "\n\nextern bool media_archive_preserve_on_chat_clear;"
        + "\nbool media_player_is_music_path(const wchar_t* path);"
        + "\nbool media_inline_audio_toggle(const wchar_t* path);",
        1,
    )

write(h, s)

# pragma comment is enough for MSVC, but keep CMake explicit too.
cmake = root / "CMakeLists.txt"
if cmake.exists():
    cm = cmake.read_text(encoding="utf-8")
    if "mfplay" not in cm.lower():
        if "    strmiids\n" in cm:
            cm = cm.replace("    strmiids\n", "    strmiids\n    mfplay\n", 1)
        elif "    ole32\n" in cm:
            cm = cm.replace("    ole32\n", "    ole32\n    mfplay\n", 1)
        cmake.write_text(cm, encoding="utf-8", newline="\n")


# -----------------------------------------------------------------------------
# telegacy.cpp: MFPlay-first video + inline audio + classic controls
# -----------------------------------------------------------------------------

s = read(t)

player_global = "static IVideoWindow* media_player_video = NULL;"
if player_global not in s:
    raise SystemExit("Could not locate media_player_video global")

s = s.replace(
    player_global,
    player_global
    + r'''

// media_tabs_av_runtime_v2
static IMFPMediaPlayer* media_player_mf = NULL;
static IMFPMediaPlayer* media_inline_audio = NULL;
static int media_player_backend = 0; // 0 none, 1 MFPlay, 2 DirectShow
static wchar_t media_inline_audio_path[MAX_PATH] = {0};
bool media_archive_preserve_on_chat_clear = false;
''',
    1,
)

helper_pos = s.find("static void media_player_release_graph()")
if helper_pos < 0:
    raise SystemExit("Could not locate media_player_release_graph")

helpers = r'''
static HRESULT media_mf_create_player(
    const wchar_t* path,
    HWND video_window,
    IMFPMediaPlayer** out_player
) {
    if (!path || !path[0] || !out_player)
        return E_INVALIDARG;

    *out_player = NULL;

    HRESULT hr =
        MFPCreateMediaPlayer(
            NULL,
            FALSE,
            MFP_OPTION_NONE,
            NULL,
            video_window,
            out_player
        );

    if (FAILED(hr) || !*out_player)
        return FAILED(hr) ? hr : E_FAIL;

    IMFPMediaItem* item = NULL;

    hr =
        (*out_player)->CreateMediaItemFromURL(
            path,
            TRUE,
            0,
            &item
        );

    if (SUCCEEDED(hr) && item)
        hr = (*out_player)->SetMediaItem(item);

    if (item)
        item->Release();

    if (FAILED(hr)) {
        (*out_player)->Shutdown();
        (*out_player)->Release();
        *out_player = NULL;
    }

    return hr;
}

static void media_inline_audio_release() {
    if (media_inline_audio) {
        media_inline_audio->Stop();
        media_inline_audio->Shutdown();
        media_inline_audio->Release();
        media_inline_audio = NULL;
    }

    media_inline_audio_path[0] = 0;
}

bool media_player_is_music_path(
    const wchar_t* path
) {
    if (!path || !path[0])
        return false;

    const wchar_t* leaf = wcsrchr(path, L'\\');
    leaf = leaf ? leaf + 1 : path;

    // Don't turn Telegacy's generated voice-note files into music rows.
    if (_wcsnicmp(leaf, L"voice", 5) == 0)
        return false;

    const wchar_t* dot = wcsrchr(leaf, L'.');
    if (!dot)
        return false;

    return
        _wcsicmp(dot, L".mp3") == 0 ||
        _wcsicmp(dot, L".m4a") == 0 ||
        _wcsicmp(dot, L".aac") == 0 ||
        _wcsicmp(dot, L".wav") == 0 ||
        _wcsicmp(dot, L".wma") == 0 ||
        _wcsicmp(dot, L".ogg") == 0 ||
        _wcsicmp(dot, L".opus") == 0 ||
        _wcsicmp(dot, L".flac") == 0;
}

bool media_inline_audio_toggle(
    const wchar_t* path
) {
    if (!media_player_is_music_path(path))
        return false;

    if (
        media_inline_audio &&
        media_inline_audio_path[0] &&
        _wcsicmp(media_inline_audio_path, path) == 0
    ) {
        MFP_MEDIAPLAYER_STATE state = MFP_MEDIAPLAYER_STATE_EMPTY;

        if (SUCCEEDED(media_inline_audio->GetState(&state))) {
            HRESULT hr = S_OK;

            if (state == MFP_MEDIAPLAYER_STATE_PLAYING)
                hr = media_inline_audio->Pause();
            else
                hr = media_inline_audio->Play();

            diag_log(
                "inline audio toggle state=%d hr=0x%08X path=%ls",
                (int)state,
                (unsigned int)hr,
                path
            );

            return SUCCEEDED(hr);
        }
    }

    media_inline_audio_release();
    CoInitialize(NULL);

    HRESULT hr =
        media_mf_create_player(
            path,
            NULL,
            &media_inline_audio
        );

    if (SUCCEEDED(hr) && media_inline_audio) {
        media_inline_audio->SetVolume(0.85f);
        hr = media_inline_audio->Play();
    }

    diag_log(
        "inline audio open hr=0x%08X path=%ls",
        (unsigned int)hr,
        path
    );

    if (FAILED(hr) || !media_inline_audio) {
        media_inline_audio_release();
        return false;
    }

    wcsncpy(
        media_inline_audio_path,
        path,
        ARRAYSIZE(media_inline_audio_path) - 1
    );
    media_inline_audio_path[ARRAYSIZE(media_inline_audio_path) - 1] = 0;

    return true;
}

static bool media_player_get_time(
    LONGLONG* position,
    LONGLONG* duration
) {
    if (!position || !duration)
        return false;

    *position = 0;
    *duration = 0;

    if (media_player_backend == 1 && media_player_mf) {
        PROPVARIANT p = {0};
        PROPVARIANT d = {0};

        HRESULT hp = media_player_mf->GetPosition(MFP_POSITIONTYPE_100NS, &p);
        HRESULT hd = media_player_mf->GetDuration(MFP_POSITIONTYPE_100NS, &d);

        if (
            SUCCEEDED(hp) &&
            SUCCEEDED(hd) &&
            p.vt == VT_I8 &&
            d.vt == VT_I8
        ) {
            *position = p.hVal.QuadPart;
            *duration = d.hVal.QuadPart;
            return *duration > 0;
        }

        return false;
    }

    if (media_player_backend == 2 && media_player_seeking) {
        return
            SUCCEEDED(media_player_seeking->GetCurrentPosition(position)) &&
            SUCCEEDED(media_player_seeking->GetDuration(duration)) &&
            *duration > 0;
    }

    return false;
}

static void media_player_set_position_v2(LONGLONG target) {
    if (media_player_backend == 1 && media_player_mf) {
        PROPVARIANT value = {0};
        value.vt = VT_I8;
        value.hVal.QuadPart = target;
        media_player_mf->SetPosition(MFP_POSITIONTYPE_100NS, &value);
        return;
    }

    if (media_player_backend == 2 && media_player_seeking) {
        media_player_seeking->SetPositions(
            &target,
            AM_SEEKING_AbsolutePositioning,
            NULL,
            AM_SEEKING_NoPositioning
        );
    }
}

static void media_player_draw_transport(DRAWITEMSTRUCT* dis) {
    if (!dis)
        return;

    RECT rc = dis->rcItem;
    FillRect(dis->hDC, &rc, GetSysColorBrush(COLOR_BTNFACE));

    DrawEdge(
        dis->hDC,
        &rc,
        (dis->itemState & ODS_SELECTED) ? EDGE_SUNKEN : EDGE_RAISED,
        BF_RECT
    );

    InflateRect(&rc, -7, -5);
    if (dis->itemState & ODS_SELECTED)
        OffsetRect(&rc, 1, 1);

    COLORREF color = GetSysColor(COLOR_BTNTEXT);
    HBRUSH brush = CreateSolidBrush(color);
    HPEN pen = CreatePen(PS_SOLID, 1, color);
    HGDIOBJ old_brush = SelectObject(dis->hDC, brush);
    HGDIOBJ old_pen = SelectObject(dis->hDC, pen);

    int cx = (rc.left + rc.right) / 2;
    int cy = (rc.top + rc.bottom) / 2;

    if (dis->CtlID == 10) {
        POINT tri[3] = {
            {cx - 5, cy - 7},
            {cx - 5, cy + 7},
            {cx + 7, cy}
        };
        Polygon(dis->hDC, tri, 3);
    } else if (dis->CtlID == 11) {
        Rectangle(dis->hDC, cx - 7, cy - 7, cx - 2, cy + 8);
        Rectangle(dis->hDC, cx + 2, cy - 7, cx + 7, cy + 8);
    } else if (dis->CtlID == 12) {
        Rectangle(dis->hDC, cx - 6, cy - 6, cx + 7, cy + 7);
    }

    SelectObject(dis->hDC, old_pen);
    SelectObject(dis->hDC, old_brush);
    DeleteObject(pen);
    DeleteObject(brush);
}

'''

s = s[:helper_pos] + helpers + s[helper_pos:]

release_v2 = r'''static void media_player_release_graph() {
    if (media_player_mf) {
        media_player_mf->Stop();
        media_player_mf->Shutdown();
        media_player_mf->Release();
        media_player_mf = NULL;
    }

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

    media_player_backend = 0;
}'''

s = replace_function(s, "static void media_player_release_graph()", release_v2)

update_v2 = r'''static void media_player_update_controls() {
    if (!hMediaPlayerSeek)
        return;

    LONGLONG position = 0;
    LONGLONG duration = 0;

    if (!media_player_get_time(&position, &duration))
        return;

    if (!media_player_user_seeking) {
        int slider = (int)(position * 1000LL / duration);
        SendMessageW(hMediaPlayerSeek, TBM_SETPOS, TRUE, slider);
    }

    if (hMediaPlayerTime) {
        wchar_t now_text[32] = {0};
        wchar_t total_text[32] = {0};
        wchar_t combined[80] = {0};

        media_player_format_time(position, now_text, ARRAYSIZE(now_text));
        media_player_format_time(duration, total_text, ARRAYSIZE(total_text));

        _snwprintf(
            combined,
            ARRAYSIZE(combined) - 1,
            L"%s / %s",
            now_text,
            total_text
        );
        combined[ARRAYSIZE(combined) - 1] = 0;
        SetWindowTextW(hMediaPlayerTime, combined);
    }
}'''

s = replace_function(s, "static void media_player_update_controls()", update_v2)

layout_v2 = r'''static void media_player_layout_video() {
    if (media_player_backend == 1 && media_player_mf) {
        media_player_mf->UpdateVideo();
        return;
    }

    if (
        media_player_backend != 2 ||
        !media_player_video ||
        !hMediaPlayerVideoHost
    ) {
        return;
    }

    RECT rc;
    GetClientRect(hMediaPlayerVideoHost, &rc);
    media_player_video->SetWindowPosition(0, 0, rc.right, rc.bottom);
}'''

s = replace_function(s, "static void media_player_layout_video()", layout_v2)

player_window_v2 = r'''static LRESULT CALLBACK TelegacyMediaPlayerWindow(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    switch (msg) {
        case WM_CREATE: {
            HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);

            hMediaPlayerVideoHost = CreateWindowExW(
                WS_EX_CLIENTEDGE,
                L"STATIC",
                L"",
                WS_CHILD | WS_VISIBLE | SS_BLACKRECT,
                8, 8, 544, 306,
                hwnd,
                (HMENU)1,
                NULL,
                NULL
            );

            hMediaPlayerPlay = CreateWindowW(
                L"BUTTON", L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                8, 324, 42, 24,
                hwnd, (HMENU)10, NULL, NULL
            );

            hMediaPlayerPause = CreateWindowW(
                L"BUTTON", L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                55, 324, 42, 24,
                hwnd, (HMENU)11, NULL, NULL
            );

            hMediaPlayerStop = CreateWindowW(
                L"BUTTON", L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                102, 324, 42, 24,
                hwnd, (HMENU)12, NULL, NULL
            );

            hMediaPlayerVolume = CreateWindowExW(
                0,
                TRACKBAR_CLASSW,
                L"",
                WS_CHILD | WS_VISIBLE | TBS_HORZ | TBS_NOTICKS,
                152, 324, 160, 24,
                hwnd, (HMENU)15, NULL, NULL
            );

            hMediaPlayerTime = CreateWindowW(
                L"STATIC",
                L"00:00 / 00:00",
                WS_CHILD | WS_VISIBLE | SS_RIGHT | SS_CENTERIMAGE,
                398, 324, 154, 24,
                hwnd, (HMENU)13, NULL, NULL
            );

            hMediaPlayerSeek = CreateWindowExW(
                0,
                TRACKBAR_CLASSW,
                L"",
                WS_CHILD | WS_VISIBLE | TBS_HORZ | TBS_NOTICKS,
                8, 354, 544, 28,
                hwnd, (HMENU)14, NULL, NULL
            );

            SendMessageW(hMediaPlayerSeek, TBM_SETRANGE, TRUE, MAKELPARAM(0, 1000));
            SendMessageW(hMediaPlayerVolume, TBM_SETRANGE, TRUE, MAKELPARAM(0, 100));
            SendMessageW(hMediaPlayerVolume, TBM_SETPOS, TRUE, 85);
            SendMessageW(hMediaPlayerTime, WM_SETFONT, (WPARAM)font, TRUE);

            SetTimer(hwnd, MEDIA_PLAYER_TIMER, 250, NULL);
            return 0;
        }

        case WM_SIZE: {
            RECT rc;
            GetClientRect(hwnd, &rc);

            int client_w = rc.right - rc.left;
            int client_h = rc.bottom - rc.top;
            int controls_y = client_h - 84;
            int seek_y = client_h - 48;

            MoveWindow(hMediaPlayerVideoHost, 8, 8, client_w - 16, controls_y - 16, TRUE);
            MoveWindow(hMediaPlayerPlay, 8, controls_y, 42, 24, TRUE);
            MoveWindow(hMediaPlayerPause, 55, controls_y, 42, 24, TRUE);
            MoveWindow(hMediaPlayerStop, 102, controls_y, 42, 24, TRUE);
            MoveWindow(hMediaPlayerVolume, 152, controls_y, 160, 24, TRUE);
            MoveWindow(hMediaPlayerTime, client_w - 162, controls_y, 154, 24, TRUE);
            MoveWindow(hMediaPlayerSeek, 8, seek_y, client_w - 16, 28, TRUE);

            media_player_layout_video();
            return 0;
        }

        case WM_DRAWITEM: {
            DRAWITEMSTRUCT* dis = (DRAWITEMSTRUCT*)lParam;
            if (dis && (dis->CtlID == 10 || dis->CtlID == 11 || dis->CtlID == 12)) {
                media_player_draw_transport(dis);
                return TRUE;
            }
            break;
        }

        case WM_COMMAND:
            switch (LOWORD(wParam)) {
                case 10:
                    if (media_player_backend == 1 && media_player_mf)
                        media_player_mf->Play();
                    else if (media_player_control)
                        media_player_control->Run();
                    return 0;

                case 11:
                    if (media_player_backend == 1 && media_player_mf)
                        media_player_mf->Pause();
                    else if (media_player_control)
                        media_player_control->Pause();
                    return 0;

                case 12:
                    if (media_player_backend == 1 && media_player_mf)
                        media_player_mf->Stop();
                    else if (media_player_control) {
                        media_player_control->Stop();
                        media_player_set_position_v2(0);
                    }
                    media_player_update_controls();
                    return 0;
            }
            break;

        case WM_HSCROLL: {
            HWND source = (HWND)lParam;

            if (source == hMediaPlayerSeek) {
                int code = LOWORD(wParam);
                if (code == TB_THUMBTRACK || code == TB_THUMBPOSITION || code == TB_ENDTRACK) {
                    media_player_user_seeking = true;

                    int slider = (int)SendMessageW(hMediaPlayerSeek, TBM_GETPOS, 0, 0);
                    LONGLONG position = 0;
                    LONGLONG duration = 0;

                    if (media_player_get_time(&position, &duration))
                        media_player_set_position_v2(duration * slider / 1000LL);

                    if (code == TB_ENDTRACK || code == TB_THUMBPOSITION)
                        media_player_user_seeking = false;

                    media_player_update_controls();
                }
                return 0;
            }

            if (source == hMediaPlayerVolume) {
                int value = (int)SendMessageW(hMediaPlayerVolume, TBM_GETPOS, 0, 0);

                if (media_player_backend == 1 && media_player_mf) {
                    media_player_mf->SetVolume((float)value / 100.0f);
                } else if (media_player_audio) {
                    long volume = value <= 0 ? -10000 : -5000 + value * 50;
                    if (volume > 0)
                        volume = 0;
                    media_player_audio->put_Volume(volume);
                }

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
            KillTimer(hwnd, MEDIA_PLAYER_TIMER);
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

    return DefWindowProcW(hwnd, msg, wParam, lParam);
}'''

s = replace_function(s, "static LRESULT CALLBACK TelegacyMediaPlayerWindow(", player_window_v2)

player_open_v2 = r'''static bool media_player_open(
    const wchar_t* path,
    bool video
) {
    if (!path || !path[0])
        return false;

    // Music never opens a separate window anymore.
    if (!video)
        return media_inline_audio_toggle(path);

    if (hMediaPlayerWindow && IsWindow(hMediaPlayerWindow))
        DestroyWindow(hMediaPlayerWindow);

    media_player_release_graph();
    media_player_is_video = true;

    HINSTANCE instance = GetModuleHandleW(NULL);

    WNDCLASSEXW wc = {0};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = TelegacyMediaPlayerWindow;
    wc.hInstance = instance;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"TelegacyMediaPlayer98";

    WNDCLASSEXW existing = {0};
    existing.cbSize = sizeof(existing);

    if (!GetClassInfoExW(instance, wc.lpszClassName, &existing)) {
        if (!RegisterClassExW(&wc))
            return false;
    }

    const wchar_t* leaf = wcsrchr(path, L'\\');
    leaf = leaf ? leaf + 1 : path;

    wchar_t title[360] = {0};
    _snwprintf(
        title,
        ARRAYSIZE(title) - 1,
        L"%s - Telegacy Media Player",
        leaf
    );

    hMediaPlayerWindow = CreateWindowExW(
        WS_EX_TOOLWINDOW,
        wc.lpszClassName,
        title,
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        600,
        455,
        hMain,
        NULL,
        instance,
        NULL
    );

    if (!hMediaPlayerWindow)
        return false;

    CoInitialize(NULL);

    HRESULT mf_hr =
        media_mf_create_player(
            path,
            hMediaPlayerVideoHost,
            &media_player_mf
        );

    if (SUCCEEDED(mf_hr) && media_player_mf) {
        media_player_backend = 1;
        media_player_mf->SetVolume(0.85f);
        mf_hr = media_player_mf->Play();
    }

    diag_log(
        "media player MFPlay hr=0x%08X path=%ls",
        (unsigned int)mf_hr,
        path
    );

    if (SUCCEEDED(mf_hr) && media_player_mf) {
        media_player_layout_video();
        media_player_update_controls();
        SetForegroundWindow(hMediaPlayerWindow);
        return true;
    }

    if (media_player_mf) {
        media_player_mf->Shutdown();
        media_player_mf->Release();
        media_player_mf = NULL;
    }

    HRESULT ds_hr =
        CoCreateInstance(
            CLSID_FilterGraph,
            NULL,
            CLSCTX_INPROC_SERVER,
            IID_IGraphBuilder,
            (void**)&media_player_graph
        );

    if (SUCCEEDED(ds_hr) && media_player_graph)
        ds_hr = media_player_graph->RenderFile(path, NULL);

    diag_log(
        "media player DirectShow fallback hr=0x%08X path=%ls",
        (unsigned int)ds_hr,
        path
    );

    if (SUCCEEDED(ds_hr) && media_player_graph) {
        media_player_graph->QueryInterface(IID_IMediaControl, (void**)&media_player_control);
        media_player_graph->QueryInterface(IID_IMediaSeeking, (void**)&media_player_seeking);
        media_player_graph->QueryInterface(IID_IBasicAudio, (void**)&media_player_audio);
        media_player_graph->QueryInterface(IID_IVideoWindow, (void**)&media_player_video);

        media_player_backend = 2;

        if (media_player_video && hMediaPlayerVideoHost) {
            media_player_video->put_Owner((OAHWND)hMediaPlayerVideoHost);
            media_player_video->put_WindowStyle(WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN);
            media_player_video->put_Visible(OATRUE);
        }

        if (media_player_audio)
            media_player_audio->put_Volume(-750);

        if (media_player_control)
            media_player_control->Run();

        media_player_layout_video();
        media_player_update_controls();
        SetForegroundWindow(hMediaPlayerWindow);
        return true;
    }

    wchar_t error[420] = {0};
    _snwprintf(
        error,
        ARRAYSIZE(error) - 1,
        L"Windows could not decode this video.\r\n\r\nMedia Foundation: 0x%08X\r\nDirectShow: 0x%08X",
        (unsigned int)mf_hr,
        (unsigned int)ds_hr
    );

    MessageBoxW(
        hMediaPlayerWindow,
        error,
        L"Telegacy Media Player",
        MB_OK | MB_ICONERROR
    );

    DestroyWindow(hMediaPlayerWindow);
    return false;
}'''

s = replace_function(s, "static bool media_player_open(", player_open_v2)

kind_v2 = r'''static int media_player_kind_from_path(
    const wchar_t* path
) {
    if (!path || !path[0])
        return 0;

    const wchar_t* dot = wcsrchr(path, L'.');
    if (!dot)
        return 0;

    if (
        _wcsicmp(dot, L".mp4") == 0 ||
        _wcsicmp(dot, L".m4v") == 0 ||
        _wcsicmp(dot, L".mov") == 0 ||
        _wcsicmp(dot, L".avi") == 0 ||
        _wcsicmp(dot, L".mkv") == 0 ||
        _wcsicmp(dot, L".webm") == 0 ||
        _wcsicmp(dot, L".wmv") == 0
    ) {
        return 1;
    }

    if (media_player_is_music_path(path))
        return 2;

    return 0;
}'''

s = replace_function(s, "static int media_player_kind_from_path(", kind_v2)

try_chat_v2 = r'''static bool media_player_try_open_chat_path(
    const wchar_t* path
) {
    int kind = media_player_kind_from_path(path);

    if (!kind)
        return false;

    media_chat_autoplay_path[0] = 0;
    media_chat_autoplay_kind = 0;

    if (kind == 2)
        return media_inline_audio_toggle(path);

    return media_player_open(path, true);
}'''

s = replace_function(s, "static bool media_player_try_open_chat_path(", try_chat_v2)

chat_complete_v2 = r'''void media_player_chat_download_complete(
    const wchar_t* path
) {
    if (
        !path ||
        !path[0] ||
        !media_chat_autoplay_path[0] ||
        media_chat_autoplay_kind == 0 ||
        _wcsicmp(path, media_chat_autoplay_path) != 0
    ) {
        return;
    }

    int kind = media_chat_autoplay_kind;
    media_chat_autoplay_path[0] = 0;
    media_chat_autoplay_kind = 0;

    if (kind == 2)
        media_inline_audio_toggle(path);
    else if (kind == 1)
        media_player_open(path, true);
}'''

s = replace_function(s, "void media_player_chat_download_complete(", chat_complete_v2)

# Prevent a Media jump from destroying the gallery cache.
clear_v2 = r'''void message_search_clear_chat_view() {
    for (int i = (int)documents.size() - 1; i >= 0; i--) {
        free(documents[i].filename);
        free(documents[i].file_reference);
    }

    documents.clear();

    for (int i = (int)links.size() - 1; i >= 0; i--)
        free(links[i].lpstrText);

    links.clear();
    messages.clear();

    memset(group_id_tofront, 0, sizeof(group_id_tofront));
    memset(group_id, 0, sizeof(group_id));

    if (chat)
        SendMessageW(chat, WM_SETTEXT, 0, (LPARAM)L"");

    if (!media_archive_preserve_on_chat_clear)
        media_archive_clear();
}'''

s = replace_function(s, "void message_search_clear_chat_view()", clear_v2)

# Make the already-existing refresh less destructive visually.
refresh_start, refresh_end = function_range(s, "static void media_archive_refresh() {")
refresh_func = s[refresh_start:refresh_end]
refresh_func = refresh_func.replace("RDW_ERASE |\n", "")
refresh_func = refresh_func.replace("RDW_ERASE |\r\n", "")
s = s[:refresh_start] + refresh_func + s[refresh_end:]

write(t, s)


# -----------------------------------------------------------------------------
# response.cpp: preserve Media on jump + request video document thumbnails
# -----------------------------------------------------------------------------

s = read(r)

jump_start, jump_end = function_range(s, "static void media_archive_handle_jump_response(")
jump_func = s[jump_start:jump_end]

old = "    message_search_clear_chat_view();"
if old not in jump_func:
    raise SystemExit("Could not locate chat clear inside Media jump response")

jump_func = jump_func.replace(
    old,
    "    media_archive_preserve_on_chat_clear = true;\n"
    "    message_search_clear_chat_view();\n"
    "    media_archive_preserve_on_chat_clear = false;",
    1,
)
s = s[:jump_start] + jump_func + s[jump_end:]

# Document flags bit 0 means thumbs are present in the Document constructor.
parser_start, parser_end = function_range(s, "static bool media_tabs_extract_document(")
parser = s[parser_start:parser_end]

old = "    document->photo_size = 0;"
if old in parser:
    parser = parser.replace(
        old,
        "    document->photo_size =\n"
        "        (kind == 1 && (doc_flags & (1 << 0))) ? 2 : 0;",
        1,
    )

s = s[:parser_start] + parser + s[parser_end:]
write(r, s)


# -----------------------------------------------------------------------------
# message.cpp: music gets a compact inline Win98-ish play row
# -----------------------------------------------------------------------------

s = read(m)

if "media_inline_music_row_v2" not in s:
    old = "\t\tbool voice = false, gif = false, round = false, sticker = false;"
    if old not in s:
        raise SystemExit("Could not locate document media flags in message.cpp")

    s = s.replace(
        old,
        "\t\tbool voice = false, gif = false, round = false, sticker = false, music = false; // media_inline_music_row_v2",
        1,
    )

    old = "\t\t\t\t\t\tvoice = (att_flags & (1 << 10)) ? true : false;"
    if old not in s:
        raise SystemExit("Could not locate DocumentAttributeAudio voice flag")

    s = s.replace(old, old + "\n\t\t\t\t\t\tmusic = !voice;", 1)

    old = (
        "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n"
        "\t\t\twritten += riched_write(chat, document.filename);\n"
        "\t\t\tdocument.max = cr_startmsg.cpMin + written;\n"
        "\t\t\tif (duration_str[0] == ' ') written += riched_write(chat, &duration_str[0]);\n"
        "\t\t\twritten += riched_write(chat, &size_str[0]);"
    )

    new = (
        "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n"
        "\t\t\tif (music) written += riched_write(chat, L\"[>] \" );\n"
        "\t\t\twritten += riched_write(chat, document.filename);\n"
        "\t\t\tif (duration_str[0] == ' ') written += riched_write(chat, &duration_str[0]);\n"
        "\t\t\twritten += riched_write(chat, &size_str[0]);\n"
        "\t\t\tdocument.max = cr_startmsg.cpMin + written;"
    )

    if old not in s:
        raise SystemExit("Could not locate document row rendering block")

    s = s.replace(old, new, 1)

write(m, s)


# -----------------------------------------------------------------------------
# Chat click behavior: one click on music; double click on video.
# This is deliberately a small textual rewrite so the v1 download machinery stays.
# -----------------------------------------------------------------------------

s = read(t)

queue_old = '''\t\t\t\t\tif (\n\t\t\t\t\t\tmedia_double_click &&\n\t\t\t\t\t\tmedia_player_kind_from_path(documents[i].filename) != 0\n\t\t\t\t\t) {\n\t\t\t\t\t\tmedia_player_queue_chat_autoplay(\n\t\t\t\t\t\t\tdocuments[i].filename\n\t\t\t\t\t\t);\n\t\t\t\t\t}\n'''

if queue_old in s:
    queue_new = '''\t\t\t\t\tint media_kind = media_player_kind_from_path(documents[i].filename);\n\t\t\t\t\tbool media_play_request =\n\t\t\t\t\t\t(media_kind == 2 && !media_double_click) ||\n\t\t\t\t\t\t(media_kind == 1 && media_double_click);\n\n\t\t\t\t\tif (media_play_request) {\n\t\t\t\t\t\tmedia_player_queue_chat_autoplay(\n\t\t\t\t\t\t\tdocuments[i].filename\n\t\t\t\t\t\t);\n\t\t\t\t\t}\n'''
    s = s.replace(queue_old, queue_new, 1)

    # Existing v1 has two guards that prevent an in-progress double-click from
    # cancelling its own download. Extend those guards to music single-click.
    s = s.replace(
        "media_double_click &&\n\t\t\t\t\t\t\t\t\tmedia_player_kind_from_path(documents[i].filename) != 0",
        "media_play_request",
        1,
    )
    s = s.replace(
        "media_double_click &&\n\t\t\t\t\t\t\t\tmedia_player_kind_from_path(documents[i].filename) != 0",
        "media_play_request",
        1,
    )

    open_old = '''\t\t\t\t\t\t} else if (media_double_click) {\n\t\t\t\t\t\t\tif (!media_player_try_open_chat_path(documents[i].filename)) {\n\t\t\t\t\t\t\t\tif ((INT_PTR)ShellExecute(NULL, L"open", documents[i].filename, NULL, NULL, SW_SHOWNORMAL) <= 32) {\n\t\t\t\t\t\t\t\t\twchar_t cmd[MAX_PATH * 2];\n\t\t\t\t\t\t\t\t\tswprintf(cmd, L"shell32.dll,OpenAs_RunDLL %s", documents[i].filename);\n\t\t\t\t\t\t\t\t\tShellExecute(NULL, L"open", L"rundll32.exe", cmd, NULL, SW_SHOWNORMAL);\n\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}\n'''

    open_new = '''\t\t\t\t\t\t} else if (media_play_request) {\n\t\t\t\t\t\t\tmedia_player_try_open_chat_path(documents[i].filename);\n\t\t\t\t\t\t} else if (media_double_click && media_kind == 0) {\n\t\t\t\t\t\t\tif ((INT_PTR)ShellExecute(NULL, L"open", documents[i].filename, NULL, NULL, SW_SHOWNORMAL) <= 32) {\n\t\t\t\t\t\t\t\twchar_t cmd[MAX_PATH * 2];\n\t\t\t\t\t\t\t\tswprintf(cmd, L"shell32.dll,OpenAs_RunDLL %s", documents[i].filename);\n\t\t\t\t\t\t\t\tShellExecute(NULL, L"open", L"rundll32.exe", cmd, NULL, SW_SHOWNORMAL);\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}\n'''

    if open_old in s:
        s = s.replace(open_old, open_new, 1)

write(t, s)


# -----------------------------------------------------------------------------
# Final diagnostics / marker
# -----------------------------------------------------------------------------

s = read(t)
if "media_tabs_av_runtime_v2" not in s:
    raise SystemExit("Media v2 marker missing after patch")

for token in (
    "MFPCreateMediaPlayer",
    "media_inline_audio_toggle",
    "media_archive_preserve_on_chat_clear",
    "BS_OWNERDRAW",
):
    if token not in s:
        raise SystemExit(f"Media v2 verification failed: {token}")

print(
    "Applied Media A/V v2: MFPlay-first video, DirectShow fallback, "
    "inline chat music, classic transport buttons, Media state preservation, "
    "and reduced redraw/flicker."
)
