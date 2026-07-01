# Domain Packs

A **Domain Pack** makes platform support pluggable. Each enterprise ecosystem —
ServiceNow, Salesforce, Jira, and future platforms (SAP, Workday, Dynamics,
GitHub, …) — is a self-contained pack that the core discovers at runtime. **The
core owns no platform data and never imports a pack by name**, so adding a
platform is a plugin, not a rewrite.

## Concepts

| Piece | Where | Responsibility |
|---|---|---|
| `DomainPack` (contract) | `nowlens.domain_packs.base` | What a pack provides: `key`, `name`, `signals`, `domains()`, a `detect()` heuristic |
| `Domain` | `nowlens.domain_packs.base` | One module / capability area (key, name, category, description, aliases, `related` edges) |
| `PlatformSignal` | `nowlens.domain_packs.base` | A detection result: `platform`, `confidence` (0–1), `matched` evidence |
| `DomainPackRegistry` | `nowlens.domain_packs.registry` | Discovers + holds packs; `detect()` returns the best signal |
| Discovery | entry-point group `nowlens.domain_packs` | How packs are found (see below) |
| Detection | `nowlens.agents.detect` | Resolves platform → module → role and routes the graph |

The bundled packs live under `src/nowlens/domain_packs/{servicenow,salesforce,jira}`
and are registered in this repo's `pyproject.toml`; third-party packs ship as
their own installable distributions.

## How discovery works

The registry loads every distribution that advertises the `nowlens.domain_packs`
entry-point group:

```toml
# pyproject.toml of the pack's distribution
[project.entry-points."nowlens.domain_packs"]
myplatform = "my_pkg.pack:MyPlatformPack"
```

At runtime, `get_registry()` calls `importlib.metadata.entry_points(group=...)`,
loads each entry-point's `DomainPack` subclass, and registers an instance. An
optional allow-list (`NOWLENS_PACKS__ENABLED=servicenow,jira`) restricts which
packs load; a pack that fails to import is logged and skipped, never crashing
startup. `NOWLENS_PACKS__DEFAULT` (default `servicenow`) is the platform used
when detection is inconclusive.

> Entry-points are read from **installed** package metadata. After editing
> `pyproject.toml`, reinstall (`pip install -e .`) so the new pack is discovered.

## Detection

The agent graph's `detect` node (`nowlens.agents.detect`) runs three
deterministic, offline heuristics before routing:

1. **Platform** — `registry.detect()` scores every pack's `detect()` and takes
   the highest. Detection only switches away from the default platform when the
   signal is **strong** (`MIN_PLATFORM_CONFIDENCE`, ~one platform-specific term);
   a lone shared alias (e.g. "service desk", used by both ServiceNow ITSM and
   Jira JSM) will not mis-route.
2. **Module** — domains scored within the *detected* platform's catalogue.
3. **Role** — developer / administrator / business analyst / architect / project
   manager / consultant / support engineer, inferred from query vocabulary.

Results are surfaced on the chat response (`platform`, `role`) and in the
`detection` trace. Users never select a platform.

## Authoring a pack

Minimal pack:

```python
from collections.abc import Mapping
from nowlens.domain_packs.base import Domain, DomainPack

_DOMAINS = {
    "boards": Domain(
        "boards", "Boards", "product",
        "Scrum and Kanban boards.",
        aliases=("scrum board", "kanban board"),
        related=("agile",),
    ),
    # ...
}

class MyPlatformPack(DomainPack):
    key = "myplatform"                 # matches the entry-point name
    name = "My Platform"
    signals = ("myplatform", "distinctive-term")   # STRONG, platform-specific

    def domains(self) -> Mapping[str, Domain]:
        return _DOMAINS
```

Then register the entry-point (above) and reinstall. That is the entire
integration — no core, agent, or API change.

### Guidelines

- **`signals` must be distinctive.** Use platform-specific terms (`apex`, `jql`,
  `glide`) so detection is confident; avoid generic vocabulary (`workflow`,
  `sprint`) that collides across platforms — put those in domain `aliases`
  instead, which score weakly.
- **`key` is stable and matches the entry-point name.** It is what
  `NOWLENS_PACKS__DEFAULT` / `ENABLED` and detection use.
- **Override `detect()`** only if the default alias/signal heuristic is
  insufficient; return a `PlatformSignal` with a calibrated confidence.
- **`related` edges** power feature-overlap analysis between modules.

## Testing a pack

Ship the pack with tests that assert discovery, detection, and module scoping —
mirror `tests/test_salesforce_pack.py` / `tests/test_jira_pack.py`:

```python
def test_pack_discovered():
    from nowlens.domain_packs import get_registry
    assert get_registry().get("myplatform") is not None

def test_detection_resolves_platform():
    from nowlens.agents.detect import detect_platform
    assert detect_platform("a distinctive-term question").platform == "myplatform"
```

## Roadmap

Shipped: **ServiceNow, Salesforce, Jira**. Planned: SAP, Workday, Microsoft
Dynamics, Azure, AWS, Google Cloud, GitHub, and broader Atlassian — each a pack,
none requiring a core change.
