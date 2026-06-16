#!/usr/bin/env python3
"""Extract raw usercmd records from QuakeWorld POV QWD demos.

Ground truth for the on-disk command record is ezQuake `cl_demo.c::CL_WriteDemoCmd`:
record time float32, record type byte, raw 24-byte `usercmd_t`, then three view-angle
float32 values. The `usercmd_t` layout is from qwprot `protocol.h`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


SCHEMA = "komodobots.qwd_usercmd.v1"

DEM_CMD = 0
DEM_READ = 1
DEM_SET = 2
DEM_MULTIPLE = 3
DEM_SINGLE = 4
DEM_STATS = 5
DEM_ALL = 6

USERCMD_STRUCT_FORMAT = "<BxxxfffhhhBB"
USERCMD_STRUCT_SIZE = struct.calcsize(USERCMD_STRUCT_FORMAT)
VIEW_ANGLES_FORMAT = "<fff"
VIEW_ANGLES_SIZE = struct.calcsize(VIEW_ANGLES_FORMAT)
RECORD_HEADER_FORMAT = "<fB"
RECORD_HEADER_SIZE = struct.calcsize(RECORD_HEADER_FORMAT)

MAX_REASONABLE_MESSAGE_BYTES = 16 * 1024 * 1024
MAX_REASONABLE_ABS_MOVE = 2000


class QwdUsercmdError(RuntimeError):
    """Raised when a QWD file cannot be walked without misalignment."""


@dataclass(frozen=True)
class UsercmdRecord:
    frame: int
    time_s: float
    msec: int
    view_angles: tuple[float, float, float]
    forwardmove: int
    sidemove: int
    upmove: int
    buttons: int
    impulse: int
    cmd_angles: tuple[float, float, float]
    file_offset: int

    def to_json_obj(self, *, include_cmd_angles: bool = False) -> dict[str, object]:
        row: dict[str, object] = {
            "schema": SCHEMA,
            "record_type": "usercmd",
            "frame": self.frame,
            "time_s": round(self.time_s, 6),
            "msec": self.msec,
            "view_angles": [round(value, 6) for value in self.view_angles],
            "forwardmove": self.forwardmove,
            "sidemove": self.sidemove,
            "upmove": self.upmove,
            "buttons": self.buttons,
            "impulse": self.impulse,
        }
        if include_cmd_angles:
            row["cmd_angles"] = [round(value, 6) for value in self.cmd_angles]
        return row


@dataclass(frozen=True)
class QwdParseResult:
    commands: list[UsercmdRecord]
    header: dict[str, object]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_available(data: bytes, cursor: int, size: int, context: str) -> None:
    if cursor + size > len(data):
        raise QwdUsercmdError(
            f"Truncated QWD while {context}: need {size} bytes at offset {cursor}, "
            f"file has {len(data)} bytes."
        )


def read_int32(data: bytes, cursor: int, context: str) -> tuple[int, int]:
    require_available(data, cursor, 4, context)
    return struct.unpack_from("<i", data, cursor)[0], cursor + 4


def parse_usercmd(payload: bytes, *, file_offset: int, frame: int, time_s: float, view_angles: tuple[float, float, float]) -> UsercmdRecord:
    if len(payload) != USERCMD_STRUCT_SIZE:
        raise QwdUsercmdError(f"usercmd payload must be {USERCMD_STRUCT_SIZE} bytes, got {len(payload)}.")
    msec, pitch, yaw, roll, forward, side, up, buttons, impulse = struct.unpack(USERCMD_STRUCT_FORMAT, payload)
    return UsercmdRecord(
        frame=frame,
        time_s=time_s,
        msec=msec,
        view_angles=view_angles,
        forwardmove=forward,
        sidemove=side,
        upmove=up,
        buttons=buttons,
        impulse=impulse,
        cmd_angles=(pitch, yaw, roll),
        file_offset=file_offset,
    )


def validate_command_plausibility(commands: list[UsercmdRecord]) -> list[str]:
    warnings: list[str] = []
    absurd_rows = [
        cmd.frame
        for cmd in commands
        if max(abs(cmd.forwardmove), abs(cmd.sidemove), abs(cmd.upmove)) > MAX_REASONABLE_ABS_MOVE
    ]
    if absurd_rows:
        warnings.append(
            "Some usercmd move values exceed "
            f"{MAX_REASONABLE_ABS_MOVE}; first frames: {absurd_rows[:10]}"
        )
    nonfinite_angles = [
        cmd.frame
        for cmd in commands
        if not all(math.isfinite(value) for value in (*cmd.view_angles, *cmd.cmd_angles))
    ]
    if nonfinite_angles:
        warnings.append(f"Some usercmd angles are non-finite; first frames: {nonfinite_angles[:10]}")
    return warnings


def parse_qwd_bytes(
    data: bytes,
    *,
    source_path: Path | None = None,
    strict_plausibility: bool = False,
) -> QwdParseResult:
    cursor = 0
    frame = 0
    last_time: float | None = None
    first_time: float | None = None
    commands: list[UsercmdRecord] = []
    warnings: list[str] = []
    record_counts: dict[str, int] = {
        "dem_cmd": 0,
        "dem_read": 0,
        "dem_set": 0,
        "dem_multiple": 0,
        "dem_single": 0,
        "dem_stats": 0,
        "dem_all": 0,
    }

    while cursor < len(data):
        record_offset = cursor
        require_available(data, cursor, RECORD_HEADER_SIZE, "reading QWD record header")
        demotime, raw_type = struct.unpack_from(RECORD_HEADER_FORMAT, data, cursor)
        cursor += RECORD_HEADER_SIZE
        message_type = raw_type & 7
        if not math.isfinite(demotime):
            raise QwdUsercmdError(f"Non-finite QWD demotime at offset {record_offset}: {demotime!r}.")
        if first_time is None:
            first_time = demotime
        if last_time is not None and demotime + 0.001 < last_time:
            warnings.append(
                f"Record time decreased at offset {record_offset}: {demotime:.6f} after {last_time:.6f}."
            )
        last_time = demotime

        if message_type == DEM_CMD:
            record_counts["dem_cmd"] += 1
            require_available(data, cursor, USERCMD_STRUCT_SIZE, "reading dem_cmd usercmd_t")
            usercmd_payload = data[cursor : cursor + USERCMD_STRUCT_SIZE]
            cursor += USERCMD_STRUCT_SIZE
            require_available(data, cursor, VIEW_ANGLES_SIZE, "reading dem_cmd viewangles")
            view_angles = struct.unpack_from(VIEW_ANGLES_FORMAT, data, cursor)
            cursor += VIEW_ANGLES_SIZE
            commands.append(
                parse_usercmd(
                    usercmd_payload,
                    file_offset=record_offset,
                    frame=frame,
                    time_s=demotime,
                    view_angles=view_angles,
                )
            )
            frame += 1
            continue

        if message_type == DEM_SET:
            record_counts["dem_set"] += 1
            require_available(data, cursor, 8, "reading dem_set sequence numbers")
            cursor += 8
            continue

        if message_type == DEM_MULTIPLE:
            record_counts["dem_multiple"] += 1
            require_available(data, cursor, 4, "reading dem_multiple player mask")
            cursor += 4
            cursor = skip_length_prefixed_message(data, cursor, "dem_multiple payload")
            continue

        if message_type in (DEM_READ, DEM_SINGLE, DEM_STATS, DEM_ALL):
            name = {
                DEM_READ: "dem_read",
                DEM_SINGLE: "dem_single",
                DEM_STATS: "dem_stats",
                DEM_ALL: "dem_all",
            }[message_type]
            record_counts[name] += 1
            cursor = skip_length_prefixed_message(data, cursor, f"{name} payload")
            continue

        raise QwdUsercmdError(f"Unsupported QWD record type {message_type} at offset {record_offset}.")

    warnings.extend(validate_command_plausibility(commands))
    if strict_plausibility and warnings:
        raise QwdUsercmdError("; ".join(warnings))

    duration = 0.0
    if first_time is not None and last_time is not None:
        duration = max(0.0, last_time - first_time)
    command_rate = round(len(commands) / duration, 3) if duration > 0 else None
    source_name = source_path.name if source_path else ""
    source_value = str(source_path) if source_path else ""
    header = {
        "schema": SCHEMA,
        "record_type": "header",
        "source_filename": source_name,
        "source_path": source_value,
        "source_sha256": sha256_bytes(data),
        "file_size_bytes": len(data),
        "bytes_read": cursor,
        "eof_clean": cursor == len(data),
        "total_records": sum(record_counts.values()),
        "record_counts": record_counts,
        "total_frames": len(commands),
        "total_duration_s": round(duration, 6),
        "command_rate_fps": command_rate,
        "usercmd_struct_size": USERCMD_STRUCT_SIZE,
        "usercmd_layout": "byte msec; 3 bytes pad; float angles[3]; short forward/sidemove/upmove; byte buttons; byte impulse",
        "view_angle_payload_size": VIEW_ANGLES_SIZE,
        "warnings": warnings,
    }
    return QwdParseResult(commands=commands, header=header)


def skip_length_prefixed_message(data: bytes, cursor: int, context: str) -> int:
    length, cursor = read_int32(data, cursor, f"reading {context} length")
    if length < 0:
        raise QwdUsercmdError(f"Negative {context} length {length} at offset {cursor - 4}.")
    if length > MAX_REASONABLE_MESSAGE_BYTES:
        raise QwdUsercmdError(f"Unreasonable {context} length {length} at offset {cursor - 4}.")
    require_available(data, cursor, length, f"reading {context}")
    return cursor + length


def parse_qwd_path(path: Path, *, strict_plausibility: bool = False) -> QwdParseResult:
    data = path.read_bytes()
    return parse_qwd_bytes(data, source_path=path, strict_plausibility=strict_plausibility)


def iter_ndjson(result: QwdParseResult, *, include_cmd_angles: bool = False) -> Iterator[str]:
    yield json.dumps(result.header, sort_keys=True)
    for command in result.commands:
        yield json.dumps(command.to_json_obj(include_cmd_angles=include_cmd_angles), sort_keys=True)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract raw usercmd records from a QuakeWorld POV .qwd demo.")
    parser.add_argument("demo", type=Path, help="Path to a first-person QuakeWorld .qwd demo.")
    parser.add_argument("--output", type=Path, help="Write line-delimited JSON to this path instead of stdout.")
    parser.add_argument(
        "--include-cmd-angles",
        action="store_true",
        help="Include raw usercmd_t angles in each row in addition to the recorded view angles.",
    )
    parser.add_argument(
        "--strict-plausibility",
        action="store_true",
        help="Fail if decoded command values look physically implausible.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] = sys.argv[1:]) -> int:
    args = parse_args(argv)
    result = parse_qwd_path(args.demo, strict_plausibility=args.strict_plausibility)
    lines = "\n".join(iter_ndjson(result, include_cmd_angles=args.include_cmd_angles)) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(lines, encoding="utf-8")
    else:
        sys.stdout.write(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

