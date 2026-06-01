## How to contribute

### Code quality checks

This repo uses `go-task` Taskfiles for repeatable formatting/linting.

- **Repo-wide checks** (docs/scripts/YAML + shared Python typing):

```bash
# Checks linting and formatting
task pre-commit-check
```

### Adding a new service

When creating a new service, mirror the structure of existing folders under `services/`.

At minimum, a new service should typically include:

- `README.md` describing purpose, config, dev/test commands.
- A container build + runtime entrypoint:
  - `docker-compose.yml`
  - `entrypoint.sh`
  - `*.dockerfile` (matching existing naming patterns)
- `src/` (and `tests/` if applicable).

Then wire the new service into the example deployment at `deployments/example_station/`.

### PR checklist

- `task pre-commit-check` passes at the repo root if you changed shared files.
- No secrets in commits (tokens, robot IPs meant to be private, keys, etc.).
- Docs/configs updated when behavior changes.
- Commits are signed off (see DCO below).

## License

Any contribution that you make to this repository will
be under the Apache 2 License, as dictated by that
[license](http://www.apache.org/licenses/LICENSE-2.0.html):

```
5. Submission of Contributions. Unless You explicitly state otherwise,
   any Contribution intentionally submitted for inclusion in the Work
   by You to the Licensor shall be under the terms and conditions of
   this License, without any additional terms or conditions.
   Notwithstanding the above, nothing herein shall supersede or modify
   the terms of any separate license agreement you may have executed
   with Licensor regarding such Contributions.
```

Contributors must sign-off each commit by adding a `Signed-off-by: ...`
line to commit messages to certify that they have the right to submit
the code they are contributing to the project according to the
[Developer Certificate of Origin (DCO)](https://developercertificate.org/).
