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
import pathlib

from inmanta.agent.handler import PythonLogger
from inmanta_plugins.sops import (
    SopsBinary,
    create_decrypted_file_reference,
    create_decrypted_value_reference,
    create_value_in_vault,
    edit_encrypted_file,
)

LOGGER = logging.getLogger(__name__)


def test_resolve_references(sops_binary: SopsBinary, sops_vault: pathlib.Path) -> None:
    with edit_encrypted_file(sops_binary, sops_vault) as vault:
        vault.update(
            {
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
        )

    # Use the references to resolve the file
    password_a_ref = create_decrypted_value_reference(
        create_decrypted_file_reference(
            sops_binary,
            sops_vault.read_text(),
            sops_vault.name.split(".")[-1],
        ),
        "users[name=a].password",
    )
    token_ref = create_decrypted_value_reference(
        create_decrypted_file_reference(
            sops_binary,
            sops_vault.read_text(),
            sops_vault.name.split(".")[-1],
        ),
        "token",
    )
    assert password_a_ref.resolve(PythonLogger(LOGGER)) == "b"
    assert token_ref.resolve(PythonLogger(LOGGER)) == "aaaa"


def test_insert_default(sops_binary: SopsBinary, sops_vault: pathlib.Path) -> None:
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

    with edit_encrypted_file(sops_binary, sops_vault) as vault:
        vault.update(example)

    with edit_encrypted_file(
        sops_binary,
        encrypted_file_path=sops_vault,
    ) as vault:
        # Validate that we decrypted the vault correctly
        assert vault == example

        # Modify the vault
        vault["token"] = "token"

    encrypted = sops_vault.read_text()

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
        f"file://{sops_vault}",
        "token",
        default="a",
    )
    other_token_ref = create_value_in_vault(
        sops_binary,
        f"file://{sops_vault}",
        "other_token",
        default="a",
    )
    with edit_encrypted_file(
        sops_binary,
        encrypted_file_path=sops_vault,
    ) as vault:
        # The value already existed, the default shouldn't be inserted
        assert vault["token"] == "token"

        # The value didn't exist yet, the default should be inserted
        assert vault["other_token"] == "a"

    assert token_ref_2.resolve(PythonLogger(LOGGER)) == "token"
    assert other_token_ref.resolve(PythonLogger(LOGGER)) == "a"
