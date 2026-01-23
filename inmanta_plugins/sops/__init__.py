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

import contextlib
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import typing
from dataclasses import dataclass

import pydantic
import requests
from inmanta_plugins.config import resolve_path

from inmanta.agent.handler import LoggerABC
from inmanta.plugins import plugin
from inmanta.references import Reference, reference
from inmanta.util import dict_path
from inmanta_plugins.sops import editor


@dataclass(frozen=True, kw_only=True)
class SopsBinary:
    path: str
    args: list[str]
    version: str


def find_sops_in_path(binary_name: str = "sops") -> SopsBinary:
    """
    Try to find sops in the current file system, which exploring the PATH
    environment variable.

    :param binary_name: The name for the binary containing the sops tool.
    """
    PATH = os.environ["PATH"].split(":")

    for folder in PATH:
        if (path := pathlib.Path(folder) / binary_name).exists():
            try:
                # Found a sops binary, execute it to resolve the version
                version_output = subprocess.check_output([str(path), "-v"], text=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Invalid binary {path}, it doesn't recognize flag -v"
                ) from e

            # Try to parse the output version
            matched = re.match(r"^sops (\d+\.\d+\.\d+)[^\d]", version_output)
            if not matched:
                raise RuntimeError(
                    f"Unexpected version format output for binary {path}: {version_output}"
                )

            return SopsBinary(
                path=str(path),
                args=[],
                version=matched.group(1),
            )

    raise LookupError(f"Failed to find any binary named {binary_name} in PATH {PATH}")


def install_sops_from_github(
    path: pathlib.Path,
    version: str = "3.11.0",
) -> SopsBinary:
    """
    Install a binary at the given path.  No file must exist at the path location.
    The binary is downloaded from github.

    :param path: The path at which the sops binary should be created.
    :param version: The version to download from github.
    """
    if path.exists():
        raise RuntimeError(f"A file already exist at path {path}")

    # Make sure the parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Figure out the architecture of the current platform
    architecture = {
        "x86_64": "amd64",
        "aarch64": "arm64",
    }[platform.machine()]

    # Define the desired sops path
    sops = SopsBinary(
        path=str(path),
        args=[],
        version=version,
    )

    # Download the sops binary and place it in the temporary folder
    with requests.get(
        (
            "https://github.com/getsops/sops/releases/download/"
            f"v{sops.version}/sops-v{sops.version}.linux.{architecture}"
        ),
        stream=True,
    ) as r:
        r.raise_for_status()
        with open(sops.path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Make sure that the sops binary is executable
    pathlib.Path(sops.path).chmod(755)

    return sops


def escape_path(raw_path: str) -> str:
    """
    Escape a path string to make it compliant with the SOPS_EDITOR env var.
    We escape any character that would split the path into multiple pieces.
    """
    return (
        raw_path.replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace('"', '\\"')
        .replace("'", "\\'")
    )


@contextlib.contextmanager
def edit_encrypted_file(
    sops_binary: SopsBinary,
    encrypted_file_path: pathlib.Path,
) -> typing.Generator[dict, None, None]:
    """
    Open the encrypted file using sops in a subprocess, yield its content, then
    write the returned dict back into the file.  This function is meant to be
    used with a context manager, to make sure the modified vault is always saved
    back into the encrypted file.

    We rely on a custom executable that we use as "editor", this executable first
    prints the content of the file on stdout, then replace the content of the file
    with what it reads on stdin.

    :param sops_binary: Information about the binary to use to edit the file
    :param encrypted_file_path: The path to the encrypted file we want to edit
    """
    python_path = escape_path(sys.executable)
    editor_path = escape_path(editor.__file__)
    process = subprocess.Popen(
        args=[
            sops_binary.path,
            "edit",
            *sops_binary.args,
            "--output-type",
            "json",
            encrypted_file_path,
        ],
        env={
            **os.environ,
            "SOPS_EDITOR": f"{python_path} {editor_path}",
        },
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def terminate() -> None:
        """
        Terminate the process, first try to let it finish on its own.  If
        it doesn't, send a SIGKILL and wait one more second.  If it still
        doesn't, raise a subprocess.TimeoutExpired exception.
        If the process finished with a non-zero exit code, we raise a
        subprocess.CalledProcessError.
        """
        try:
            return_code = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait(timeout=1.0)

        stderr = process.stderr.read()
        if return_code != 0:
            raise subprocess.CalledProcessError(
                return_code,
                process.args,
                stderr=stderr,
            )

    # Read the decrypted content of the file until EOF
    lines = []
    while (line := process.stdout.readline()) != "EOF\n":
        lines.append(line)

    stdout = "".join(lines)
    if not stdout:
        terminate()

    vault = json.loads(stdout)
    try:
        yield vault
    finally:
        # Write the vault object back
        process.stdin.write(json.dumps(vault))
        process.stdin.close()
        terminate()


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
        encrypted_file_type: str | Reference[str],
    ):
        super().__init__()
        self.binary = binary
        self.encrypted_file = encrypted_file
        self.encrypted_file_type = encrypted_file_type

    def resolve(self, logger: LoggerABC) -> dict:
        binary = self.resolve_other(self.binary, logger)
        encrypted_file = self.resolve_other(self.encrypted_file, logger)
        encrypted_file_type = self.resolve_other(self.encrypted_file_type, logger)

        # Run existing binary to decrypt the file
        output = subprocess.check_output(
            [
                binary.path,
                "decrypt",
                *binary.args,
                "--input-type",
                encrypted_file_type,
                "--output-type",
                "json",
            ],
            input=encrypted_file,
            text=True,
        )

        # Output should always be a dict
        # https://github.com/getsops/sops?tab=readme-ov-file#36top-level-arrays
        return pydantic.TypeAdapter(dict).validate_python(json.loads(output))


@plugin
def create_decrypted_file_reference(
    sops_binary: SopsBinary | Reference[SopsBinary],
    encrypted_file: str | Reference[str],
    encrypted_file_type: str | Reference[str],
) -> DecryptedFileReference:
    return DecryptedFileReference(sops_binary, encrypted_file, encrypted_file_type)


@reference("sops::DecryptedValueReference")
class DecryptedValueReference(Reference[str]):
    def __init__(
        self,
        decrypted_file: dict | Reference[dict],
        value_path: str | Reference[str],
    ):
        super().__init__()
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
) -> DecryptedValueReference:
    return DecryptedValueReference(decrypted_file, value_path)


@plugin
def create_decrypted_value_reference_with_default(
    sops_binary: SopsBinary,
    encrypted_file_path: str,
    value_path: str,
    *,
    default: str | None = None,
) -> DecryptedValueReference:
    """
    This plugin returns a reference to a encrypted value.  The difference
    with the create_decrypted_value_reference is that this plugin can also
    validate during compile that the encrypted_value exists, and insert a
    default value in the encrypted file if no value has been defined yet.

    :param sops_binary: The sops binary that can be used to decrypt the file.
    :param encrypted_file_path: The path to the encrypted file in which we
        expect to find our secret value.
    :param value_path: The dict path expression pointing to the value within
        the file.
    :param default: A default value that can be added to the file if no value
        exists.  The file will then be updated with that value.
    """
    path = dict_path.to_path(value_path)
    file_path = pathlib.Path(resolve_path(encrypted_file_path))

    with edit_encrypted_file(sops_binary, file_path) as decrypted_file:
        try:
            path.get_element(decrypted_file)
        except LookupError:
            if default is not None:
                path.set_element(decrypted_file, default)
            else:
                raise RuntimeError(
                    f"No value at path {value_path} in encrypted_file {encrypted_file_path}"
                )

    return DecryptedValueReference(
        decrypted_file=DecryptedFileReference(
            sops_binary,
            file_path.read_text(),
            file_path.name.split(".")[-1],
        ),
        value_path=value_path,
    )
