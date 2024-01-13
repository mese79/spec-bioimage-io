from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Tuple,
    Type,
    Union,
)

from pydantic import Field
from pydantic_core import PydanticUndefined
from typing_extensions import Annotated

import bioimageio.spec
from bioimageio.spec import application, collection, dataset, generic, model, notebook
from bioimageio.spec._internal.base_nodes import InvalidDescription, ResourceDescriptionBase
from bioimageio.spec._internal.constants import DISCOVER, LATEST, VERSION
from bioimageio.spec._internal.types import BioimageioYamlContent, RelativeFilePath, YamlValue
from bioimageio.spec._internal.utils import iterate_annotated_union
from bioimageio.spec._internal.validation_context import validation_context_var
from bioimageio.spec.summary import ErrorEntry, ValidationSummary, WarningEntry

_ResourceDescr_v0_2 = Union[
    Annotated[
        Union[
            application.v0_2.ApplicationDescr,
            collection.v0_2.CollectionDescr,
            dataset.v0_2.DatasetDescr,
            model.v0_4.ModelDescr,
            notebook.v0_2.NotebookDescr,
        ],
        Field(discriminator="type"),
    ],
    generic.v0_2.GenericDescr,
]
"""A resource description following the 0.2.x (model: 0.4.x) specification format"""

_ResourceDescription_v0_3 = Union[
    Annotated[
        Union[
            application.v0_3.ApplicationDescr,
            collection.v0_3.CollectionDescr,
            dataset.v0_3.DatasetDescr,
            model.v0_5.ModelDescr,
            notebook.v0_3.NotebookDescr,
        ],
        Field(discriminator="type"),
    ],
    generic.v0_3.GenericDescr,
]
"""A resource description following the 0.3.x (model: 0.5.x) specification format"""

LatestResourceDescr = _ResourceDescription_v0_3
"""A resource description following the latest specification format"""


SpecificResourceDescr = Annotated[
    Union[
        application.AnyApplicationDescr,
        collection.AnyCollectionDescr,
        dataset.AnyDatasetDescr,
        model.AnyModelDescr,
        notebook.AnyNotebookDescr,
    ],
    Field(discriminator="type"),
]
"""Any of the implemented, non-generic resource descriptions"""

ResourceDescr = Union[
    SpecificResourceDescr,
    generic.AnyGenericDescr,
]
"""Any of the implemented resource descriptions"""


def dump_description(rd: ResourceDescr, exclude_unset: bool = True) -> BioimageioYamlContent:
    """Converts a resource to a dictionary containing only simple types that can directly be serialzed to YAML."""
    return rd.model_dump(mode="json", exclude_unset=exclude_unset)


def build_description(
    data: BioimageioYamlContent,
    /,
    *,
    format_version: Union[Literal["discover"], Literal["latest"], str] = DISCOVER,
) -> Union[ResourceDescr, InvalidDescription]:
    discovered_type, discovered_format_version, use_format_version = _check_type_and_format_version(data)
    if use_format_version != discovered_format_version:
        data = dict(data)
        data["format_version"] = use_format_version
        future_patch_warning = WarningEntry(
            loc=("format_version",),
            msg=f"Treated future patch version {discovered_format_version} as {use_format_version}.",
            type="alert",
        )
    else:
        future_patch_warning = None

    fv = use_format_version if format_version == DISCOVER else format_version
    rd_class = _get_rd_class(discovered_type, format_version=fv)
    if isinstance(rd_class, str):
        context = validation_context_var.get()
        rd = InvalidDescription()
        rd.validation_summaries.append(
            ValidationSummary(
                bioimageio_spec_version=VERSION,
                errors=[ErrorEntry(loc=(), msg=rd_class, type="error")],
                name=f"bioimageio.spec static {discovered_type} validation (format version: {format_version}).",
                source_name=str(RelativeFilePath(context.file_name).get_absolute(context.root)),
                status="failed",
                warnings=[],
            )
        )
    else:
        rd = rd_class.load(data)

    assert rd.validation_summaries, "missing validation summary"
    if future_patch_warning:
        rd.validation_summaries[0].warnings.insert(0, future_patch_warning)

    return rd


def validate_format(
    data: BioimageioYamlContent,
    /,
    *,
    as_format: Union[Literal["discover", "latest"], str] = DISCOVER,
) -> ValidationSummary:
    rd = build_description(data, format_version=as_format)
    return rd.validation_summaries[0]


def _check_type_and_format_version(data: Union[YamlValue, BioimageioYamlContent]) -> Tuple[str, str, str]:
    if not isinstance(data, dict):
        raise TypeError(f"Invalid content of type '{type(data)}'")

    typ = data.get("type")
    if not isinstance(typ, str):
        raise TypeError(f"Invalid type '{typ}' of type {type(typ)}")

    fv = data.get("format_version")
    if not isinstance(fv, str):
        raise TypeError(f"Invalid format version '{fv}' of type {type(fv)}")

    if fv in _get_supported_format_versions(typ):
        use_fv = fv
    elif hasattr(bioimageio.spec, typ):
        # type is specialized...
        type_module = getattr(bioimageio.spec, typ)
        # ...and major/minor format version is unknown
        v_module = type_module  # use latest
        if fv.count(".") == 2:
            v_module_name = f"v{fv[:fv.rfind('.')].replace('.', '_')}"
            if hasattr(type_module, v_module_name):
                # ...and we know the major/minor format version (only patch is unknown)
                v_module = getattr(type_module, v_module_name)

        rd_class = getattr(v_module, typ.capitalize() + "Descr")
        assert issubclass(rd_class, ResourceDescriptionBase)
        use_fv = rd_class.implemented_format_version
    else:
        # fallback: type is not specialized (yet) and format version is unknown
        use_fv = generic.GenericDescr.implemented_format_version  # latest generic

    return typ, fv, use_fv


def _get_rd_class(type_: str, /, format_version: str = LATEST) -> Union[Type[ResourceDescr], str]:
    """Get the appropriate resource description class for a given `type` and `format_version`.

    returns:
        resource description class
        or string with error message

    """
    assert isinstance(format_version, str)
    if format_version != LATEST and format_version.count(".") == 0:
        format_version = format_version + ".0"
    elif format_version.count(".") == 2:
        format_version = format_version[: format_version.rfind(".")]

    rd_classes: Dict[str, Dict[str, Type[ResourceDescr]]] = {}
    for typ, rd_class in _iterate_over_rd_classes():
        per_fv: Dict[str, Type[ResourceDescr]] = rd_classes.setdefault(typ, {})

        ma, mi, _pa = rd_class.implemented_format_version_tuple
        key = f"{ma}.{mi}"
        assert key not in per_fv, (key, per_fv)
        per_fv[key] = rd_class

    for typ, rd_class in _iterate_over_latest_rd_classes():
        rd_classes[typ]["latest"] = rd_class

    rd_class = rd_classes.get(type_, rd_classes["generic"]).get(format_version)
    if rd_class is None:
        return f"{type_} (or generic) specification {format_version} does not exist."

    return rd_class


def _get_supported_format_versions(typ: str) -> Tuple[str, ...]:
    supported: Dict[str, List[str]] = {}
    for t, rd_class in _iterate_over_rd_classes():
        format_versions = supported.setdefault(t, [])
        ma, mi, pa = rd_class.implemented_format_version_tuple
        for p in range(pa + 1):
            format_versions.append(f"{ma}.{mi}.{p}")

    supported["model"].extend([f"0.3.{i}" for i in range(7)])  # model 0.3 can be converted
    return tuple(supported.get(typ, supported["generic"]))


def _iterate_over_rd_classes() -> Iterable[Tuple[str, Type[ResourceDescr]]]:
    for rd_class in iterate_annotated_union(ResourceDescr):
        typ = rd_class.model_fields["type"].default
        if typ is PydanticUndefined:
            typ = "generic"

        assert isinstance(typ, str), typ
        yield typ, rd_class


def _iterate_over_latest_rd_classes() -> Iterable[Tuple[str, Type[ResourceDescr]]]:
    for rd_class in iterate_annotated_union(LatestResourceDescr):
        typ: Any = rd_class.model_fields["type"].default
        if typ is PydanticUndefined:
            typ = "generic"

        assert isinstance(typ, str), typ
        yield typ, rd_class
