"""
Copyright 2026 Guillaume Everarts de Velp

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

import asyncio
import grp
import os
import pathlib
import typing

from pytest_inmanta.plugin import Project

from inmanta.server.protocol import Server
from inmanta_plugins.sops import SopsBinary, edit_encrypted_file


def update_example(name: str, model: str) -> None:
    """
    Find the example with the given name in the readme, and make sure
    the model is the described one.
    """
    readme_file = pathlib.Path(__file__).parent.parent / "README.md"
    readme = readme_file.read_text()

    marker_start = f"<x-example-{name}>"
    start = readme.find(marker_start)
    if start == -1:
        raise RuntimeError(
            f"Can not find marker {marker_start} in readme {readme_file}"
        )

    marker_end = f"</x-example-{name}>"
    end = readme.find(marker_end, start)
    if end == -1:
        raise RuntimeError(f"Can not find marker {marker_end} in readme {readme_file}")

    current_model = readme[start : end + len(marker_end)]
    desired_model = marker_start + "\n\n```\n" + model + "\n```\n\n" + marker_end

    if current_model != desired_model:
        readme_file.write_text(
            readme[:start] + desired_model + readme[end + len(marker_end) :]
        )


async def off_main_thread[T](func: typing.Callable[[], T]) -> T:
    return await asyncio.get_event_loop().run_in_executor(None, func)


async def test_simple(
    project: Project,
    server: Server,
    sops_binary: SopsBinary,
    sops_vault: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
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

    user = os.getlogin()
    group = grp.getgrgid(os.getgid()).gr_name
    password_file = tmp_path / "a.secret"

    model = f"""
        import mitogen
        import files
        import files::host
        import sops

        import std

        host = std::Host(
            name="localhost",
            os=std::linux,
            via=mitogen::Local(),
        )

        files::TextFile(
            host=host,
            path={repr(str(password_file))},
            owner={repr(user)},
            group={repr(group)},
            purged=false,
            # The content of the file should be the password of user "a"
            content=sops::create_decrypted_value_reference(
                # The password is located in the decrypted vault file
                sops::create_decrypted_file_reference(
                    # The vault should be decrypted with sops, which is
                    # installed by this reference.
                    sops::create_sops_binary_reference(),
                    # The encrypted content of the file can be extracted
                    # using this reference
                    files::create_text_file_content_reference(
                        "file://{sops_vault}",
                    ),
                    {repr(sops_vault.name.split(".")[-1])},
                ),
                "users[name=a].password",
            ),
        )
    """

    def test() -> None:
        assert not password_file.exists()
        project.compile(model, no_dedent=False)
        assert project.dryrun_resource("files::TextFile")
        project.deploy_resource("files::TextFile")
        assert not project.dryrun_resource("files::TextFile")
        assert password_file.read_text() == "b"

    await off_main_thread(test)
    tested_model = pathlib.Path(project._test_project_dir, "main.cf").read_text()
    tested_model = tested_model.replace(str(tmp_path), "/example/folder")
    update_example("simple", tested_model)


async def test_generate(
    project: Project,
    server: Server,
    sops_binary: SopsBinary,
    sops_vault: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    with edit_encrypted_file(sops_binary, sops_vault) as vault:
        vault.update(
            {
                "token": "aaaa",
            }
        )

    user = os.getlogin()
    group = grp.getgrgid(os.getgid()).gr_name
    password_file = tmp_path / "a.secret"

    model = f"""
        import mitogen
        import files
        import files::host
        import sops

        import std

        host = std::Host(
            name="localhost",
            os=std::linux,
            via=mitogen::Local(),
        )

        files::TextFile(
            host=host,
            path={repr(str(password_file))},
            owner={repr(user)},
            group={repr(group)},
            purged=false,
            # The content of the file should be the password of user "a", if no password
            # for user a has been defined, create one with default value "b"
            content=sops::create_value_in_vault(
                # The vault should be decrypted with sops, which is
                # installed by this reference.
                sops::create_sops_binary_reference(),
                # The vault is available at this path
                "file://{sops_vault}",
                # This is the location of the password within the vault
                "users[name=a].password",
                default="b",
            ),
        )
    """

    def test() -> None:
        assert not password_file.exists()
        project.compile(model, no_dedent=False)
        assert project.dryrun_resource("files::TextFile")
        project.deploy_resource("files::TextFile")
        assert not project.dryrun_resource("files::TextFile")
        assert password_file.read_text() == "b"

    await off_main_thread(test)
    tested_model = pathlib.Path(project._test_project_dir, "main.cf").read_text()
    tested_model = tested_model.replace(str(tmp_path), "/example/folder")
    update_example("generate", tested_model)
