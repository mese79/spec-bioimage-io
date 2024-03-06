import typing
from datetime import datetime
from pathlib import Path

import pytest
from dateutil.parser import isoparse
from pydantic import RootModel, TypeAdapter

from bioimageio.spec._internal import types
from bioimageio.spec._internal.io import RelativeFilePath
from bioimageio.spec._internal.types import Datetime, SiUnit
from tests.utils import check_type

TYPE_ARGS = {
    types.ApplicationId: "appdev/app",
    types.CollectionId: "collectionid",
    types.DatasetId: "dataset-id",
    types.Datetime: (2024, 2, 14),
    types.Datetime: datetime.now().isoformat(),
    types.DeprecatedLicenseId: "AGPL-1.0",
    types.Doi: "10.5281/zenodo.5764892",
    types.Identifier: "id",
    types.IdentifierAnno: "id",
    types.ImportantFileSource: "README.md",
    types.LicenseId: "MIT",
    types.LowerCaseIdentifier: "id",
    types.LowerCaseIdentifierAnno: "id",
    types.ModelId: "modelid",
    types.NotebookId: "notebookid",
    types.OrcidId: "0000-0001-2345-6789",
    types.RelativeFilePath: Path(__file__).relative_to(Path().absolute()),
    types.ResourceId: "resoruce-id",
    types.SiUnit: "kg",
    types.AbsoluteDirectory: str(Path(__file__).absolute().parent),
    types.AbsoluteFilePath: str(Path(__file__).absolute()),
    types.FileName: "lala.py",
    types.Version: "1.0",
    types.HttpUrl: "http://example.com",
    types.Sha256: "0" * 64,
}

IGNORE_TYPES_MEMBERS = {
    "AfterValidator",
    "annotated_types",
    "Annotated",
    "annotations",
    "Any",
    "BeforeValidator",
    "datetime",
    "field_validation",
    "ImportantFileSource",  # an annoated union
    "iskeyword",
    "isoparse",
    "Literal",
    "NotEmpty",
    "RootModel",
    "Sequence",
    "StringConstraints",
    "TypeVar",
    "typing",
    "Union",
    "ValidatedString",
    "YamlValue",
}


@pytest.mark.parametrize(
    "name",
    [
        name
        for name in dir(types)
        if not name.startswith("_") and name not in IGNORE_TYPES_MEMBERS
    ],
)
def test_type_is_usable(name: str):
    """check if a type can be instantiated or is a common Python type (e.g. Union or Literal)"""
    typ = getattr(types, name)
    if typ in TYPE_ARGS:
        args = TYPE_ARGS[typ]
        if not isinstance(args, tuple):
            args = (args,)
        _ = typ(*args)
    elif isinstance(typ, str):
        pass  # ignore string constants
    else:
        origin = typing.get_origin(typ)
        assert origin in (dict, list, typing.Union, typing.Literal) or type(typ) in (
            typing.TypeVar,
        ), name


@pytest.mark.parametrize("path", [Path(__file__), Path()])
def test_relative_path(path: Path):
    with pytest.raises(ValueError):
        _ = RelativeFilePath(path.absolute())

    with pytest.raises(ValueError):
        _ = RelativeFilePath(
            str(path.absolute())  # pyright: ignore[reportArgumentType]
        )

    with pytest.raises(ValueError):
        _ = RelativeFilePath(
            path.absolute().as_posix()  # pyright: ignore[reportArgumentType]
        )


@pytest.mark.parametrize("value", ["lx·s", "kg/m^2·s^-2"])
def test_si_unit(value: str):
    check_type(SiUnit, value)


@pytest.mark.parametrize("value", ["lxs", " kg"])
def test_si_unit_invalid(value: str):
    check_type(SiUnit, value, is_invalid=True)


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            "2019-12-11T12:22:32+00:00",
            isoparse("2019-12-11T12:22:32+00:00"),
        ),
        (
            "2019-12-11T12:22:32",
            datetime(2019, 12, 11, 12, 22, 32),
        ),
        ("2019-12-11T12:22:32Z", isoparse("2019-12-11T12:22:32+00:00")),
        # (  # TODO follow up on https://github.com/pydantic/pydantic/issues/8964
        #     "2019-12-11T12:22:32-00:08",
        #     isoparse("2019-12-11T12:22:32-00:08"),
        # ),
    ],
)
def test_datetime(value: str, expected: datetime):
    check_type(
        Datetime,
        value,
        expected_root=expected,
        expected_deserialized=value.replace("+00:00", "Z"),
    )


@pytest.mark.parametrize(
    "value",
    [
        "2024-03-06T14:21:34.384830",
        "2024-03-06T14:21:34+00:00",
        "2024-03-06T14:21:34+00:05",
        # "2024-03-06T14:21:34-00:08",  # TODO follow up on https://github.com/pydantic/pydantic/issues/8964
    ],
)
def test_datetime_more(value: str):
    DateTime = RootModel[datetime]
    # DateTime = Datetime
    root_adapter = TypeAdapter(DateTime)
    datetime_adapter = TypeAdapter(datetime)

    expected = isoparse(value)

    actual_init = DateTime(expected)
    assert actual_init.root == expected

    actual_root = root_adapter.validate_python(value)
    assert actual_root.root == expected
    assert root_adapter.dump_python(actual_root, mode="python") == expected
    assert root_adapter.dump_python(actual_root, mode="json") == value.replace(
        "+00:00", "Z"
    )

    actual_datetime = datetime_adapter.validate_python(value)
    assert actual_datetime == expected
    assert datetime_adapter.dump_python(actual_datetime, mode="python") == expected
    assert datetime_adapter.dump_python(actual_datetime, mode="json") == value.replace(
        "+00:00", "Z"
    )


@pytest.mark.parametrize(
    "value",
    [
        "2019-12-11T12:22:32+00/00",
        "2019-12-11T12:22:32Y",
        "2019-12-11T12:22:32Zulu",
        "201912-11T12:22:32+00:00",
        "now",
        "today",
    ],
)
def test_datetime_invalid(value: str):
    check_type(Datetime, value, is_invalid=True)
