from typing import Literal, Optional

from pydantic import HttpUrl

from bioimageio.spec._internal.base_nodes import Node
from bioimageio.spec._internal.types import DatasetId as DatasetId
from bioimageio.spec.generic.v0_2 import AbsoluteFilePath as AbsoluteFilePath
from bioimageio.spec.generic.v0_2 import Attachments as Attachments
from bioimageio.spec.generic.v0_2 import Author as Author
from bioimageio.spec.generic.v0_2 import Badge as Badge
from bioimageio.spec.generic.v0_2 import CiteEntry as CiteEntry
from bioimageio.spec.generic.v0_2 import FileSource as FileSource
from bioimageio.spec.generic.v0_2 import GenericBase
from bioimageio.spec.generic.v0_2 import LinkedResource as LinkedResource
from bioimageio.spec.generic.v0_2 import Maintainer as Maintainer
from bioimageio.spec.generic.v0_2 import RelativeFilePath as RelativeFilePath
from bioimageio.spec.generic.v0_2 import ResourceId as ResourceId


class Dataset(GenericBase, title="bioimage.io dataset specification"):
    """A bioimage.io dataset resource description file (dataset RDF) describes a dataset relevant to bioimage
    processing.
    """

    type: Literal["dataset"] = "dataset"

    source: Optional[HttpUrl] = None
    """"URL to the source of the dataset."""


class LinkedDataset(Node):
    """Reference to a bioimage.io dataset."""

    id: DatasetId
    """A valid dataset `id` from the bioimage.io collection."""
