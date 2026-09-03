# HW2A000FF — All-Platform Remake

Convert **Hammerwatch** (HWM) assets into the **A000FF** format used by *Heroes
of Hammerwatch*, *Hammerwatch II* and the *Hammerwatch Anniversary Edition*.

This is a cross-platform Python port of
[bennpham/hw2a000ff](https://github.com/bennpham/hw2a000ff), a Windows-only
C# WinForms tool. It runs on Linux, macOS and Windows, works as a command-line
program or an importable library, and — unlike the original — tells you which
path is wrong when something is missing.

```
hw2a000ff convert --source Hammerwatch/assets --output out
```

## Install

Requires **Python 3.11 or newer**. The converter itself has no dependencies.

```bash
pip install git+https://github.com/bennpham/HW2A000FF-AllPlatform-Remake
```

Or from a clone:

```bash
git clone https://github.com/bennpham/HW2A000FF-AllPlatform-Remake
cd HW2A000FF-AllPlatform-Remake
pip install -e .
```

Add the optional `png` extra if you want PNGs re-encoded to 32bpp the way the
original did. Without it they are copied through unchanged and the run warns:

```bash
pip install -e ".[png]"
```

## Two workflows

These are the same two the original tool documented on its main tab.

**Converting the base game.** Point `--source` at the game's assets folder and
leave the fallback unset:

```bash
hw2a000ff convert \
  --source "C:/Program Files (x86)/Steam/steamapps/common/Hammerwatch/assets" \
  --output ./assets_hwr
```

**Converting a scenario or campaign.** The scenario's own assets go in
`--source`, the base game assets in `--fallback` so anything the scenario does
not override is still found. Point `--levels-xml` at the campaign's index to
convert its levels:

```bash
hw2a000ff convert \
  --source  ./MyCampaign/assets \
  --fallback "C:/.../Hammerwatch/assets" \
  --levels-xml ./MyCampaign/campaign/levels.xml \
  --output  ./out
```

**Converting one unit.** The original's "Convert single unit" button:

```bash
hw2a000ff convert-unit units/gnaar.xml gnaar.unit
```

**Checking before you convert.** `doctor` runs every input check and reports
what would be skipped, without writing anything:

```bash
hw2a000ff doctor --source ./MyCampaign/assets --levels-xml ./MyCampaign/campaign/levels.xml
```

## Options

Every control on the original's window has a flag.

| Flag | Original control | Default |
|---|---|---|
| `--source DIR` | Source path | required |
| `--fallback DIR` | Fallback path | none |
| `--levels-xml PATH` | levels.xml | none |
| `--output DIR` | Output path | required |
| `--prefix STR` | Output path prefix | empty |
| `--strings-prefix STR` | Strings → key prefix | `hwport.` |
| `--only LIST` / `--skip LIST` | the Converters checkboxes | all stages on |
| `--health-scale N` | Actor health scale | `1.0` |
| `--range-scale N` | Range scale | `1.0` |
| `--damage-scale N` | Damage scale | `1.0` |
| `--speed-scale N` | Actor speed scale | `1.0` |
| `--modify-wall-collision` | Sprites → Modify wall collision | off |
| `--dry-run` | — | off |
| `-v` / `-q` | — | — |

The four scales are plain multipliers: `1.0` is the original's 100% slider.

Stage names for `--only`/`--skip`: `actors`, `projectiles`, `doodads`,
`tilesets`, `items`, `strings`, `speech-styles`, `fonts`, `loot`, `levels`,
`sounds`.

Two flags have no equivalent in the original:

- `--require-game-install` restores its hard requirement that `Hammerwatch.exe`
  sit next to the assets folder. Off by default — see below.
- `--line-endings crlf` reproduces the byte-for-byte output of a Windows run.
  The default is `lf`.

## Config file

For anything you run more than once, keep the settings in a file:

```bash
hw2a000ff init-config > hw2a000ff.toml
hw2a000ff convert --config hw2a000ff.toml
```

Relative paths in the config resolve against the config file's own directory,
so it can live next to a campaign and travel with it. Command-line flags
override the file.

## Using it from your own code

The package is importable and holds no global state, so it is safe to call more
than once in a process — from a map generator, for instance:

```python
from pathlib import Path
from hw2a000ff import Settings, convert_all

report = convert_all(Settings(
    source_path=Path("generated/assets"),
    output_path=Path("out"),
    levels_path=Path("generated/campaign/levels.xml"),
))

print(report.summary())
for warning in report.warnings:
    print("warning:", warning)
```

`convert_all` raises `ConversionError` (or `SettingsError`) for anything that
stops the run; everything recoverable lands in `report.warnings`.

## Troubleshooting

### "The directory name is invalid" in the original tool

If you came here from that crash, this is what it was:

```
System.IO.IOException: The directory name is invalid.
   at System.IO.Directory.GetFiles(String path, ...)
   at hw2a000ff.FormMain.<>c__DisplayClass3_0.<buttonConvert_Click>b__0()
```

`FormMain.cs` reads three directories without checking any of them first — the
source path, `<levels.xml folder>/levels/`, and `<source>/sound`. Only the first
is one you typed. A generated campaign or a partial asset dump routinely has no
`sound/` folder and no `levels/` folder beside its `levels.xml`, and .NET's
exception names no path, so all three failures look identical.

This port checks all three up front. Missing optional folders skip their stage
with a note rather than ending the run:

```
note: no 'sound' directory under ./MyCampaign/assets; skipping soundbanks
note: no 'levels' directory beside levels.xml; skipping levels
Converted 42 file(s) in 0.312 seconds.
```

Run `hw2a000ff doctor` to see those notes without converting anything.

### "Hammerwatch.exe was not found"

The original refuses to start unless `Hammerwatch.exe` sits in the parent of
your source or fallback path. That check exists to catch a mistyped path, but it
also blocks every legitimate use where there is no game install next to the
assets — a generated campaign, an extracted asset dump, a CI job. Here it is a
note, and conversion proceeds. Pass `--require-game-install` if you want the
original behaviour.

### Referenced assets are missing

Warnings like `couldn't locate asset 'units/gnaar.png'` mean a converted file
points at something not found under `--source` or `--fallback`. When converting
a scenario, this usually means `--fallback` is unset or wrong: the scenario
inherits most of its art from the base game. The original printed these to a
console its own GUI never showed.

### Converted numbers look wrong

If you used the original on a machine whose locale uses a comma decimal
separator, its output floats are corrupt: the conversion thread does not inherit
the invariant culture the UI thread sets. This port is locale-independent.

## What this port changes

Beyond running everywhere, it fixes fifteen defects found while reading the C#.
The full table, with line references, is in
[`.claude/skills/hwm-a000ff/SKILL.md`](.claude/skills/hwm-a000ff/SKILL.md) —
along with the format reference: extension map, scale constants, behavior→class
mappings, sprite naming, script renames and lighting maths.

The short version: the three unguarded directory reads, the `Hammerwatch.exe`
gate, the locale bug, floats written into `<int>` fields, several
null-dereferences that crashed on incomplete input, a `SpewSkill` field mixup,
static state leaking between runs, and silent failures that are now reported.

Conversion output is otherwise intended to match the original.

## Limitations

- **Parity is verified by reading, not by running.** The goldens in `tests/`
  were derived from the C# source; there was no .NET toolchain or real
  Hammerwatch asset tree available while porting. If you have both, run the two
  tools over the same assets and open an issue with any diff — that is the most
  useful contribution right now.
- The gaps the original left open are still open: `summon` and `nova` skills,
  buffs, particle wiring for `spew`, a real `checkpoint` behavior, and two
  hardcoded enemy attack sounds. They are listed in the skill file.
- PNGs are only re-encoded to 32bpp when the `png` extra is installed.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

The suite covers the parser's quirks, each converter, the crash regressions and
the CLI, plus golden files for a synthetic mini-campaign under
`tests/fixtures/`. Regenerate goldens after an intentional change with
`HW2A000FF_REGOLD=1 python -m pytest tests/test_golden.py`.

A GitHub Actions workflow — the suite on Linux, macOS and Windows across Python
3.11-3.13, plus a run with no third-party packages installed — is checked in at
`.github/ci.yml.example`. It is not active yet; move it into place to enable it:

```bash
mkdir -p .github/workflows
git mv .github/ci.yml.example .github/workflows/ci.yml
```

## Credits

All conversion logic is a port of `hw2a000ff` by
[Crackshell](https://github.com/Crackshell/hw2a000ff), by way of
[this fork](https://github.com/bennpham/hw2a000ff). Hammerwatch, Heroes of
Hammerwatch and Hammerwatch II are Crackshell's; this port is unaffiliated
with them.

## License

MIT.
