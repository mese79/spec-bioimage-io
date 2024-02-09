from pydantic import AnyUrl

from bioimageio.spec._description import validate_format
from bioimageio.spec._internal.types import BioimageioYamlContent
from bioimageio.spec._internal.validation_context import ValidationContext


def test_forward_compatibility(unet2d_data: BioimageioYamlContent):
    data = dict(unet2d_data)
    v_future = "0.9999.0"
    data["format_version"] = v_future  # assume it is valid in a future format version

    summary = validate_format(
        data, context=ValidationContext(root=AnyUrl("https://example.com/"), perform_io_checks=False)
    )
    assert summary.status == "passed", summary.errors

    # expect warning about treating future format version as latest
    ws = summary.warnings
    assert len(ws) >= 1, ws
    assert ws[0].loc == ("format_version",), ws[0].loc


def test_no_forward_compatibility(unet2d_data: BioimageioYamlContent):
    data = dict(unet2d_data)
    data["authors"] = 42  # make sure rdf is invalid
    data["format_version"] = "0.9999.0"  # assume it is valid in a future format version

    summary = validate_format(
        data, context=ValidationContext(root=AnyUrl("https://example.com/"), perform_io_checks=False)
    )
    assert summary.status == "failed", summary

    assert len(summary.errors) == 1, summary.errors
    assert summary.errors[0].loc == ("authors",), summary.errors[0].loc

    # expect warning about treating future format version as latest
    ws = summary.warnings
    assert len(ws) >= 1, ws
    assert ws[0].loc == ("format_version",), ws[0].loc
