#!/usr/bin/env python3
"""Pre-flight every Keyboard Sounds Pro pack in <out>/keyboard-sounds-pro/.
Each check is a trap that has actually broken a pack. Needs PyYAML.

    python3 validate.py [--out dist] [--crossover 160]
"""
import argparse, array, io, json, math, os, sys, wave, zipfile
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
# Pro's Go backend key table (backend/key/key_windows.go). PascalCase Windows
# names, NOT pynput's snake_case. An unlisted name fails SILENTLY.
PRO_KEYS = set(json.load(open(os.path.join(HERE, "data", "pro-key-names.json"))))

SR, REPEAT_MS = 44100, 32.3
REPEAT_PRONE = {"back", "nav", "num", "key-repeat"}     # keys a user can hold down


def audio(z, name):
    w = wave.open(io.BytesIO(z.read(name)))
    a = array.array('h'); a.frombytes(w.readframes(w.getnframes()))
    return [float(x) for x in a], w.getframerate(), w.getnchannels()


def audible_ms(s):
    pk = max((abs(x) for x in s), default=0) or 1
    idx = [i for i, x in enumerate(s) if abs(x) > pk * 0.01]
    return (max(idx) / SR * 1000) if idx else 0.0


def low_pct(s, xo):
    """Share of energy between 40 Hz and the crossover (coarse DFT, 20 Hz bins)."""
    def e(lo, hi):
        t = 0.0
        for f in range(lo, hi, 20):
            w = 2 * math.pi * f / SR
            re = sum(x * math.cos(w * i) for i, x in enumerate(s))
            im = sum(x * math.sin(w * i) for i, x in enumerate(s))
            t += re * re + im * im
        return t
    lo = e(40, xo); tot = lo + e(xo, 8000)
    return (lo / tot * 100) if tot else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "dist"),
                    help="build output directory, or any folder holding a keyboard-sounds-pro/ dir")
    ap.add_argument("--crossover", type=int, default=160,
                    help="2.1-speaker sub crossover in Hz; 0 disables the check (default 160)")
    args = ap.parse_args()
    kdir = os.path.join(args.out, "keyboard-sounds-pro")
    if not os.path.isdir(kdir):
        kdir = args.out
    fails = []
    packs = sorted(f for f in os.listdir(kdir) if f.endswith(".zip"))

    for fn in packs:
        z = zipfile.ZipFile(os.path.join(kdir, fn)); files = {i.filename for i in z.infolist()}
        def bad(msg): fails.append(f"{fn}: {msg}")

        if any("/" in f for f in files): bad("files must sit at the zip ROOT")
        if "profile.yaml" not in files:
            bad("no profile.yaml"); continue
        y = yaml.safe_load(z.read("profile.yaml"))

        dev = y["profile"].get("device", "keyboard")
        sect = "keys" if dev == "keyboard" else "buttons"
        blk = y.get(sect)
        if not blk:
            bad(f"missing '{sect}' section"); continue

        # Pro's Go backend unmarshals `default` into []string; `sound` stays a scalar.
        if not isinstance(blk.get("default"), list):
            bad(f"{sect}.default must be a LIST (Go: cannot unmarshal !!str into []string)")
        for m in blk.get("other", []) or []:
            if not isinstance(m.get("sound"), str):
                bad(f"{sect}.other[].sound must be a scalar string, got {type(m.get('sound')).__name__}")

        names, refs = {s["id"] for s in y["sources"]}, set()
        for s in y["sources"]:
            src = s["source"]
            refs |= {src} if isinstance(src, str) else set(src.values())
        for r in refs - files: bad(f"source file '{r}' missing from zip")
        for r in files - refs - {"profile.yaml"}: bad(f"'{r}' is in the zip but no source uses it")
        d = blk.get("default", [])
        used = (set(d) if isinstance(d, list) else {d}) | {m["sound"] for m in blk.get("other", []) or []}
        for u in used - names: bad(f"mapping references undefined source '{u}'")
        for u in names - used: bad(f"source '{u}' is defined but never used")

        # a release that reuses the press sample makes every key fire twice
        for s in y["sources"]:
            src = s["source"]
            if isinstance(src, dict) and src.get("press") and src.get("press") == src.get("release"):
                bad(f"source '{s['id']}': release == press, the key will sound twice")

        if sect == "keys":
            allk = [k for m in blk.get("other", []) or [] for k in m["keys"]]
            for k in {k for k in allk if allk.count(k) > 1}: bad(f"key '{k}' mapped twice")
            for k in allk:
                if not isinstance(k, str):        # unquoted digits become ints
                    bad(f"key {k!r} is {type(k).__name__}, must be a quoted string")
                elif k not in PRO_KEYS:
                    bad(f"key '{k}' is not in Pro's key table -- it will never fire")
        else:
            for m in blk.get("other", []) or []:
                for b in m["buttons"]:
                    if b not in ("left", "right", "middle"): bad(f"invalid mouse button '{b}'")

        for f in sorted(files - {"profile.yaml"}):
            s, rate, ch = audio(z, f)
            if rate != SR or ch != 1: bad(f"{f}: {ch}ch @ {rate} Hz, expected mono 44100")
            if not any(s): continue
            if f[:-4] in REPEAT_PRONE and audible_ms(s) > REPEAT_MS:
                bad(f"{f}: {audible_ms(s):.1f} ms audible -- a held key will smear (limit {REPEAT_MS} ms)")
            if args.crossover and low_pct(s, args.crossover) > 15:
                bad(f"{f}: {low_pct(s, args.crossover):.0f}% below {args.crossover} Hz -- "
                    "on a 2.1 system it splits to the subwoofer and arrives smeared")

    print(f"checked {len(packs)} packs in {kdir}")
    if fails:
        print("\nFAILURES:")
        for f in fails: print("  -", f)
        sys.exit(1)
    print("all packs pass")


if __name__ == "__main__":
    main()
