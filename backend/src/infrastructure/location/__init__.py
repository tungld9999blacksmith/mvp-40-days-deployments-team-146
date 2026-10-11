"""Place data providers for the location module (Amazon Location / GrabMaps, offline fake)."""

from .aws_places import AwsGrabPlacesProvider
from .fake import FakePlacesProvider

__all__ = ["AwsGrabPlacesProvider", "FakePlacesProvider"]
