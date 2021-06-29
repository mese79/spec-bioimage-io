from typing import Sequence

from marshmallow import missing

from bioimageio.spec import v0_1
from bioimageio.spec.shared.common import get_args
from bioimageio.spec.shared.model_loader_utils import ModelLoaderBase
from . import converters, nodes, raw_nodes, schema


class ModelLoader(ModelLoaderBase):
    preceding_model_loader = v0_1.utils.ModelLoader
    converters = converters
    schema = schema
    raw_nodes = raw_nodes
    nodes = nodes


def get_nn_instance(
    node: nodes.Model,  # type: ignore  # Name "nodes.Model" is not defined ???
    weight_order: Sequence[nodes.WeightsFormat] = get_args(nodes.WeightsFormat),  # type: ignore  # not defined ???
    **kwargs,
):
    assert NotImplementedError("weight_order")
    if isinstance(node, nodes.Model):  # type: ignore
        if not isinstance(node.source, nodes.ImportedSource):  # type: ignore
            raise ValueError(
                f"Encountered unexpected node.source type {type(node.source)}. "  # type: ignore
                f"`get_nn_instance` requires _UriNodeTransformer and _SourceNodeTransformer to be applied beforehand."
            )

        joined_kwargs = {} if node.kwargs is missing else dict(node.kwargs)  # type: ignore
        joined_kwargs.update(kwargs)
        return node.source(**joined_kwargs)
    else:
        raise TypeError(node)
