__all__ = ["Collection", "Episode", "Library", "Movie", "Season", "Show"]

from typing import Literal

from pydantic import AliasPath, Field
from pydantic.alias_generators import to_pascal

from mediux_posters.services._base import (
    BaseCollection,
    BaseEpisode,
    BaseMovie,
    BaseSeason,
    BaseShow,
)
from mediux_posters.utils import BaseModel


class EmbyModel(BaseModel, alias_generator=to_pascal, extra="ignore"): ...


class Library(EmbyModel):
    id: str
    title: str = Field(alias="Name")
    type: Literal["movies", "tvshows", "unknown"] = Field(alias="CollectionType")


class Episode(BaseEpisode, EmbyModel):
    number: int = Field(alias="IndexNumber")


class Season(BaseSeason, EmbyModel):
    number: int = Field(alias="IndexNumber", default=1)


class Show(BaseShow, EmbyModel):
    tmdb_id: int = Field(validation_alias=AliasPath("ProviderIds", "Tmdb"))
    year: int | None = Field(alias="ProductionYear", default=None)


class Movie(BaseMovie, EmbyModel):
    tmdb_id: int = Field(validation_alias=AliasPath("ProviderIds", "Tmdb"))
    year: int = Field(alias="ProductionYear")


class Collection(BaseCollection, EmbyModel):
    pass
