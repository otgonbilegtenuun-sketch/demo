# Detection evaluation harness

Manual ground-truth eval for the bullying / behavior heuristics.
Without this, threshold tweaks are guesses.

## Workflow

1. Capture short clips (~10–30 s) of real classroom footage and drop them in
   `eval/clips/`. Filenames are arbitrary; what matters is the label file.
2. Label each clip in `eval/labels.csv`:

   ```
   filename,truth_label
   clip_001.mp4,fight
   clip_002.mp4,normal
   clip_003.mp4,note_passing
   clip_004.mp4,crowd_normal
   ```

   Allowed `truth_label` values:
   - `fight`         — should fire
   - `crowd_bully`   — should fire (multiple people targeting one)
   - `normal`        — should NOT fire
   - `crowd_normal`  — group activity, should NOT fire (group work, recess play)
   - `note_passing`  — should NOT fire today (will once pose lands)

3. Run `python eval/run_eval.py`. It will:
   - Spin up a headless `CameraProcessor` per clip via `start_from_file`
   - Capture any `on_bullying_incident` events that fire
   - Compare against the truth labels
   - Print per-signal precision / recall and a confusion table

## Goal

Target on first pass: **precision >= 0.6**, **recall >= 0.4** for `fight` and
`crowd_bully`. False-positive rate on `normal` < 5%. If you can't hit those,
the heuristics are too aggressive and `INCIDENT_THRESHOLD` should go up.

Re-run after every threshold change. Save numbers in `eval/runs/` to track
progress.
