import pytest

from clipperx.config import Config


def test_default_config_is_valid():
    Config().validate()


def test_rejects_landscape_output():
    with pytest.raises(ValueError):
        Config(output_width=1920, output_height=1080).validate()


def test_rejects_tiny_analysis_proxy():
    with pytest.raises(ValueError):
        Config(analysis_width=100).validate()
