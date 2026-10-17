"""Switch-provider request model."""

from pydantic import BaseModel, ConfigDict, Field


class LlmProviderChoice(BaseModel):
    """The provider to write into config.yaml as llm.provider."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider: str = Field(min_length=1)
