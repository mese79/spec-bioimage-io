from unittest import TestCase


class TestForwardCompatibility(TestCase):
    def setUp(self) -> None:
        return super().setUp()


# def test_forward_compatibility_error(unet2d_fixed_shape):
#     from bioimageio.spec.utils import validate

#     assert yaml is not None
#     data = yaml.load(unet2d_fixed_shape)

#     data["authors"] = 42  # make sure rdf is invalid
#     data["format_version"] = "9999.0.0"  # assume it is valid in a future format version

#     error = validate(data)["error"]

#     # even though the format version is correctly formatted, it should be mentioned here as we treat the future format
#     # version as the current latest. If this attempted forward compatibility fails we have to report that we did it.
#     assert isinstance(error, dict)
#     assert "format_version" in error
