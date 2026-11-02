# Bring your own samples

Nothing in this folder is committed (see `.gitignore`), and nothing here is
needed: by default every sound is synthesised by `build.py`.

If you own (or have the right to use) other short sounds, drop them in here
with these exact names and rebuild with `python3 build.py`. Each one is
trimmed of leading silence, cut to a keystroke length with an exponential
tail, faded, and level-matched to the rest of the pack. Unfilled slots simply
fall back to the default key sound.

| file | keys (Keyboard Sounds Pro names) | cut to |
|---|---|---|
| `enter.wav` | `Enter` | 110 ms |
| `nav.wav` | `Tab`, arrows, `Home`/`End`, `PageUp`/`PageDown`, `Insert`, `PrintScreen`, `ScrollLock`, `Pause`, `F1`–`F12` | 28 ms (repeat-safe) |
| `num.wav` | `"0"`–`"9"`, `Num0`–`Num9`, `Num.` | 30 ms |
| `esc.wav` | `Escape` | 72 ms |
| `win.wav` | `LeftWin`, `RightWin` | 120 ms |
| `caps.wav` | `CapsLock` | 110 ms |
| `playpause.wav` | `F17` (see `MEDIA-KEYS.ahk`) | 64 ms |
| `mouse-left.wav` | left button (replaces the synthesised blip) | 39 ms |
| `mouse-right.wav` | right button | 62 ms |
| `mouse-middle.wav` | middle button | 36 ms |

Without `nav.wav`, the nav keys get a 28 ms synthesised blip so a held arrow
key still stutters rather than drones.

Any PCM WAV works (8/16/24/32-bit, mono or stereo, any sample rate); it is
converted to mono 44.1 kHz 16-bit. Pick the single chirp you want and trim it
roughly yourself: the build keeps the *start* of the file, so a sample with
three beeps in it will only ever play the first.

**Licensing is on you.** Packs built with your samples contain your audio.
Don't publish them, or open a pull request with them, unless you have the
rights. `python3 build.py --synth-only` ignores this folder entirely.
