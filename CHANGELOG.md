# Changelog

## v0.2.2 - ?

- Rename sops binary instead of creating symlink: handle race-condition when multiple agents install the same binary at the same time.
- Edit vault file only once when using sops::create_value_in_vault multiple times in a compile.
- sops::create_value_in_vault will insert a null value in the vault where the missing values are when no default is provided.

## v0.2.1 - 2026-01-24

- Don't convert vault file to json when using sops::create_value_in_vault
- Add logs when running subprocesses and installing sops binary from github

## v0.2.0 - 2026-01-24

- Add sops::create_sops_binary_reference to easily install sops and use it in related references

## v0.1.0 - 2026-01-23

- Add sops::create_value_in_vault to ensure a value exists in an encrypted sops file, and get a reference to it
- Add sops::create_decrypted_value_reference to reference a value in a decrypted sops file
- Add sops::create_decrypted_file_reference to decrypt a sops file with a reference

## v0.0.1 - 2025-12-27

- First empty release
