"""Robust EWMA/z-score and two-sided CUSUM change-point detectors (Bible §11.2, §4.2 classical).

For gradual / gray faults (rate_limited_uplink, impaired_link) the link stays operationally up, so
oper-state (§11.1) is silent and the signal lives in the counter *rates* (errors, discards, octets).
Both detectors are causal scalar recurrences: each computes the crossing decision for a sample from
statistics of strictly earlier samples, then folds the current sample into its state — so a sample
never masks its own anomaly, and online == offline replay.

Feed a *rate* series (counters converted to per-second rates by the §9.2 feature stage), not raw
cumulative counters. Thresholds are validation-tuned then frozen (§10.2); defaults are placeholders.
"""

from __future__ import annotations

from closcall.sensors.common import Alarm, Debouncer, Sample

_MAD_TO_SIGMA = 1.4826  # scales mean-absolute-deviation to a robust sigma estimate for gaussians


class RobustEwmaZScore:
    """EWMA mean + EWMA mean-absolute-deviation; raise when |z| = |x-mean|/sigma crosses (§11.2).

    Robust to heavy tails via MAD-based scale rather than variance. `warmup` samples establish a
    baseline before any alarm is allowed.
    """

    def __init__(
        self,
        *,
        alpha: float = 0.3,
        z_threshold: float = 4.0,
        warmup: int = 5,
        persistence: int = 2,
        cooldown_s: float = 30.0,
        eps: float = 1e-9,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self._alpha = alpha
        self._z_threshold = z_threshold
        self._warmup = warmup
        self._eps = eps
        self._deb = Debouncer(persistence=persistence, cooldown_s=cooldown_s)
        self._mean: float | None = None
        self._mad: float = 0.0
        self._n: int = 0

    def update(self, sample: Sample) -> Alarm | None:
        x = sample.value
        if self._mean is None:  # first sample seeds the baseline; no decision yet
            self._mean = x
            self._n = 1
            return None
        dev = abs(x - self._mean)  # deviation from the PAST estimate (causal)
        sigma = _MAD_TO_SIGMA * self._mad
        z = (x - self._mean) / sigma if (self._n >= self._warmup and sigma > self._eps) else 0.0
        crossing = abs(z) >= self._z_threshold
        # Hold the baseline during a crossing: folding an anomaly into mean/scale would let it
        # self-mask after one sample, so a sustained shift could never satisfy persistence>=2. Only
        # non-anomalous samples update the baseline (robust behavior); it resumes on recovery.
        if not crossing:
            self._mean = (1 - self._alpha) * self._mean + self._alpha * x
            self._mad = (1 - self._alpha) * self._mad + self._alpha * dev
        self._n += 1
        if self._deb.observe(sample.t, crossing):
            return Alarm(sample.t, "robust_ewma_z", f"|z|>={self._z_threshold}")
        return None


class Cusum:
    """Two-sided CUSUM change-point detector on a slowly-tracked reference mean (§11.2).

    Accumulates signed deviations beyond a slack band `slack_k`; raises when either the upward
    (`sp`) or downward (`sn`) cumulative sum exceeds `threshold_h`, then resets. Inputs are assumed
    roughly standardized (the §9.2 feature stage scales), so `slack_k`/`threshold_h` are in sigma.
    """

    def __init__(
        self,
        *,
        slack_k: float = 0.5,
        threshold_h: float = 5.0,
        ref_alpha: float = 0.05,
        warmup: int = 5,
        persistence: int = 1,
        cooldown_s: float = 30.0,
    ) -> None:
        self._slack_k = slack_k
        self._threshold_h = threshold_h
        self._ref_alpha = ref_alpha
        self._warmup = warmup
        self._deb = Debouncer(persistence=persistence, cooldown_s=cooldown_s)
        self._mean: float | None = None
        self._sp: float = 0.0
        self._sn: float = 0.0
        self._n: int = 0

    def update(self, sample: Sample) -> Alarm | None:
        x = sample.value
        if self._mean is None:
            self._mean = x
            self._n = 1
            return None
        d = x - self._mean  # deviation from the past reference (causal)
        self._sp = max(0.0, self._sp + d - self._slack_k)
        self._sn = min(0.0, self._sn + d + self._slack_k)
        crossing = self._n >= self._warmup and (
            self._sp > self._threshold_h or -self._sn > self._threshold_h
        )
        self._mean = (1 - self._ref_alpha) * self._mean + self._ref_alpha * x
        self._n += 1
        if crossing:  # reset accumulators after a detection
            self._sp = 0.0
            self._sn = 0.0
        if self._deb.observe(sample.t, crossing):
            return Alarm(sample.t, "cusum", f"S>{self._threshold_h}")
        return None


__all__ = ["Cusum", "RobustEwmaZScore"]
