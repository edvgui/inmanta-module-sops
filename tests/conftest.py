"""
Copyright 2025 Guillaume Everarts de Velp

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Contact: edvgui@gmail.com
"""

import logging

import pytest

from inmanta.agent.handler import PythonLogger
from inmanta_plugins.sops import SopsBinary, create_sops_binary_reference

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def sops_binary(tmp_path_factory: pytest.TempPathFactory) -> SopsBinary:
    """
    This fixture makes sure there is a version of sops available on the system.
    If no binary can be found in the path, it downloads a version from github.
    """
    try:
        return create_sops_binary_reference().get(PythonLogger(LOGGER))
    except RuntimeError:
        return create_sops_binary_reference(
            install_to_path=str(tmp_path_factory.mktemp("sops") / "sops")
        ).get(PythonLogger(LOGGER))
