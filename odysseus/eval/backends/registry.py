"""Backend registry — loads profiles from a directory of YAML files."""

from __future__ import annotations

from pathlib import Path

from odysseus.eval.backends.litellm_backend import LiteLLMBackend
from odysseus.eval.backends.profile import BackendProfile


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

    def create_backend(self, label: str) -> LiteLLMBackend:
        profile = self.get_profile(label)
        if profile.type == "mock_echo":
            from odysseus.eval.backends.mock_echo import MockEchoBackend

            return MockEchoBackend(profile)  # type: ignore[return-value]
        return LiteLLMBackend(profile)

    def list_profiles(self) -> list[str]:
        return list(self._profiles.keys())
