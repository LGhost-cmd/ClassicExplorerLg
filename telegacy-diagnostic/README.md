# Telegacy 1.0.4 diagnostic build

This package creates a diagnostic build from the exact upstream `v1.0.4` tag.

It targets the reproducible startup crash after login while Telegacy shows
"Updating data...". The Windows Error Reporting entry showed:

- exception `0xC0000005`
- faulting module `telegacy.exe`
- repeatable fault offset `0x00001AEF`

## Instrumentation

The patch adds `%TEMP%\Telegacy-diagnostic.log` and records:

- response constructor IDs and lengths
- peers/total/folder counts during initial sync
- gzip-packed responses
- `messages.dialogs` / `messages.dialogsSlice`
- `messages.dialogFilters`
- `folder_handler`
- unhandled exception code/address and x86 registers

It does not record message bodies, passwords, phone numbers, authentication
tokens, or session.dat contents.

The diagnostic patch also guards upstream `array_find`. In v1.0.4 it scans
forever without a buffer length if a requested constructor is absent. That is a
plausible source of the repeatable access violation. Successful normal searches
are unchanged; an invalid/unbounded scan is logged before terminating.

## Build via GitHub Actions

Copy these directories into the root of a GitHub repository:

- `.github`
- `telegacy-diagnostic`

Commit them, then open:

**Actions -> Build Telegacy diagnostic -> Run workflow**

The workflow clones the exact Telegacy v1.0.4 source, applies the patch, builds
32-bit RelWithDebInfo using MSVC/vcpkg, and uploads the artifact
`Telegacy-1.0.4-diagnostic-x86`.

The upstream project officially builds with Visual C++ 6.0 SP6, an old Platform
SDK, and a separate library pack. This CI recipe deliberately uses modern MSVC
with compatibility flags. If the first Actions run exposes old-source
compatibility errors, the next step is to patch only those compiler issues.

## Test

Do not overwrite your installed Telegacy yet.

1. Put the diagnostic EXE in a separate folder.
2. Copy next to it the runtime folders/files from the normal Telegacy install
   that it needs (`langs`, Rich Edit DLL/assets if present).
3. Run the diagnostic EXE.
4. After it stops, open:

   `%TEMP%\Telegacy-diagnostic.log`

Send that file back for analysis.
