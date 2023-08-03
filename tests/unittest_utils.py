from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional, Sequence, Type, Union
from unittest import TestCase

from pydantic import TypeAdapter, ValidationError
from ruamel.yaml import YAML

from bioimageio.spec import LatestResourceDescription, ResourceDescription
from bioimageio.spec.shared.nodes import Node
from bioimageio.spec.shared.validation import ValidationContext
from bioimageio.spec.utils import format_summary, load_description

yaml = YAML(typ="safe")


@dataclass
class SubTest(ABC):
    kwargs: Dict[str, Any]
    name: Optional[str] = None
    context: Optional[ValidationContext] = None
    node_class: Optional[Type[Node]] = None

    def __post_init__(self):
        if self.__class__ == SubTest:
            raise TypeError("Cannot instantiate abstract class.")


@dataclass
class Valid(SubTest):
    expected_dump_raw: Optional[Dict[str, Any]] = None
    expected_dump_python: Optional[Dict[str, Any]] = None


@dataclass
class Invalid(SubTest):
    expect: Type[Exception] = ValidationError


@dataclass
class TypeSubTest:
    val: Any
    exp: Any


class TestBases:
    class TestNode(TestCase, ABC):
        """template to test any Node subclass with valid and invalid kwargs"""

        default_node_class: Type[Node]
        default_context: ValidationContext = ValidationContext(root=Path(__file__).parent)

        sub_tests: Sequence[SubTest]
        allow_empty: bool = False

        def test_valid(self):
            for st in self.sub_tests:
                if isinstance(st, Invalid):
                    continue

                assert isinstance(st, Valid)
                with self.subTest(**self.get_subtest_kwargs(st)):
                    nc = self.get_node_class(st)
                    node = nc.model_validate(st.kwargs, context=self.get_context(st))
                    for mode, expected in [
                        ("python", st.expected_dump_python),
                        ("json", st.expected_dump_raw),
                    ]:
                        actual = node.model_dump(mode=mode, round_trip=True)
                        assert expected is None or actual == expected, (actual, expected)

        def test_invalid(self):
            for st in self.sub_tests:
                if isinstance(st, Valid):
                    continue

                assert isinstance(st, Invalid)
                with self.subTest(**self.get_subtest_kwargs(st)):
                    nc = self.get_node_class(st)
                    self.assertRaises(st.expect, nc.model_validate, st.kwargs, context=self.get_context(st))

        def test_empty(self):
            """assure that emtpy input data raises a validation error, not a KeyError, AttributeError, etc."""
            if not hasattr(self, "default_node_class"):
                self.skipTest("no default node class specified")

            nc = self.default_node_class
            if self.allow_empty:
                _ = nc.model_validate({})
            else:
                self.assertRaises(ValidationError, nc.model_validate, {})

        def get_context(self, st: SubTest) -> Dict[str, Any]:
            if st.context is None:
                return dict(self.default_context)
            else:
                return dict(st.context)

        def get_node_class(self, st: SubTest) -> Type[Node]:
            return st.node_class or self.default_node_class

        @staticmethod
        def get_subtest_kwargs(st: SubTest) -> Dict[str, Any]:
            if st.name is not None:
                return dict(name=st.name)
            else:
                ret = dict(st.kwargs)
                if st.context is not None:
                    ret["context"] = st.context

                return ret

    class TestType(TestCase, ABC):
        type_: ClassVar[Type[Any]]
        valid: Sequence[Union[Any, TypeSubTest]]
        invalid: Sequence[Any]
        type_adapter: TypeAdapter[Any]

        @classmethod
        def setUpClass(cls) -> None:
            cls.type_adapter = TypeAdapter(cls.type_)
            return super().setUpClass()

        def test_valid(self):
            for v in self.valid:
                if isinstance(v, TypeSubTest):
                    val = v.val
                else:
                    val = v

                with self.subTest(v=val):
                    try:
                        actual = self.type_adapter.validate_python(v)
                    except Exception as e:
                        self.fail(str(e))

                    if isinstance(v, TypeSubTest):
                        self.assertEqual(actual, v.exp)

        def test_invalid(self):
            for v in self.invalid:
                with self.subTest(iv=v):
                    self.assertRaises(ValidationError, self.type_adapter.validate_python, v)

    class TestManyRdfs(TestCase, ABC):
        rdf_root: Path
        adapter: ClassVar[TypeAdapter[ResourceDescription]] = TypeAdapter(ResourceDescription)
        latest_adapter: ClassVar[TypeAdapter[LatestResourceDescription]] = TypeAdapter(LatestResourceDescription)

        def __init_subclass__(cls) -> None:
            for rdf in cls.yield_rdf_paths():

                def test_rdf(self: TestBases.TestManyRdfs, rdf_path: Path = rdf) -> None:
                    with rdf_path.open(encoding="utf-8") as f:
                        data = yaml.load(f)

                    context = ValidationContext(root=rdf_path.parent)
                    if rdf_path.stem.startswith("invalid"):
                        rd, _ = load_description(data, context=context)
                        if rd is not None:
                            self.fail("Invalid RDF passed validation")

                    with self.subTest("as-is"):
                        rd, summary = load_description(data, context=context, format_version="discover")
                        if rd is None:
                            self.fail(format_summary(summary))

                        deserialized = rd.model_dump()
                        self.assertEqual(data, deserialized, "roundtrip")

                    with self.subTest("as-latest"):
                        rd, summary = load_description(data, context=context, format_version="latest")
                        if rd is None:
                            self.fail(format_summary(summary))

                        deserialized = rd.model_dump()
                        self.assertEqual(data, deserialized, "roundtrip")

                subfolder = "".join(f"_{sf}" for sf in rdf.relative_to(cls.rdf_root).as_posix().split("/")[:-1])
                test_case_name: str = f"test{subfolder}_{rdf.stem}"
                setattr(cls, test_case_name, test_rdf)

            return super().__init_subclass__()

        @classmethod
        def yield_rdf_paths(cls):
            assert cls.rdf_root.exists()
            for rdf in cls.rdf_root.glob("**/*.yaml"):
                if rdf.name.startswith("invalid_rdf") or rdf.name.startswith("rdf"):
                    yield rdf
