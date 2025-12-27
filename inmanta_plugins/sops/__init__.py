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
import subprocess
from dataclasses import dataclass

import pydantic

from inmanta.agent.handler import LoggerABC
from inmanta.plugins import plugin
from inmanta.references import Reference, reference
from inmanta.util import dict_path


@dataclass(frozen=True, kw_only=True)
class SopsBinary:
    path: str
    args: list[str]
    version: str


@reference("sops::DecryptedFileReference")
class DecryptedFileReference(Reference[dict]):
    """
    Resolve the content of an encrypted sops file using the gpg key
    in the orchestrator file system.
    """

    def __init__(
        self,
        binary: SopsBinary | Reference[SopsBinary],
        encrypted_file: str | Reference[str],
    ):
        self.binary = binary
        self.encrypted_file = encrypted_file

    def resolve(self, logger: LoggerABC) -> dict:
        binary = self.resolve_other(self.binary, logger)
        encrypted_file = self.resolve_other(self.encrypted_file, logger)

        # Run existing binary to decrypt the file
        output = subprocess.check_output(
            [binary.path, "decrypt", *binary.args, "--output-type", "json"],
            input=encrypted_file,
            text=True,
        )

        # Output should always be a dict
        # https://github.com/getsops/sops?tab=readme-ov-file#36top-level-arrays
        return pydantic.TypeAdapter(dict).validate_python(json.loads(output))


@plugin
def create_decrypted_file_reference(
    binary: SopsBinary | Reference[SopsBinary],
    encrypted_file: str | Reference[str],
) -> DecryptedFileReference:
    return DecryptedFileReference(binary, encrypted_file)


@reference("sops::DecryptedValueReference")
class DecryptedValueReference(Reference[str]):
    def __init__(
        self,
        decrypted_file: dict | Reference[dict],
        value_path: str | Reference[str],
    ):
        self.decrypted_file = decrypted_file
        self.value_path = value_path

    def resolve(self, logger: LoggerABC) -> str:
        decrypted_file = self.resolve_other(self.decrypted_file, logger)
        value_path = dict_path.to_path(self.resolve_other(self.value_path, logger))
        return value_path.get_element(decrypted_file)


@plugin
def create_decrypted_value_reference(
    decrypted_file: dict | Reference[dict],
    value_path: str | Reference[str],
) -> str:
    return DecryptedValueReference(decrypted_file, value_path)
