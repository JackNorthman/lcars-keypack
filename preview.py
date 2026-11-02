#!/usr/bin/env python3
"""Render typing simulations so the packs can be auditioned before installing.

Sections: normal typing ~7/s, fast burst ~12/s, held backspace (Windows
default: 250 ms delay, then ~31 repeats/sec). Writes <out>/preview-<pack>.wav
and prints the "continuous-tone duty" of each section.

    python3 build.py && python3 preview.py [--out dist]
"""
import argparse, array, math, os, random, wave

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))


def load(p):
    w = wave.open(p); d = array.array('h'); d.frombytes(w.readframes(w.getnframes())); w.close()
    return d


def render(events, tail_ms=600):
    n = int(SR * (max(t for t, _ in events) + tail_ms / 1000.0)) + 4096
    buf = [0.0] * n
    for t, s in events:
        off = int(t * SR)
        for i, v in enumerate(s):
            buf[off + i] += v
    return buf


def analyse(buf, a, b, label):
    """Duty = fraction of the window above -50 dBFS. Higher = closer to a
    sustained tone than to discrete keystrokes."""
    seg = buf[int(a * SR):int(b * SR)]
    rms = math.sqrt(sum(x * x for x in seg) / len(seg)) or 1e-9
    thr = 32768 * 10 ** (-50 / 20)
    duty = sum(1 for x in seg if abs(x) > thr) / len(seg)
    print(f"    {label:16s} RMS {20*math.log10(rms/32768):+5.1f} dBFS   continuous-tone duty {duty*100:3.0f}%")


def simulate(out_dir, tag, key, space, repeat):
    ev, t = [], 0.0
    rng = random.Random(1720)
    for i in range(28):                      # normal typing, a space every ~5 keys
        ev.append((t, space if (space and i % 5 == 4) else key)); t += 0.143 * rng.uniform(0.72, 1.35)
    t += 0.9
    burst_a = t
    for _ in range(24):                      # fast burst
        ev.append((t, key)); t += 0.083 * rng.uniform(0.9, 1.1)
    burst_b = t; t += 0.9
    hold_a = t
    ev.append((t, repeat)); t += 0.25        # held backspace: delay, then auto-repeat
    for _ in range(40):
        ev.append((t, repeat)); t += 1 / 31.0
    hold_b = t

    buf = render(ev)
    pk = max(abs(x) for x in buf) or 1
    print(f"  {tag}: {len(ev)} keystrokes, {len(buf)/SR:.1f} s, peak {20*math.log10(pk/32768):+.1f} dBFS"
          + ("  <-- CLIPPING" if pk >= 32767 else ""))
    analyse(buf, burst_a, burst_b, "fast burst")
    analyse(buf, hold_a + 0.3, hold_b, "held backspace")

    pcm = array.array('h', [max(-32768, min(32767, int(round(x)))) for x in buf])
    path = os.path.join(out_dir, f"preview-{tag}.wav")
    w = wave.open(path, 'w')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes()); w.close()
    print(f"    wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "dist"), help="build output directory (default ./dist)")
    out = os.path.abspath(ap.parse_args().out)
    b = os.path.join(out, "build")
    for tag in ("lcars", "lcars-short"):
        d = os.path.join(b, f"ksp-{tag}")
        simulate(out, tag, load(f"{d}/key.wav"), None, load(f"{d}/key-repeat.wav"))
    d = os.path.join(b, "ksp-lcars-plus")
    simulate(out, "lcars-plus", load(f"{d}/key.wav"), load(f"{d}/space.wav"), load(f"{d}/back.wav"))


if __name__ == "__main__":
    main()
