#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_media_audio_video_fix.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
m = root / "src" / "message.cpp"

for p in (t, m):
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


base = read(t)
if "media_tabs_av_runtime_v56" in base:
    print("Media A/V v5.6 fix already applied.")
    raise SystemExit(0)

if (
    "media_inline_audio_redraw_guard_v55" not in base
    or "media_chat_layout_transaction = false;" not in base
):
    raise SystemExit(
        "Media A/V v5.5 runtime was not found. Run patch_media_tabs_av.py first."
    )

# =============================================================================
# Media A/V v5.6 - robust audio switching + unified in-chat video card
# - switching from one inline audio track to another reuses the existing
#   MFPlay instance and swaps its media item atomically
# - the old audio row is explicitly redrawn as stopped before the switch
# - in-chat video is a single clickable preview card (no detached filename row)
# =============================================================================

s = read(t)

if "media_tabs_av_runtime_v56" not in s:
    marker_anchor = "bool media_chat_layout_transaction = false;"
    if marker_anchor not in s:
        raise SystemExit("Could not locate v5.5 media layout global for v5.6.")

    s = s.replace(
        marker_anchor,
        marker_anchor + "\n// media_tabs_av_runtime_v56",
        1,
    )

    release_v56 = r'''static void media_inline_audio_release() {
    if (media_inline_audio) {
        media_inline_audio_requested_play_state = 0;
        media_inline_audio_requested_play_confirmations = 0;
        media_inline_audio_visual_playing = false;
        media_inline_audio_visual_play_hold_until = 0;

        media_inline_audio->Stop();
        media_inline_audio_last_second = -1;
        media_inline_audio_apply_visual(true);

        media_inline_audio->Shutdown();
        media_inline_audio->Release();
        media_inline_audio = NULL;
    }

    if (media_inline_audio_timer) {
        KillTimer(NULL, media_inline_audio_timer);
        media_inline_audio_timer = 0;
    }

    media_inline_audio_path[0] = 0;
    media_inline_audio_last_second = -1;
    media_inline_audio_cached_duration = 0;
    media_inline_audio_drag_preview = 0;
    media_inline_audio_seek_dirty = false;
    media_inline_audio_visual_seek_hold_until = 0;
    media_inline_audio_visual_seek_position = 0;
    media_inline_audio_visual_play_hold_until = 0;
    media_inline_audio_visual_playing = false;
    media_inline_audio_requested_play_state = -1;
    media_inline_audio_requested_play_confirmations = 0;
}'''
    s = replace_function(
        s,
        "static void media_inline_audio_release()",
        release_v56,
    )

    toggle_v56 = r'''bool media_inline_audio_toggle(
    const wchar_t* path
) {
    if (!media_player_is_music_path(path))
        return false;

    bool same_track =
        media_inline_audio &&
        media_inline_audio_path[0] &&
        _wcsicmp(media_inline_audio_path, path) == 0;

    if (same_track) {
        MFP_MEDIAPLAYER_STATE state =
            MFP_MEDIAPLAYER_STATE_EMPTY;

        if (SUCCEEDED(media_inline_audio->GetState(&state))) {
            HRESULT hr = S_OK;

            bool currently_shown_as_playing =
                media_inline_audio_visual_is_playing(
                    state
                );

            bool requested_playing =
                !currently_shown_as_playing;

            if (requested_playing)
                hr = media_inline_audio->Play();
            else
                hr = media_inline_audio->Pause();

            if (SUCCEEDED(hr)) {
                media_inline_audio_visual_request_playing(
                    requested_playing
                );
                media_inline_audio_last_second = -1;
                media_inline_audio_apply_visual(true);
            }

            diag_log(
                "inline audio toggle state=%d hr=0x%08X path=%ls",
                (int)state,
                (unsigned int)hr,
                path
            );

            media_inline_audio_start_timer();
            return SUCCEEDED(hr);
        }
    }

    if (
        media_inline_audio &&
        media_inline_audio_path[0] &&
        !same_track
    ) {
        media_inline_audio_requested_play_state = 0;
        media_inline_audio_requested_play_confirmations = 0;
        media_inline_audio_visual_playing = false;
        media_inline_audio_visual_play_hold_until = 0;

        media_inline_audio->Stop();
        media_inline_audio_last_second = -1;
        media_inline_audio_apply_visual(true);

        IMFPMediaItem* item = NULL;

        HRESULT hr =
            media_inline_audio->CreateMediaItemFromURL(
                path,
                TRUE,
                0,
                &item
            );

        if (SUCCEEDED(hr) && item) {
            hr =
                media_inline_audio->SetMediaItem(
                    item
                );
        }

        if (item) {
            item->Release();
            item = NULL;
        }

        if (SUCCEEDED(hr)) {
            wcsncpy(
                media_inline_audio_path,
                path,
                ARRAYSIZE(media_inline_audio_path) - 1
            );
            media_inline_audio_path[
                ARRAYSIZE(media_inline_audio_path) - 1
            ] = 0;

            media_inline_audio_cached_duration = 0;
            media_inline_audio_drag_preview = 0;
            media_inline_audio_seek_dirty = false;
            media_inline_audio_visual_seek_hold_until = 0;
            media_inline_audio_visual_seek_position = 0;
            media_inline_audio_requested_play_state = -1;
            media_inline_audio_requested_play_confirmations = 0;

            media_inline_audio->SetVolume(
                (float)media_inline_audio_volume /
                100.0f
            );

            HRESULT rate_hr =
                media_inline_audio->SetRate(
                    media_playback_rates[
                        media_inline_audio_rate_index
                    ]
                );

            diag_log(
                "inline audio switch speed rate=%.2f hr=0x%08X",
                media_playback_rates[
                    media_inline_audio_rate_index
                ],
                (unsigned int)rate_hr
            );

            hr = media_inline_audio->Play();

            diag_log(
                "inline audio switch hr=0x%08X path=%ls",
                (unsigned int)hr,
                path
            );

            if (SUCCEEDED(hr)) {
                media_inline_audio_visual_request_playing(true);
                media_inline_audio_last_second = -1;
                media_inline_audio_start_timer();
                media_inline_audio_apply_visual(true);
                return true;
            }
        }

        diag_log(
            "inline audio switch fallback hr=0x%08X path=%ls",
            (unsigned int)hr,
            path
        );

        media_inline_audio_release();
    } else if (media_inline_audio) {
        media_inline_audio_release();
    }

    CoInitialize(NULL);

    HRESULT hr =
        media_mf_create_player(
            path,
            NULL,
            &media_inline_audio
        );

    if (SUCCEEDED(hr) && media_inline_audio) {
        wcsncpy(
            media_inline_audio_path,
            path,
            ARRAYSIZE(media_inline_audio_path) - 1
        );
        media_inline_audio_path[
            ARRAYSIZE(media_inline_audio_path) - 1
        ] = 0;

        media_inline_audio_cached_duration = 0;
        media_inline_audio_drag_preview = 0;
        media_inline_audio_seek_dirty = false;
        media_inline_audio_visual_seek_hold_until = 0;
        media_inline_audio_visual_seek_position = 0;
        media_inline_audio_requested_play_state = -1;
        media_inline_audio_requested_play_confirmations = 0;

        media_inline_audio->SetVolume(
            (float)media_inline_audio_volume /
            100.0f
        );

        HRESULT rate_hr =
            media_inline_audio->SetRate(
                media_playback_rates[
                    media_inline_audio_rate_index
                ]
            );

        diag_log(
            "inline audio initial speed rate=%.2f hr=0x%08X",
            media_playback_rates[
                media_inline_audio_rate_index
            ],
            (unsigned int)rate_hr
        );

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

    media_inline_audio_visual_request_playing(true);
    media_inline_audio_last_second = -1;
    media_inline_audio_start_timer();
    media_inline_audio_apply_visual(true);

    return true;
}'''

    s = replace_function(
        s,
        "bool media_inline_audio_toggle(",
        toggle_v56,
    )

write(t, s)


s = read(m)

if "media_chat_video_unified_v56" not in s:
    start = s.find(
        "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n\n"
        "\t\t\tif (video && video_has_thumb && !same_photo) {"
    )

    if start < 0:
        raise SystemExit(
            "Could not locate generated video/document row for v5.6."
        )

    end_marker = "\n\t\t\tdocument.max = cr_startmsg.cpMin + written;"
    end = s.find(end_marker, start)
    if end < 0:
        raise SystemExit(
            "Could not locate generated video/document row end for v5.6."
        )
    end += len(end_marker)

    row_v56 = r'''			document.min = cr_startmsg.cpMin + written;

			// media_chat_video_unified_v56
			if (video && video_has_thumb && !same_photo) {
				video_thumb_document = document;
				video_thumb_document.filename =
					document.filename
						? _wcsdup(document.filename)
						: NULL;

				int thumb_ref_len =
					document.file_reference
						? tlstr_len(document.file_reference, true)
						: 0;

				video_thumb_document.file_reference = NULL;

				if (thumb_ref_len > 0) {
					video_thumb_document.file_reference =
						(BYTE*)malloc(thumb_ref_len);

					if (video_thumb_document.file_reference) {
						memcpy(
							video_thumb_document.file_reference,
							document.file_reference,
							thumb_ref_len
						);
					}
				}

				if (
					video_thumb_document.filename &&
					video_thumb_document.file_reference
				) {
					video_thumb_document.photo_size = 3;
					video_thumb_document.visible = true;
					memset(
						video_thumb_document.photo_msg_id,
						0,
						8
					);

					video_thumb_document.min =
						cr_startmsg.cpMin + written;

					HBITMAP placeholder =
						media_chat_video_placeholder();

					if (placeholder) {
						insert_image(
							chat,
							NULL,
							placeholder
						);
						DeleteObject(placeholder);
						written++;
					}

					video_thumb_document.max =
						cr_startmsg.cpMin + written;

					if (
						video_thumb_document.max >
							video_thumb_document.min
					) {
						CHARRANGE video_range;
						video_range.cpMin =
							video_thumb_document.min;
						video_range.cpMax =
							video_thumb_document.max;

						SendMessageW(
							chat,
							EM_EXSETSEL,
							0,
							(LPARAM)&video_range
						);

						CHARFORMAT2W link_format;
						memset(
							&link_format,
							0,
							sizeof(link_format)
						);
						link_format.cbSize =
							sizeof(link_format);
						link_format.dwMask = CFM_LINK;
						link_format.dwEffects = CFE_LINK;

						SendMessageW(
							chat,
							EM_SETCHARFORMAT,
							SCF_SELECTION,
							(LPARAM)&link_format
						);

						SendMessageW(
							chat,
							EM_SETSEL,
							INT_MAX - 1,
							INT_MAX - 1
						);

						added_video_thumb = true;
						added_doc = false;

						free(document.filename);
						free(document.file_reference);
						document.filename = NULL;
						document.file_reference = NULL;

						written += riched_write(
							chat,
							L"\n"
						);
					}
				}

				if (!added_video_thumb) {
					free(video_thumb_document.filename);
					free(video_thumb_document.file_reference);
					memset(
						&video_thumb_document,
						0,
						sizeof(video_thumb_document)
					);
				}
			}

			if (!added_video_thumb) {
				if (music)
					written += riched_write(chat, L"[>] " );

				written += riched_write(
					chat,
					document.filename
				);

				if (duration_str[0] == ' ')
					written += riched_write(
						chat,
						&duration_str[0]
					);

				written += riched_write(
					chat,
					&size_str[0]
				);

				if (music) {
					written += riched_write(chat, L"\n");

					HBITMAP audio_player =
						media_inline_audio_make_bitmap(
							media_duration_seconds,
							0,
							false,
							85
						);

					if (audio_player) {
						insert_image(
							chat,
							NULL,
							audio_player
						);

						DeleteObject(audio_player);
						written++;
					}
				}

				document.max =
					cr_startmsg.cpMin + written;
			}'''

    s = s[:start] + row_v56 + s[end:]

write(m, s)

checks_v56 = {
    t: [
        "media_tabs_av_runtime_v56",
        "inline audio switch hr=",
        "CreateMediaItemFromURL(",
        "SetMediaItem(",
    ],
    m: [
        "media_chat_video_unified_v56",
        "added_doc = false;",
        "link_format.dwEffects = CFE_LINK;",
    ],
}

for path, tokens in checks_v56.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"Media v5.6 verification failed in {path.name}: {token}"
            )

print(
    "Applied Media A/V v5.6: robust inline-audio track switching and unified "
    "clickable in-chat video preview cards."
)
