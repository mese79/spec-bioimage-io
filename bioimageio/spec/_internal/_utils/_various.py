from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import pydantic

from bioimageio.spec._internal._constants import IN_PACKAGE_MESSAGE


# slimmed down version of pydantic.Field with explicit extras
def Field(  # noqa C901  NOSONAR: S1542
    default: Any = ...,
    *,
    default_factory: Optional[Callable[[], Any]] = None,
    alias: Optional[str] = None,
    validation_alias: Union[str, pydantic.AliasPath, pydantic.AliasChoices, None] = None,
    description: str = "",
    examples: Optional[List[Any]] = None,
    exclude: Optional[bool] = None,
    discriminator: Optional[str] = None,
    kw_only: Optional[bool] = None,
    pattern: Optional[str] = None,
    strict: Optional[bool] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    multiple_of: Optional[float] = None,
    allow_inf_nan: Optional[bool] = None,
    max_digits: Optional[int] = None,
    decimal_places: Optional[int] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    in_package: bool = False,  # bioimageio specific
) -> Any:
    """wrap pydantic.Field"""
    return pydantic.Field(
        default,
        default_factory=default_factory,
        alias=alias,
        validation_alias=validation_alias,
        description=(IN_PACKAGE_MESSAGE if in_package else "") + description,
        examples=examples,
        exclude=exclude,
        discriminator=discriminator,
        kw_only=kw_only,
        pattern=pattern,
        strict=strict,
        gt=gt,
        ge=ge,
        lt=lt,
        le=le,
        multiple_of=multiple_of,
        allow_inf_nan=allow_inf_nan,
        max_digits=max_digits,
        decimal_places=decimal_places,
        min_length=min_length,
        max_length=max_length,
    )


def ensure_raw(value: Union[pydantic.BaseModel, Any]) -> Union[Dict[str, Any], Any]:
    if isinstance(value, pydantic.BaseModel):
        return value.model_dump(exclude_unset=True, exclude_defaults=False, exclude_none=False)
    else:
        return value


def nest_locs(locs: Sequence[Tuple[Tuple[Union[int, str], ...], str]]) -> Dict[str, Any]:
    return {}
