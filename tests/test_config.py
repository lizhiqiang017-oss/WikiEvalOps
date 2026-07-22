import pytest
from pydantic import ValidationError

from wikievalops.config import QualityGateRule


def test_quality_gate_rejects_inverted_thresholds():
    with pytest.raises(ValidationError, match="block_below 不能高于 warn_below"):
        QualityGateRule(warn_below=0.8, block_below=0.9)
