# Sops module

[![pypi version](https://img.shields.io/pypi/v/inmanta-module-sops.svg)](https://pypi.python.org/pypi/inmanta-module-sops/)
[![build status](https://img.shields.io/github/actions/workflow/status/edvgui/inmanta-module-sops/continuous-integration.yml)](https://github.com/edvgui/inmanta-module-sops/actions)

## How to use

1. Create gpg key on the orchestrator

```console
inmanta@96abdaa7233f:~$ gpg --full-generate-key
```

2. Generate key on the dev machine (same as step above)

3. Import orchestrator key in dev keyring

```console
# On the orchestrator
inmanta@96abdaa7233f:~$ gpg --armor --export email > orchestrator.gpg

# On the dev machine
guillaume@framework:~$ gpg --import orchestrator.gpg
```

4. Create keyring file with sops providing fingerprint of dev key and orchestrator key.  Edit it using sops binary.

```console
guillaume@framework:/tmp/sops-test$ echo "{}" > test.yml
guillaume@framework:/tmp/sops-test$ sops --pgp 49CAF9DCDAC1643FCBDFCAB93BF8D3BC3B08C360,6F405B4881FF1DE18A4696641BCDCFE5D361E275 -e test.yml > test.encrypted.yml
guillaume@framework:/tmp/sops-test$ sops edit test.encrypted.yml
```

5. Reference existing value in sops file in the model.

<x-example-simple>

```
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
    path='/example/folder/a.secret',
    owner='guillaume',
    group='guillaume',
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
                "file:///example/folder/test.yml",
            ),
            'yml',
        ),
        "users[name=a].password",
    ),
)

```

</x-example-simple>

6. (Alternatively) Reference value in sops file, create it if it doesn't exist.

<x-example-generate>

```
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
    path='/example/folder/a.secret',
    owner='guillaume',
    group='guillaume',
    purged=false,
    # The content of the file should be the password of user "a", if no password
    # for user a has been defined, create one with default value "b"
    content=sops::create_value_in_vault(
        # The vault should be decrypted with sops, which is
        # installed by this reference.
        sops::create_sops_binary_reference(),
        # The vault is available at this path
        "file:///example/folder/test.yml",
        # This is the location of the password within the vault
        "users[name=a].password",
        default="b",
    ),
)

```

</x-example-generate>


## Running tests

1. Set up a new virtual environment using uv and install the dependencies.

```bash
uv venv -p 3.12
make install
```

2. Run tests

```bash
uv run pytest tests
```
