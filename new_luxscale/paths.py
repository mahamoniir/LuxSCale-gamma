"""Resolve LuxScaleAI repository root (parent directory of the ``luxscale`` package)."""

import os


def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
