# Version workflow

- Keep each application version in a separate `V<version>` folder.
- `V0.1` is archived. Do not change its files.
- `V0.2` is archived. Do not change its files.
- `V0.3` is archived. Do not change its files.
- Current working version is `V0.3.4`.
- When the user requests the next version, create a new version folder from the previous version's source and documentation. Preserve old folders, and put the new EXE and release ZIP inside the new folder.
- Do not copy `.git`, generated test data, user databases or image collections into release packages.
- Run commands from the version folder; builds use its `build.ps1` and `tools/package_release.py`.
