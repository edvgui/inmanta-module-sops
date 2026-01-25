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
import pathlib
import sys

import yaml


def parse_file(content: str, extension: str) -> dict:
    match extension:
        case "json":
            return json.loads(content)
        case "yml" | "yaml":
            return yaml.safe_load(content)
        case _:
            raise ValueError(
                f"Unsupported extension, can not parse file ending in {extension}"
            )


def serialize_file(content: dict, extension: str) -> str:
    match extension:
        case "json":
            return json.dumps(content, indent=2)
        case "yml" | "yaml":
            return yaml.safe_dump(content, indent=2)
        case _:
            raise ValueError(
                f"Unsupported extension, can not write to file ending in {extension}"
            )


if __name__ == "__main__":
    FILE = pathlib.Path(sys.argv[1])
    extension = FILE.name.split(".")[-1]
    original_content = FILE.read_text()
    parsed_input = parse_file(original_content, extension)
    print(json.dumps(parsed_input))
    print("EOF")
    sys.stdout.flush()
    parsed_output = json.loads(sys.stdin.read())
    if parsed_input == parsed_output:
        # No need to update the file, give back the old value
        # Make sure that a formatting difference doesn't create
        # empty updates
        FILE.write_text(original_content)
    else:
        FILE.write_text(serialize_file(parsed_output, extension))
