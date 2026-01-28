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
import contextvars
import functools
import json
import logging
import os
import pathlib
import platform
import re
import socket
import subprocess
import sys
import typing
import uuid
from dataclasses import dataclass

import pydantic
import requests
from inmanta_plugins.config import resolve_path
from inmanta_plugins.files import create_text_file_content_reference

from inmanta.agent.handler import LoggerABC, PythonLogger
from inmanta.compiler import finalizer
from inmanta.plugins import plugin
from inmanta.references import Reference, reference
from inmanta.util import dict_path
from inmanta_plugins.sops import editor

LOGGER: contextvars.ContextVar[LoggerABC] = contextvars.ContextVar(
    "LOGGER",
    default=PythonLogger(logging.getLogger(__name__)),
)
CMD_LINE_PREFIX = f"inmanta@{socket.gethostname()}$"


def get_logger() -> LoggerABC:
    """
    Get the logger that is available in the current context.
    """
    return LOGGER.get()


@contextlib.contextmanager
def set_logger(logger: LoggerABC) -> typing.Iterator[None]:
    """
    Set the logger that should be used in this context.
    """
    token = LOGGER.set(logger)
    try:
        yield None
    finally:
        LOGGER.reset(token)


@dataclass(frozen=True, kw_only=True)
class SopsBinary:
    path: str
    version: str


def system_path() -> list[pathlib.Path]:
    """
    Return a list of paths representing the paths defined in the PATH env var.
    """
    return [pathlib.Path(p) for p in os.environ["PATH"].split(":")]


def find_sops_in_path(
    binary_name: str = "sops",
    *,
    path: list[pathlib.Path] | None = None,
    logger: LoggerABC | None = None,
) -> SopsBinary:
    """
    Try to find sops in the current file system, which exploring the PATH
    environment variable.

    :param binary_name: The name for the binary containing the sops tool.
    :param path: A custom list of folder to explore instead of the system's PATH env var.
    """
    if logger is None:
        logger = get_logger()

    if path is None:
        path = system_path()

    for folder in path:
        if (binary := folder / binary_name).exists():
            try:
                # Found a sops binary, execute it to resolve the version
                args = [str(binary), "-v"]
                version_output = subprocess.check_output(
                    args,
                    text=True,
                    stderr=subprocess.PIPE,
                    env=os.environ,
                )
            except subprocess.CalledProcessError as e:
                # Log the output of the command, for debug purposes
                logger.debug(
                    "%(prefix)s %(cmd)s",
                    prefix=CMD_LINE_PREFIX,
                    cmd=" ".join(e.cmd),
                    stderr=e.stderr,
                    returncode=e.returncode,
                )
                raise RuntimeError(
                    f"Invalid binary {binary}, it doesn't recognize flag -v"
                ) from e
            except PermissionError as e:
                # The file can not be executed, log the error and try to find it
                # elsewhere
                logger.debug(str(e))
                raise RuntimeError(
                    f"Invalid binary {binary}, it is not executable"
                ) from e

            # Log the output of the command, for debug purposes
            logger.debug(
                "%(prefix)s %(cmd)s",
                prefix=CMD_LINE_PREFIX,
                cmd=" ".join(args),
                stdout=version_output,
                returncode=0,
            )

            # Try to parse the output version
            matched = re.match(r"^sops (\d+\.\d+\.\d+)[^\d]", version_output)
            if not matched:
                raise RuntimeError(
                    f"Unexpected version format output for binary {binary}: {version_output}"
                )

            return SopsBinary(
                path=str(binary),
                version=matched.group(1),
            )

    raise LookupError(f"Failed to find any binary named {binary_name} in PATH {path}")


def install_sops_from_github(
    path: pathlib.Path,
    version: str = "3.11.0",
    *,
    logger: LoggerABC | None = None,
) -> SopsBinary:
    """
    Install a binary at the given path.  No file must exist at the path location.
    The binary is downloaded from github.

    :param path: The path at which the sops binary should be created.
    :param version: The version to download from github.
    """
    if logger is None:
        logger = get_logger()

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
        version=version,
    )

    # Download the file in a temporary file, then move it where the sops binary
    # should go.  We do this in case multiple handlers try to place the binary
    # at the same place, at the same time
    temp_binary = path.with_name(f"sops-{uuid.uuid4()}")

    # Open the file first, to make sure we have permission to write to it
    with open(str(temp_binary), "wb") as f:
        # Download the sops binary and place it in the file
        with requests.get(
            (
                "https://github.com/getsops/sops/releases/download/"
                f"v{sops.version}/sops-v{sops.version}.linux.{architecture}"
            ),
            stream=True,
        ) as r:
            logger.debug(
                "%(request_method)s %(request_url)s: %(response_status)d (%(response_reason)s)",
                request_method=r.request.method,
                request_url=r.request.url,
                response_status=r.status_code,
                response_reason=r.reason,
            )
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Make sure that the sops binary is executable
    temp_binary.chmod(0o755)

    # Move the binary where the sops file is expected
    temp_binary.replace(sops.path)

    return sops


@functools.lru_cache
def get_sops(
    install_to_path: str | None = None,
    install_from_github: bool = True,
) -> SopsBinary:
    """
    Get a sops binary that can be used in the current context. Install if
    from github if it can't be found and install_from_github is True.

    :param install_to_path: A path to which the binary should be found, or
        installed if it is not there yet.  When unset, try to find the binary
        in any path defined in the PATH env var.
    :param install_from_github: When set to true, and the binary can not be
        found, install it from github.
    """
    if install_to_path is not None:
        # Try to find the binary at the given path
        binary_path = pathlib.Path(install_to_path)
        try:
            return find_sops_in_path(
                binary_path.name,
                path=[binary_path.parent],
            )
        except LookupError:
            if install_from_github:
                # Fallback to github install
                return install_sops_from_github(
                    binary_path,
                )
            else:
                # Nothing we can do, raise initial error
                raise

    else:
        try:
            # Try to find any binary named sops in the system path
            return find_sops_in_path()
        except LookupError:
            if install_from_github:
                # We need to find an editable folder in the path
                # and install the binary from github there
                for folder in system_path():
                    try:
                        return install_sops_from_github(
                            folder / "sops",
                        )
                    except PermissionError:
                        pass
                else:
                    raise RuntimeError(
                        "Failed to install sops. "
                        f"None of the folder provided in the system path are writable: {system_path()}"
                    )
            else:
                # Nothing we can do, raise initial error
                raise


@reference("sops::SopsBinaryReference")
class SopsBinaryReference(Reference[SopsBinary]):
    """
    Create a reference that makes sure the sops binary is installed on the
    system that needs to resolve the reference.
    """

    def __init__(
        self,
        install_to_path: str | None = None,
        install_from_github: bool = True,
    ):
        super().__init__()
        self.install_to_path = install_to_path
        self.install_from_github = install_from_github

    def resolve(self, logger: LoggerABC) -> SopsBinary:
        with set_logger(logger):
            return get_sops(
                self.install_to_path,
                self.install_from_github,
            )


@functools.lru_cache
def _create_sops_binary_reference(
    install_to_path: str | None = None,
    install_from_github: bool = True,
) -> SopsBinaryReference:
    return SopsBinaryReference(
        install_to_path=install_to_path,
        install_from_github=install_from_github,
    )


@plugin
def create_sops_binary_reference(
    install_to_path: str | None = None,
    install_from_github: bool = True,
) -> SopsBinaryReference:
    """
    Create a reference to a working sops binary in the given file system.

    :param install_to_path: When a path is provided, we will look for the
        sops binary at the given path.  The path should include the binary
        name.  If the sops binary can not be found, and install_from_github
        is False, a LookupError will be raised.
        If no path is provided, teh reference will try to find a binary named
        "sops" anywhere in the folder defined in the user's PATH env var. If
        the sops binary can not be found, and install_from_github is True, we
        will try to install the binary in the first writable path.  Otherwise
        a LookupError will be raised.
    :param install_from_github: Whether the binary should be installed from
        github when it can not be found locally.
    """
    return _create_sops_binary_reference(
        install_to_path=install_to_path,
        install_from_github=install_from_github,
    )


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
    *,
    logger: LoggerABC | None = None,
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
    if logger is None:
        logger = PythonLogger(LOGGER)

    python_path = escape_path(sys.executable)
    editor_path = escape_path(editor.__file__)
    process = subprocess.Popen(
        args=[
            sops_binary.path,
            "edit",
            str(encrypted_file_path),
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

    assert process.stdin is not None
    assert process.stdout is not None

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

        assert process.stderr is not None
        stderr = process.stderr.read()
        # Exit code 0: File was successfully changed
        # Exit code 200: File didn't need to be changed
        if return_code not in [0, 200]:
            logger.error(
                "%(prefix)s %(cmd)s",
                prefix=CMD_LINE_PREFIX,
                cmd=" ".join(process.args),
                stderr=stderr,
                returncode=return_code,
            )
            raise subprocess.CalledProcessError(
                return_code,
                process.args,
                stderr=stderr,
            )
        else:
            logger.debug(
                "%(prefix)s %(cmd)s",
                prefix=CMD_LINE_PREFIX,
                cmd=" ".join(process.args),
                stderr=stderr,
                returncode=return_code,
            )

    # Read the decrypted content of the file until EOF
    lines = []
    while process.poll() is None and (line := process.stdout.readline()) != "EOF\n":
        lines.append(line)

    stdout = "".join(lines)
    if not stdout:
        terminate()

    try:
        vault = json.loads(stdout)
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
        try:
            output = subprocess.check_output(
                [
                    binary.path,
                    "decrypt",
                    "--filename-override",
                    f"file.{encrypted_file_type}",
                    "--output-type",
                    "json",
                ],
                input=encrypted_file,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ,
            )
        except subprocess.CalledProcessError as exc:
            logger.error(
                "%(prefix)s %(cmd)s",
                prefix=CMD_LINE_PREFIX,
                cmd=" ".join(exc.cmd),
                stderr=str(exc.stderr),
                returncode=exc.returncode,
            )
            raise

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


@functools.lru_cache
def share_edit_encrypted_file(
    sops_binary: SopsBinary,
    encrypted_file_path: pathlib.Path,
    *,
    logger: LoggerABC | None = None,
) -> dict:
    """
    More performant alternative to edit_encrypted_file.  This function opens the
    file, gets the vault and let it be modified by whomever calls the function.
    At the end of the compile, the vault is written back to file.  This function
    should only be used in compiles, where the finalizers are triggered.  Otherwise
    the file will remain open and unmodified and the cache won't be cleared.
    """

    def open_encrypted_file() -> typing.Iterator[dict]:
        # Convert the contextmanager into an iterator, so we can
        # split the code execution of the opening and the closing of the file
        with edit_encrypted_file(
            sops_binary, encrypted_file_path, logger=logger
        ) as vault:
            yield vault

    # Open the file and get the decrypted vault
    encrypted_file = open_encrypted_file()
    vault = next(encrypted_file)

    def close_encrypted_file() -> None:
        # Now we can close the file, this will raise a StopIteration as we reach
        # the end of the iterator (this is expected)
        with contextlib.suppress(StopIteration):
            next(encrypted_file)

    # Make sure the file is closed at the end of the compile
    finalizer(close_encrypted_file)

    return vault


@finalizer
def clear_caches() -> None:
    """
    Clear the sops binary installation and vault opening cache
    at the end of the compile.
    """
    _create_sops_binary_reference.cache_clear()
    share_edit_encrypted_file.cache_clear()


# This global variable will contain all the missing vault values
# collected during a compile.  At the end of the compile, we raise
# an exception mentioning all of these, to let the user know he
# should fill in these values in the vault.
MISSING_VAULT_VALUES: dict[str, set[str]] = dict()


@finalizer
def validate_vault_completeness() -> None:
    """
    Raise an exception if any of the values expected to be found
    in a vault were missing and didn't have a default to put in
    place.
    """

    def msg(vault: str, values: set[str]) -> str:
        return (
            f"Vault {vault} is incomplete, it is missing the following values: "
            + "\n- "
            + "\n- ".join(sorted(values))
        )

    try:
        if len(MISSING_VAULT_VALUES) == 1:
            # Once vault, simpler exception
            raise RuntimeError(msg(*MISSING_VAULT_VALUES.popitem()))
        elif len(MISSING_VAULT_VALUES) > 1:
            # Multiple vaults, group exceptions
            raise ExceptionGroup(
                "Multiple vaults are incomplete.",
                [
                    RuntimeError(msg(vault, values))
                    for vault, values in MISSING_VAULT_VALUES.items()
                ],
            )
        else:
            # All is well
            pass
    finally:
        MISSING_VAULT_VALUES.clear()


@plugin
def create_value_in_vault(
    sops_binary: SopsBinary | Reference[SopsBinary],
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
    # Resolve the binary, as we will need to use in this compile
    match sops_binary:
        case Reference():
            resolved_sops_binary = sops_binary.get(get_logger())
        case _:
            resolved_sops_binary = sops_binary

    path = dict_path.to_path(value_path)
    file_path = pathlib.Path(resolve_path(encrypted_file_path))

    # Try to find the value in the vault
    vault = share_edit_encrypted_file(resolved_sops_binary, file_path)
    try:
        value = path.get_element(vault)
    except LookupError:
        value = None

    if value is not None:
        # The value is there, all is good
        pass
    elif default is not None:
        # The value is missing, but we have a default to put in place
        # insert the default
        path.set_element(vault, default)
        value = default
    else:
        # The value is missing and we don't have a default to put in
        # place, put a "None" placeholder in the vault that the user
        # should fill in
        path.set_element(vault, None)

    if value is None:
        # Add the value to the list of missing values, don't fail now
        # but wait for the end of the compile so we can report multiple
        # missing values at once
        missing = MISSING_VAULT_VALUES.setdefault(encrypted_file_path, set())
        missing.add(value_path)

    return DecryptedValueReference(
        decrypted_file=DecryptedFileReference(
            sops_binary,
            create_text_file_content_reference(encrypted_file_path),
            file_path.name.split(".")[-1],
        ),
        value_path=value_path,
    )
