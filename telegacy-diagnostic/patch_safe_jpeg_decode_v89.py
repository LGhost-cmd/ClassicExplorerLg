#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_safe_jpeg_decode_v89.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
helpers = root / "src" / "helpers.cpp"
response = root / "src" / "response.cpp"

for path in (helpers, response):
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


s = read(helpers)

if "safe_jpeg_decode_v89" in s:
    print("Safe JPEG decode v8.9 already applied.")
    raise SystemExit(0)

include_anchor = "#include <telegacy.h>\n"
if include_anchor not in s:
    raise SystemExit("Could not locate helpers include anchor.")

s = s.replace(
    include_anchor,
    include_anchor + "#include <setjmp.h>\n",
    1,
)

fs, fe = function_range(s, "HBITMAP jpg_to_bmp(")

replacement = r'''// safe_jpeg_decode_v89
struct MediaChatJpegErrorV89 {
    jpeg_error_mgr pub;
    jmp_buf jump;
    char message[JMSG_LENGTH_MAX];
};

static void media_chat_jpeg_error_exit_v89(
    j_common_ptr common
) {
    MediaChatJpegErrorV89* error =
        (MediaChatJpegErrorV89*)common->err;

    error->message[0] = 0;

    if (common->err->format_message) {
        common->err->format_message(
            common,
            error->message
        );
    }

    longjmp(
        error->jump,
        1
    );
}

HBITMAP jpg_to_bmp(
    BYTE* myjpg,
    int myjpg_size
) {
    if (
        !myjpg ||
        myjpg_size < 4
    ) {
        diag_log(
            "chat v89 JPEG rejected empty/short bytes=%d",
            myjpg_size
        );
        return NULL;
    }

    // Telegram thumbs reaching this helper must be JPEG. v8.1 first tries
    // WebP for sticker thumbs; if the fallback is neither JPEG nor WebP,
    // never hand it to libjpeg's fatal parser.
    if (
        myjpg[0] != 0xFF ||
        myjpg[1] != 0xD8
    ) {
        diag_log(
            "chat v89 JPEG rejected signature bytes=%d first=%02X%02X%02X%02X",
            myjpg_size,
            (unsigned int)myjpg[0],
            (unsigned int)myjpg[1],
            (unsigned int)myjpg[2],
            (unsigned int)myjpg[3]
        );
        return NULL;
    }

    jpeg_decompress_struct cinfo;
    MediaChatJpegErrorV89 jerr;

    memset(
        &cinfo,
        0,
        sizeof(cinfo)
    );
    memset(
        &jerr,
        0,
        sizeof(jerr)
    );

    cinfo.err =
        jpeg_std_error(
            &jerr.pub
        );

    jerr.pub.error_exit =
        media_chat_jpeg_error_exit_v89;

    if (
        setjmp(
            jerr.jump
        )
    ) {
        if (cinfo.mem)
            jpeg_destroy_decompress(
                &cinfo
            );

        diag_log(
            "chat v89 JPEG decode recovered bytes=%d error=%s",
            myjpg_size,
            jerr.message[0]
                ? jerr.message
                : "libjpeg fatal error"
        );

        return NULL;
    }

    jpeg_create_decompress(
        &cinfo
    );

    jpeg_mem_src(
        &cinfo,
        myjpg,
        myjpg_size
    );

    if (
        jpeg_read_header(
            &cinfo,
            TRUE
        ) != JPEG_HEADER_OK
    ) {
        jpeg_destroy_decompress(
            &cinfo
        );

        diag_log(
            "chat v89 JPEG rejected header bytes=%d",
            myjpg_size
        );

        return NULL;
    }

    // rgb_to_bmp expects three channels when alpha == false.
    cinfo.out_color_space = JCS_RGB;

    jpeg_start_decompress(
        &cinfo
    );

    unsigned int width =
        cinfo.output_width;
    unsigned int height =
        cinfo.output_height;

    if (
        width == 0 ||
        height == 0 ||
        width > 8192 ||
        height > 8192 ||
        cinfo.output_components != 3
    ) {
        jpeg_abort_decompress(
            &cinfo
        );
        jpeg_destroy_decompress(
            &cinfo
        );

        diag_log(
            "chat v89 JPEG rejected dimensions=%ux%u components=%d bytes=%d",
            width,
            height,
            cinfo.output_components,
            myjpg_size
        );

        return NULL;
    }

    size_t row_bytes =
        (size_t)width * 3u;

    if (
        row_bytes / 3u != width ||
        height >
            (
                (size_t)-1 /
                row_bytes
            )
    ) {
        jpeg_abort_decompress(
            &cinfo
        );
        jpeg_destroy_decompress(
            &cinfo
        );

        diag_log(
            "chat v89 JPEG rejected allocation overflow dimensions=%ux%u",
            width,
            height
        );

        return NULL;
    }

    size_t total_bytes =
        row_bytes *
        (size_t)height;

    // A chat thumbnail has no legitimate reason to allocate hundreds of MB.
    if (
        total_bytes == 0 ||
        total_bytes >
            256u * 1024u * 1024u
    ) {
        jpeg_abort_decompress(
            &cinfo
        );
        jpeg_destroy_decompress(
            &cinfo
        );

        diag_log(
            "chat v89 JPEG rejected allocation bytes=%Iu dimensions=%ux%u",
            total_bytes,
            width,
            height
        );

        return NULL;
    }

    BYTE* rgb =
        (BYTE*)malloc(
            total_bytes
        );

    if (!rgb) {
        jpeg_abort_decompress(
            &cinfo
        );
        jpeg_destroy_decompress(
            &cinfo
        );

        diag_log(
            "chat v89 JPEG allocation failed bytes=%Iu dimensions=%ux%u",
            total_bytes,
            width,
            height
        );

        return NULL;
    }

    while (
        cinfo.output_scanline <
        cinfo.output_height
    ) {
        JSAMPROW row =
            rgb +
            (size_t)cinfo.output_scanline *
            row_bytes;

        if (
            jpeg_read_scanlines(
                &cinfo,
                &row,
                1
            ) != 1
        ) {
            free(rgb);

            jpeg_abort_decompress(
                &cinfo
            );
            jpeg_destroy_decompress(
                &cinfo
            );

            diag_log(
                "chat v89 JPEG scanline stalled line=%u/%u",
                cinfo.output_scanline,
                cinfo.output_height
            );

            return NULL;
        }
    }

    jpeg_finish_decompress(
        &cinfo
    );
    jpeg_destroy_decompress(
        &cinfo
    );

    HBITMAP bitmap = NULL;

    __try {
        bitmap =
            rgb_to_bmp(
                rgb,
                false,
                (int)width,
                (int)height
            );

        // rgb_to_bmp owns/frees rgb on its normal path.
        rgb = NULL;
    }
    __except (
        EXCEPTION_EXECUTE_HANDLER
    ) {
        DWORD code =
            GetExceptionCode();

        if (rgb)
            free(rgb);

        diag_log(
            "chat v89 JPEG bitmap conversion recovered exception=0x%08lX dimensions=%ux%u",
            code,
            width,
            height
        );

        return NULL;
    }

    if (!bitmap) {
        diag_log(
            "chat v89 JPEG bitmap conversion returned null dimensions=%ux%u",
            width,
            height
        );
    }

    return bitmap;
}'''

s = s[:fs] + replacement + s[fe:]
write(helpers, s)



# ---------------------------------------------------------------------------
# The v8.1 sticker thumbnail path had an ownership bug:
# WebPDecodeRGBA() -> rgb_to_bmp() -> WebPFree(rgba).
# rgb_to_bmp() already calls free(rgb), so the subsequent WebPFree was a
# second free of the same allocation. Depending on heap state this can terminate
# Telegacy on the next upload.file response with no SEH diagnostic at all.
# Transfer ownership to rgb_to_bmp exactly once and contain conversion faults.
# ---------------------------------------------------------------------------
s = read(response)

webp_old = r'''                        if (
                            rgba &&
                            width > 0 &&
                            height > 0
                        ) {
                            hClone =
                                rgb_to_bmp(
                                    rgba,
                                    true,
                                    width,
                                    height
                                );

                            WebPFree(rgba);
                        }
'''

webp_new = r'''                        if (
                            rgba &&
                            width > 0 &&
                            height > 0 &&
                            width <= 4096 &&
                            height <= 4096
                        ) {
                            // safe_jpeg_decode_v89 also fixes WebP ownership:
                            // rgb_to_bmp owns and frees its input on the normal
                            // path, so detach rgba before calling it. Never
                            // WebPFree the same pointer afterwards.
                            BYTE* owned_rgba = rgba;
                            rgba = NULL;

                            __try {
                                hClone =
                                    rgb_to_bmp(
                                        owned_rgba,
                                        true,
                                        width,
                                        height
                                    );
                            }
                            __except (
                                EXCEPTION_EXECUTE_HANDLER
                            ) {
                                diag_log(
                                    "chat v89 WebP bitmap conversion recovered exception=0x%08lX dimensions=%dx%d",
                                    GetExceptionCode(),
                                    width,
                                    height
                                );

                                hClone = NULL;
                            }
                        }

                        // Only buffers not transferred to rgb_to_bmp remain
                        // owned by libwebp here (for example rejected dimensions).
                        if (rgba) {
                            WebPFree(rgba);
                            rgba = NULL;
                        }
'''

if webp_old not in s:
    raise SystemExit(
        "Could not locate v8.1 WebP thumbnail ownership block."
    )

s = s.replace(
    webp_old,
    webp_new,
    1
)

write(response, s)

response_data = read(response)
for token in (
    "safe_jpeg_decode_v89 also fixes WebP ownership",
    "BYTE* owned_rgba = rgba;",
    "chat v89 WebP bitmap conversion recovered",
):
    if token not in response_data:
        raise SystemExit(
            f"v8.9 WebP ownership verification failed: {token}"
        )


data = read(helpers)
for token in (
    "safe_jpeg_decode_v89",
    "media_chat_jpeg_error_exit_v89",
    "setjmp(",
    "chat v89 JPEG rejected signature",
    "chat v89 JPEG decode recovered",
    "chat v89 JPEG bitmap conversion recovered",
):
    if token not in data:
        raise SystemExit(f"v8.9 verification failed: {token}")

print(
    "Applied safe media decode v8.9: the v8.1 WebP thumbnail double-free is removed "
    "by transferring RGBA ownership exactly once to rgb_to_bmp, conversion faults "
    "are contained, and invalid/unexpected JPEG fallback payloads can no longer "
    "terminate Telegacy through libjpeg's default fatal error handler."
)
