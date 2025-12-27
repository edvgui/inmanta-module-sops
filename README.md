# sops Module

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

5. Reference the sops file in the model.

TODO


## Running tests

1. Set up a new virtual environment, then install the module in it. The first line assumes you have ``virtualenvwrapper``
installed. If you don't, you can replace it with `python3 -m venv .env && source .env/bin/activate`.

```bash
mkvirtualenv inmanta-test -p python3 -a .
pip install -e . -c requirements.txt -r requirements.dev.txt
```

2. Run tests

```bash
pytest tests
```
