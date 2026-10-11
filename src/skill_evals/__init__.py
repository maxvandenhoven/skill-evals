"""Evaluate whether coding agents load and follow skills, in Docker Sandboxes.

The `skill-evals` command (see cli.py) runs evals in sandboxes (run.py) and scores
their MLflow traces (score.py, with the scorers in scorers/ and the per-harness trace
readers in traces/). What it runs comes from the project that .skill-evals.yaml
describes (config.py); `skill-evals init` creates one with the shipped harnesses/.
"""
