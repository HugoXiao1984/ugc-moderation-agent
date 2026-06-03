"""Wrapper that loads the same jurisdiction scripts that Code Interpreter runs.

Source of truth lives in `policies_scripts/`; this package dynamically loads
those files so imports like `from ugc_moderation.policies import cn` work for
unit tests and Python-side fallbacks.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "policies_scripts"


def _load(name: str):
    path = _SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # satisfies `from common import ...`
    spec.loader.exec_module(module)
    return module


common = _load("common")
cn = _load("cn")
eu = _load("eu")
us = _load("us")

JURISDICTIONS = {"CN": cn, "EU": eu, "US": us}


def evaluate(jurisdiction: str, signals: dict):
    return JURISDICTIONS[jurisdiction.upper()].evaluate(signals)


def scripts_dir() -> Path:
    return _SCRIPTS_DIR
