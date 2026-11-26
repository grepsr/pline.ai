# Publishing the pline.ai MCP server and skill

This runbook covers every channel where the MCP server and the skill are, or should be, listed: npm,
the official MCP Registry, Anthropic's Claude directory, Cursor and VS Code, Glama, the `skills` CLI,
and the community GitHub lists. It records what the repository automates, what a maintainer does by
hand, which credentials each step needs, and the prerequisites that gate everything.

## Prerequisites that gate every channel

| Prerequisite | Why | Status |
|---|---|---|
| Public repository | The MCP Registry resolves `repository.url`; npm provenance attestations need a public repo; the Claude directory requires a public GitHub repository before a plugin bundle goes live; awesome lists, Glama, and `npx skills add` only read public repositories; GHCR images pushed from a private repository are private; the `ubuntu-*-arm` runners used for Linux arm64 and the arm64 image are free only for public repositories. | **Done.** `grepsr/pline.ai` is public. |
| Open-source license | The Claude directory blocks a plugin without a `LICENSE` file or `license` in `plugin.json`; npm warns without one; awesome-list maintainers and crates.io require one. | **Done.** MIT, in `LICENSE`, `mcp-server/Cargo.toml`, `npm/package.json`, `.claude-plugin/plugin.json`, and the README. |
| Public GHCR package | The registry validates the OCI package anonymously. | Verify `pline-mcp` is public before publishing the MCP Registry entry. |
| npm package names | Launcher: `pline-ai`; platform packages are scoped as `@pline/api-<os>-<cpu>` because npm's spam detection rejects new unscoped `*-win32-x64` names. | The `pline` npm org exists; `NPM_TOKEN` must have publish rights on it for the first scoped publish. |
| A new version tag | Tags are immutable release inputs; `v0.3.12` is the latest published release. | Use the next version, `0.3.13`, after the version bump reaches `main`. |

## Credentials and secrets

Nothing in the repository needs a long-lived secret once trusted publishing is set up. The table
lists what each step authenticates with and who sets it up.

| Step | Auth | Secret in GitHub? | One-time setup |
|---|---|---|---|
| GitHub Release, binaries, SHA256SUMS | `GITHUB_TOKEN` (`contents: write`) | No | None |
| GHCR image push | `GITHUB_TOKEN` (`packages: write`) | No | Set the package public once |
| npm publish, steady state | npm **trusted publishing**: the workflow's GitHub OIDC token (`id-token: write`) is exchanged for a short-lived npm credential; provenance is attached automatically on a public repo | No | On npmjs.com, for **each** of the six packages: **Package settings → Trusted publisher → GitHub Actions**, organization `grepsr`, repository `pline.ai`, workflow filename `publish.yml`, environment `npm-publish` (the `npm` job declares it, so it must match exactly). Requires npm CLI 11.5.1+ (the workflow uses Node 24). |
| npm publish, first time | A package must exist before a trusted publisher can be configured on it, so the first version of each package is published with a token | `NPM_TOKEN`, temporarily | Create a **granular access token** on npmjs.com with **Read and write** on packages, **Bypass 2FA** enabled, and the shortest expiry that covers the release. Store it as an **Environment secret** named `NPM_TOKEN` on the `npm-publish` environment (repo → Settings → Environments); the workflow passes it as `NODE_AUTH_TOKEN`. After the first publish, configure trusted publishers and delete the token and the secret. Alternatively run `npm publish` locally once from `npm/` and `npm/dist/*` while logged in. |
| MCP Registry | `mcp-publisher login github-oidc`: GitHub OIDC grants the `io.github.grepsr/*` namespace to workflows in this organization | No | None. Switching to an `ai.pline/...` name instead needs DNS auth: publish an Ed25519 public key in a TXT record on `pline.ai`, store the private key as `MCP_PRIVATE_KEY`, change `name` in `server.json`, `mcpName` in `npm/package.json`, and the Dockerfile label together, and change the login step to `mcp-publisher login dns --domain pline.ai`. |
| Claude directory | Interactive, from a claude.ai account on a Pro, Max, Team, or Enterprise plan | No | None |
| Glama, awesome lists, mcpservers.org | A GitHub account for PRs, an email for the form | No | None |
| crates.io (optional, not wired up) | `CARGO_REGISTRY_TOKEN`, or crates.io trusted publishing | Only if you add the `cargo` package type | Needs `license` in `Cargo.toml` |

The `npm` job already declares `environment: npm-publish`; GitHub creates the environment unprotected on
first use, so configure it before the first release: Settings → Environments → `npm-publish` → add the
`NPM_TOKEN` secret, restrict **Deployment branches and tags** to `v*`, and add a required reviewer.
Anyone who can push a tag can otherwise run the publish job with the token. The same hardening applies to `MCP_PRIVATE_KEY` if DNS auth is
adopted. GitHub OIDC tokens need no such care: they exist only for the duration of the job.

## Release flow (one tag drives everything)

1. Bump the version with `python3 tests/check_versions.py --set X.Y.Z`. It rewrites
   `mcp-server/Cargo.toml` and `Cargo.lock`, `server.json` (top level, every `packages[].version`, the
   OCI image tag), `npm/package.json` (`version` and all five `optionalDependencies`),
   `plugin/.claude-plugin/plugin.json`, `plugin/.cursor-plugin/plugin.json`, and
   `plugin/.codex-plugin/plugin.json` (`version`),
   `.claude-plugin/marketplace.json` and `.cursor-plugin/marketplace.json`, and the release links, archive names, and image tags in both
   READMEs, then verifies. Without `--set` the same script runs in CI and fails on any mismatch.
2. Push the tag `v<version>`. [release.yml](.github/workflows/release.yml) then:
   - builds and smoke-tests the five platform binaries (macOS arm64/x64, Linux x64/arm64, Windows x64);
   - builds the Docker image natively on amd64 and arm64 runners, pushes both by digest to
     `ghcr.io/grepsr/pline-mcp`, stitches them into the `<version>` and `latest` tags, and verifies the
     `io.modelcontextprotocol.server.name` label equals the `name` in `server.json`;
   - creates a **draft** GitHub Release with the archives and `SHA256SUMS`.
3. Review and publish the draft release.
4. Publishing the release fires [publish.yml](.github/workflows/publish.yml):
   - **npm**: downloads the release archives, assembles the five platform packages with
     [`npm/build-platform-packages.py`](npm/build-platform-packages.py), publishes each (skipping
     versions already on npm), then publishes the `pline-ai` launcher, and finally runs
     `npx -y pline-ai@<version> --help` to prove the published package works;
   - **registry**: checks that `pline-ai@<version>` on npm carries `mcpName` and that the image is
     publicly pullable with the right label, validates `server.json`, logs in with GitHub OIDC, and
     publishes `io.github.grepsr/pline-ai`.
   Re-run it from the Actions tab with the tag as input if it needs repeating; tick **skip_npm** to
   republish only the registry entry. If the registry rejects the tag's `server.json`, fix it on
   `main` and set **server_ref** to `main`: the registry stage then reads `server.json` from that ref
   (its versions must still match the tag) without a new release.

The README's one-click Cursor and VS Code buttons run `npx -y pline-ai` unpinned, so they do not
change between releases. Regenerate them only if the command or environment variables change:

```sh
python3 - <<'EOF'
import base64, json
from urllib.parse import quote
cursor = {"command": "npx", "args": ["-y", "pline-ai"], "env": {"PLINE_BASE_URL": "https://apix.pline.ai/v1", "PLINE_API_KEY": "your-own-api-key"}}
print("cursor link: https://cursor.com/install-mcp?name=pline-ai&config=" + base64.b64encode(json.dumps(cursor, separators=(",", ":")).encode()).decode())
vscode = {"name": "pline-ai", "command": "npx", "args": ["-y", "pline-ai"],
          "env": {"PLINE_BASE_URL": "${input:pline-base-url}", "PLINE_API_KEY": "${input:pline-api-key}"},
          "inputs": [{"id": "pline-base-url", "type": "promptString", "description": "pline.ai API base URL", "default": "https://apix.pline.ai/v1"},
                     {"id": "pline-api-key", "type": "promptString", "description": "pline.ai API key", "password": True}]}
print("vscode query:", quote(json.dumps(vscode, separators=(",", ":")), safe=""))
EOF
```

## 1. npm (`npx -y pline-ai`)

- **Layout:** [`npm/`](npm) holds the `pline-ai` launcher (`bin/pline-mcp.js`, README, package.json
  with `mcpName`). It resolves the binary from `PLINE_MCP_BINARY`, then from the platform package
  installed through `optionalDependencies` (`@pline/api-darwin-arm64`, `-darwin-x64`, `-linux-x64`,
  `-linux-arm64`, `-win32-x64`), then from a checksum-verified download of the GitHub Release archive
  cached under `~/.cache/pline-mcp/<version>/`. Platform packages are generated in CI, never committed.
- **Testing locally:** `cargo build --manifest-path mcp-server/Cargo.toml --locked`, then
  `PLINE_MCP_BINARY=$PWD/mcp-server/target/debug/pline-mcp python3 tests/smoke.py npm/bin/pline-mcp.js`.
  CI runs the same, plus `npm pack --dry-run`.
- **Publishing:** the npm stage of `publish.yml`, see above. All six packages share one version.
- **Check a release:** `npm view pline-ai@<version>` and `npx -y pline-ai@<version> --help`.

## 2. Official MCP Registry

- **What is published:** [`server.json`](server.json), name `io.github.grepsr/pline-ai`, two packages:
  the `npm` package `pline-ai` (run with `npx`) and the `oci` image `ghcr.io/grepsr/pline-mcp:<version>`,
  both over stdio with `PLINE_BASE_URL` and `PLINE_API_KEY` (the key marked secret).
- **Ownership proof:** `mcpName` in `npm/package.json` and the Dockerfile `LABEL
  io.modelcontextprotocol.server.name` must both equal the `name` in `server.json`; CI and the
  publish workflow check both. The registry rejects the publish if either artifact is missing or private.
- **Optional extra packages** (add only once the artifact exists, because the registry validates
  every package):
  - `cargo`: publish `pline-mcp` to crates.io and add a visible `mcp-name: io.github.grepsr/pline-ai`
    line to `mcp-server/README.md`; crates.io strips HTML comments, so it must be plain text.
  - `mcpb`: zip a prebuilt binary with an MCPB `manifest.json`, attach it to the GitHub Release, and
    record its SHA-256 in `fileSha256`.
  - `remotes`: if the operator hosts the Streamable HTTP mode publicly, add
    `{"type": "streamable-http", "url": "https://.../mcp"}`.
- **Check a listing:**

  ```sh
  curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.grepsr/pline-ai"
  ```

- **Review and timing:** none. Publishing is immediate once validation passes. Aggregators such as
  PulseMCP and Glama ingest the registry automatically.

## 3. Claude directory (claude.ai, Claude Desktop, Cowork, Claude Code)

The directory accepts two listing kinds. Desktop extensions (MCPB) are no longer accepted, so a local
server is distributed as a **plugin bundle**.

### Plugin bundle (the `plugin/` folder)

- [`plugin/`](plugin) is the plugin, submitted with **Plugin path** `plugin` so the directory scans
  only what it ships: [`plugin.json`](plugin/.claude-plugin/plugin.json) (with `privacyPolicyUrl`),
  an MCP-only version of the `pline-ai` skill, the icon, a README with the privacy policy section,
  and the license. Its
  `pline.ai` MCP server is the **hosted** `https://mcp.pline.ai/mcp` (OAuth), so the plugin works on
  claude.ai as well as in Claude Code and Cowork, and stores no API key.
- The plugin's skill is MCP-only on purpose: no Python client, no `PLINE_API_KEY`, and no direct API
  host. The directory holds any plugin that reads a local credential and also sends data off the
  machine (`MCP_FORWARDS_CREDENTIAL_ENV`); with OAuth through the hosted server none is needed. The
  standalone `skills/pline-ai` (for `npx skills add`) keeps the Python client. When you change the
  standalone skill, update `plugin/skills/pline-ai/SKILL.md` to match in MCP terms;
  `tests/check_plugin.py` (CI) enforces the same name, description, and `agents/openai.yaml`, and
  fails if the plugin gains a script or a credential reference.
- [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) points at `./plugin`, so anyone
  can install without the directory:

  ```sh
  claude plugin marketplace add grepsr/pline.ai
  claude plugin install pline-ai@pline-ai
  ```

- Validate before submitting: `claude plugin validate plugin` and `claude plugin validate .`
  (marketplace).
- Submit at [claude.ai/directory/manage](https://claude.ai/directory/manage) from the Grepsr
  organization account (the first organization to submit a repository owns the listing):
  **Submit new → Plugin bundle**, **Repository** `grepsr/pline.ai`, **Plugin path** `plugin`, then
  **Validate**, fix anything **Blocking**, and **Submit for review**.
- Expected holds, which a reviewer clears: `assets/icon.png` (an image the scanner cannot prove is
  never executed) and `NAME_CONFUSABLE` (`pline-ai` is within two characters of the unrelated
  "Plane" listing).
- After approval, every commit on the tracked branch is re-scanned and published automatically.
  The version script raises `version` in `plugin.json` with each release.

### MCP connector (`https://mcp.pline.ai/mcp`)

The hosted server (`pline-mcp` in `pline-hades-gitops`, DNS in `pline-hades-infra`) answers `/mcp`
with `401` and a `WWW-Authenticate` header that leads to Supabase OAuth 2.1 with dynamic client
registration; every tool declares a `title` and `readOnlyHint` or `destructiveHint`. Submit it with
**Submit new → MCP connector** and URL `https://mcp.pline.ai/mcp`, then pair it with the plugin
listing. Reviewers need a pline.ai test account with a workspace, an active API key, and credits.

## 4. Cursor and VS Code

- [`.cursor/mcp.json`](.cursor/mcp.json) and [`.vscode/mcp.json`](.vscode/mcp.json) are picked up when
  the repository is opened as a workspace. Both run `npx -y pline-ai`; Cursor reads
  `PLINE_BASE_URL`/`PLINE_API_KEY` from the environment, VS Code prompts for them (the key is masked).
- The README carries one-click **Add to Cursor** and **Install in VS Code** buttons with the same
  command, so users need Node.js but not Rust or Docker.
- Nothing indicates Cursor ingests the official registry; the `cursor/mcp-servers` repository is
  archived. Cursor lists **plugins** instead, and the `plugin/` folder is also a Cursor plugin.

### Cursor plugin (the `plugin/` folder)

- [`plugin/.cursor-plugin/plugin.json`](plugin/.cursor-plugin/plugin.json) is the Cursor manifest
  for the same folder the Claude directory scans: same name, description, and links, `logo`
  `assets/icon.png`, `skills` `skills/`, and `mcpServers` `.mcp.json`.
  [`plugin/.mcp.json`](plugin/.mcp.json) declares the hosted `https://mcp.pline.ai/mcp` (OAuth, so no
  `variables` and no API key). [`.cursor-plugin/marketplace.json`](.cursor-plugin/marketplace.json)
  at the root points at `plugin`. `tests/check_plugin.py` keeps the Cursor manifest, `.mcp.json`, and
  the Claude manifest in agreement; `tests/check_versions.py` keeps the versions in step.
- Test locally before submitting: copy `plugin/` to `~/.cursor/plugins/local/pline-ai`, run
  **Developer: Reload Window**, open **Customize**, and confirm the `pline-ai` skill and the
  `plugin-pline-ai-pline-ai` MCP server appear and that the OAuth sign-in completes.
- **cursor.directory first.** Cursor staff steer most publishers to the community directory before
  the curated Marketplace (one Marketplace applicant was declined and told to list there first).
  Submit at [cursor.directory/plugins/new](https://cursor.directory/plugins/new): sign in with GitHub,
  paste `https://github.com/grepsr/pline.ai`, and submit. It auto-detects `skills/*/SKILL.md` and
  `.mcp.json`.
- **Cursor Marketplace.** Submit the repository URL at
  [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish). The form always submits
  as the signed-in individual; say in the description that this is a Grepsr company submission and
  give the contact address (the manifest `author` already names Grepsr). Review is manual with no
  SLA; follow up at marketplace-publishing@cursor.com, and on the Cursor forum if that goes quiet.
- Checklist ([Cursor reference](https://cursor.com/docs/reference/plugins#submission-checklist)):
  valid `.cursor-plugin/plugin.json`, kebab-case `name`, clear `description`, valid skill
  frontmatter, logo committed and referenced by relative path, README, relative paths only, every
  `${VAR}` declared (none are used), tested locally, `.cursor-plugin/marketplace.json` at the root.
- VS Code's MCP gallery (`@mcp` in the Extensions view) is GitHub's curated
  [MCP Registry](https://github.com/mcp). Being in the official registry is the prerequisite; ask
  for inclusion by emailing partnerships@github.com until self-publication opens.

## 4a. Codex and ChatGPT

- **Codex** (CLI, IDE extension, app) reads `~/.codex/config.toml`; the README's
  [Codex MCP section](README.md#codex-1) gives `codex mcp add` and an `env_vars` variant that keeps
  the key out of the file. `npx skills add grepsr/pline.ai -a codex` installs the skill.
- `codex plugin marketplace add grepsr/pline.ai` reads `.claude-plugin/marketplace.json` and installs
  `plugin/`, using [`plugin/.codex-plugin/plugin.json`](plugin/.codex-plugin/plugin.json): Codex sees
  the hosted server as streamable HTTP at `https://mcp.pline.ai/mcp`; sign in with
  `codex mcp login pline-ai`. To try a branch without touching your own Codex setup:
  `CODEX_HOME=$(mktemp -d) codex plugin marketplace add "$PWD"`, then
  `codex plugin add pline-ai@pline-ai` and `codex mcp list`.
- **ChatGPT** and the shared OpenAI plugin directory (platform.openai.com/plugins) accept only a
  remote HTTPS MCP endpoint with OAuth 2.1 or no auth; API-key headers and local stdio servers are
  not supported. `https://mcp.pline.ai/mcp` meets that requirement.

### OpenAI plugin directory (ChatGPT and Codex)

One listing covers ChatGPT and Codex. Claude directory approval does not carry over. Guides:
[Submit a Claude Code plugin](https://developers.openai.com/plugins/guides/submit-claude-plugin),
[Submit plugins](https://developers.openai.com/plugins/deploy/submission),
[submission errors](https://developers.openai.com/plugins/deploy/submission-errors).

- **Package.** `plugin/.codex-plugin/plugin.json` carries the listing (`interface`: display name,
  30-character short description, category `Data & Analytics`, capabilities, three example prompts,
  icon, and the website, support, privacy, and terms URLs) plus the review material under
  `extensions.com.openai`: five positive and three negative test cases and the release notes, which
  the portal imports from the ZIP. It reads the server from `plugin/.mcp.json`. `tests/check_plugin.py`
  enforces the directory's limits; update `release_notes` with each submitted version. The package
  must not declare hooks or apps.
- **Build the ZIP** from the plugin folder, so `.codex-plugin/plugin.json` sits at the archive root:
  `cd plugin && zip -r ../pline-ai-plugin.zip . -x '.DS_Store'`.
- **One-time setup, outside the repository:**
  - OpenAI organization owned by Grepsr, with business verification done in
    [organization settings](https://platform.openai.com/settings/organization/general) so the listing
    shows Grepsr; the submitter needs owner or **Apps Management Write**.
  - Domain verification: serve the token the portal shows, as plain text, at
    `https://mcp.pline.ai/.well-known/openai-apps-challenge` (the `pline-mcp` deployment in
    `pline-hades-gitops`, or a parent origin on `pline.ai`).
  - OAuth: advertise and allow the `openid` and `email` scopes and expose a UserInfo endpoint that
    returns `email` and `email_verified: true` (Supabase). Registration is dynamic (DCR), so the
    package carries no client ID or secret.
  - Reviewer account: a dedicated pline.ai test account with a workspace and credits that signs in
    without MFA, email codes, or magic links. Enter its credentials in the portal, never in the ZIP.
  - A demo video of the test cases, at an accessible URL (`demo_recording_url`, or enter it in the
    portal).
- **Submit:** [platform.openai.com/plugins](https://platform.openai.com/plugins) → **Upload new or
  existing plugin** → choose the Grepsr developer identity → upload the ZIP. Fix **Metadata &
  Skills** findings, then **MCPs → Connect** (domain challenge, then OAuth sign-in with the test
  account) and wait for the tool scan. Run every test case with the test account, complete **Review
  details**, and **Submit for review**. After approval, **Publish plugin**. The server is rescanned
  daily, so tool changes need no new ZIP; changes to metadata or the skill do.

## 5. Skill distribution (`npx skills add`)

The [`skills`](https://skills.sh) CLI installs skills from any public GitHub repository into the
folders of 70+ agents. It discovers `skills/pline-ai/SKILL.md` directly and also reads
`.claude-plugin/marketplace.json`, so once the repository is public:

```sh
npx skills add grepsr/pline.ai            # prompts for agents; -g for user-wide, -y to accept
npx skills add grepsr/pline.ai -a cursor  # one agent
npx skills add grepsr/pline.ai --list     # show what it found
```

skills.sh lists repositories automatically from install activity; there is no submission form.

## 6. Glama

Glama indexes public GitHub repositories automatically and ingests the official registry.
[`glama.json`](glama.json) at the repository root names the GitHub accounts allowed to claim and
edit the listing; add maintainers there. After the repository is public, claim the listing at
`https://glama.ai/mcp/servers/grepsr/pline-api` (sign in with GitHub). Glama's scorecard rewards a
license, a README with install steps, and tests, all of which this repository has.

## 7. Community lists and aggregators

Open these only after the repository is public and licensed. Each is a pull request or form filled in
by a maintainer; none are automated here.

### punkpeye/awesome-mcp-servers (pull request)

Its CI labels a PR `missing-glama` until the server is listed and passing on Glama, so finish
[Glama](#6-glama) first and include the score badge after the link. Fork, add the line under
**🔎 Search & Data Extraction** (or **📂 Browser Automation**, where other
scrape/crawl/map servers appear) keeping alphabetical order by repository, and open a PR titled
`Add grepsr/pline.ai`. The legend markers: 🎖️ official, 🦀 Rust, ☁️ cloud service (the scraping
runs on pline.ai), and the three OS badges because the server runs on all three.

```markdown
- [grepsr/pline.ai](https://github.com/grepsr/pline.ai) [![grepsr/pline.ai MCP server](https://glama.ai/mcp/servers/grepsr/pline-api/badges/score.svg)](https://glama.ai/mcp/servers/grepsr/pline-api) 🎖️ 🦀 ☁️ 🍎 🪟 🐧 - Scrape, batch-scrape, crawl, map and search the web through the pline.ai API, returning Markdown, HTML, screenshots or structured JSON with session reuse and background jobs.
```

Typical turnaround is a few days to two weeks.

### wong2/awesome-mcp-servers and mcpservers.org (form)

This list does not accept pull requests. Submit at <https://mcpservers.org/submit> with:
name `pline.ai`, category **Web Scraping**, the one-sentence description above, repository
`https://github.com/grepsr/pline.ai`, official registry name `io.github.grepsr/pline-ai`, remote
connections unchecked (until a hosted endpoint exists), and a contact email. The free tier reviews
within about two weeks.

### modelcontextprotocol/servers

No longer lists third-party servers: its README keeps only reference servers and points to the
official registry, and CONTRIBUTING.md accepts issues, not pull requests. The registry entry covers it.

### PulseMCP

Submissions are still paused (checked October 2026) while PulseMCP rebuilds its pipeline; it ingests the official
registry automatically when they resume, so the registry publish above covers it.

## Status checklist

| Channel | Mechanism | Done in repo | Maintainer action |
|---|---|---|---|
| npm `pline-ai` + platform packages | `npm/` + `publish.yml` npm stage | Yes | First publish with `NPM_TOKEN`, then configure trusted publishers and drop the token |
| MCP Registry | `server.json` + `publish.yml` registry stage (OIDC) | Yes | Make repo and GHCR package public, then publish a release |
| GHCR image | `release.yml` image jobs | Yes | Set package visibility to public once |
| Claude directory, plugin bundle | `plugin/` (hosted MCP + skill) | Yes | Submit with Plugin path `plugin` |
| Claude directory, MCP connector | `https://mcp.pline.ai/mcp` with OAuth | Yes | Submit after `mcp.pline.ai` DNS and route are live |
| Cursor / VS Code | Workspace configs + README buttons | Yes | None |
| Cursor directory listings | cursor.directory / Cursor Marketplace form | No | Submit the forms |
| VS Code gallery (GitHub MCP Registry) | Curated from the official registry | No | Email partnerships@github.com |
| Codex | README `codex mcp add` / `config.toml` | Yes | None |
| ChatGPT, OpenAI plugin directory | `https://mcp.pline.ai/mcp` with OAuth | Endpoint ready | Submit at platform.openai.com/plugins |
| Skill via `npx skills add` | `skills/pline-ai/` + marketplace.json | Yes | Make the repo public |
| Glama | `glama.json` + auto-index | Yes | Claim the listing after going public |
| awesome-mcp-servers | PR | Entry drafted above | List on Glama, then open the PR |
| mcpservers.org | Form | Values drafted above | Submit the form |
| modelcontextprotocol/servers | Registry only | Covered by the registry | None |
| PulseMCP | Ingests the registry | Covered by the registry | None while submissions are paused |
