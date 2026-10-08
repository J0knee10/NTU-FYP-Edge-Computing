"""Step 1: feature extraction. One feature vector per window of vibration.

    from features import DEFAULT_SPEC, extract, Normaliser
"""

from .extract import FEATURE_NAMES, Windows, extract, extract_many
from .normalise import Normaliser
from .spec import DEFAULT_SPEC, FeatureSpec

__all__ = ["DEFAULT_SPEC", "FEATURE_NAMES", "FeatureSpec", "Normaliser", "Windows", "extract", "extract_many"]
