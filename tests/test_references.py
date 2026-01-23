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

from inmanta.agent.handler import PythonLogger
from inmanta_plugins.sops import (
    SopsBinary,
    create_decrypted_file_reference,
    create_decrypted_value_reference,
    create_value_in_vault,
    edit_encrypted_file,
)

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


def test_resolve_references(sops_binary: SopsBinary, tmp_path: pathlib.Path) -> None:
    example = {
        "users": [
            {
                "name": "a",
                "password": "b",
            },
            {
                "name": "b",
                "password": "c",
            },
        ],
        "token": "aaaa",
    }
    example_file = tmp_path / "file.json"
    example_file.write_text(json.dumps(example))

    fingerprints = ",".join(get_gpg_fingerprints())

    # Encrypt the secret file with sops
    encrypted = subprocess.check_output(
        [
            sops_binary.path,
            f"--pgp={fingerprints}",
            "-e",
            str(example_file),
        ],
        text=True,
    )
    encrypted_example = json.loads(encrypted)
    assert encrypted_example["token"].startswith("ENC")
    assert encrypted_example["users"][0]["name"].startswith("ENC")
    assert encrypted_example["users"][0]["password"].startswith("ENC")

    # Use the references to resolve the file
    password_a_ref = create_decrypted_value_reference(
        create_decrypted_file_reference(
            sops_binary,
            encrypted,
            "json",
        ),
        "users[name=a].password",
    )
    token_ref = create_decrypted_value_reference(
        create_decrypted_file_reference(
            sops_binary,
            encrypted,
            "json",
        ),
        "token",
    )
    assert password_a_ref.resolve(PythonLogger(LOGGER)) == "b"
    assert token_ref.resolve(PythonLogger(LOGGER)) == "aaaa"


def test_insert_default(sops_binary: SopsBinary, tmp_path: pathlib.Path) -> None:
    example = {
        "users": [
            {
                "name": "a",
                "password": "b",
            },
            {
                "name": "b",
                "password": "c",
            },
        ],
        "token": "aaaa",
    }
    example_file = tmp_path / "file.json"
    example_file.write_text(json.dumps(example))

    fingerprints = ",".join(get_gpg_fingerprints())

    # Encrypt the secret file with sops
    encrypted = subprocess.check_output(
        [
            sops_binary.path,
            f"--pgp={fingerprints}",
            "-e",
            str(example_file),
        ],
        text=True,
    )
    encrypted_example = json.loads(encrypted)
    assert encrypted_example["token"].startswith("ENC")
    assert encrypted_example["users"][0]["name"].startswith("ENC")
    assert encrypted_example["users"][0]["password"].startswith("ENC")

    encrypted_file = tmp_path / "file.enc.json"
    encrypted_file.write_text(encrypted)

    with edit_encrypted_file(
        sops_binary,
        encrypted_file_path=str(encrypted_file),
    ) as vault:
        # Validate that we decrypted the vault correctly
        assert vault == example

        # Modify the vault
        vault["token"] = "token"

    encrypted = encrypted_file.read_text()

    # Use the references to resolve the file
    password_a_ref = create_decrypted_value_reference(
        create_decrypted_file_reference(
            sops_binary,
            encrypted,
            "json",
        ),
        "users[name=a].password",
    )
    token_ref = create_decrypted_value_reference(
        create_decrypted_file_reference(
            sops_binary,
            encrypted,
            "json",
        ),
        "token",
    )
    assert password_a_ref.resolve(PythonLogger(LOGGER)) == "b"
    assert token_ref.resolve(PythonLogger(LOGGER)) == "token"

    token_ref_2 = create_value_in_vault(
        sops_binary,
        f"file://{encrypted_file}",
        "token",
        default="a",
    )
    other_token_ref = create_value_in_vault(
        sops_binary,
        f"file://{encrypted_file}",
        "other_token",
        default="a",
    )
    with edit_encrypted_file(
        sops_binary,
        encrypted_file_path=str(encrypted_file),
    ) as vault:
        # The value already existed, the default shouldn't be inserted
        assert vault["token"] == "token"

        # The value didn't exist yet, the default should be inserted
        assert vault["other_token"] == "a"

    assert token_ref_2.resolve(PythonLogger(LOGGER)) == "token"
    assert other_token_ref.resolve(PythonLogger(LOGGER)) == "a"
