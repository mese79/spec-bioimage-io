import typing
import warnings
from copy import deepcopy

from marshmallow import RAISE, ValidationError, missing as missing_, pre_load, validates, validates_schema

from bioimageio.spec.model.v0_3.schema import (
    KerasHdf5WeightsEntry,
    ModelParent,
    OnnxWeightsEntry,
    Postprocessing,
    Preprocessing,
    PytorchScriptWeightsEntry,
    PytorchStateDictWeightsEntry,
    RunMode,
    TensorflowJsWeightsEntry,
    TensorflowSavedModelBundleWeightsEntry,
    WeightsEntryBase,
    _common_sha256_hint,
)
from bioimageio.spec.rdf import v0_2 as rdf
from bioimageio.spec.shared import field_validators, fields
from bioimageio.spec.shared.common import get_args, get_args_flat
from bioimageio.spec.shared.schema import SharedBioImageIOSchema
from . import raw_nodes

Author = rdf.schema.Author
CiteEntry = rdf.schema.CiteEntry


class BioImageIOSchema(SharedBioImageIOSchema):
    raw_nodes = raw_nodes


class Tensor(BioImageIOSchema):
    name = fields.String(
        required=True,
        validate=field_validators.Predicate("isidentifier"),
        bioimageio_description="Tensor name. No duplicates are allowed.",
    )
    description = fields.String()
    axes = fields.Axes(
        required=True,
        bioimageio_description="""Axes identifying characters from: bitczyx. Same length and order as the axes in `shape`.

    | character | description |
    | --- | --- |
    |  b  |  batch (groups multiple samples) |
    |  i  |  instance/index/element |
    |  t  |  time |
    |  c  |  channel |
    |  z  |  spatial dimension z |
    |  y  |  spatial dimension y |
    |  x  |  spatial dimension x |""",
    )
    data_type = fields.String(
        required=True,
        bioimageio_description="The data type of this tensor. For inputs, only `float32` is allowed and the consumer "
        "software needs to ensure that the correct data type is passed here. For outputs can be any of `float32, "
        "float64, (u)int8, (u)int16, (u)int32, (u)int64`. The data flow in bioimage.io models is explained "
        "[in this diagram.](https://docs.google.com/drawings/d/1FTw8-Rn6a6nXdkZ_SkMumtcjvur9mtIhRqLwnKqZNHM/edit).",
    )
    data_range = fields.Tuple(
        (fields.Float(allow_nan=True), fields.Float(allow_nan=True)),
        bioimageio_description="Tuple `(minimum, maximum)` specifying the allowed range of the data in this tensor. "
        "If not specified, the full data range that can be expressed in `data_type` is allowed.",
    )
    shape: fields.Union

    processing_name: str

    @validates_schema
    def validate_processing_kwargs(self, data, **kwargs):
        axes = data["axes"]
        processing_list = data.get(self.processing_name, [])
        for processing in processing_list:
            name = processing.name
            kwargs = processing.kwargs or {}
            kwarg_axes = kwargs.get("axes", "")
            if any(a not in axes for a in kwarg_axes):
                raise ValidationError("`kwargs.axes` needs to be subset of axes")


class InputTensor(Tensor):
    shape = fields.InputShape(required=True, bioimageio_description="Specification of tensor shape.")
    preprocessing = fields.List(
        fields.Nested(Preprocessing), bioimageio_description="Description of how this input should be preprocessed."
    )
    processing_name = "preprocessing"

    @validates_schema
    def zero_batch_step_and_one_batch_size(self, data, **kwargs):
        axes = data["axes"]
        shape = data["shape"]

        bidx = axes.find("b")
        if bidx == -1:
            return

        if isinstance(shape, raw_nodes.ParametrizedInputShape):
            step = shape.step
            shape = shape.min

        elif isinstance(shape, list):
            step = [0] * len(shape)
        else:
            raise ValidationError(f"Unknown shape type {type(shape)}")

        if step[bidx] != 0:
            raise ValidationError(
                "Input shape step has to be zero in the batch dimension (the batch dimension can always be "
                "increased, but `step` should specify how to increase the minimal shape to find the largest "
                "single batch shape)"
            )

        if shape[bidx] != 1:
            raise ValidationError("Input shape has to be 1 in the batch dimension b.")


class OutputTensor(Tensor):
    shape = fields.OutputShape(required=True)
    halo = fields.List(
        fields.Integer,
        bioimageio_description="The halo to crop from the output tensor (for example to crop away boundary effects or "
        "for tiling). The halo should be cropped from both sides, i.e. `shape_after_crop = shape - 2 * halo`. The "
        "`halo` is not cropped by the bioimage.io model, but is left to be cropped by the consumer software. Use "
        "`shape:offset` if the model output itself is cropped and input and output shapes not fixed.",
    )
    postprocessing = fields.List(
        fields.Nested(Postprocessing), bioimageio_description="Description of how this output should be postprocessed."
    )
    processing_name = "postprocessing"

    @validates_schema
    def matching_halo_length(self, data, **kwargs):
        shape = data["shape"]
        halo = data.get("halo")
        if halo is None:
            return
        elif isinstance(shape, list) or isinstance(shape, raw_nodes.ImplicitOutputShape):
            if len(halo) != len(shape):
                raise ValidationError(f"halo {halo} has to have same length as shape {shape}!")
        else:
            raise NotImplementedError(type(shape))


WeightsEntry = typing.Union[
    PytorchStateDictWeightsEntry,
    PytorchScriptWeightsEntry,
    KerasHdf5WeightsEntry,
    TensorflowJsWeightsEntry,
    TensorflowSavedModelBundleWeightsEntry,
    OnnxWeightsEntry,
]


class Model(rdf.schema.RDF):
    raw_nodes = raw_nodes

    class Meta:
        unknown = RAISE

    bioimageio_description = f"""# BioImage.IO Model Resource Description File Specification {get_args(raw_nodes.FormatVersion)[-1]}
This specification defines the fields used in a BioImage.IO-compliant resource description file (`RDF`) for describing AI models with pretrained weights.
These fields are typically stored in YAML files which we called Model Resource Description Files or `model RDF`.
The model RDFs can be downloaded or uploaded to the bioimage.io website, produced or consumed by BioImage.IO-compatible consumers(e.g. image analysis software or other website).

The model RDF YAML file contains mandatory and optional fields. In the following description, optional fields are indicated by _optional_.
_optional*_ with an asterisk indicates the field is optional depending on the value in another field.
"""
    # todo: unify authors with RDF (optional or required?)
    authors = fields.List(
        fields.Nested(Author), required=True, bioimageio_description=rdf.schema.RDF.authors_bioimageio_description
    )

    badges = missing_  # todo: allow badges for Model (RDF has it)
    cite = fields.Nested(
        CiteEntry,
        many=True,
        required=True,  # todo: unify authors with RDF (optional or required?)
        bioimageio_description=rdf.schema.RDF.cite_bioimageio_description,
    )

    download_url = missing_  # todo: allow download_url for Model (RDF has it)

    dependencies = fields.Dependencies(  # todo: add validation (0.4.0?)
        bioimageio_description="Dependency manager and dependency file, specified as `<dependency manager>:<relative "
        "path to file>`. For example: 'conda:./environment.yaml', 'maven:./pom.xml', or 'pip:./requirements.txt'"
    )

    format_version = fields.String(
        validate=field_validators.OneOf(get_args_flat(raw_nodes.FormatVersion)),
        required=True,
        bioimageio_description_order=0,
        bioimageio_description=f"""Version of the BioImage.IO Model Resource Description File Specification used.
This is mandatory, and important for the consumer software to verify before parsing the fields.
The recommended behavior for the implementation is to keep backward compatibility and throw an error if the model yaml
is in an unsupported format version. The current format version described here is
{get_args(raw_nodes.FormatVersion)[-1]}""",
    )

    framework = fields.String(
        validate=field_validators.OneOf(get_args(raw_nodes.Framework)),
        bioimageio_description=f"The deep learning framework of the source code. One of: "
        f"{', '.join(get_args(raw_nodes.Framework))}. This field is only required if the field `source` is present.",
    )

    git_repo = fields.String(
        validate=field_validators.URL(schemes=["http", "https"]),
        bioimageio_description=rdf.schema.RDF.git_repo_bioimageio_description
        + "If the model is contained in a subfolder of a git repository, then a url to the exact folder"
        + "(which contains the configuration yaml file) should be used.",
    )

    icon = missing_  # todo: allow icon for Model (RDF has it)

    kwargs = fields.Kwargs(
        bioimageio_description="Keyword arguments for the implementation specified by `source`. "
        "This field is only required if the field `source` is present."
    )

    language = fields.String(
        validate=field_validators.OneOf(get_args(raw_nodes.Language)),
        bioimageio_maybe_required=True,
        bioimageio_description=f"Programming language of the source code. One of: "
        f"{', '.join(get_args(raw_nodes.Language))}. This field is only required if the field `source` is present.",
    )

    license = fields.String(
        required=True,  # todo: unify license with RDF (optional or required?)
        bioimageio_description=rdf.schema.RDF.license_bioimageio_description,
    )

    name = fields.String(
        # validate=field_validators.Length(max=36),  # todo: enforce in future version (0.4.0?)
        required=True,
        bioimageio_description="Name of this model. It should be human-readable and only contain letters, numbers, "
        "`_`, `-` or spaces and not be longer than 36 characters.",
    )

    packaged_by = fields.List(
        fields.Nested(Author),
        bioimageio_description=f"The persons that have packaged and uploaded this model. Only needs to be specified if "
        f"different from `authors` in root or any entry in `weights`.",
    )

    parent = fields.Nested(
        ModelParent,
        bioimageio_description="Parent model from which the trained weights of this model have been derived, e.g. by "
        "finetuning the weights of this model on a different dataset. For format changes of the same trained model "
        "checkpoint, see `weights`.",
    )

    run_mode = fields.Nested(
        RunMode,
        bioimageio_description="Custom run mode for this model: for more complex prediction procedures like test time "
        "data augmentation that currently cannot be expressed in the specification. "
        "No standard run modes are defined yet.",
    )

    sha256 = fields.String(
        validate=field_validators.Length(equal=64),
        bioimageio_description="SHA256 checksum of the model source code file."
        + _common_sha256_hint
        + " This field is only required if the field source is present.",
    )

    source = fields.ImportableSource(
        bioimageio_maybe_required=True,
        bioimageio_description="Language and framework specific implementation. As some weights contain the model "
        "architecture, the source is optional depending on the present weight formats. `source` can either point to a "
        "local implementation: `<relative path to file>:<identifier of implementation within the source file>` or the "
        "implementation in an available dependency: `<root-dependency>.<sub-dependency>.<identifier>`.\nFor example: "
        "`my_function.py:MyImplementation` or `core_library.some_module.some_function`.",
    )

    timestamp = fields.DateTime(
        required=True,
        bioimageio_description="Timestamp of the initial creation of this model in [ISO 8601]"
        "(#https://en.wikipedia.org/wiki/ISO_8601) format.",
    )

    weights = fields.Dict(
        fields.String(
            validate=field_validators.OneOf(get_args(raw_nodes.WeightsFormat)),
            required=True,
            bioimageio_description=f"Format of this set of weights. Weight formats can define additional (optional or "
            f"required) fields. See [supported_formats_and_operations.md#Weight Format]"
            f"(https://github.com/bioimage-io/configuration/blob/master/supported_formats_and_operations.md#weight_format). "
            f"One of: {', '.join(get_args(raw_nodes.WeightsFormat))}",
        ),
        fields.Union([fields.Nested(we) for we in get_args(WeightsEntry)]),
        required=True,
        bioimageio_description="The weights for this model. Weights can be given for different formats, but should "
        "otherwise be equivalent. The available weight formats determine which consumers can use this model.",
    )

    @pre_load
    def add_weights_format_key_to_weights_entry_value(self, data: dict, many=False, partial=False, **kwargs):
        data = deepcopy(data)  # Schema.validate() calls pre_load methods, thus we should not modify the input data
        if many or partial:
            raise NotImplementedError

        for weights_format, weights_entry in data.get("weights", {}).items():
            if "weights_format" in weights_entry:
                raise ValidationError(f"Got unexpected key 'weights_format' in weights entry {weights_format}")

            weights_entry["weights_format"] = weights_format

        return data

    inputs = fields.Nested(
        InputTensor, many=True, bioimageio_description="Describes the input tensors expected by this model."
    )

    @validates("inputs")
    def no_duplicate_input_tensor_names(self, value: typing.List[InputTensor]):
        names = [t.name for t in value]
        if len(names) > len(set(names)):
            raise ValidationError("Duplicate input tensor names are not allowed.")

    outputs = fields.Nested(
        OutputTensor, many=True, bioimageio_description="Describes the output tensors from this model."
    )

    @validates("outputs")
    def no_duplicate_output_tensor_names(self, value: typing.List[InputTensor]):
        names = [t.name for t in value]
        if len(names) > len(set(names)):
            raise ValidationError("Duplicate output tensor names are not allowed.")

    @validates_schema
    def no_duplicate_tensor_names(self, data, **kwargs):
        names = [t.name for t in data["inputs"] + data["outputs"]]
        if len(names) > len(set(names)):
            raise ValidationError("Duplicate tensor names are not allowed.")

    test_inputs = fields.List(
        fields.URI,
        required=True,
        bioimageio_description="List of URIs to test inputs as described in inputs for a single test case. "
        "Supported file formats/extensions: '.npy'",
    )
    test_outputs = fields.List(fields.URI, required=True, bioimageio_description="Analog to to test_inputs.")

    sample_inputs = fields.List(
        fields.URI,
        bioimageio_description="List of URIs to sample inputs to illustrate possible inputs for the model, for example "
        "stored as png or tif images.",
    )
    sample_outputs = fields.List(
        fields.URI, bioimageio_description="List of URIs to sample outputs corresponding to the `sample_inputs`."
    )

    config = fields.Dict(
        bioimageio_description=rdf.schema.RDF.config_bioimageio_description
        + """

For example:
```yaml
config:
  # custom config for DeepImageJ, see https://github.com/bioimage-io/configuration/issues/23
  deepimagej:
    model_keys:
      # In principle the tag "SERVING" is used in almost every tf model
      model_tag: tf.saved_model.tag_constants.SERVING
      # Signature definition to call the model. Again "SERVING" is the most general
      signature_definition: tf.saved_model.signature_constants.DEFAULT_SERVING_SIGNATURE_DEF_KEY
    test_information:
      input_size: [2048x2048] # Size of the input images
      output_size: [1264x1264 ]# Size of all the outputs
      device: cpu # Device used. In principle either cpu or GPU
      memory_peak: 257.7 Mb # Maximum memory consumed by the model in the device
      runtime: 78.8s # Time it took to run the model
      pixel_size: [9.658E-4µmx9.658E-4µm] # Size of the pixels of the input
```
"""
    )

    @validates_schema
    def language_and_framework_match(self, data, **kwargs):
        field_names = ("language", "framework")
        valid_combinations = [
            ("python", "scikit-learn"),  # todo: remove
            ("python", "pytorch"),
            ("python", "tensorflow"),
            ("java", "tensorflow"),
        ]
        if "source" not in data:
            valid_combinations.append((missing_, missing_))
            valid_combinations.append(("python", missing_))
            valid_combinations.append(("java", missing_))

        combination = tuple(data.get(name, missing_) for name in field_names)
        if combination not in valid_combinations:
            raise ValidationError(f"invalid combination of {dict(zip(field_names, combination))}")

    @validates_schema
    def source_specified_if_required(self, data, **kwargs):
        if "source" in data:
            return

        weights_format_requires_source = {
            "pytorch_state_dict": True,
            "pytorch_script": False,
            "keras_hdf5": False,
            "tensorflow_js": False,
            "tensorflow_saved_model_bundle": False,
            "onnx": False,
        }
        require_source = {wf for wf in data["weights"] if weights_format_requires_source[wf]}
        if require_source:
            raise ValidationError(
                f"These specified weight formats require source code to be specified: {require_source}"
            )

    @validates_schema
    def validate_reference_tensor_names(self, data, **kwargs):
        valid_input_tensor_references = [ipt.name for ipt in data["inputs"]]
        for out in data["outputs"]:
            if out.postprocessing is missing_:
                continue

            for postpr in out.postprocessing:
                if postpr.kwargs is missing_:
                    continue

                ref_tensor = postpr.kwargs.get("reference_tensor", missing_)
                if ref_tensor is not missing_ and ref_tensor not in valid_input_tensor_references:
                    raise ValidationError(f"{ref_tensor} not found in inputs")

    @validates_schema
    def weights_entries_match_weights_formats(self, data, **kwargs):
        weights: typing.Dict[str, WeightsEntryBase] = data["weights"]
        for weights_format, weights_entry in weights.items():
            if weights_format in ["keras_hdf5", "tensorflow_js", "tensorflow_saved_model_bundle"]:
                assert isinstance(
                    weights_entry,
                    (
                        raw_nodes.KerasHdf5WeightsEntry,
                        raw_nodes.TensorflowJsWeightsEntry,
                        raw_nodes.TensorflowSavedModelBundleWeightsEntry,
                    ),
                )
                if weights_entry.tensorflow_version is missing_:
                    # todo: raise ValidationError (allow -> require)?
                    warnings.warn(f"missing 'tensorflow_version' entry for weights format {weights_format}")

            if weights_format == "onnx":
                assert isinstance(weights_entry, raw_nodes.OnnxWeightsEntry)
                if weights_entry.opset_version is missing_:
                    # todo: raise ValidationError?
                    warnings.warn(f"missing 'opset_version' entry for weights format {weights_format}")
