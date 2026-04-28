"""
run_eval.py — score the bullying / behavior detector against labeled clips.

Run from repo root:
    python eval/run_eval.py

Reads:
    eval/labels.csv  (filename, truth_label)
    eval/clips/*.mp4

Prints:
    - per-clip prediction (any incident fired? primary signal? score?)
    - precision / recall vs truth
    - false positive rate on normal/crowd_normal clips
"""

import csv
import os
import sys
import time

# Allow `import camera` from the backend/ directory
HERE  = os.path.dirname(os.path.abspath(__file__))
ROOT  = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from camera import CameraProcessor, set_clips_dir  # noqa: E402


POSITIVE = {"fight", "crowd_bully"}
NEGATIVE = {"normal", "crowd_normal", "note_passing"}


def run_one(clip_path: str, max_wait_s: float = 60.0):
    """Run one clip; return list of incidents that fired."""
    proc = CameraProcessor()
    incidents: list = []
    proc.on_bullying_incident = incidents.append

    if not proc.start_from_file(clip_path):
        return None

    deadline = time.time() + max_wait_s
    while proc.is_running and time.time() < deadline:
        time.sleep(0.5)
    proc.stop()
    return incidents


def score(rows: list):
    tp = fp = tn = fn = 0
    per_signal: dict = {}
    for r in rows:
        truth = r["truth_label"]
        pred  = bool(r["incidents"])
        if truth in POSITIVE:
            if pred: tp += 1
            else:    fn += 1
        elif truth in NEGATIVE:
            if pred: fp += 1
            else:    tn += 1
        for inc in r["incidents"]:
            sig = inc.get("primary_signal", "?")
            per_signal[sig] = per_signal.get(sig, 0) + 1

    precision = tp / max(tp + fp, 1)
    recall    = tp / max(tp + fn, 1)
    fpr       = fp / max(fp + tn, 1)
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 3),
        "recall":    round(recall, 3),
        "fpr":       round(fpr, 3),
        "fires_by_signal": per_signal,
    }


def main():
    import json
    labels_path  = os.path.join(HERE, "labels.csv")
    clips_dir    = os.path.join(HERE, "clips")
    results_path = os.path.join(HERE, "last_run.json")
    set_clips_dir(os.path.join(HERE, "_tmp_clips"))   # detector wants a clips dir
    write_json   = "--json" in sys.argv

    if not os.path.exists(labels_path):
        print("eval/labels.csv missing"); return 1

    rows_in = []
    with open(labels_path) as f:
        for row in csv.DictReader(f):
            if row.get("filename") and row.get("truth_label"):
                rows_in.append(row)

    if not rows_in:
        print("No labeled clips. See eval/README.md for the workflow.")
        return 0

    print(f"[eval] {len(rows_in)} clip(s)")
    rows_out = []
    for r in rows_in:
        path = os.path.join(clips_dir, r["filename"])
        if not os.path.exists(path):
            print(f"  ! missing: {r['filename']}"); continue
        incidents = run_one(path) or []
        verdict   = "FIRE" if incidents else "----"
        sig       = incidents[0]["primary_signal"] if incidents else "-"
        sc        = incidents[0]["score"]          if incidents else "-"
        print(f"  [{verdict}] {r['filename']:30s} truth={r['truth_label']:12s} sig={sig} score={sc}")
        rows_out.append({**r, "incidents": incidents})

    s = score(rows_out)
    print()
    print(f"  TP={s['tp']}  FP={s['fp']}  TN={s['tn']}  FN={s['fn']}")
    print(f"  precision={s['precision']}  recall={s['recall']}  FPR={s['fpr']}")
    print(f"  fires_by_signal: {s['fires_by_signal']}")

    if write_json:
        out = {
            "run_at":      time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_clips":     len(rows_out),
            "summary":     s,
            "per_clip":    [{
                "filename":       r["filename"],
                "truth_label":    r["truth_label"],
                "fired":          bool(r["incidents"]),
                "primary_signal": (r["incidents"][0]["primary_signal"] if r["incidents"] else None),
                "score":          (r["incidents"][0]["score"]          if r["incidents"] else None),
                "n_incidents":    len(r["incidents"]),
            } for r in rows_out],
        }
        with open(results_path, "w") as f:
            json.dump(out, f, indent=2)
        print(f"[eval] wrote {results_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
