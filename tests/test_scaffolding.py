"""Sanity check that the project scaffolding is importable. Replace once M2+ adds real modules."""

import api
import pipeline


def test_pipeline_package_imports():
    assert pipeline is not None


def test_api_package_imports():
    assert api is not None
