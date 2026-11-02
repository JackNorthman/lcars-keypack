# lcars-keypack

An LCARS-style keypress soundpack for Windows (and Linux) keyboard-sound apps:
**Keyboard Sounds Pro** and **MechvibesDX**. Every key gives a short, clean two-tone computer blip instead of
a mechanical click.

Every sound is **synthesised** by `build.py` from sine waves and standard-library
Python. No recordings are used or shipped.

> **Unofficial fan work.** Not affiliated with, endorsed by or connected to CBS
> Studios or Paramount. *Star Trek* and *LCARS* are trademarks of CBS Studios
> Inc. / Paramount. The sounds here are original syntheses "in the style of",
> not audio from any production.

## Quick start

1. Install Keyboard Sounds Pro.
2. Download a zip from [`packs/keyboard-sounds-pro/`](packs/keyboard-sounds-pro/):

   | pack | what it is |
   |---|---|
   | `lcars.zip` | **Start here.** One tone on every key (70 ms); backspace/delete get a short version so holding them stutters rather than drones. |
   | `lcars-short.zip` | Same, with a 40 ms decay on every key, for fast typists. |
   | `lcars-plus.zip` | Per-key sounds: quieter space, a descending glide on backspace/delete, short repeat-safe blip on arrows/Tab/F-keys, release ticks, and media sounds on F13–F18 (see [Media keys](#media-keys)). |
   | `lcars-mouse.zip` | A short blip for mouse buttons. |

3. In the app: **Profiles → Import** and pick the zip.
   Or from the command line: `kbs add-profile -z .\lcars.zip`

**MechvibesDX:** unzip [`packs/mechvibes-dx/lcars-soundpacks.zip`](packs/mechvibes-dx/)
and drop the `lcars/` and `lcars-short/` folders into the soundpacks directory
(the app's "open soundpacks folder" button finds it), then restart and pick the pack.

## Building it yourself

```bash
python3 build.py                 # -> dist/keyboard-sounds-pro/*.zip, dist/mechvibes-dx/*.zip
python3 preview.py               # -> dist/preview-*.wav, 10 s auditions with measurements
python3 validate.py              # pre-flight every pack (needs PyYAML)
```

`build.py` and `preview.py` need only Python 3.8+ and the standard library.
`validate.py` also needs [PyYAML](https://pypi.org/project/PyYAML/).

The build is deterministic: `python3 build.py --synth-only` reproduces the zips in
`packs/` byte for byte.

### Bring your own samples

`lcars-plus` has optional slots for Enter, nav keys, digits, Escape, Win, Caps Lock,
play/pause and the mouse buttons. Drop WAVs with the right names into
[`samples/`](samples/README.md) and rebuild; each one is trimmed, shortened and
level-matched to the rest of the pack. Unfilled slots fall back to the default
sound. `samples/*.wav` is git-ignored, so your audio stays out of the repo. Only
use sounds you have the right to use, and don't redistribute packs built with them
unless you do.

## The sound

- **The blip:** 1720 Hz (decay time constant 23 ms) plus 2580 Hz at −11 dB
  (time constant 14 ms), with a 2 ms attack and a 5 ms tail fade.
- **Gain baked in:** samples peak at −13.8 dBFS (a −5.8 dBFS blip at 0.4×). A
  full-scale blip is far too hot for a keypress and would leave the app's volume
  slider almost no useful travel. Raise it in the app if it's too quiet.
- **2 ms fade-out** to true zero on every sample, so a retrigger never clicks.
- **No pitch variation.** The usual cure for "machine-gun" repetition is a random
  ±6% playback rate. On a pure synth tone that reads as the tone *alternating*,
  not as realism, so it's deliberately one tone.
- **No leading silence.** Any silence before the onset is pure keypress latency.
- **WAV, not MP3.** The app's built-in profiles ship MP3, but MP3 encoder delay
  adds leading silence, which on a keypress is latency again.
- **Mono 44.1 kHz.** If your output device runs at 44.1 kHz in Windows shared
  mode, nothing gets resampled.

### Why backspace gets its own 28 ms sample

The real constraint is Windows **auto-repeat**, not the app. Held keys repeat at
about 31 per second, i.e. one every **32 ms**. A 70 ms blip overlaps the next
one, and a held backspace smears into a sustained tone. Backspace and delete
therefore get a separate sample cut to 28 ms (about 23 ms once the onset is
trimmed), which leaves a gap before each repeat, so it stays a stutter.

Anything a user can hold (backspace, arrows, digits) must be quiet by about 32 ms.
`build.py` flags samples that aren't, and `validate.py` fails them.

Measured by `preview.py` ("continuous-tone duty" = share of the window above
−50 dBFS; higher means closer to a drone than to separate keystrokes):

| pack | fast burst ~12/s | held backspace ~31/s |
|---|---|---|
| `lcars` | 77% | 50% |
| `lcars-short` | 31% | 50% |
| `lcars-plus` | 77% | 61% |

If `lcars` rings at your typing speed, switch to `lcars-short`.

## Format notes and gotchas

These are the traps that silently broke earlier versions of this pack.
`validate.py` checks for every one of them.

### Keyboard Sounds Pro `profile.yaml`

```yaml
profile:
  name: LCARS
  device: keyboard            # or: mouse
sources:
  - id: key
    source: key.wav           # a filename, or {press: a.wav, release: b.wav}
  - id: back
    source: { press: back.wav, release: rel.wav }
keys:
  default: [ key ]            # ALWAYS a list
  other:
    - sound: back             # a scalar -- do NOT wrap this one
      keys: [ "Backspace", "Delete" ]
```

- **`keys.default` / `buttons.default` must be a YAML list.** Pro's Go backend
  unmarshals it into `[]string`, and `default: key` fails the import with
  `cannot unmarshal !!str into []string`. `other[].sound` stays a scalar. The
  original Python Keyboard Sounds accepted either, which is why some docs read as
  permissive.
- **Pro uses PascalCase Windows key names, not pynput's.** `Space`, `Enter`,
  `Backspace`, `Escape`, `Tab`, `Delete`, `PageUp`, `LeftWin`, `CapsLock`,
  `LeftShift`, `Num0`–`Num9`, `F1`–`F24`… The snake_case names in the Python
  project's `profile.template.yaml` (`space`, `esc`, `page_up`) **never fire in
  Pro**. The full list (114 keys, from Pro's `backend/key/key_windows.go`) is in
  [`data/pro-key-names.json`](data/pro-key-names.json). The Linux build uses the
  same names.
- **Bad key names fail silently.** A misspelt or unknown name isn't an error. The
  key just falls through to `default`, and you never hear the sound you mapped.
- **Quote digit keys:** `"0"`, not `0`. Unquoted, YAML parses them as integers,
  they never match the key's string name, and that fails silently too.
- **Don't reuse the press sample as the release** (`release: num.wav` on a `num`
  press): every key then sounds twice, once going down and once coming up.
- **Mouse profiles** use `device: mouse` and a `buttons:` section. Unlike key
  names, button names *are* validated (`left`, `right`, `middle`).
- **Zip layout:** `profile.yaml` and the WAVs at the **root** of the zip, not in a
  folder.

### Media keys

Media and volume keys (VK `0xAD`–`0xB3`) are **not in Pro's key table at all**,
so no profile can map them, whether from the editor or by hand-editing YAML.

`F13`–`F24` *are* in the table, and nothing uses them by default. So:

1. Set your macropad (or remapper) to send **F13–F18** instead of media keys.
2. `lcars-plus` plays a sound on those keys: volume up = rising glide, volume
   down = falling glide, mute = falling away, previous/next = a descending or
   ascending pair of blips. Direction is carried by pitch, so you can tell them
   apart by ear. F17 (play/pause) is a bring-your-own slot.
3. [`MEDIA-KEYS.ahk`](MEDIA-KEYS.ahk) (AutoHotkey v2) turns F13–F18 into the real
   media commands.

| key | sound | does |
|---|---|---|
| F13 | rising glide | volume up |
| F14 | falling glide | volume down |
| F15 | falling away | mute |
| F16 | descending pair | previous track |
| F17 | (your sample) | play/pause |
| F18 | ascending pair | next track |

Holding volume up still measures about 88% continuous: the 50 ms glides overlap
into a sweep. Cutting them below 32 ms would fix that, but it makes up and down
hard to tell apart, which is the whole point. They're left long on purpose.

Even in apps that *can* name media keys, many HID "consumer control" devices (what
most USB/Bluetooth macropads send) reach Windows as `WM_APPCOMMAND`, not as key
events, so a low-level keyboard hook never sees them. If a media key is silent on
the macropad but works on a normal keyboard, the device is bypassing the hook.

### MechvibesDX `config.json` (v2)

- `sound` / `soundup` are fallbacks for every keycode you don't define, so no
  exhaustive scancode map is needed. `soundup` points at `silence.wav` because a
  synth blip has no release component.
- Keycode `14` = backspace (from the v2 docs example). `83` and `57427` are
  included as delete variants; they're unverified but harmless if unused.

### Caveat: every keydown clicks

Soundpack apps hook raw keydown, so Shift, Ctrl and every modifier inside a
shortcut makes a sound too. Keyboard Sounds Pro's per-application rules (enable it
only in text-heavy apps) are the closest thing to "only sound when typing text".
You can also map the modifiers to a silent source.

### Linux

Keyboard Sounds Pro has a Linux build (beta at the time of writing) that uses the
same PascalCase key names, so the same zips import unchanged. It reads
`/dev/input` directly: add your user to the `input` group, then log out and back
in. Media keys are missing from the Linux key table too.

## Repo layout

| path | |
|---|---|
| `build.py` | synthesises every sample, writes the profiles, zips the packs |
| `preview.py` | renders audition WAVs and prints the duty measurements |
| `validate.py` | pre-flight checks for every pack (needs PyYAML) |
| `packs/` | prebuilt zips (`build.py --synth-only` output) |
| `samples/` | optional bring-your-own WAVs (git-ignored) |
| `data/pro-key-names.json` | Keyboard Sounds Pro's key-name table, for validation |
| `MEDIA-KEYS.ahk` | AutoHotkey v2 script: F13–F18 → media commands |

`validate.py --crossover 160` (the default) also fails any sample with more than
15% of its energy below 160 Hz. On a 2.1 speaker system, a transient that
straddles the subwoofer crossover gets split between desk and floor and arrives
smeared. Use `--crossover 0` to turn the check off.

## Licence

MIT. See [LICENSE](LICENSE). This covers the code and the synthesised sounds. It
grants nothing over the trademarks named above.
