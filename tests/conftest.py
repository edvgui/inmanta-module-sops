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

from inmanta_plugins.sops import SopsBinary, find_sops_in_path, install_sops_from_github

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def sops_binary(tmp_path_factory: pytest.TempPathFactory) -> SopsBinary:
    """
    This fixture makes sure there is a version of sops available on the system.
    If no binary can be found in the path, it downloads a version from github.
    """
    try:
        # Check if sops is already installed on the system
        sops = find_sops_in_path()
        LOGGER.info(
            "Using existing sops binary at path %s (version %s)",
            sops.path,
            sops.version,
        )
        return sops
    except LookupError:
        pass

    # Fallback to downloading sops from github
    sops = install_sops_from_github(
        tmp_path_factory.mktemp("sops") / "sops",
        version="3.11.0",
    )
    LOGGER.info(
        "Using downloaded sops binary available at path %s (version %s)",
        sops.path,
        sops.version,
    )
    return sops
