#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


SAT_PREFIX = b"SAT"
CRLF = b"\r\n"
HEADER_MARKER = b"SATHDR "
HEADER_SUFFIX = b"(TIME-STAMP)\r\n"
INSTRUMENT_RE = re.compile(rb"^(SAT[A-Z]{3}\d{4})")


@dataclass(frozen=True)
class Record:
    start: int
    end: int
    instrument: str
    timestamp: datetime


def decode_timestamp(raw: bytes) -> datetime | None:
    """
    Decodes a 7-byte timestamp into a datetime object. Timestamp is expected to be in the following format:
    Bytes 0-2 (inclusive): YYYYDDD - YYYY is the year, DDD is the Julian day of the year. Jan 1st would be 001.
    Bytes 3-6 (inclusive): HHMMSSmmm - HH=hours, MM-minutes, SS=seconds, mmmm=milliseconds. UTC time.

    Args:
        raw: Raw binary payload to decode.

    Returns: Decoded datetime object.
    """

    if len(raw) != 7:
        return None

    date_value = int.from_bytes(raw[:3], "big")
    time_value = int.from_bytes(raw[3:], "big")

    year = date_value // 1000
    day_of_year = date_value % 1000
    if year < 1900 or year > 3000 or day_of_year < 1 or day_of_year > 366:
        return None

    hhmmssmmm = f"{time_value:09d}"
    hour = int(hhmmssmmm[0:2])
    minute = int(hhmmssmmm[2:4])
    second = int(hhmmssmmm[4:6])
    millisecond = int(hhmmssmmm[6:9])

    if hour > 23 or minute > 59 or second > 59 or millisecond > 999:
        return None

    try:
        # build the datetime as 01-01-YYYYT00:00:00:00 then add timedelta to get final datetime
        return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(
            days=day_of_year - 1,
            hours=hour,
            minutes=minute,
            seconds=second,
            milliseconds=millisecond,
        )
    except ValueError:
        return None


def extract_instrument(line: bytes) -> str:
    """Extract the instrument id from a record line, or return an empty string."""
    match = INSTRUMENT_RE.match(line)
    if not match:
        return ""
    return match.group(1).decode("ascii", errors="ignore")


def parse_records(data: bytes) -> list[Record]:
    """Parse valid SAT records from a mixed binary/text payload."""
    records: list[Record] = []
    cursor = 0
    data_len = len(data)

    while cursor < data_len:
        # find the next instance of "SAT" starting from cursor position
        start = data.find(SAT_PREFIX, cursor)
        if start == -1:
            break

        line_end = data.find(CRLF, start)
        if line_end == -1:
            break

        # timestamp starts after the two CRLF bytes
        ts_start = line_end + 2
        ts_end = ts_start + 7
        if ts_end > data_len:
            break

        # Reject obvious false positives by requiring a valid date/time payload.
        timestamp = decode_timestamp(data[ts_start:ts_end])
        if timestamp is None:
            cursor = start + 1
            continue

        # When possible, require the next record boundary to also look like SAT*. (headers also start with SAT)
        if ts_end < data_len and data[ts_end : ts_end + 3] != SAT_PREFIX:
            # Keep a valid final record even if a file has trailing footer bytes.
            if data.find(SAT_PREFIX, ts_end) != -1:
                cursor = start + 1
                continue

        instrument = extract_instrument(data[start:line_end])
        if not instrument:
            cursor = start + 1
            continue

        records.append(
            Record(
                start=start,
                end=ts_end,
                instrument=instrument,
                timestamp=timestamp,
            )
        )
        cursor = ts_end

    return records


def split_bursts_by_gap(records: list[Record], gap_seconds: float) -> list[tuple[int, int]]:
    """Split records into burst index ranges using timestamp gaps."""
    if not records:
        return []

    bursts: list[tuple[int, int]] = []
    burst_start = 0
    for idx in range(len(records) - 1):
        if (records[idx + 1].timestamp - records[idx].timestamp).total_seconds() > gap_seconds:
            bursts.append((burst_start, idx))
            burst_start = idx + 1
    bursts.append((burst_start, len(records) - 1))
    return bursts


def split_bursts_by_headers(data: bytes, records: list[Record]) -> list[tuple[int, int]]:
    """Split records into burst index ranges using SATHDR header markers."""
    if not records:
        return []

    record_starts = [record.start for record in records]
    starts: list[int] = []
    cursor = 0

    while True:
        hdr_start = data.find(HEADER_MARKER, cursor)
        if hdr_start == -1:
            break

        line_end = data.find(CRLF, hdr_start)
        if line_end == -1:
            break

        line = data[hdr_start : line_end + 2]
        cursor = line_end + 2
        # keep looping until we find the HEADER_SUFFIX
        if not line.endswith(HEADER_SUFFIX):
            continue

        idx = bisect.bisect_left(record_starts, line_end + 2)
        if idx < len(records):
            starts.append(idx)

    if not starts:
        return []

    # starts is the index where a new burst starts in the list of records
    starts = sorted(set(starts))
    if starts[0] != 0:
        starts.insert(0, 0)

    bursts: list[tuple[int, int]] = []
    for pos, burst_start in enumerate(starts):
        # burst ends at the index before the next burst starts.
        # If it is the last burst, it ends at the index of the final record.
        burst_end = starts[pos + 1] - 1 if pos + 1 < len(starts) else len(records) - 1
        if burst_start <= burst_end:
            bursts.append((burst_start, burst_end))
    return bursts


def filtered_indices_for_burst(
    records: list[Record], burst_start: int, burst_end: int, instrument_filter: str | None
) -> list[int]:
    """Return record indices in a burst, optionally filtered by instrument prefix."""
    if instrument_filter is None:
        return list(range(burst_start, burst_end + 1))

    return [
        idx
        for idx in range(burst_start, burst_end + 1)
        if records[idx].instrument == instrument_filter
        or records[idx].instrument.startswith(instrument_filter)
    ]


def select_bursts(
    data: bytes, records: list[Record], gap_seconds: float, burst_mode: str
) -> tuple[list[tuple[int, int]], str]:
    """Choose burst boundaries based on mode and return ranges with the chosen mode label."""
    if burst_mode == "header":
        header_bursts = split_bursts_by_headers(data, records)
        return header_bursts, "header"

    if burst_mode == "gap":
        return split_bursts_by_gap(records, gap_seconds), "gap"

    # auto - try header first, then fallback to gap
    header_bursts = split_bursts_by_headers(data, records)
    if header_bursts:
        return header_bursts, "header(auto)"
    return split_bursts_by_gap(records, gap_seconds), "gap(auto)"


def split_bursts(indices: list[int], records: list[Record], gap_seconds: float) -> list[list[int]]:
    """Backward-compatible helper that splits a provided index list by timestamp gaps."""
    # Backward-compatible helper retained for any external imports.
    if not indices:
        return []

    bursts: list[list[int]] = []
    burst_start = 0
    for pos in range(len(indices) - 1):
        left = records[indices[pos]].timestamp
        right = records[indices[pos + 1]].timestamp
        if (right - left).total_seconds() > gap_seconds:
            bursts.append(indices[burst_start : pos + 1])
            burst_start = pos + 1

    bursts.append(indices[burst_start:])
    return bursts


def remove_records(data: bytes, records: list[Record], remove_indices: set[int]) -> bytes:
    """
    Returns a new payload with flagged records removed.

    Args:
        data: The original binary payload of the file.
        records: List of Records in the file
        remove_indices: List of indices to remove records from (from the 'records' parameter)

    Returns: New payload with flagged records removed.

    """
    if not remove_indices:
        return data

    chunks: list[bytes] = []
    cursor = 0
    for idx, record in enumerate(records):
        if idx not in remove_indices:
            continue
        chunks.append(data[cursor : record.start])
        cursor = record.end
    chunks.append(data[cursor:])
    return b"".join(chunks)


def clean_file(
    input_path: Path,
    output_path: Path,
    *,
    gap_seconds: float,
    instrument_filter: str | None,
    burst_mode: str,
    dry_run: bool,
) -> tuple[int, int, int, int]:
    """Clean one input file and optionally write its cleaned copy to disk."""
    source = input_path.read_bytes()
    records = parse_records(source)

    bursts, chosen_mode = select_bursts(source, records, gap_seconds, burst_mode)

    remove_indices: set[int] = set()
    singleton_bursts = 0
    target_count = 0
    for burst_start, burst_end in bursts:
        # lists the indexes in records for a burst.
        # Optionally filters to only return indexes that are for the instrument in instrument_filter
        burst_indices = filtered_indices_for_burst(records, burst_start, burst_end, instrument_filter)
        target_count += len(burst_indices)
        if len(burst_indices) == 1:
            singleton_bursts += 1
            continue
        if len(burst_indices) >= 2:
            # remove the first and last indices from a burst
            remove_indices.add(burst_indices[0])
            remove_indices.add(burst_indices[-1])

    cleaned = remove_records(source, records, remove_indices)

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(cleaned)

    print(
        f"\"{input_path}\": parsed={len(records)} | target_records={target_count} | "
        f"bursts={len(bursts)} | removed={len(remove_indices)} "
        f"singleton_bursts={singleton_bursts} | mode={chosen_mode} "
        f"bytes_removed={len(source) - len(cleaned)} | "
        f"output={output_path}"
    )

    return len(records), target_count, len(bursts), len(remove_indices)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for burst-edge trimming."""
    parser = argparse.ArgumentParser(
        description=(
            "Create cleaned copies of SAT RAW files in a directory by removing the "
            "first and last reading from each timestamp-defined burst."
        )
    )
    parser.add_argument(
        "--input-dirs",
        type=Path,
        nargs="+",
        help=(
            "One or more directories containing input RAW files (.raw or .RAW). "
            "If omitted, you will be prompted."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory where cleaned copies are written. If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--gap-seconds",
        type=float,
        default=60.0,
        help="Gap threshold (seconds) that starts a new burst. Default: 60.",
    )
    parser.add_argument(
        "--burst-mode",
        choices=("auto", "header", "gap"),
        default="auto",
        help="Burst detection method. Default: auto (prefer headers, fallback to gap).",
    )
    parser.add_argument(
        "--instrument",
        type=str,
        default=None,
        help=(
            "If set, only trim burst edges for records whose instrument starts with this value. "
            "If omitted in an interactive session, you will be prompted."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and report only; do not write files.",
    )
    args = parser.parse_args()
    return prompt_for_missing_required_args(args, parser)


def prompt_for_input_dirs() -> list[Path]:
    """Prompt for one or more input directories."""
    print("Missing required argument: --input-dirs")
    print("Enter one input directory per line. Press Enter on a blank line when done.")

    input_dirs: list[Path] = []
    while True:
        raw = input(f"Input directory {len(input_dirs) + 1}: ").strip()
        if not raw:
            if input_dirs:
                return input_dirs
            print("At least one input directory is required.")
            continue
        input_dirs.append(Path(raw))


def prompt_for_output_dir() -> Path:
    """Prompt for output directory."""
    print("Missing required argument: --output-dir")
    while True:
        raw = input("Output directory: ").strip()
        if raw:
            return Path(raw)
        print("Output directory is required.")


def prompt_for_instrument_filter() -> str | None:
    """Prompt for optional instrument prefix."""
    print("Optional argument not provided: --instrument")
    raw = input("Instrument prefix (leave blank for no filter): ").strip()
    return raw or None


def prompt_for_missing_required_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> argparse.Namespace:
    """Prompt for missing required args and optional instrument when interactive."""
    missing: list[str] = []
    if not args.input_dirs:
        missing.append("--input-dirs")
    if args.output_dir is None:
        missing.append("--output-dir")

    if not sys.stdin.isatty():
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
        return args

    try:
        if not args.input_dirs:
            args.input_dirs = prompt_for_input_dirs()
        if args.output_dir is None:
            args.output_dir = prompt_for_output_dir()
        if args.instrument is None:
            args.instrument = prompt_for_instrument_filter()
    except (EOFError, KeyboardInterrupt):
        print("\nInput cancelled.", file=sys.stderr)
        raise SystemExit(1)

    return args


def list_raw_files(input_dir: Path) -> list[tuple[Path, Path]]:
    """Return sorted (absolute_path, relative_path) pairs for .raw/.RAW files under a directory."""
    files: list[tuple[Path, Path]] = []
    for path in input_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".raw":
            continue
        files.append((path, input_dir.name / path.relative_to(input_dir)))
    return sorted(files, key=lambda item: str(item[1]))


def main() -> int:
    """CLI entry point."""
    args = parse_args()

    input_dirs: list[Path] = args.input_dirs

    valid_dirs: list[Path] = []
    missing_dirs: list[Path] = []
    for d in input_dirs:
        if not d.exists() or not d.is_dir():
            missing_dirs.append(d)
        else:
            valid_dirs.append(d)

    input_dirs = valid_dirs

    if missing_dirs:
        for input_dir in missing_dirs:
            print(f"{input_dir}: directory not found or not a directory.", file=sys.stderr)
        if not input_dirs:
            return 1

    # tuple[Path, Path] is (absolute_path, path_relative_to_input_dir)
    input_files: list[tuple[Path, Path]] = []
    for input_dir in input_dirs:
        input_files.extend(list_raw_files(input_dir))

    if not input_files:
        print("No .raw/.RAW files found in the provided input directories.", file=sys.stderr)
        return 1

    failures = 0
    output_rel_map: dict[Path, Path] = {}
    for input_path, rel_path in input_files:
        prior = output_rel_map.get(rel_path)
        if prior is not None and prior != input_path:
            print(
                f"Output collision for relative path {rel_path}: "
                f"{prior} and {input_path}. Use distinct input directories."
            )
            failures += 1
            continue
        output_rel_map[rel_path] = input_path

        output_path = args.output_dir / rel_path
        clean_file(
            input_path=input_path,
            output_path=output_path,
            gap_seconds=args.gap_seconds,
            instrument_filter=args.instrument,
            burst_mode=args.burst_mode,
            dry_run=args.dry_run,
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
