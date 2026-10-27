# Third-party and inherited material

Status: application source, adapted PushPilot temporary-map geometry and original documentation/UI artwork. No supplied map artwork, raw camera photograph, model weights, archived operating profile or POC driver is bundled. Runtime and build dependencies are declared below and resolved by lockfiles.

Python and Node are external prerequisites; their runtimes are not bundled. Python dependencies are installed separately. The built frontend includes its React dependencies. No software license has been selected for PushPilot itself; dependency licenses do not license this repository's original code or artwork.

## Dependencies

Versions below were resolved on 2026-10-27. Python license identifiers were checked against installed distribution metadata; frontend identifiers are recorded by the npm lockfile. Keep upstream notices with any redistributed packages.

| Material | Source/version | Upstream license | Use |
|---|---|---|---|
| React and React DOM | npm, 19.3.1 | MIT | Browser runtime |
| TypeScript | npm, 7.0.2 | Apache-2.0 | Local type checking |
| Vite | npm, 8.3.5 | MIT | Local build/dev server |
| React/React DOM type definitions | npm, 19.3.0 | MIT | Local type checking |
| FastAPI | PyPI, 0.162.0 | MIT | HTTP API |
| Uvicorn | PyPI, 0.54.0 | BSD-3-Clause | ASGI server |
| HTTPX | PyPI, 0.28.1 | BSD-3-Clause | Server-side Meta requests |
| python-multipart | PyPI, 0.0.32 | Apache-2.0 | Bounded recorded-image uploads |
| OpenCV contrib headless | PyPI, 5.0.0.93 | Apache-2.0 | Recorded-image marker detection and test projection |
| NumPy | PyPI, 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Numerical image geometry; identifier from installed distribution metadata |
| Pydantic / pydantic-core | PyPI, 2.14.1 / 2.50.1 | MIT | Request validation |
| Starlette | PyPI, 1.10.0 | BSD-3-Clause | ASGI framework dependency |
| anyio, annotated-doc, annotated-types, h11, typing-inspection | PyPI, exact versions in `requirements.lock` | MIT | Python transitive dependencies |
| click, httpcore, idna | PyPI, exact versions in `requirements.lock` | BSD-3-Clause | Python transitive dependencies |
| certifi | PyPI, 2026.10.23 | MPL-2.0 | CA certificate bundle |
| opentelemetry-api | PyPI, 1.45.1 | Apache-2.0 | FastAPI transitive dependency |
| typing_extensions | PyPI, 4.16.0 | PSF-2.0 | Python typing support |

The complete npm build resolution, including platform-specific optional tools, is in `frontend/package-lock.json`. The complete Python resolution is in `requirements.lock`; platform-specific wheel hashes are not pinned. Source archives exclude `node_modules`, `.venv` and `frontend/dist`. The frontend's `public/third-party-licenses.txt` carries the original React runtime notices into each built distribution.

Meta is accessed as an external service through its documented HTTPS API; no Meta SDK or model weights are included. Provider access remains subject to the account's applicable service terms. Recorded live checks establish the limited scope in [`docs/META_API_CHECK.md`](docs/META_API_CHECK.md).

## Original and inherited artwork

`backend/data/little-town-temporary.json` adapts geometry, graph, named destinations and marker facts from the pre-existing PushPilot `production-v11/map-definition.json`, SHA-256 `dea6c955e01f2bc91333d8e47246a960d926831772603245e89183340b52481a`. This is inherited design data, not newly authored road geometry. The adapter strips historical POC provenance paths, obsolete grasp/transport assumptions, robot transforms and artwork. New route supervision and recorded-scene processing are separately authored application code. No new license grant for the inherited material is asserted.

The README cover and retained editable workflow are original vector illustrations created for this repository. Conceptual process diagrams were created with the built-in image generation tool, using English prompts and no source photographs or third-party media inputs. The voice-enabled revision uses the earlier repository-generated architecture image as its edit target. See [`docs/assets/README.md`](docs/assets/README.md) for the asset inventory, [`GENERATION_PROMPTS.md`](docs/assets/GENERATION_PROMPTS.md) and [`VOICE_GENERATION_PROMPTS.md`](docs/assets/VOICE_GENERATION_PROMPTS.md) for exact prompts. The generated diagrams are documentation, not camera captures, model results or working-product screenshots. Asset origin does not establish a software or artwork license.

For inherited PushPilot code, identify the exact original component and version, applicable rights and newly changed portions. Preserve required notices. Existing robot plumbing, map bytes, reference screenshots and earlier success clips are not newly created by copying them here.

Keep private participant-guide copies, user reference images, handoff archives, raw observations and unreviewed media outside release packages. Add only material whose use and distribution have been reviewed. Model API service terms and SDK licenses, if later used, need their own recorded versions; an API integration does not include or redistribute the model itself.
