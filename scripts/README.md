# `trim_burst_edges.py`

`trim_burst_edges.py` creates cleaned copies of SAT RAW files by removing the first and last reading from each burst.

It is designed for mixed ASCII/binary RAW payloads where each reading looks like:

- ASCII line beginning with an instrument id (for example `SATCTD9264`)
- ASCII sensor data readings from the instrument, separated by white space
- CRLF `\r\n`
- 7 binary timestamp bytes:
- bytes 0-2: `YYYYDDD` (year + Julian day)
- bytes 3-6: `HHMMSSmmm` (UTC time including milliseconds)

Example: 
```
SATCTD9264   19.9636, 0.00010
æöËƒø
```

## What It Does

- Parses valid reading records from each `.raw` / `.RAW` file.
- Detects burst boundaries with one of:
- `header`: uses `SATHDR ... (TIME-STAMP)\r\n` markers.
- `gap`: uses timestamp jumps greater than `--gap-seconds` (defaults to 60 seconds).
- `auto` (default): tries `header`, falls back to `gap`.
- Optionally filters trimming to a single instrument prefix with `--instrument` (example: SATCTD).
- Removes only the first and last matching reading in each burst.
- Preserves all other bytes (including headers/padding/other instruments).

## Input And Output Behavior

- Input is one or more directories (`--input-dirs`).
- Discovery is recursive (`rglob`) within each input directory.
- Only files with extension `.raw` (case-insensitive) are processed.
- Output files are written under `--output-dir`, preserving each input directory name and subpath.

Example:

- Input file: `<inpur_dir>/data/2025336.RAW`
- Output dir: `<output_dir>/`
- Output file: `<output_dir>/<inpur_dir>/data/2025336.RAW`

## Usage

```bash
python scripts/trim_burst_edges.py \
  --input-dirs resource/data \
  --output-dir resource/cleaned
```

### Example usage (CTD only, header boundaries)

```bash
python scripts/trim_burst_edges.py \
  --input-dirs resource/data \
  --output-dir resource/cleaned \
  --burst-mode header \
  --instrument SATCTD
```

### Dry run (no files written)

```bash
python scripts/trim_burst_edges.py \
  --input-dirs resource/data \
  --output-dir resource/cleaned \
  --dry-run
```

### Multiple input directories

```bash
python scripts/trim_burst_edges.py \
  --input-dirs resource/data /path/to/other/raws \
  --output-dir resource/cleaned \
  --burst-mode auto
```

## Command-Line Options

- `--input-dirs`: One or more directories containing raw files. Required. Can be absolute paths, or relative to the current working directory.
- `--output-dir`: Base directory for cleaned output files. Required. Can be absolute path, or relative to the current working directory.
- `--burst-mode`: `auto`, `header`, or `gap`. Default `auto`.
- `--gap-seconds`: Gap threshold for `gap` mode. Default `60.0`.
- `--instrument`: Instrument prefix filter, for example `SATCTD`.
- `--dry-run`: Analyze and print results only; do not write files.

## Per-File Summary Output

For each processed file the script prints metrics, including:

- `parsed`: total records parsed from the file
- `target_records`: records eligible for trimming (after instrument filter)
- `bursts`: number of bursts detected
- `removed`: number of records removed
- `singleton_bursts`: bursts with only one matching target record
- `mode`: actual burst mode used (`header`, `gap`, or auto fallback result)
- `bytes_removed`: total bytes removed from the output payload
- `output`: output file path

## Notes

- `--instrument` uses prefix matching. `SATCTD` will match `SATCTD9264`.
- Header bytes are preserved. Only selected reading record byte ranges are removed.
- If two input directories would produce the same output relative path, the script reports an output collision.
