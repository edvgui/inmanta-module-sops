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

import os
import pathlib

import pytest
from pytest_inmanta.plugin import Project

from inmanta_plugins.sops import SopsBinary, find_sops_in_path


def test_basics(project: Project) -> None:
    project.compile("import sops")


def test_install(monkeypatch: pytest.MonkeyPatch, sops_binary: SopsBinary) -> None:
    """
    Make sure that the sops_binary that is currently used would be found
    by the find_sops_in_path helper.
    """
    binary_path = pathlib.Path(sops_binary.path)

    with monkeypatch.context() as ctx:
        ctx.setenv("PATH", str(binary_path.parent) + ":" + os.environ["PATH"])
        assert find_sops_in_path(binary_path.name) == sops_binary
