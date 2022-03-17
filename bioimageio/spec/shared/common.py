import os
import pathlib
import tempfile
import warnings
from typing import Any, Generic, Iterable, List, Optional, Sequence

try:
    from typing import Literal, get_args, get_origin, Protocol
except ImportError:
    from typing_extensions import Literal, get_args, get_origin, Protocol  # type: ignore


try:
    from ruamel.yaml import YAML  # not available in pyodide
except ImportError:
    yaml: Optional["MyYAML"] = None
else:

    class MyYAML(YAML):
        """add convenient improvements over YAML
        improve dump:
            - make sure to dump with utf-8 encoding. on windows encoding 'windows-1252' may otherwise be used
            - expose indentation kwargs for dump
        """

        def dump(self, data, stream=None, *, transform=None):
            if isinstance(stream, pathlib.Path):
                with stream.open("wt", encoding="utf-8") as f:
                    return super().dump(data, f, transform=transform)
            else:
                return super().dump(data, stream, transform=transform)

    yaml = MyYAML(typ="safe")


try:
    from tqdm import tqdm  # not available in pyodide
except ImportError:

    class tqdm:  # type: ignore
        """no-op tqdm"""

        def __init__(self, iterable: Optional[Iterable] = None, *args, **kwargs):
            self.iterable = iterable

        def __iter__(self):
            if self.iterable is not None:
                yield from self.iterable

        def update(self, *args, **kwargs):
            pass


BIOIMAGEIO_CACHE_PATH = pathlib.Path(
    os.getenv("BIOIMAGEIO_CACHE_PATH", pathlib.Path(tempfile.gettempdir()) / "bioimageio_cache")
)
BIOIMAGEIO_USE_CACHE = os.getenv("BIOIMAGEIO_USE_CACHE", "true").lower() in ("false", "no")

# keep a reference to temporary directories and files.
# These temporary locations are used instead of paths in BIOIMAGEIO_CACHE_PATH if BIOIMAGEIO_USE_CACHE is true,
# so that we guarantee that these temporary directories/file objects are not garbage collected too early
# and thus their content removed from disk, while we still have a pathlib.Path pointing there
no_cache_tmp_list: List[Any] = []

BIOIMAGEIO_SITE_CONFIG_URL = "https://raw.githubusercontent.com/bioimage-io/bioimage.io/main/site.config.json"
BIOIMAGEIO_COLLECTION_URL = "https://bioimage-io.github.io/collection-bioimage-io/collection.json"


DOI_REGEX = r"^10[.][0-9]{4,9}\/[-._;()\/:A-Za-z0-9]+$"
RDF_NAMES = ("rdf.yaml", "model.yaml")


class ValidationWarning(UserWarning):
    """a warning category to warn with during RDF validation"""

    @staticmethod
    def get_warning_summary(val_warns: Sequence[warnings.WarningMessage]) -> dict:
        """Summarize warning messages of the ValidationWarning category"""

        def add_to_summary(s, keys, msg):
            key = keys.pop(0)
            if "[" in key:
                key, rest = key.split("[")
                assert rest[-1] == "]"
                idx = int(rest[:-1])
            else:
                idx = None

            if key not in s:
                s[key] = {} if keys or idx is not None else msg

            s = s[key]

            if idx is not None:
                if idx not in s:
                    s[idx] = {} if keys else {"warning": msg}

                s = s[idx]

            if keys:
                assert isinstance(s, dict), (keys, s)
                add_to_summary(s, keys, msg)

        summary: dict = {}
        for vw in val_warns:
            assert issubclass(vw.category, ValidationWarning)
            msg = str(vw.message)
            if ": " in msg:
                keys_, *rest = msg.split(": ")
                msg = ": ".join(rest)
                keys = keys_.split(":")
            else:
                keys = []

            add_to_summary(summary, keys, msg)

        return summary


def get_format_version_module(type_: str, format_version: str):
    assert "." in format_version
    import bioimageio.spec

    type_ = get_spec_type_from_type(type_)
    version_mod_name = "v" + "_".join(format_version.split(".")[:2])
    try:
        return getattr(getattr(bioimageio.spec, type_), version_mod_name)
    except AttributeError:
        raise ValueError(
            f"Invalid RDF format version {format_version} for RDF type {type_}. "
            f"Submodule bioimageio.spec.{type_}.{version_mod_name} does not exist."
        )


def get_patched_format_version(type_: str, format_version: str):
    """return latest patched format version for given type and major/minor of format_version"""
    version_mod = get_format_version_module(type_, format_version)
    return version_mod.format_version


def get_spec_type_from_type(type_: str):
    if type_ in ("model", "collection"):
        return type_
    else:
        return "rdf"


def get_latest_format_version_module(type_: str):
    type_ = get_spec_type_from_type(type_)
    import bioimageio.spec

    try:
        return getattr(bioimageio.spec, type_)
    except AttributeError:
        raise ValueError(f"Invalid RDF type {type_}")


def get_latest_format_version(type_: str):
    return get_latest_format_version_module(type_).format_version


def get_class_name_from_type(type_: str):
    type_ = get_spec_type_from_type(type_)
    if type_ == "rdf":
        return "RDF"
    else:
        return type_.title()


def get_args_flat(tp):
    flat_args = []
    for a in get_args(tp):
        orig = get_origin(a)
        if orig is Literal or orig is Generic:
            flat_args += list(get_args(a))
        else:
            flat_args.append(a)

    return tuple(flat_args)


def nested_default_dict_as_nested_dict(nested_dd):
    if isinstance(nested_dd, dict):
        return {key: (nested_default_dict_as_nested_dict(value)) for key, value in nested_dd.items()}
    elif isinstance(nested_dd, list):
        return [nested_default_dict_as_nested_dict(value) for value in nested_dd]
    else:
        return nested_dd
