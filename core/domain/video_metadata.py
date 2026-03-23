from pydantic import BaseModel, field_validator


class VideoMetadata(BaseModel, frozen=True):
    """Domain Value Object: describes where a video is and how to sample it."""

    path: str
    sample_interval: float = 1.0

    @field_validator("sample_interval")
    @classmethod
    def interval_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("sample_interval must be > 0")
        return v
