"""Backend registry — loads profiles from a directory of YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from compass.eval.backends.profile import BackendProfile

if TYPE_CHECKING:
    from compass.eval.protocols import Backend


class BackendRegistry:
    def __init__(self, profiles: dict[str, BackendProfile] | None = None) -> None:
        self._profiles: dict[str, BackendProfile] = profiles or {}

    @classmethod
    def from_directory(cls, path: Path) -> BackendRegistry:
        profiles: dict[str, BackendProfile] = {}
        for file in sorted(path.glob("*.yaml")):
            profiles[file.stem] = BackendProfile.from_yaml(file)
        for file in sorted(path.glob("*.yml")):
            if file.stem not in profiles:
                profiles[file.stem] = BackendProfile.from_yaml(file)
        return cls(profiles)

    def get_profile(self, label: str) -> BackendProfile:
        if label not in self._profiles:
            raise KeyError(f"Unknown backend profile: '{label}'. Available: {list(self._profiles.keys())}")
        return self._profiles[label]

    def create_backend(self, label: str) -> Backend:
        profile = self.get_profile(label)
        if profile.provider == "mock_echo":
            from compass.eval.backends.mock_echo import MockEchoBackend

            return MockEchoBackend(profile)
        elif profile.provider == "openai":
            from compass.eval.backends.openai_backend import OpenAIBackend

            return OpenAIBackend(profile)
        elif profile.provider == "bedrock":
            from compass.eval.backends.bedrock_backend import BedrockBackend

            return BedrockBackend(profile)
        else:
            from compass.eval.backends.anthropic_backend import AnthropicBackend

            return AnthropicBackend(profile)

    def list_profiles(self) -> list[str]:
        return list(self._profiles.keys())
