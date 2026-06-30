# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Backend registry and client abstraction."""

from compass.eval.backends.anthropic_backend import AnthropicBackend
from compass.eval.backends.bedrock_backend import BedrockBackend
from compass.eval.backends.openai_backend import OpenAIBackend
from compass.eval.backends.profile import BackendProfile
from compass.eval.backends.registry import BackendRegistry

__all__ = [
    "AnthropicBackend",
    "BedrockBackend",
    "BackendProfile",
    "BackendRegistry",
    "OpenAIBackend",
]
