from typing import Any, ClassVar, Dict, Literal, Tuple, Union

from pydantic import Field, TypeAdapter, field_validator
from typing_extensions import Annotated

from bioimageio.spec._internal.types import NonEmpty, RdfContent
from bioimageio.spec._internal.validation_context import InternalValidationContext
from bioimageio.spec.application.v0_2 import Application as Application02
from bioimageio.spec.application.v0_3 import Application as Application03
from bioimageio.spec.collection import v0_2
from bioimageio.spec.dataset.v0_2 import Dataset as Dataset02
from bioimageio.spec.dataset.v0_3 import Dataset as Dataset03
from bioimageio.spec.generic.v0_2 import Generic as Generic02
from bioimageio.spec.generic.v0_3 import *
from bioimageio.spec.generic.v0_3 import GenericBase
from bioimageio.spec.model.v0_4 import Model as Model04
from bioimageio.spec.model.v0_5 import Model as Model05
from bioimageio.spec.notebook.v0_2 import Notebook as Notebook02
from bioimageio.spec.notebook.v0_3 import Notebook as Notebook03

__all__ = [
    "Attachments",
    "Author",
    "Badge",
    "CiteEntry",
    "Collection",
    "CollectionEntry",
    "LinkedResource",
    "Maintainer",
]


AnyApplication = Annotated[Union[Application02, Application03], Field(discriminator="format_version")]
AnyDataset = Annotated[Union[Dataset02, Dataset03], Field(discriminator="format_version")]
AnyModel = Annotated[Union[Model04, Model05], Field(discriminator="format_version")]
AnyNotebook = Annotated[Union[Notebook02, Notebook03], Field(discriminator="format_version")]

EntryNode = Union[
    Annotated[Union[AnyApplication, AnyDataset, AnyModel, AnyNotebook], Field(discriminator="type")], Generic02, Generic
]


class CollectionEntry(v0_2.CollectionEntryBase, frozen=True):
    """A valid resource description (RD).
    The entry RD is based on the collection description itself.
    Fields are added/overwritten by the content of `rdf_source` if `rdf_source` is specified,
    and finally added/overwritten by any fields specified directly in the entry.
    Except for the `id` field, fields are overwritten entirely, their content is not merged!
    The final `id` for each collection entry is composed of the collection's `id`
    and the entry's 'sub-'`id`, specified remotely as part of `rdf_source` or superseeded in-place,
    such that the `final_entry_id = <collection_id>/<entry_id>`"""

    entry_adapter: ClassVar[TypeAdapter[EntryNode]] = TypeAdapter(EntryNode)
    _entry: EntryNode

    @property
    def entry(self) -> EntryNode:
        return self._entry


class Collection(GenericBase, extra="allow", frozen=True, title="bioimage.io collection specification"):
    """A bioimage.io collection resource description file (collection RDF) describes a collection of bioimage.io
    resources.
    The resources listed in a collection RDF have types other than 'collection'; collections cannot be nested.
    """

    type: Literal["collection"] = "collection"

    @classmethod
    def _update_context_and_data(cls, context: InternalValidationContext, data: Dict[Any, Any]) -> None:
        super()._update_context_and_data(context, data)
        collection_base_content = {k: v for k, v in data.items() if k != "collection"}
        assert "collection_base_content" not in context or context["collection_base_content"] == collection_base_content
        context["collection_base_content"] = collection_base_content

    collection: NonEmpty[Tuple[CollectionEntry, ...]]
    """Collection entries"""

    @field_validator("collection")
    @classmethod
    def check_unique_ids(cls, value: NonEmpty[Tuple[CollectionEntry, ...]]) -> NonEmpty[Tuple[CollectionEntry, ...]]:
        v0_2.Collection.check_unique_ids_impl(value)
        return value

    @classmethod
    def convert_from_older_format(cls, data: RdfContent, context: InternalValidationContext) -> None:
        v0_2.Collection.move_groups_to_collection_field(data)
        super().convert_from_older_format(data, context)
