__all__ = ["Emby"]

from mediux_posters.services.jellyfin import Jellyfin
from mediux_posters.services.service_cache import ServiceCache


class Emby(Jellyfin):
    """Emby is Jellyfin's ancestor: same item/image API, different prefix and auth header."""

    def __init__(self, base_url: str, token: str, cache: ServiceCache):
        super().__init__(base_url=base_url.rstrip("/") + "/emby", token=token, cache=cache)
        del self.client.headers["Authorization"]
        self.client.headers["X-Emby-Token"] = token
