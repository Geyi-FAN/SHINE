# SHINE

Audio-Switch continuous spoken robot interaction research archive.

## Frozen Ours implementation

- `ours/runtime/`: exact tracked source export of C3r runtime commit `98bcb048d6e61b42125d8027b59f8fda197e6d02`, revision `audio-c3r-prereval-repairs-v8-20261114`.
- `evaluation/ours/`: exact evaluation adapters used for the finished 930 registered first attempts.
- `protocols/ours930_v8_original/`: original category protocol snapshots, not silently normalized.
- `archive/ours930_20261114/`: registration, source hashes, run lock and measurement amendment.
- `results/ours930_v8_original/`: 930-case original results, counts and fixed-model QA audit.
- `results/historical_comparison/`: historical table and explicit comparability audit. Old baseline columns are NOT a completed harmonized rerun.

Actor: π0.5 E3, 744 trajectories, exported step30000 params (EMA provenance unspecified). Four C3r roles use Paratera04 Qwen3.8-27B; spoken interaction uses Qwen3.8-omni-flash-realtime; visual QA retains its Qwen3.8-max channel. YOLO/M1 provides predicted points and observed memory. T1 uses the repaired raw-task direct route. Simulator preparation, benchmark scoring and final task feedback are declared separately; do not describe the entire benchmark as simulator-free.

Original 930 trials finished 2026-11-14. Non-QA Interaction805/840, Target746/792, physical Instruction517/588, T6 qualified QA87/90. Unknowns and one infrastructure-aborted first trial are retained. The data were used during development and are not an independently sealed test set.

## Reproducibility boundaries

This is a versioned research code and evaluation archive, not a self-contained environment image. Model weights, benchmark audio/images/reference action banks, Python/Node dependencies, raw rollout videos and private credentials are external resources. Site-specific absolute paths remain in the frozen source deliberately. Original nested READMEs include historical checkpoints; this root README and archived run lock describe the finished run.

Do not publish `.env`, `private`, API keys or model weights. No credentials are included. Upstream licensing notices in `ours/runtime/THIRD_PARTY.md` and source directories remain applicable; no new blanket license is asserted.

## New common-scoring comparison

The requested rerun preserves the old ASR+Agent Oracle-assisted definition and the old pure-ASR definition. It does not adopt the previous proposed non-Oracle replacement baseline. New common-scoring exports and rerun results will be separately versioned; existing numbers above remain unchanged.

## Review entries

- [Current paper draft table](results/paper_current/TABLE_CURRENT.md) (historical baselines, explicitly not a harmonized final comparison).
- [Common scoring and Oracle baseline definition](docs/EVALUATION_ALIGNMENT.md).
- `python3 scripts/restore_runtime_git.py` reconstructs the exact original shallow runtime commit in a fresh clone; original source bytes, tree and commit identity were verified in a disposable copy. External models/environments and site paths must still be configured.

Common-scoring rerun status:15/15 engineering preflights completed without infrastructure/scoring errors; new1770 registered baseline first attempts started on server240 (four GPU lanes). This is a collection in progress, not a new final score. See evaluation/common_v1/deployment_audit/FORMAL_LAUNCH_STATUS.json.
