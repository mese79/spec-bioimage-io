import json
from pathlib import Path

from . import nodes, raw_nodes, schema, utils
from .common import BIOIMAGEIO_CACHE_PATH, get_args, yaml  # noqa
from .utils import download_uri_to_local_path, get_dict_and_root_path_from_yaml_source

_license_file = Path(__file__).parent.parent / "static" / "licenses.json"
_license_data = json.loads(_license_file.read_text())

LICENSES = {x["licenseId"]: x for x in _license_data["licenses"]}
LICENSE_DATA_VERSION = _license_data["licenseListVersion"]
