# Pod Data Cleaning

This repository provides standalone executables that trim burst-edge records from SAT RAW files.

## Download

From GitHub Releases, download:

- `pod-data-cleaning-windows.zip`
- `pod-data-cleaning-linux.zip`
- `pod-data-cleaning-macos.zip`

Each ZIP contains:

- platform executable (`pod-data-cleaning.exe` on Windows, `pod-data-cleaning` on Linux/macOS)
- `README.md`

## Quick Start (Windows)

1. Extract `pod-data-cleaning-windows.zip`.
2. Open PowerShell in the extracted folder.
3. Run:

```powershell
.\pod-data-cleaning.exe --input-dirs "C:\path\to\input" --output-dir "C:\path\to\output"
```

## Quick Start (Linux)

1. Extract `pod-data-cleaning-linux.zip`.
2. Open a terminal in the extracted folder.
3. Make the binary executable and run:

```bash
chmod +x ./pod-data-cleaning
./pod-data-cleaning --input-dirs "/path/to/input" --output-dir "/path/to/output"
```

## Quick Start (macOS)

1. Extract `pod-data-cleaning-macos.zip`.
2. Open Terminal in the extracted folder.
3. Make the binary executable and run:

```bash
chmod +x ./pod-data-cleaning
./pod-data-cleaning --input-dirs "/path/to/input" --output-dir "/path/to/output"
```

If macOS blocks first launch, remove quarantine and retry:

```bash
xattr -d com.apple.quarantine ./pod-data-cleaning
```

## Required Inputs

- `--input-dirs`: one or more directories to search recursively for `.raw` / `.RAW` files
- `--output-dir`: output directory for cleaned files

If either required argument is omitted in an interactive terminal, the app will prompt for it.

## Common Options

- `--gap-seconds 60` (default: `60`)
- `--burst-mode auto|header|gap` (default: `auto`)
- `--instrument SATABC1234` (optional prefix filter)
- `--dry-run` (analyze only; do not write output)

## Examples

Single input directory:

```powershell
.\pod-data-cleaning.exe --input-dirs "C:\raw-data" --output-dir "C:\cleaned-data"
```

Multiple input directories:

```powershell
.\pod-data-cleaning.exe --input-dirs "C:\raw-a" "D:\raw-b" --output-dir "C:\cleaned-data"
```

Dry run:

```powershell
.\pod-data-cleaning.exe --input-dirs "C:\raw-data" --output-dir "C:\cleaned-data" --dry-run
```

Linux/macOS dry run:

```bash
./pod-data-cleaning --input-dirs "/path/to/raw-data" --output-dir "/path/to/cleaned-data" --dry-run
```

## Build Notes

The GitHub Actions workflow builds and publishes Windows, Linux, and macOS packages on tag pushes and release publish events.
