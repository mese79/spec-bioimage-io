from __future__ import annotations

import ast
import collections.abc
import inspect
import traceback
from abc import ABC
from copy import deepcopy
from typing import (
    Any,
    ClassVar,
    Dict,
    FrozenSet,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
    get_type_hints,
)

import pydantic
from pydantic import (
    AnyUrl,
    DirectoryPath,
    Field,
    GetCoreSchemaHandler,
    PrivateAttr,
    StringConstraints,
    TypeAdapter,
    model_validator,
)
from pydantic_core import PydanticUndefined, core_schema
from typing_extensions import Annotated, LiteralString, Never, Self

from bioimageio.spec._internal import settings
from bioimageio.spec._internal.constants import (
    ERROR,
    IN_PACKAGE_MESSAGE,
    INFO,
    VERSION,
    WARNING_LEVEL_CONTEXT_KEY,
    WARNING_LEVEL_TO_NAME,
)
from bioimageio.spec._internal.io_utils import download, get_sha256
from bioimageio.spec._internal.types import BioimageioYamlContent, RelativeFilePath
from bioimageio.spec._internal.types import FileSource as FileSource
from bioimageio.spec._internal.types import Sha256 as Sha256
from bioimageio.spec._internal.utils import unindent
from bioimageio.spec._internal.validation_context import (
    ValidationContext,
    validation_context_var,
)
from bioimageio.spec.summary import ErrorEntry, ValidationSummary, WarningEntry


class Node(
    pydantic.BaseModel,
    extra="forbid",
    frozen=False,
    populate_by_name=True,
    revalidate_instances="always",
    validate_assignment=True,
    validate_default=True,
    validate_return=True,
):
    """Subpart of a resource description"""

    _stored_validation_context: ValidationContext = PrivateAttr(default_factory=validation_context_var.get)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any):
        super().__pydantic_init_subclass__(**kwargs)
        if settings.set_undefined_field_descriptions_from_var_docstrings:
            cls._set_undefined_field_descriptions_from_var_docstrings()
            # cls._set_undefined_field_descriptions_from_field_name()  # todo: decide if we can remove this

    @property
    def validation_context(self):
        """The validation context of this Node.
        The validation context is reused, for example,
        when validating assignments or resolving relative files during packaging.
        """
        return self._stored_validation_context

    @classmethod
    def model_validate(
        cls,
        obj: Union[Any, Dict[str, Any]],
        *,
        strict: Optional[bool] = None,
        from_attributes: Optional[bool] = None,
        context: Union[ValidationContext, Dict[str, Any], None] = None,
    ) -> Self:
        """Validate a pydantic model instance.

        Args:
            obj: The object to validate.
            strict: Whether to raise an exception on invalid fields.
            from_attributes: Whether to extract data from object attributes.
            context: Additional context to pass to the validator.

        Raises:
            ValidationError: If the object failed validation.

        Returns:
            The validated description instance.
        """
        __tracebackhide__ = True

        if context is None:
            context = validation_context_var.get()
        elif isinstance(context, dict):
            context = ValidationContext(**context)

        if isinstance(obj, dict):
            assert all(isinstance(k, str) for k in obj), obj

        with context:
            # use validation context as context manager for equal behavior of __init__ and model_validate
            return super().model_validate(obj, strict=strict, from_attributes=from_attributes)

    @classmethod
    def _set_undefined_field_descriptions_from_var_docstrings(cls) -> None:
        for klass in inspect.getmro(cls):
            if issubclass(klass, Node):
                cls._set_undefined_field_descriptions_from_var_docstrings_impl(klass)

    @classmethod
    def _set_undefined_field_descriptions_from_var_docstrings_impl(cls, klass: Type[Any]):
        try:
            source = inspect.getsource(klass)
        except OSError:
            if klass.__module__ == "pydantic.main":
                # klass is probably a dynamically created pydantic Model (using pydantic.create_model)
                return
            else:
                raise

        unindented_source = unindent(source)
        module = ast.parse(unindented_source)
        assert isinstance(module, ast.Module), module
        class_def = module.body[0]
        assert isinstance(class_def, ast.ClassDef), class_def
        if len(class_def.body) < 2:
            return

        for last, node in zip(class_def.body, class_def.body[1:]):
            if not (
                isinstance(last, ast.AnnAssign) and isinstance(last.target, ast.Name) and isinstance(node, ast.Expr)
            ):
                continue

            field_name = last.target.id
            if field_name not in cls.model_fields:
                continue

            info = cls.model_fields[field_name]
            description = info.description or ""
            if description and description != IN_PACKAGE_MESSAGE:
                continue

            doc_node = node.value
            if isinstance(doc_node, ast.Constant):
                docstring = doc_node.value
            else:
                raise NotImplementedError(doc_node)

            info.description = description + docstring

    @classmethod
    def _set_undefined_field_descriptions_from_field_name(cls):
        for name, info in cls.model_fields.items():
            if info.description is None:
                info.description = name


class NodeWithExplicitlySetFields(Node):
    fields_to_set_explicitly: ClassVar[FrozenSet[LiteralString]] = frozenset()
    """set set these fields explicitly with their default value if they are not set,
    such that they are always included even when dumping with 'exlude_unset'"""

    @model_validator(mode="before")
    @classmethod
    def set_fields_explicitly(cls, data: Union[Any, Dict[Any, Any]]) -> Union[Any, Dict[Any, Any]]:
        if isinstance(data, dict):
            for name in cls.fields_to_set_explicitly:
                if name not in data:
                    data[name] = cls.model_fields[name].get_default(call_default_factory=True)

        return data


class ResourceDescriptionBase(NodeWithExplicitlySetFields, ABC):
    """base class for all resource descriptions"""

    _validation_summaries: List[ValidationSummary] = PrivateAttr(default_factory=list)

    fields_to_set_explicitly: ClassVar[FrozenSet[LiteralString]] = frozenset({"type", "format_version"})
    implemented_format_version: ClassVar[str]
    implemented_format_version_tuple: ClassVar[Tuple[int, int, int]]

    # type: LiteralString  # TODO: make abstract fields
    # format_version: LiteralString  # TODO: make abstract fields

    @property
    def validation_summaries(self) -> List[ValidationSummary]:
        return self._validation_summaries

    @property
    def root(self) -> Union[AnyUrl, DirectoryPath]:
        return self._stored_validation_context.root

    @classmethod
    def from_other_descr(cls, descr: Never) -> Self:
        """convert from a different resource description, e.g. different major/minor format_version.

        Args:
            descr: A bioimageio resource description instance
            context: validation context for new description instance.
                If `None` the stored validation context from `descr` is used.

        Raises:
            NotImplementedError: if conversion from given descr class is not implemented
            ValidationError: If conversion failed/resulted in an invalid description
        """
        raise NotImplementedError(f"converting {descr} to {cls.__name__} is not implemented")

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any):
        super().__pydantic_init_subclass__(**kwargs)
        if "format_version" in cls.model_fields and cls.model_fields["format_version"].default is not PydanticUndefined:
            cls.implemented_format_version = cls.model_fields["format_version"].default
            if "." not in cls.implemented_format_version:
                cls.implemented_format_version_tuple = (0, 0, 0)
            else:
                cls.implemented_format_version_tuple = cast(
                    Tuple[int, int, int], tuple(int(x) for x in cls.implemented_format_version.split("."))
                )
            assert len(cls.implemented_format_version_tuple) == 3, cls.implemented_format_version_tuple

    @classmethod
    def load(
        cls,
        data: BioimageioYamlContent,
    ) -> Union[Self, InvalidDescription]:
        context = validation_context_var.get()

        with context:
            rd, errors, tb, val_warnings = cls._load_impl(deepcopy(data))

        if context.warning_level > INFO:
            all_warnings_context = context.model_copy(update={WARNING_LEVEL_CONTEXT_KEY: INFO})
            # get validation warnings by reloading
            with all_warnings_context:
                _, _, _, val_warnings = cls._load_impl(deepcopy(data))

        summary = ValidationSummary(
            bioimageio_spec_version=VERSION,
            errors=errors,
            name=f"bioimageio.spec validation as {rd.type} {rd.format_version}",  # type: ignore
            source_name=str(RelativeFilePath(context.file_name).get_absolute(context.root)),
            status="failed" if errors else "passed",
            warnings=val_warnings,
            traceback=tb,
        )

        rd._validation_summaries.append(summary)
        return rd

    @classmethod
    def _load_impl(
        cls, data: BioimageioYamlContent
    ) -> Tuple[Union[Self, InvalidDescription], List[ErrorEntry], List[str], List[WarningEntry]]:
        rd: Union[Self, InvalidDescription, None] = None
        val_errors: List[ErrorEntry] = []
        val_warnings: List[WarningEntry] = []
        tb: List[str] = []

        try:
            rd = cls.model_validate(data)
        except pydantic.ValidationError as e:
            for ee in e.errors(include_url=False):
                if (severity := ee.get("ctx", {}).get("severity", ERROR)) < ERROR:
                    val_warnings.append(WarningEntry(loc=ee["loc"], msg=ee["msg"], type=ee["type"], severity=severity))
                else:
                    val_errors.append(ErrorEntry(loc=ee["loc"], msg=ee["msg"], type=ee["type"]))

            if len(val_errors) == 0:
                val_errors.append(
                    ErrorEntry(
                        loc=(),
                        msg=(
                            f"Encountered {len(val_warnings)} more severe than warning level "
                            f"'{WARNING_LEVEL_TO_NAME[validation_context_var.get().warning_level]}'"
                        ),
                        type="severe_warnings",
                    )
                )
        except Exception as e:
            val_errors.append(ErrorEntry(loc=(), msg=str(e), type=type(e).__name__))
            tb = traceback.format_tb(e.__traceback__)

        if rd is None:
            try:
                rd = InvalidDescription.model_validate(data)
            except Exception:
                resource_type = cls.model_fields["type"].default
                format_version = cls.implemented_format_version
                rd = InvalidDescription(type=resource_type, format_version=format_version)

        return rd, val_errors, tb, val_warnings


class InvalidDescription(ResourceDescriptionBase, extra="allow", title="An invalid resource description"):
    type: Any = "unknown"
    format_version: Any = "unknown"
    fields_to_set_explicitly: ClassVar[FrozenSet[LiteralString]] = frozenset()


class StringNode(collections.UserString, ABC):
    """deprecated! don't use for new spec fields!"""

    _pattern: ClassVar[str]
    _node_class: Type[Node]
    _node: Optional[Node] = None

    def __init__(self: Self, seq: object) -> None:
        super().__init__(seq)
        type_hints = {fn: t for fn, t in get_type_hints(self.__class__).items() if not fn.startswith("_")}
        defaults = {fn: getattr(self.__class__, fn, Field()) for fn in type_hints}
        field_definitions: Dict[str, Any] = {fn: (t, defaults[fn]) for fn, t in type_hints.items()}
        self._node_class = pydantic.create_model(
            self.__class__.__name__,
            __base__=Node,
            __module__=self.__module__,
            **field_definitions,
        )

        # freeze after initialization
        def __setattr__(self: Self, __name: str, __value: Any):
            raise AttributeError(f"{self} is immutable.")

        self.__setattr__ = __setattr__  # type: ignore

    @property
    def model_fields(self):
        return self._node_class.model_fields

    def __getattr__(self, name: str):
        if name in self._node_class.model_fields:
            if self._node is None:
                raise AttributeError(f"{name} only available after validation")

            return getattr(self._node, name)

        raise AttributeError(name)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Type[Any], handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        assert issubclass(source, StringNode), source
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(pattern=cls._pattern),
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize,
                info_arg=False,
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def _get_data(cls, valid_string_data: str) -> Dict[str, Any]:
        raise NotImplementedError(f"{cls.__name__}._get_data()")

    @classmethod
    def _validate(cls, value: str) -> Self:
        valid_string_data = TypeAdapter(Annotated[str, StringConstraints(pattern=cls._pattern)]).validate_python(value)
        data = cls._get_data(valid_string_data)
        self = cls(valid_string_data)
        object.__setattr__(self, "_node", self._node_class.model_validate(data))
        return self

    def _serialize(self) -> str:
        return self.data


class KwargsNode(Node):
    def get(self, item: str, default: Any = None) -> Any:
        return self[item] if item in self else default

    def __getitem__(self, item: str) -> Any:
        if item in self.model_fields:
            return getattr(self, item)
        else:
            raise KeyError(item)

    def __contains__(self, item: str) -> int:
        return item in self.model_fields


class FileDescr(Node):
    source: FileSource
    """∈📦 file source"""

    sha256: Optional[Sha256] = None
    """SHA256 checksum of the source file"""

    @model_validator(mode="after")
    def validate_sha256(self) -> Self:
        context = self._stored_validation_context
        if not context.perform_io_checks:
            return self

        local_source = download(self.source, sha256=self.sha256, root=context.root).path
        actual_sha = get_sha256(local_source)
        if self.sha256 is None:
            self.sha256 = actual_sha
        elif self.sha256 != actual_sha:
            raise ValueError(
                f"Sha256 mismatch for {self.source}. Expected {self.sha256}, got {actual_sha}. "
                "Update expected `sha256` or point to the matching file."
            )

        return self

    def download(self):
        return download(self.source, sha256=self.sha256, root=self._stored_validation_context.root)
