#!/usr/bin/env python3
"""Build LCARS-style keypress soundpacks for Keyboard Sounds Pro and MechvibesDX.

Every sound in the default build is synthesised here from sine waves -- no
audio file is read. Optional extra slots (enter, nav, digits, ...) can be
filled from your own samples in samples/; see samples/README.md.

    python3 build.py                  # synthesised sounds + any samples/ you supplied
    python3 build.py --synth-only     # ignore samples/ (what packs/ is built with)
    python3 build.py --out somewhere  # default: ./dist

Standard library only.
"""
import argparse, array, json, math, os, shutil, sys, wave, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100                 # mono 44.1 kHz 16-bit everywhere
FADE_MS = 2.0              # guard fade to true zero, so a retrigger never clicks
REPEAT_SAFE_MS = 28.0      # Windows auto-repeat ~31/s = 32 ms spacing (see README)
REPEAT_LIMIT_MS = 32.3     # anything a user can hold must be quieter than this by then
REPEAT_PRONE = {"back", "nav", "num", "key-repeat"}

# Levels (peak dBFS). -13.8 = a -5.8 dBFS blip with 0.4x gain baked in, which
# leaves the app's volume slider useful travel instead of pinning it near zero.
L_MAIN, L_SECOND, L_SPACE, L_REL = -13.8, -16.5, -19.0, -26.0

ZIP_DATE = (2026, 1, 1, 0, 0, 0)   # fixed timestamps -> byte-identical rebuilds


# ------------------------------------------------------------------ synthesis
LEAD = 219   # samples (~5 ms) of silence before the blip -- see blip()


def blip(frames=3308):
    """The LCARS key blip: 1720 Hz (decay tau 23 ms) + 2580 Hz (tau 14 ms,
    -11 dB), 2 ms linear attack, 5 ms linear tail; 75 ms file. Pure synthesis.

    The tone starts ~5 ms into the buffer. Every cut/knee/glide below was tuned
    against a blip positioned like that, so the lead-in is kept here and
    trim_lead() strips it from each finished sample: the sounds come out as
    designed, minus 5 ms of keypress latency."""
    tone, att, tail = frames - LEAD, int(SR * 0.002), int(SR * 0.005)
    out = [0.0] * LEAD
    for i in range(tone):
        t = i / SR
        v = (math.exp(-t / 0.023) * math.sin(2 * math.pi * 1720 * t)
             + 0.276 * math.exp(-t / 0.014) * math.sin(2 * math.pi * 2580 * t))
        if i < att:
            v *= i / att
        if i >= tone - tail:
            v *= (tone - i) / tail
        out.append(v)
    return out


def trim_lead(d):
    """Drop leading digital silence (it is pure latency on a keypress)."""
    i = next((i for i, x in enumerate(d) if abs(x) >= 0.5), None)
    return d if i is None else d[i:]


def resample(d, ratio):
    """Linear-interpolation resample. ratio > 1 raises pitch (and shortens)."""
    n = int(len(d) / ratio); out = []
    for i in range(n):
        p = i * ratio; j = int(p); f = p - j
        a = d[j] if j < len(d) else 0.0
        b = d[j + 1] if j + 1 < len(d) else 0.0
        out.append(a + (b - a) * f)
    return out


def glide(d, r0, r1, dur_ms):
    """Pitch glide: playback rate goes r0 -> r1 across the output (r < 1 = lower)."""
    n = int(SR * dur_ms / 1000); out = []; pos = 0.0
    for i in range(n):
        r = r0 + (r1 - r0) * (i / max(1, n - 1))
        j = int(pos); f = pos - j
        a = d[j] if j < len(d) else 0.0
        b = d[j + 1] if j + 1 < len(d) else 0.0
        out.append(a + (b - a) * f); pos += r
    return out


def shape(d, cut_ms=None, knee_ms=12.0, tau_ms=8.0, attack_ms=0.0):
    """Optionally truncate with an extra exponential decay after `knee_ms` so the
    tail dies early, de-click the start, and always fade the last 2 ms to zero."""
    n = len(d) if cut_ms is None else min(len(d), int(SR * cut_ms / 1000))
    out = list(d[:n])
    if cut_ms is not None:
        for i in range(n):
            t = i / SR * 1000.0
            if t > knee_ms:
                out[i] *= math.exp(-(t - knee_ms) / tau_ms)
    if attack_ms:
        a = int(SR * attack_ms / 1000)
        for i in range(min(a, n)):
            out[i] *= i / a
    f = int(SR * FADE_MS / 1000)
    for i in range(max(0, n - f), n):
        out[i] *= (n - i) / f
    return out


def norm(d, dbfs):
    pk = max((abs(x) for x in d), default=0.0) or 1.0
    g = (32768 * 10 ** (dbfs / 20)) / pk
    return [x * g for x in d]


def pad(ms):
    return [0.0] * int(SR * ms / 1000)


def pair(src, r_a, r_b, seg_ms=20.0, gap_ms=24.0):
    """Two short blips at fixed pitches -- a direction cue, not a glide."""
    a = shape(resample(src, r_a), cut_ms=seg_ms, knee_ms=5.0, tau_ms=6.0)
    b = shape(resample(src, r_b), cut_ms=seg_ms, knee_ms=5.0, tau_ms=6.0)
    return a + pad(gap_ms) + b


def audible_ms(d):
    pk = max((abs(x) for x in d), default=0.0) or 1.0
    idx = [i for i, x in enumerate(d) if abs(x) > pk * 0.01]
    return (max(idx) / SR * 1000) if idx else 0.0


def peak_dbfs(d):
    pk = max((abs(x) for x in d), default=0.0) or 1.0
    return 20 * math.log10(pk / 32768)


# ------------------------------------------------------------------ file I/O
def save(path, d):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = trim_lead(d)
    a = array.array('h', [max(-32768, min(32767, int(round(x)))) for x in d])
    w = wave.open(path, 'w'); w.setnchannels(1); w.setsampwidth(2)
    w.setframerate(SR); w.writeframes(a.tobytes()); w.close()


def load_any(path):
    """Read a PCM WAV (8/16/24/32-bit, any channels, any rate) -> mono float list
    at 44.1 kHz, scaled to 16-bit range, leading silence trimmed (it is latency)."""
    w = wave.open(path)
    ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    raw = w.readframes(n); w.close()
    if sw == 1:
        s = [(b - 128) * 256.0 for b in raw]
    elif sw == 2:
        a = array.array('h'); a.frombytes(raw[:len(raw) // 2 * 2])
        if sys.byteorder == 'big': a.byteswap()
        s = [float(x) for x in a]
    elif sw == 3:
        s = [int.from_bytes(raw[i:i + 3], 'little', signed=True) / 256.0
             for i in range(0, len(raw) - 2, 3)]
    elif sw == 4:
        a = array.array('i'); a.frombytes(raw[:len(raw) // 4 * 4])
        if sys.byteorder == 'big': a.byteswap()
        s = [x / 65536.0 for x in a]
    else:
        raise SystemExit(f"{path}: unsupported sample width {sw}")
    if ch > 1:
        s = [sum(s[i:i + ch]) / ch for i in range(0, len(s) - ch + 1, ch)]
    if rate != SR:
        s = resample(s, rate / SR)
    pk = max((abs(x) for x in s), default=0.0)
    if not pk:
        raise SystemExit(f"{path}: file is silent")
    start = next(i for i, x in enumerate(s) if abs(x) > pk * 0.01)
    return s[start:]


def zipdir(src_dir, out_zip):
    """Zip a directory with files at the zip ROOT (Keyboard Sounds requires it)."""
    os.makedirs(os.path.dirname(out_zip), exist_ok=True)
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for dirpath, _, files in sorted(os.walk(src_dir)):
            for f in sorted(files):
                fp = os.path.join(dirpath, f)
                zi = zipfile.ZipInfo(os.path.relpath(fp, src_dir), ZIP_DATE)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                with open(fp, 'rb') as fh:
                    z.writestr(zi, fh.read())


# ------------------------------------------------------------------ profiles
def profile_yaml(name, desc, device, sources, default, other):
    """sources: [(id, press_file, release_file_or_None)]
    default: [id, ...]  (MUST be a list -- Pro's Go backend wants []string)
    other:   [(id, [key or button names])]  (sound is a SCALAR)"""
    sect, field = ("keys", "keys") if device == "keyboard" else ("buttons", "buttons")
    src = []
    for sid, press, rel in sources:
        if rel:
            src.append(f"  - id: {sid}\n    source:\n      press: {press}\n      release: {rel}")
        else:
            src.append(f"  - id: {sid}\n    source: {press}")
    oth = []
    for sid, names in other:
        # every name quoted: unquoted digits would parse as YAML ints and never match
        quoted = ", ".join(json.dumps(k) for k in names)
        oth.append(f"    - sound: {sid}\n      {field}: [ {quoted} ]")
    body = f"""# Keyboard Sounds Pro profile -- generated by build.py, edit that instead.
# Key names are Pro's PascalCase Windows names (Space, Escape, PageUp, LeftWin,
# Num0 ...), NOT pynput's snake_case. A misspelt name is ignored SILENTLY.
profile:
  name: {json.dumps(name)}
  author: lcars-keypack
  description: {json.dumps(desc)}
  device: {device}

sources:
{chr(10).join(src)}

{sect}:
  default: [ {", ".join(default)} ]
"""
    if oth:
        body += "\n  other:\n" + "\n".join(oth) + "\n"
    return body


def mechvibes_config(name, tag, split):
    # keycode 14 = backspace (from the MechvibesDX v2 docs example).
    # 83 / 57427 = numpad-del / extended-delete: unverified, harmless if unused.
    return {
        "id": tag,
        "name": name,
        "key_define_type": "multi",
        "sound": "key.wav",        # fallback keydown -- covers every keycode
        "soundup": "silence.wav",  # a synth blip has no release component
        "defines": {k: "key-repeat.wav" for k in ("14", "83", "57427")} if split else {},
        "version": 2,
    }


# ------------------------------------------------------------------ bring-your-own slots
# slot -> (Pro key names, shape() args, level). Fill by dropping samples/<slot>.wav.
BYO_KEYS = {
    "enter":     (["Enter"], dict(cut_ms=110.0, knee_ms=30.0, tau_ms=22.0), L_MAIN),
    "nav":       (["Tab", "Up", "Down", "Left", "Right", "Home", "End", "PageUp", "PageDown",
                   "Insert", "PrintScreen", "ScrollLock", "Pause"] + [f"F{i}" for i in range(1, 13)],
                  dict(cut_ms=REPEAT_SAFE_MS, knee_ms=8.0, tau_ms=5.0), L_SECOND),
    "num":       ([str(i) for i in range(10)] + [f"Num{i}" for i in range(10)] + ["Num."],
                  dict(cut_ms=30.0, knee_ms=9.0, tau_ms=6.0, attack_ms=1.0), L_SECOND),
    "esc":       (["Escape"], dict(cut_ms=72.0, knee_ms=22.0, tau_ms=16.0, attack_ms=1.5), L_SECOND),
    "win":       (["LeftWin", "RightWin"], dict(cut_ms=120.0, knee_ms=34.0, tau_ms=24.0), L_SECOND),
    "caps":      (["CapsLock"], dict(cut_ms=110.0, knee_ms=30.0, tau_ms=22.0), L_SECOND),
    "playpause": (["F17"], dict(cut_ms=64.0, knee_ms=20.0, tau_ms=15.0, attack_ms=1.5), L_MAIN),
}
BYO_MOUSE = {
    "left":   dict(cut_ms=39.0, knee_ms=14.0, tau_ms=12.0),
    "right":  dict(cut_ms=62.0, knee_ms=20.0, tau_ms=15.0, attack_ms=1.5),
    "middle": dict(cut_ms=36.0, knee_ms=14.0, tau_ms=11.0, attack_ms=1.0),
}


def find_sample(sdir, slot, prefix=""):
    if not sdir:
        return None
    p = os.path.join(sdir, f"{prefix}{slot}.wav")
    return p if os.path.isfile(p) else None


# ------------------------------------------------------------------ build
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "dist"), help="output directory (default ./dist)")
    ap.add_argument("--samples", default=os.path.join(HERE, "samples"), help="bring-your-own samples folder")
    ap.add_argument("--synth-only", action="store_true", help="ignore the samples folder")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    sdir = None if args.synth_only else args.samples
    stage = os.path.join(out, "build")
    shutil.rmtree(stage, ignore_errors=True)
    used_byo = []

    key = blip()
    print(f"key blip: {len(trim_lead(key))/SR*1000:.0f} ms, 1720 + 2580 Hz, synthesised")

    def emit(pack, bank):
        d = os.path.join(stage, pack)
        os.makedirs(d, exist_ok=True)
        print(f"\n{pack}")
        for n, s in bank.items():
            s = trim_lead(s)
            save(f"{d}/{n}.wav", s)
            flag = ""
            if n in REPEAT_PRONE and audible_ms(s) > REPEAT_LIMIT_MS:
                flag = "  <-- NOT repeat-safe: a held key will smear into a tone"
            print(f"  {n:11s} {len(s)/SR*1000:6.1f} ms  audible {audible_ms(s):5.1f} ms  "
                  f"peak {peak_dbfs(s):+6.1f} dBFS{flag}")
        return d

    # --- lcars / lcars-short: one tone, plus a short sample for backspace/delete
    repeat = norm(shape(key, cut_ms=REPEAT_SAFE_MS, knee_ms=8.0, tau_ms=5.0), L_MAIN)
    basic = {
        "lcars":       ("LCARS", norm(shape(key), L_MAIN),
                        "LCARS blip, 75 ms; backspace/delete shortened so held keys stutter"),
        "lcars-short": ("LCARS (short)", norm(shape(key, cut_ms=45.0), L_MAIN),
                        "LCARS blip with a 45 ms decay on every key, for fast typists"),
    }
    for tag, (name, k, desc) in basic.items():
        d = emit(f"ksp-{tag}", {"key": k, "key-repeat": repeat})
        open(f"{d}/profile.yaml", "w").write(profile_yaml(
            name, desc, "keyboard",
            [("key", "key.wav", None), ("key_repeat", "key-repeat.wav", None)],
            ["key"], [("key_repeat", ["Backspace", "Delete"])]))
        zipdir(d, f"{out}/keyboard-sounds-pro/{tag}.zip")

        mv = os.path.join(stage, "mechvibes", tag)
        os.makedirs(mv, exist_ok=True)
        save(f"{mv}/key.wav", k); save(f"{mv}/key-repeat.wav", repeat); save(f"{mv}/silence.wav", pad(5))
        open(f"{mv}/config.json", "w").write(json.dumps(mechvibes_config(name, tag, True), indent=2) + "\n")
    zipdir(os.path.join(stage, "mechvibes"), f"{out}/mechvibes-dx/lcars-soundpacks.zip")

    # --- lcars-plus: per-key sounds. Synthesised core + optional BYO slots.
    plus = {
        "key":     norm(shape(key), L_MAIN),
        "rel":     norm(shape(key, cut_ms=18.0, knee_ms=3.0, tau_ms=4.0), L_REL),
        # space: the letters' own tone, shorter and ~5 dB down
        "space":   norm(shape(key, cut_ms=55.0, knee_ms=13.0, tau_ms=11.0), L_SPACE),
        # backspace/delete: a descending glide reads as "reverse"; repeat-safe
        "back":    norm(shape(glide(key, 1.0, 0.42, REPEAT_SAFE_MS), cut_ms=REPEAT_SAFE_MS,
                              knee_ms=6.0, tau_ms=9.0), L_SECOND),
        # media sounds on F13-F18: direction carried by pitch, tellable blind
        "volup":   norm(shape(glide(key, 0.60, 1.50, 50.0), cut_ms=50.0, knee_ms=14.0, tau_ms=13.0), L_SECOND),
        "voldown": norm(shape(glide(key, 1.50, 0.60, 50.0), cut_ms=50.0, knee_ms=14.0, tau_ms=13.0), L_SECOND),
        "mute":    norm(shape(glide(key, 1.00, 0.30, 42.0), cut_ms=42.0, knee_ms=10.0, tau_ms=10.0), L_SECOND),
        "next":    norm(pair(key, 0.90, 1.30), L_MAIN),
        "prev":    norm(pair(key, 1.30, 0.90), L_MAIN),
    }
    mapping = [("space", ["Space"]), ("back", ["Backspace", "Delete"]),
               ("volup", ["F13"]), ("voldown", ["F14"]), ("mute", ["F15"]),
               ("prev", ["F16"]), ("next", ["F18"])]
    for slot, (keys, sh, lvl) in BYO_KEYS.items():
        p = find_sample(sdir, slot)
        if p:
            plus[slot] = norm(shape(load_any(p), **sh), lvl)
            used_byo.append(p)
        elif slot == "nav":
            # no sample: still give the repeat-prone keys a short blip so held
            # arrows stutter instead of droning
            plus[slot] = norm(shape(key, cut_ms=REPEAT_SAFE_MS, knee_ms=8.0, tau_ms=5.0), L_SECOND)
        else:
            continue                     # unfilled slot -> those keys use the default
        mapping.append((slot, keys))
    d = emit("ksp-lcars-plus", plus)
    ids = [n for n in plus if n != "rel"]
    open(f"{d}/profile.yaml", "w").write(profile_yaml(
        "LCARS Plus", "LCARS keyboard soundscape, per-key sounds", "keyboard",
        [(i, f"{i}.wav", "rel.wav") for i in ids], ["key"], mapping))
    zipdir(d, f"{out}/keyboard-sounds-pro/lcars-plus.zip")

    # --- lcars-mouse: left defaults to a short synthesised blip; right/middle BYO
    mouse, mmap = {}, []
    p = find_sample(sdir, "left", "mouse-")
    left_src = load_any(p) if p else key
    if p: used_byo.append(p)
    mouse["left"] = norm(shape(left_src, **BYO_MOUSE["left"]), L_MAIN)
    mouse["rel"] = norm(shape(left_src, cut_ms=16.0, knee_ms=3.0, tau_ms=4.0), L_REL)
    for b in ("right", "middle"):
        p = find_sample(sdir, b, "mouse-")
        if p:
            mouse[b] = norm(shape(load_any(p), **BYO_MOUSE[b]), L_MAIN)
            mmap.append((b, [b])); used_byo.append(p)
    d = emit("ksp-lcars-mouse", mouse)
    open(f"{d}/profile.yaml", "w").write(profile_yaml(
        "LCARS Mouse", "LCARS sounds for mouse buttons", "mouse",
        [(b, f"{b}.wav", "rel.wav") for b in mouse if b != "rel"], ["left"], mmap))
    zipdir(d, f"{out}/keyboard-sounds-pro/lcars-mouse.zip")

    print(f"\nwrote {out}/keyboard-sounds-pro/*.zip and {out}/mechvibes-dx/lcars-soundpacks.zip")
    if used_byo:
        print("\nincluded YOUR samples (do not redistribute these packs unless you own the audio):")
        for p in used_byo:
            print("  -", p)
    else:
        print("every sound is synthesised -- no audio files were read")


if __name__ == "__main__":
    main()
