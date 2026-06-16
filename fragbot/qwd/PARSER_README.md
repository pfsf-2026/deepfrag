# QWD Usercmd Extractor

`tools/qwd_usercmd/qwd_usercmd.py` extracts raw client input commands from first-person QuakeWorld `.qwd` POV demos.

This is intentionally separate from the MVD pipeline. Normal server-side MVDs record broadcast state/events and do not carry exact player `usercmd_t` movement intent. POV `.qwd` demos do carry that command stream as `dem_cmd` records.

## Ground Truth

The parser is source-grounded in ezQuake:

- `src/cl_demo.c::CL_WriteDemoCmd()` writes `float demotime`, `byte dem_cmd`, a raw `usercmd_t`, then `12` bytes of viewangles.
- `src/cl_demo.c::CL_WriteDemoMessage()` writes `dem_read` records as `float`, `byte`, `int32 length`, and payload bytes.
- `src/qwprot/src/protocol.h::usercmd_t` defines the command layout.
- `src/com_msg.c::MSG_WriteDeltaUsercmd()` cross-checks the canonical command field set.

The validated `usercmd_t` layout is `24` bytes:

```text
byte msec
3 bytes padding
float angles[3]
short forwardmove
short sidemove
short upmove
byte buttons
byte impulse
```

## Usage

```powershell
python tools/qwd_usercmd/qwd_usercmd.py C:\path\to\demo.qwd --output artifacts/qwd-usercmd/demo.ndjson
```

Each output is line-delimited JSON:

- first row: `record_type="header"`, schema, source filename, SHA-256, clean EOF status, record counts, total frames, duration, command rate, and struct size
- following rows: `record_type="usercmd"`, `frame`, `time_s`, `msec`, `view_angles`, `forwardmove`, `sidemove`, `upmove`, `buttons`, `impulse`

Pass `--include-cmd-angles` to include the raw angles embedded inside the `usercmd_t` in addition to the following viewangle payload.

## Validation

Focused tests:

```powershell
python -m unittest tests.test_qwd_usercmd -v
```

Real-demo smoke example:

```powershell
python tools/qwd_usercmd/qwd_usercmd.py C:\Users\benya\projects\quakeworld\data\quake-development\clients\xerialqw-bench\qw\matchinfo\demos\tricks\dm2_bunny_to_gl.qwd --output artifacts/qwd-usercmd/dm2_bunny_to_gl.ndjson --include-cmd-angles --strict-plausibility
```

`artifacts/` is intentionally ignored. Keep raw/demo outputs there and promote only compact evidence into docs or committed experiment summaries.
