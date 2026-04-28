# Detection Evaluation Harness

Manual ground-truth evaluation for the bullying and behavior heuristics.
Without this, threshold changes are guesses.

## Workflow

1. Capture short clips (10-30 s) of real classroom footage and drop them in
   `apps/edge-agent/eval/clips/`.
2. Label each clip in `apps/edge-agent/eval/labels.csv`:

   ```csv
   filename,truth_label
   clip_001.mp4,fight
   clip_002.mp4,normal
   clip_003.mp4,note_passing
   clip_004.mp4,crowd_normal
   ```

3. Run:

   ```bash
   python apps/edge-agent/eval/run_eval.py
   ```

Allowed `truth_label` values:

- `fight`: should fire
- `crowd_bully`: should fire
- `normal`: should not fire
- `crowd_normal`: group activity, should not fire
- `note_passing`: should not fire today

The runner spins up a headless `CameraProcessor` per clip, captures any
`on_bullying_incident` events, compares them against labels, and prints
precision, recall, false-positive rate, and a confusion table.

## Goal

First-pass target:

- Precision >= 0.6
- Recall >= 0.4 for `fight` and `crowd_bully`
- False-positive rate on `normal` < 5%

If the detector cannot hit those numbers on real footage, the heuristics are too
aggressive and thresholds should go up before more features are added.
