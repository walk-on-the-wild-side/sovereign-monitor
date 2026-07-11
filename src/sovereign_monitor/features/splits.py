"""Time-aware cross-validation splits (SPEC: expanding windows, never shuffled)."""

from collections.abc import Iterator

import numpy as np


def expanding_window_splits(
    n_observations: int, n_splits: int, minimum_train: int
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train, test) index arrays; training always precedes and grows.

    The observations are assumed time-ordered. The region after minimum_train is
    partitioned into n_splits contiguous test blocks; each split trains on
    everything strictly before its test block.
    """
    if n_observations <= minimum_train:
        raise ValueError("not enough observations for the requested minimum train size")
    test_region = n_observations - minimum_train
    if n_splits < 1 or n_splits > test_region:
        raise ValueError("n_splits must be between 1 and the size of the test region")

    boundaries = np.linspace(minimum_train, n_observations, n_splits + 1, dtype=int)
    for split in range(n_splits):
        test_start, test_end = boundaries[split], boundaries[split + 1]
        yield np.arange(0, test_start), np.arange(test_start, test_end)
