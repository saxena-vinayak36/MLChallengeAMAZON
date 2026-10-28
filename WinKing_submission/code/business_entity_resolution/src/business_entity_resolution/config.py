"""Environment- and path-detection shared across notebooks (Plan §4.2).

The same import works on the local IDE and inside a SageMaker notebook instance;
notebooks may still inline the config cell for copy-paste convenience, but they call
into this module so the truth lives in one place.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass


LOCAL_ROOT_DEFAULT = "/Users/pocketfm/Desktop/amazon_ML/Working Folder"
SAGEMAKER_ROOT_DEFAULT = "/home/ec2-user/SageMaker/ber"


def is_sagemaker() -> bool:
    """True inside a SageMaker notebook/training instance."""
    return pathlib.Path("/opt/ml").exists() or "SM_CURRENT_HOST" in os.environ


@dataclass(frozen=True)
class Paths:
    root: pathlib.Path
    data: pathlib.Path         # student_resource/dataset
    train: pathlib.Path        # student_resource/dataset/train
    test: pathlib.Path         # student_resource/dataset/test
    artifacts: pathlib.Path    # parquet intermediates + runs.jsonl
    output: pathlib.Path       # the two submission TSVs
    src: pathlib.Path
    validator: pathlib.Path

    def ensure(self) -> "Paths":
        for p in (self.artifacts, self.output):
            p.mkdir(parents=True, exist_ok=True)
        return self


def detect_paths(
    local_root: str = LOCAL_ROOT_DEFAULT,
    sagemaker_root: str = SAGEMAKER_ROOT_DEFAULT,
) -> Paths:
    """Return a Paths object appropriate to the current environment.

    Override the root by setting BER_ROOT in the environment before import.
    """
    root_env = os.environ.get("BER_ROOT")
    if root_env:
        root = pathlib.Path(root_env)
    elif is_sagemaker():
        root = pathlib.Path(sagemaker_root)
    else:
        root = pathlib.Path(local_root)

    data = root / "student_resource" / "dataset"
    return Paths(
        root=root,
        data=data,
        train=data / "train",
        test=data / "test",
        artifacts=root / "artifacts",
        output=root / "output",
        src=root / "src",
        validator=root / "student_resource" / "utils" / "validate_submission.py",
    ).ensure()


def n_jobs() -> int:
    """Parallelism derived from the instance, not hardcoded."""
    return os.cpu_count() or 1
