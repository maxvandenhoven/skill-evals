"""Wire @mlflow/codex into Codex inside the sandbox. Run by the tracing kit.

Two steps, both safe to re-run:

1. Register the notify hook in ~/.codex/config.toml:
       notify = ["mlflow-codex", "notify-hook"]
   It must be a top-level key. The sandbox image's config.toml ends with
   `[mcp_servers...]` tables, and in TOML every key after a `[table]` header
   belongs to that table, so the line is inserted at the TOP of the file.

2. Patch the connector so tool calls become TOOL spans.
   @mlflow/codex 0.4.0 only understands transcript records of type
   `function_call` / `function_call_output`. Newer Codex versions record tool
   calls as `custom_tool_call` / `custom_tool_call_output` (the freeform
   `exec` tool). Without this patch those calls are dropped silently, and with
   them every `cat .../SKILL.md`, the very signal a skill eval needs.
   The patch rewrites custom records into function-call records as the
   transcript is read. The `mlflow-codex` binary runs bundle/cli.js (not
   dist/), so that is the file patched.

Runs with the sandbox image's python3 and the standard library only.
"""

import pathlib
import subprocess

CONFIG = pathlib.Path.home() / ".codex" / "config.toml"
HOOK = (
    "# MLflow tracing: upload a trace after every turn (added by the tracing kit)\n"
    'notify = ["mlflow-codex", "notify-hook"]\n\n'
)

# The connector's transcript parser in @mlflow/codex 0.4.0's bundle/cli.js, and its
# replacement: the same line plus a normalising step. MARKER makes re-runs a no-op.
MARKER = "/* patched: custom_tool_call */"
ORIGINAL = (
    'return content.split("\\n").filter((line) => line.trim())'
    ".map((line) => JSON.parse(line));\n}"
)
PATCHED = (
    'return content.split("\\n").filter((line) => line.trim())'
    ".map((line) => JSON.parse(line))"
    ".map(normalizeCustomToolCall);\n}\n"
    + MARKER
    + """
function normalizeCustomToolCall(record) {
    const p = record.payload;
    if (record.type !== 'response_item' || !p) return record;
    if (p.type === 'custom_tool_call') {
        return { ...record, payload: { ...p, type: 'function_call',
            arguments: JSON.stringify({ input: p.input ?? '' }) } };
    }
    if (p.type === 'custom_tool_call_output') {
        return { ...record, payload: { ...p, type: 'function_call_output' } };
    }
    return record;
}"""
)


def add_notify_hook(config: pathlib.Path) -> bool:
    """Register the MLflow notify hook at the top of Codex's config.

    Args:
        config: Path to Codex's config.toml; created if missing.

    Returns:
        True if the hook was added, False if a `notify` key already existed.
    """
    config.parent.mkdir(parents=True, exist_ok=True)
    text = config.read_text() if config.exists() else ""
    if any(line.strip().startswith("notify") for line in text.splitlines()):
        return False
    config.write_text(HOOK + text)
    return True


def connector_bundle() -> pathlib.Path:
    """Locate the JavaScript bundle that the `mlflow-codex` binary runs.

    Returns:
        The path of @mlflow/codex's bundle/cli.js in npm's global modules.
    """
    npm_root = subprocess.run(
        ["npm", "root", "-g"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return pathlib.Path(npm_root) / "@mlflow" / "codex" / "bundle" / "cli.js"


def patch_connector(bundle: pathlib.Path) -> bool:
    """Make the connector turn `custom_tool_call` records into TOOL spans.

    Args:
        bundle: The connector's bundle/cli.js.

    Returns:
        True if the bundle was patched now, False if it was already patched.

    Raises:
        SystemExit: If the bundle doesn't contain the expected parser line, e.g.
            after an @mlflow/codex upgrade. Failing loudly beats a silent no-op,
            which would bring back the missing tool spans.
    """
    src = bundle.read_text()
    if MARKER in src:
        return False
    if ORIGINAL not in src:
        msg = f"unexpected layout in {bundle}; was @mlflow/codex upgraded?"
        raise SystemExit(msg)
    bundle.write_text(src.replace(ORIGINAL, PATCHED, 1))
    return True


def main() -> None:
    """Run both setup steps and report what changed."""
    if add_notify_hook(CONFIG):
        print(f"added notify hook to {CONFIG}")
    bundle = connector_bundle()
    print(f"{'patched' if patch_connector(bundle) else 'already patched'}: {bundle}")


if __name__ == "__main__":
    main()
