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

import json
import logging
import pathlib
import subprocess

import pytest

from inmanta.agent.handler import PythonLogger
from inmanta_plugins.sops import SopsBinary, create_sops_binary_reference

LOGGER = logging.getLogger(__name__)


def get_gpg_fingerprints() -> list[str]:
    """
    Resolve all the gpg fingerprints available to the user.
    """
    out = subprocess.check_output(
        ["gpg", "--list-keys", "--with-colons"],
        text=True,
    )

    # Find all the lines defining a fingerprint and return them as a list
    return [
        line.removeprefix("fpr").strip(":")
        for line in out.splitlines()
        if line.startswith("fpr:")
    ]


@pytest.fixture(scope="function")
def sops_vault(sops_binary: SopsBinary, tmp_path: pathlib.Path) -> pathlib.Path:
    """
    Create an empty vault that can be used in the tests.
    """
    example = {}
    example_file = tmp_path / "test.yml"
    example_file.write_text(json.dumps(example))

    # Figure out the gpg fingerprints available on the system, use
    # them all the encrypt the file, to make sure that whichever our
    # test can use is available.
    fingerprints = ",".join(get_gpg_fingerprints())

    # Encrypt the secret file with sops
    subprocess.check_call(
        [
            sops_binary.path,
            f"--pgp={fingerprints}",
            "-e",
            "-i",
            str(example_file),
        ],
    )

    return example_file


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
