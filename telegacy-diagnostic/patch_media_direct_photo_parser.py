#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_media_direct_photo_parser.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for p in (t, r):
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


s = read(t)

if "media_archive_direct_photo_parser_v1" not in s:
    if "0x56e9f0e4" not in s and "0x9609a51c" not in s:
        raise SystemExit(
            "Could not locate Telegram Media search filter constructor."
        )

    s = s.replace(
        "// inputMessagesFilterPhotoVideo#56e9f0e4",
        "// inputMessagesFilterPhotos#9609a51c",
    )
    s = s.replace(
        "0x56e9f0e4",
        "0x9609a51c",
    )

    marker = "static bool media_archive_request_server_page_ex("
    pos = s.find(marker)
    if pos < 0:
        marker = "static bool media_archive_request_server_page("
        pos = s.find(marker)

    if pos < 0:
        raise SystemExit(
            "Could not locate Media server request function."
        )

    s = (
        s[:pos]
        + "// media_archive_direct_photo_parser_v1\n"
        + s[pos:]
    )

write(t, s)


s = read(r)

if "media_archive_extract_photo_document_v1" in s:
    print("Direct Media photo parser already applied.")
    raise SystemExit(0)

handler_signature = "static void media_archive_handle_server_response("
handler_start, handler_end = function_range(s, handler_signature)

helpers = r'''
// ======================================================================================
// Stable Media metadata parser
// ======================================================================================

// media_archive_extract_photo_document_v1

static bool media_archive_add_checked_offset(
    int* offset,
    int add,
    int available
) {
    if (
        !offset ||
        add < 0 ||
        *offset < 0 ||
        *offset > available ||
        add > available - *offset
    ) {
        return false;
    }

    *offset += add;
    return true;
}

static bool media_archive_message_envelope(
    BYTE* message,
    int available,
    int* consumed_out,
    int* message_id_out,
    BYTE** media_out,
    int* media_length_out
) {
    if (
        !message ||
        available < 12 ||
        !consumed_out ||
        !message_id_out ||
        !media_out ||
        !media_length_out
    ) {
        return false;
    }

    *consumed_out = 0;
    *message_id_out = 0;
    *media_out = NULL;
    *media_length_out = 0;

    int msg_cons = read_le(message, 4);
    int offset_msg = 4;

    if (offset_msg + 4 > available)
        return false;

    int flags_msg =
        read_le(
            message + offset_msg,
            4
        );

    if (msg_cons == 0x90a6ca84) {
        if (!media_archive_add_checked_offset(
            &offset_msg,
            8,
            available
        )) {
            return false;
        }

        if (flags_msg & (1 << 0)) {
            if (!media_archive_add_checked_offset(
                &offset_msg,
                12,
                available
            )) {
                return false;
            }
        }

        *consumed_out = offset_msg;
        return true;
    }

    bool service =
        msg_cons == 0xd3d28540;

    if (
        !service &&
        msg_cons != 0x96fdbbe9
    ) {
        diag_log(
            "media metadata unsupported message ctor=0x%08X",
            (unsigned int)msg_cons
        );
        return false;
    }

    int flags_msg2 = 0;

    if (!service) {
        if (offset_msg + 8 > available)
            return false;

        flags_msg2 =
            read_le(
                message + offset_msg + 4,
                4
            );
    } else {
        offset_msg -= 4;
    }

    if (offset_msg + 12 > available)
        return false;

    BYTE* msg_id =
        message +
        offset_msg +
        8;

    *message_id_out =
        read_le(
            msg_id,
            4
        );

    offset_msg += 12;

    if (flags_msg & (1 << 8)) {
        if (!media_archive_add_checked_offset(&offset_msg, 12, available))
            return false;
    }

    if (flags_msg & (1 << 29)) {
        if (!media_archive_add_checked_offset(&offset_msg, 4, available))
            return false;
    }

    if (!media_archive_add_checked_offset(&offset_msg, 12, available))
        return false;

    if (flags_msg & (1 << 28)) {
        if (!media_archive_add_checked_offset(&offset_msg, 12, available))
            return false;
    }

    if (flags_msg & (1 << 2)) {
        if (offset_msg + 4 > available)
            return false;

        int n = msgfwd_offset(message + offset_msg);

        if (
            n <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, n, available)
        ) {
            return false;
        }
    }

    if (flags_msg & (1 << 11)) {
        if (!media_archive_add_checked_offset(&offset_msg, 8, available))
            return false;
    }

    if (
        !service &&
        (flags_msg2 & (1 << 0))
    ) {
        if (!media_archive_add_checked_offset(&offset_msg, 8, available))
            return false;
    }

    if (flags_msg & (1 << 3)) {
        if (offset_msg + 4 > available)
            return false;

        int n = msgrpl_offset(message + offset_msg);

        if (
            n <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, n, available)
        ) {
            return false;
        }
    }

    if (!media_archive_add_checked_offset(&offset_msg, 4, available))
        return false;

    if (service) {
        if (offset_msg + 4 > available)
            return false;

        int n = msgact_offset(message + offset_msg);

        if (
            n <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, n, available)
        ) {
            return false;
        }
    } else {
        if (offset_msg >= available)
            return false;

        int text_len =
            tlstr_len(
                message + offset_msg,
                true
            );

        if (
            text_len <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, text_len, available)
        ) {
            return false;
        }

        if (flags_msg & (1 << 9)) {
            if (offset_msg + 4 > available)
                return false;

            BYTE* media =
                message +
                offset_msg;

            int media_len =
                messagemedia_offset(
                    media
                );

            if (
                media_len <= 0 ||
                media_len >
                    available -
                    offset_msg
            ) {
                return false;
            }

            *media_out = media;
            *media_length_out = media_len;

            offset_msg += media_len;
        }
    }

    if (flags_msg & (1 << 6)) {
        if (offset_msg + 4 > available)
            return false;

        int n = replymarkup_offset(message + offset_msg);

        if (
            n <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, n, available)
        ) {
            return false;
        }
    }

    if (flags_msg & (1 << 7)) {
        if (offset_msg + 8 > available)
            return false;

        int count =
            read_le(
                message + offset_msg + 4,
                4
            );

        if (count < 0 || count > 100000)
            return false;

        offset_msg += 8;

        for (int j = 0; j < count; j++) {
            if (offset_msg + 4 > available)
                return false;

            int n =
                msgent_offset(
                    message + offset_msg,
                    NULL
                );

            if (
                n <= 0 ||
                !media_archive_add_checked_offset(&offset_msg, n, available)
            ) {
                return false;
            }
        }
    }

    if (flags_msg & (1 << 10)) {
        if (!media_archive_add_checked_offset(&offset_msg, 8, available))
            return false;
    }

    if (flags_msg & (1 << 23)) {
        if (offset_msg + 16 > available)
            return false;

        int flags_msgrep =
            read_le(
                message +
                offset_msg +
                4,
                4
            );

        offset_msg += 16;

        if (flags_msgrep & (1 << 1)) {
            if (offset_msg + 8 > available)
                return false;

            int count =
                read_le(
                    message +
                    offset_msg +
                    4,
                    4
                );

            if (count < 0 || count > 100000)
                return false;

            offset_msg += 8;

            if (
                count >
                (available - offset_msg) / 12
            ) {
                return false;
            }

            offset_msg += count * 12;
        }

        if (flags_msgrep & (1 << 0)) {
            if (!media_archive_add_checked_offset(&offset_msg, 8, available))
                return false;
        }

        if (flags_msgrep & (1 << 2)) {
            if (!media_archive_add_checked_offset(&offset_msg, 4, available))
                return false;
        }

        if (flags_msgrep & (1 << 3)) {
            if (!media_archive_add_checked_offset(&offset_msg, 4, available))
                return false;
        }
    }

    if (flags_msg & (1 << 15)) {
        if (!media_archive_add_checked_offset(&offset_msg, 4, available))
            return false;
    }

    if (flags_msg & (1 << 16)) {
        if (offset_msg >= available)
            return false;

        int n =
            tlstr_len(
                message + offset_msg,
                true
            );

        if (
            n <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, n, available)
        ) {
            return false;
        }
    }

    if (flags_msg & (1 << 17)) {
        if (!media_archive_add_checked_offset(&offset_msg, 8, available))
            return false;
    }

    if (flags_msg & (1 << 20)) {
        if (offset_msg + 4 > available)
            return false;

        int n = msgreact_offset(message + offset_msg);

        if (
            n <= 0 ||
            !media_archive_add_checked_offset(&offset_msg, n, available)
        ) {
            return false;
        }
    }

    if (flags_msg & (1 << 22)) {
        if (offset_msg + 8 > available)
            return false;

        int count =
            read_le(
                message +
                offset_msg +
                4,
                4
            );

        if (count < 0 || count > 100000)
            return false;

        offset_msg += 8;

        for (int j = 0; j < count; j++) {
            if (!media_archive_add_checked_offset(&offset_msg, 4, available))
                return false;

            for (int k = 0; k < 3; k++) {
                if (offset_msg >= available)
                    return false;

                int n =
                    tlstr_len(
                        message +
                        offset_msg,
                        true
                    );

                if (
                    n <= 0 ||
                    !media_archive_add_checked_offset(&offset_msg, n, available)
                ) {
                    return false;
                }
            }
        }
    }

    if (flags_msg & (1 << 25)) {
        if (!media_archive_add_checked_offset(&offset_msg, 4, available))
            return false;
    }

    if (flags_msg & (1 << 30)) {
        if (!media_archive_add_checked_offset(&offset_msg, 4, available))
            return false;
    }

    if (
        !service &&
        (flags_msg2 & (1 << 2))
    ) {
        if (!media_archive_add_checked_offset(&offset_msg, 8, available))
            return false;
    }

    if (
        !service &&
        (flags_msg2 & (1 << 3))
    ) {
        if (offset_msg + 8 > available)
            return false;

        int flags_facts =
            read_le(
                message +
                offset_msg +
                4,
                4
            );

        offset_msg += 8;

        if (flags_facts & (1 << 1)) {
            if (offset_msg >= available)
                return false;

            int n =
                tlstr_len(
                    message +
                    offset_msg,
                    true
                );

            if (
                n <= 0 ||
                !media_archive_add_checked_offset(&offset_msg, n, available)
            ) {
                return false;
            }

            if (offset_msg + 4 > available)
                return false;

            n =
                textwithent_offset(
                    message +
                    offset_msg
                );

            if (
                n <= 0 ||
                !media_archive_add_checked_offset(&offset_msg, n, available)
            ) {
                return false;
            }
        }

        if (!media_archive_add_checked_offset(&offset_msg, 8, available))
            return false;
    }

    if (
        !service &&
        (flags_msg2 & (1 << 5))
    ) {
        if (!media_archive_add_checked_offset(&offset_msg, 4, available))
            return false;
    }

    *consumed_out = offset_msg;
    return true;
}

static void media_archive_free_document_fields(
    Document* document
) {
    if (!document)
        return;

    free(document->filename);
    free(document->file_reference);

    document->filename = NULL;
    document->file_reference = NULL;
}

static bool media_archive_extract_photo_document(
    BYTE* media,
    int media_length,
    int message_id,
    Document* document
) {
    if (
        !media ||
        !document ||
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

    // messageMediaPhoto#695150d7
    if (read_le(media, 4) != 0x695150d7)
        return false;

    int media_flags =
        read_le(
            media + 4,
            4
        );

    if (!(media_flags & (1 << 0)))
        return false;

    int photo_flags =
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

    int fileref_len =
        tlstr_len(
            media + 32,
            true
        );

    if (
        fileref_len <= 0 ||
        fileref_len >
            media_length - 32
    ) {
        return false;
    }

    document->file_reference =
        (BYTE*)malloc(
            fileref_len
        );

    if (!document->file_reference)
        return false;

    memcpy(
        document->file_reference,
        media + 32,
        fileref_len
    );

    document->filename =
        (wchar_t*)malloc(
            64 *
            sizeof(wchar_t)
        );

    if (!document->filename) {
        media_archive_free_document_fields(
            document
        );
        return false;
    }

    _snwprintf(
        document->filename,
        63,
        L"photo%08X.jpg",
        (unsigned int)read_le(
            document->access_hash + 4,
            4
        )
    );

    document->filename[63] = 0;

    int offset =
        44 +
        fileref_len;

    if (
        offset < 4 ||
        offset > media_length
    ) {
        media_archive_free_document_fields(
            document
        );
        return false;
    }

    int count =
        read_le(
            media +
            offset -
            4,
            4
        );

    if (count <= 0 || count > 128) {
        media_archive_free_document_fields(
            document
        );
        return false;
    }

    char size_main = 0;
    __int64 size_main_bytes = 0;

    for (int i = 0; i < count; i++) {
        if (offset + 24 > media_length) {
            media_archive_free_document_fields(
                document
            );
            return false;
        }

        int photosize_cons =
            read_le(
                media + offset,
                4
            );

        char size =
            (char)media[
                offset + 5
            ];

        int size_object_len =
            photo_video_size_offset(
                media + offset,
                true,
                false,
                false
            );

        if (
            size_object_len <= 0 ||
            size_object_len >
                media_length -
                offset
        ) {
            media_archive_free_document_fields(
                document
            );
            return false;
        }

        if (
            (size > size_main || size == 'w') &&
            size != 'i' &&
            size != 'j'
        ) {
            __int64 candidate_size = 0;

            if (photosize_cons == 0xfa3efb95) {
                int vector_count =
                    read_le(
                        media +
                        offset +
                        20,
                        4
                    );

                if (
                    vector_count < 0 ||
                    vector_count > 100000 ||
                    vector_count >
                        (
                            media_length -
                            offset -
                            24
                        ) / 4
                ) {
                    media_archive_free_document_fields(
                        document
                    );
                    return false;
                }

                int size_pos =
                    offset +
                    20 +
                    vector_count *
                    4;

                if (size_pos + 4 > media_length) {
                    media_archive_free_document_fields(
                        document
                    );
                    return false;
                }

                candidate_size =
                    read_le(
                        media +
                        size_pos,
                        4
                    );
            } else {
                candidate_size =
                    read_le(
                        media +
                        offset +
                        16,
                        4
                    );
            }

            size_main = size;
            size_main_bytes = candidate_size;
        }

        offset += size_object_len;
    }

    if (photo_flags & (1 << 1)) {
        if (offset + 4 > media_length) {
            media_archive_free_document_fields(
                document
            );
            return false;
        }

        int n =
            photo_video_size_offset(
                media + offset,
                false,
                false,
                true
            );

        if (
            n <= 0 ||
            n >
                media_length -
                offset
        ) {
            media_archive_free_document_fields(
                document
            );
            return false;
        }

        offset += n;
    }

    if (
        offset + 4 > media_length ||
        !size_main
    ) {
        media_archive_free_document_fields(
            document
        );
        return false;
    }

    document->dc =
        read_le(
            media + offset,
            4
        );

    document->size =
        size_main_bytes;

    document->photo_size =
        size_main;

    document->visible = false;
    document->min = -message_id;
    document->max = -message_id;

    memset(
        document->photo_msg_id,
        0,
        8
    );

    return true;
}

'''

s = s[:handler_start] + helpers + s[handler_start:]

handler_start, handler_end = function_range(
    s,
    handler_signature
)

new_handler = r'''static void media_archive_handle_server_response(
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
            "media metadata response vector failed ctor=0x%08X length=%d",
            constructor,
            length
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

    if (count < 0 || count > 1000) {
        diag_log(
            "media metadata invalid count=%d total=%d",
            count,
            total
        );

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

    for (int i = 0; i < count; i++) {
        if (
            offset < 0 ||
            offset >= length
        ) {
            diag_log(
                "media metadata page truncated item=%d offset=%d length=%d",
                i,
                offset,
                length
            );
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
                "media metadata envelope failed item=%d offset=%d ctor=0x%08X",
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
            diag_log(
                "media metadata invalid consumed item=%d consumed=%d remaining=%d",
                i,
                consumed,
                length - offset
            );
            break;
        }

        diag_log(
            "media metadata item=%d id=%d consumed=%d media_ctor=0x%08X",
            i,
            message_id,
            consumed,
            media
                ? (unsigned int)read_le(media, 4)
                : 0
        );

        if (message_id > 0)
            last_id = message_id;

        if (media) {
            Document document;

            if (media_archive_extract_photo_document(
                media,
                media_length,
                message_id,
                &document
            )) {
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
            } else {
                diag_log(
                    "media metadata photo extraction skipped item=%d id=%d media_ctor=0x%08X",
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
        "media metadata page complete raw=%d parsed=%d added=%d total=%d last_id=%d",
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

    if (added_count > 0) {
        media_archive_start_next_download();
    }
}'''

s = (
    s[:handler_start]
    + new_handler
    + s[handler_end:]
)

required = [
    "media_archive_extract_photo_document_v1",
    "media_archive_message_envelope(",
    "media metadata page complete",
    "media_archive_extract_photo_document(",
]

for token in required:
    if token not in s:
        raise SystemExit(
            "Internal verification failed: " + token
        )

write(r, s)

print(
    "Applied stable direct photo-only Media parser. "
    "Hidden RichEdit/message_handler is no longer used for gallery pages."
)
