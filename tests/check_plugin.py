"""Check the plugin in plugin/ (Claude directory, Cursor Marketplace, OpenAI plugin directory).

    python3 tests/check_plugin.py          # verify, exit 1 on any problem

The plugin is submitted from its own folder so the directory scans only what the plugin ships. Its
MCP server is the hosted https://mcp.pline.ai/mcp, where the user signs in with OAuth, so its copy
of the pline-ai skill is MCP-only: it must not read a credential from the user's machine (no
PLINE_API_KEY, no direct API host, no bundled scripts). The directory holds any plugin that pairs a
local credential read with a remote destination. The Cursor manifest (.cursor-plugin/plugin.json)
describes the same folder and reads the same hosted server from plugin/.mcp.json, which
cursor.directory also auto-detects. The Codex manifest (.codex-plugin/plugin.json) is what the
OpenAI plugin directory (ChatGPT and Codex) reads from the uploaded ZIP; its listing and review
fields follow the directory's final-submission limits. The standalone skill in skills/pline-ai, which
`npx skills add grepsr/pline.ai` installs, keeps its Python client and API reference.
"""

import json
from pathlib import Path
import struct
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugin'
SKILL = ROOT / 'skills/pline-ai'
PLUGIN_SKILL = PLUGIN / 'skills/pline-ai'
HOSTED_MCP_URL = 'https://mcp.pline.ai/mcp'
LISTING_LINKS = {
    'documentationUrl': 'https://github.com/grepsr/pline.ai#readme',
    'supportUrl': 'https://github.com/grepsr/pline.ai/issues',
    'privacyPolicyUrl': 'https://www.pline.ai/privacy-policy',
    'termsOfServiceUrl': 'https://www.pline.ai/terms-of-service',
}
# What the directory's credential scan treats as reading a key and sending it off the machine.
FORBIDDEN = re.compile(
    r'PLINE_API_KEY|PLINE_BASE_URL|apix\.pline\.ai|x-api-key|os\.environ|process\.env|api[ _-]?key',
    re.IGNORECASE,
)
EXECUTABLE_SUFFIXES = {'.py', '.sh', '.js', '.mjs', '.cjs', '.ts', '.rb', '.ps1'}


def frontmatter(path):
    text = path.read_text(encoding='utf-8')
    match = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(':')
        fields[key.strip()] = value.strip()
    return fields


def relative_inside(base, value):
    # Cursor's submission checklist: manifest paths are relative, with no '..' and no absolute path.
    path = Path(value)
    return bool(value) and not path.is_absolute() and '..' not in path.parts and (base / path).exists()


def check_cursor(claude_manifest):
    problems = []
    cursor_path = PLUGIN / '.cursor-plugin/plugin.json'
    if not cursor_path.is_file():
        return ['plugin/.cursor-plugin/plugin.json is missing']
    cursor = json.loads(cursor_path.read_text(encoding='utf-8'))
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', cursor.get('name', '')):
        problems.append(f'Cursor plugin name {cursor.get("name")!r} must be lowercase kebab-case')
    for key in ('name', 'description', 'homepage', 'repository', 'license', 'keywords'):
        if cursor.get(key) != claude_manifest.get(key):
            problems.append(f'Cursor plugin.json {key} differs from the Claude manifest')
    codex_path = PLUGIN / '.codex-plugin/plugin.json'
    codex_name = json.loads(codex_path.read_text(encoding='utf-8')).get('interface', {}).get('displayName') if codex_path.is_file() else None
    if cursor.get('displayName') != codex_name:
        problems.append(f'Cursor plugin.json displayName {cursor.get("displayName")!r} must match the Codex displayName {codex_name!r}')
    if cursor.get('author', {}).get('name') != claude_manifest.get('author', {}).get('name'):
        problems.append('Cursor plugin.json author.name differs from the Claude manifest')
    for key in ('logo', 'skills', 'mcpServers'):
        value = cursor.get(key)
        if not isinstance(value, str) or not relative_inside(PLUGIN, value):
            problems.append(f'Cursor plugin.json {key} {value!r} must be a relative path that exists inside plugin/')
    if 'variables' in cursor:
        problems.append('Cursor plugin.json must not declare variables; the hosted server uses OAuth')

    mcp_path = PLUGIN / '.mcp.json'
    servers = json.loads(mcp_path.read_text(encoding='utf-8')).get('mcpServers', {}) if mcp_path.is_file() else {}
    if servers != claude_manifest.get('mcpServers'):
        problems.append(f'plugin/.mcp.json must declare the same servers as the Claude manifest, found {servers}')

    marketplace_path = ROOT / '.cursor-plugin/marketplace.json'
    if not marketplace_path.is_file():
        return problems + ['.cursor-plugin/marketplace.json is missing']
    marketplace = json.loads(marketplace_path.read_text(encoding='utf-8'))
    entries = marketplace.get('plugins', [])
    if [(e.get('name'), e.get('source')) for e in entries] != [(cursor.get('name'), 'plugin')]:
        problems.append(f'.cursor-plugin/marketplace.json must list only {cursor.get("name")!r} at source "plugin"')
    if not marketplace.get('owner', {}).get('name'):
        problems.append('.cursor-plugin/marketplace.json needs owner.name')
    return problems


OPENAI_CATEGORIES = {
    'Productivity', 'Creativity', 'Developer Tools', 'Business & Operations', 'Data & Analytics',
    'Communication', 'Education & Research', 'Security', 'Finance', 'Healthcare', 'Travel',
    'Entertainment', 'Other',
}


def png_size(path):
    data = path.read_bytes()[:24]
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', data[16:24])


def check_codex(claude_manifest):
    # Limits from https://developers.openai.com/plugins/deploy/submission-errors (final submission).
    problems = []
    path = PLUGIN / '.codex-plugin/plugin.json'
    if not path.is_file():
        return ['plugin/.codex-plugin/plugin.json is missing']
    codex = json.loads(path.read_text(encoding='utf-8'))
    label = 'Codex plugin.json'
    for key in ('name', 'description', 'homepage', 'repository', 'license', 'keywords'):
        if codex.get(key) != claude_manifest.get(key):
            problems.append(f'{label} {key} differs from the Claude manifest')
    if not codex.get('author', {}).get('name'):
        problems.append(f'{label} needs author.name')
    if len(codex.get('keywords', [])) > 25:
        problems.append(f'{label} allows at most 25 keywords')
    for key in ('skills', 'mcpServers'):
        value = codex.get(key, '').removeprefix('./')
        if not relative_inside(PLUGIN, value):
            problems.append(f'{label} {key} {codex.get(key)!r} must be a relative path that exists inside plugin/')
    for key in ('hooks', 'apps'):
        if key in codex:
            problems.append(f'{label} must not declare {key}; the directory rejects packages with them')

    ui = codex.get('interface', {})
    limits = {'displayName': 30, 'shortDescription': 30, 'longDescription': 4000, 'developerName': 80}
    for key, limit in limits.items():
        value = ui.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            problems.append(f'{label} interface.{key} must be non-empty and at most {limit} characters: {value!r}')
        elif key != 'longDescription' and '\n' in value:
            problems.append(f'{label} interface.{key} must be one line')
    if ui.get('category') not in OPENAI_CATEGORIES:
        problems.append(f'{label} interface.category {ui.get("category")!r} is not a directory category')
    capabilities = ui.get('capabilities', [])
    if len(capabilities) > 20 or any(not c.strip() or len(c) > 120 for c in capabilities):
        problems.append(f'{label} interface.capabilities: at most 20, each one line of at most 120 characters')
    prompts = ui.get('defaultPrompt', [])
    if not 1 <= len(prompts) <= 3 or len(set(prompts)) != len(prompts) or any(len(p) > 128 or '@' in p for p in prompts):
        problems.append(f'{label} interface.defaultPrompt: 1-3 unique prompts, at most 128 characters, no @mentions')
    links = {'websiteURL': None, 'supportURL': 'supportUrl', 'privacyPolicyURL': 'privacyPolicyUrl',
             'termsOfServiceURL': 'termsOfServiceUrl'}
    for key, claude_key in links.items():
        value = ui.get(key, '')
        if not value.startswith('https://'):
            problems.append(f'{label} interface.{key} must be an https URL')
        elif claude_key and value != claude_manifest.get(claude_key):
            problems.append(f'{label} interface.{key} differs from the Claude manifest {claude_key}')
    for key in ('composerIcon', 'logo'):
        value = ui.get(key, '').removeprefix('./')
        size = png_size(PLUGIN / value) if relative_inside(PLUGIN, value) else None
        if not size or size[0] != size[1] or not 48 <= size[0] <= 4096:
            problems.append(f'{label} interface.{key} {ui.get(key)!r} must be a square PNG of 48-4096 px inside plugin/')

    review = codex.get('extensions', {}).get('com.openai', {}).get('review', {})
    cases = review.get('test_cases', {})
    if len(cases.get('positive', [])) != 5 or len(cases.get('negative', [])) != 3:
        problems.append(f'{label} review needs exactly 5 positive and 3 negative test cases')
    for case in cases.get('positive', []):
        if not all(case.get(k) for k in ('description', 'prompt', 'tools_triggered', 'expected_behavior')):
            problems.append(f'{label} positive test case {case.get("description")!r} is incomplete')
    if not codex.get('extensions', {}).get('com.openai', {}).get('publication', {}).get('release_notes'):
        problems.append(f'{label} needs extensions.com.openai.publication.release_notes')
    return problems


def check():
    problems = []

    if not (PLUGIN_SKILL / 'SKILL.md').is_file():
        problems.append('plugin/skills/pline-ai/SKILL.md is missing')
    else:
        ours, theirs = frontmatter(PLUGIN_SKILL / 'SKILL.md'), frontmatter(SKILL / 'SKILL.md')
        for key in ('name', 'description'):
            if ours.get(key) != theirs.get(key):
                problems.append(f'plugin skill {key} differs from skills/pline-ai: {ours.get(key)!r} != {theirs.get(key)!r}')
    for rel in ('agents/openai.yaml',):
        if (PLUGIN_SKILL / rel).read_bytes() != (SKILL / rel).read_bytes():
            problems.append(f'plugin/skills/pline-ai/{rel} differs from skills/pline-ai/{rel}')

    for path in sorted(PLUGIN.rglob('*')):
        if not path.is_file() or path.suffix in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
            continue
        rel = path.relative_to(ROOT)
        if path.suffix in EXECUTABLE_SUFFIXES:
            problems.append(f'{rel}: the plugin must not bundle scripts; it uses the hosted MCP server')
        # README included: the scanner reads prose too ("API key" next to the API host was held).
        hit = FORBIDDEN.search(path.read_text(encoding='utf-8', errors='replace'))
        if hit:
            problems.append(f'{rel}: mentions {hit.group(0)!r}; the plugin must not read a local credential')

    manifest = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    servers = manifest.get('mcpServers', {})
    if (len(servers) != 1 or any(s != {'type': 'http', 'url': HOSTED_MCP_URL} for s in servers.values())):
        problems.append(f'plugin.json must declare exactly one http MCP server at {HOSTED_MCP_URL} and nothing else: {servers}')
    # Set explicitly: without them the directory guesses from the README (it once took
    # example.com from an example prompt as the documentation link).
    for key, wanted in LISTING_LINKS.items():
        if manifest.get(key) != wanted:
            problems.append(f'plugin.json {key} must be {wanted}, found {manifest.get(key)!r}')
    if 'userConfig' in manifest:
        problems.append('plugin.json must not ask for credentials through userConfig; the server uses OAuth')
    icon = manifest.get('icon')
    if not icon or not (PLUGIN / icon).is_file():
        problems.append(f'plugin.json icon {icon!r} does not exist inside plugin/')
    for name in ('README.md', 'LICENSE'):
        if not (PLUGIN / name).is_file():
            problems.append(f'plugin/{name} is missing')

    marketplace = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
    sources = [entry.get('source') for entry in marketplace.get('plugins', [])]
    if sources != ['./plugin']:
        problems.append(f'.claude-plugin/marketplace.json must list the plugin at ./plugin, found {sources}')

    problems += check_cursor(manifest)
    problems += check_codex(manifest)

    if problems:
        print('Plugin check failed:', file=sys.stderr)
        for problem in problems:
            print(f'  - {problem}', file=sys.stderr)
        return 1
    print(f'Plugin OK (Claude + Cursor + Codex): MCP-only skill, hosted MCP server {HOSTED_MCP_URL}, no local credential reads')
    return 0


if __name__ == '__main__':
    sys.exit(check())
