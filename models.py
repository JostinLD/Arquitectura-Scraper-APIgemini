"""Modelos Pydantic que validan y estructuran los datos extraídos."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

DataSource = Literal["network", "dom"]
PostType = Literal["Image", "Video", "Carousel"]


class Profile(BaseModel):
    username: str
    user_id: str | None = None
    full_name: str | None = None
    biography: str | None = None
    followers: int | None = Field(default=None, ge=0)
    following: int | None = Field(default=None, ge=0)
    posts_count: int | None = Field(default=None, ge=0)
    is_private: bool | None = None
    is_verified: bool | None = None
    external_url: str | None = None
    profile_pic_url: str | None = None
    source: DataSource = "network"


class Comment(BaseModel):
    username: str | None = None
    text: str


class Post(BaseModel):
    post_id: str
    shortcode: str
    url: str
    caption: str | None = None
    timestamp: datetime | None = None
    like_count: int | None = None
    comment_count: int | None = None
    image_url: str | None = None
    is_video: bool = False
    post_type: PostType = "Image"
    media_count: int | None = Field(default=None, ge=0)  # solo en carruseles
    hashtags: list[str] = Field(default_factory=list)
    top_comments: list[Comment] = Field(default_factory=list)
    source: DataSource = "network"


class SeguidorMuestra(BaseModel):
    """Una cuenta de la lista de seguidores y su número de seguidores (leído con hover)."""
    usuario: str
    seguidores: int = Field(ge=0)


class ScrapeResult(BaseModel):
    profile: Profile
    posts: list[Post]
    total_posts: int
    # Muestra de seguidores para la ley de Benford (vacía si no se extrajo).
    muestra_seguidores: list[SeguidorMuestra] = Field(default_factory=list)
    cuentas_saltadas: int = 0  # cuentas cuya tarjeta emergente no cargó
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
