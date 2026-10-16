__all__ = ["Emby"]

import logging
import mimetypes
import platform
from base64 import b64encode
from http import HTTPStatus
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError
from requests import Session
from requests.exceptions import HTTPError, JSONDecodeError, RequestException, Timeout

from mediux_posters import __version__
from mediux_posters.console import CONSOLE
from mediux_posters.errors import AuthenticationError, ServiceError
from mediux_posters.mediux import FileType
from mediux_posters.services._base import BaseService
from mediux_posters.services.emby.schemas import (
    Collection,
    Episode,
    Library,
    Movie,
    Season,
    Show,
)
from mediux_posters.services.service_cache import ServiceCache

LOGGER = logging.getLogger(__name__)


class Emby(BaseService[str, Show, Season, Episode, Collection, Movie]):
    def __init__(self, base_url: str, token: str, cache: ServiceCache):
        super().__init__(cache=cache)
        self.base_url = base_url.rstrip("/") + "/emby"
        self.client = Session()
        self.client.headers.update(
            {
                "Accept": "application/json",
                "X-Emby-Token": token,
                "User-Agent": f"Mediux-Posters/{__version__} ({platform.system()}: {platform.release()}; Python v{platform.python_version()})",  # noqa: E501
            }
        )

    @classmethod
    def extract_id(
        cls, entry: dict[str, dict[str, str | None]], prefix: str = "Tmdb"
    ) -> str | None:
        return entry.get("ProviderIds", {}).get(prefix)

    def _perform_request(
        self,
        method: Literal["GET", "POST"],
        endpoint: str,
        params: dict[str, str | bool] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        url = self.base_url + endpoint

        try:
            response = self.client.request(
                method=method, url=url, params=params, data=body, headers=headers
            )
            response.raise_for_status()
            return response.json() if method == "GET" else {}
        except Timeout as err:
            raise ServiceError("Service took too long to respond") from err
        except HTTPError as err:
            status_code = (
                HTTPStatus.INTERNAL_SERVER_ERROR
                if err.response is None
                else err.response.status_code
            )
            # Emby errors are plain text, not Json problem details
            error_msg = "" if err.response is None else err.response.text.strip()[:200]
            if status_code in (401, 403):
                raise AuthenticationError(f"{status_code}: {error_msg}") from err
            raise ServiceError(f"{status_code}: {error_msg}") from err
        except RequestException as err:
            raise ServiceError(f"Unable to connect to '{url}'") from err
        except JSONDecodeError as err:
            raise ServiceError("Unable to parse response as Json") from err

    def _list_libraries(
        self,
        media_type: Literal["movies", "tvshows", "unknown"],
        skip_libraries: list[str] | None = None,
    ) -> list[Library]:
        skip_libraries = skip_libraries or []
        results = [
            x
            for x in self._perform_request("GET", "/Library/MediaFolders").get("Items", [])
            if x.get("CollectionType") == media_type
        ]
        results = [x for x in results if x.get("Name") not in skip_libraries]
        try:
            return TypeAdapter(list[Library]).validate_python(results)
        except ValidationError as err:
            raise ServiceError(err) from err

    def validate(self) -> bool:
        try:
            self._list_libraries(media_type="movies")
            return True
        except ServiceError as err:
            LOGGER.warning("[Emby] %s", err)
        return False

    def list_episodes(self, show_id: str, season_id: str) -> list[Episode]:
        try:
            results = self._perform_request(
                "GET",
                f"/Shows/{show_id}/Episodes",
                params={"SeasonId": season_id, "Fields": "ProviderIds"},
            ).get("Items", [])
            return TypeAdapter(list[Episode]).validate_python(results)
        except ValidationError as err:
            raise ServiceError(err) from err

    def list_seasons(self, show_id: str) -> list[Season]:
        try:
            results = self._perform_request(
                "GET", f"/Shows/{show_id}/Seasons", params={"Fields": "ProviderIds"}
            ).get("Items", [])
            return TypeAdapter(list[Season]).validate_python(results)
        except ValidationError as err:
            raise ServiceError(err) from err

    def _list_items(
        self,
        media_type: Literal["movies", "tvshows"],
        item_type: Literal["Movie", "Series"],
        model: type[Movie] | type[Show],
        skip_libraries: list[str] | None,
        tmdb_id: int | None,
        item_id: str | None,
    ) -> list:
        output = []
        for library in self._list_libraries(media_type=media_type, skip_libraries=skip_libraries):
            params: dict[str, str | bool] = {
                "HasTmdbId": True,
                "Fields": "ProviderIds",
                "ParentId": library.id,
                "Recursive": True,
                "IncludeItemTypes": item_type,
            }
            if item_id:
                params["Ids"] = item_id
            results = self._perform_request("GET", "/Items", params=params).get("Items", [])
            for result in results:
                tmdb = self.extract_id(entry=result)
                if not tmdb or (tmdb_id is not None and int(tmdb) != tmdb_id):
                    continue
                try:
                    output.append(TypeAdapter(model).validate_python(result))
                except ValidationError as err:
                    raise ServiceError(err) from err
        return output

    def _list_shows(
        self,
        skip_libraries: list[str] | None = None,
        tmdb_id: int | None = None,
        series_id: str | None = None,
    ) -> list[Show]:
        return self._list_items("tvshows", "Series", Show, skip_libraries, tmdb_id, series_id)

    def list_shows(self, skip_libraries: list[str] | None = None) -> list[Show]:
        return self._list_shows(skip_libraries=skip_libraries)

    def get_show(self, tmdb_id: int) -> Show | None:
        return next(iter(self._list_shows(tmdb_id=tmdb_id)), None)

    def list_collections(self, skip_libraries: list[str] | None = None) -> list[Collection]:  # noqa: ARG002
        return []

    def get_collection(self, tmdb_id: int) -> Collection | None:  # noqa: ARG002
        return None

    def list_collection_movies(self, collection_id: int | str) -> list[Movie]:  # noqa: ARG002
        return []

    def _list_movies(
        self,
        skip_libraries: list[str] | None = None,
        tmdb_id: int | None = None,
        movie_id: str | None = None,
    ) -> list[Movie]:
        return self._list_items("movies", "Movie", Movie, skip_libraries, tmdb_id, movie_id)

    def list_movies(self, skip_libraries: list[str] | None = None) -> list[Movie]:
        return self._list_movies(skip_libraries=skip_libraries)

    def get_movie(self, tmdb_id: int) -> Movie | None:
        return next(iter(self._list_movies(tmdb_id=tmdb_id)), None)

    def upload_image(
        self,
        object_id: int | str,
        image_file: Path,
        file_type: FileType,
        kometa_integration: bool,  # noqa: ARG002
    ) -> bool:
        element = {
            FileType.BACKDROP: "Backdrop",
            FileType.POSTER: "Primary",
            FileType.TITLE_CARD: "Primary",
            FileType.LOGO: "Logo",
        }.get(file_type)
        if not element:
            return False
        with CONSOLE.status(rf"\[Emby] Uploading {image_file.parent.name}/{image_file.name}"):
            mime_type, _ = mimetypes.guess_type(image_file)
            if not mime_type:
                mime_type = "image/jpeg"
            with image_file.open("rb") as stream:
                image_data = b64encode(stream.read())
            try:
                self._perform_request(
                    "POST",
                    f"/Items/{object_id}/Images/{element}",
                    headers={"Content-Type": mime_type},
                    body=image_data,
                )
                return True
            except ServiceError as err:
                LOGGER.error(
                    "[Emby] Failed to upload '%s/%s': %s",
                    image_file.parent.name,
                    image_file.name,
                    err,
                )
        return False
