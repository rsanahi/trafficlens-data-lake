"""
Spatial Reconstruction — Domain Exceptions

Both exceptions inherit from ValueError intentionally:
  - This allows callers using `pytest.raises(ValueError)` or bare `except ValueError`
    to catch them without importing the specific exception class.
  - The subclass names provide specificity at the domain boundary — callers that
    care about the distinction (e.g., application-layer error routing) import the
    specific subclass; callers that just want "invalid input" catch ValueError.
  - Do NOT remove the ValueError inheritance to enforce stricter typing — doing so
    would silently break existing callers and tests.
"""


class SceneReliabilityError(ValueError):
    """
    Domain exception: a SplatScene fails its own internal reliability checks.

    Raised when a reconstruction produces a degenerate scene:
    - Zero Gaussians (failed training run).
    - No registered camera poses (empty SfM output).
    - Reprojection error above MAX_REPROJECTION_ERROR (floater cloud).

    Inherits ValueError for broad-catch compatibility. Use SceneReliabilityError
    directly when routing errors at the application layer.
    """
    pass


class ContractViolationError(ValueError):
    """
    Domain exception: a SplatScene fails the InferenceContract pre-injection validation.

    Raised when a scene passes SplatScene's own internal thresholds (i.e., it is a
    technically valid reconstruction) but does NOT meet the stricter quality bar
    required before entering the synthetic scenario injection or active learning pipeline.

    Inherits ValueError for broad-catch compatibility. Use ContractViolationError
    directly when routing errors at the application layer.
    """
    pass
