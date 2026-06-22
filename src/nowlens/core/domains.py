"""ServiceNow domain registry.

A small, curated knowledge base of the ServiceNow products / capability areas
the platform reasons about. Agents use this for lightweight domain detection,
metadata tagging during ingestion, and feature-overlap analysis (the
``related`` graph encodes commonly-confused or overlapping capabilities).

This is intentionally hand-maintained data rather than a stub — extend it as
coverage grows.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Domain:
    key: str
    name: str
    category: str
    description: str
    aliases: tuple[str, ...] = ()
    related: tuple[str, ...] = ()


DOMAINS: dict[str, Domain] = {
    "itsm": Domain(
        "itsm",
        "IT Service Management",
        "product",
        "Incident, problem, change, request, and service catalog processes.",
        aliases=("incident management", "change management", "problem management", "service desk"),
        related=("csm", "itom", "cmdb", "flow_designer"),
    ),
    "csm": Domain(
        "csm",
        "Customer Service Management",
        "product",
        "External customer cases, accounts, contacts, and service operations.",
        aliases=("customer service", "case management"),
        related=("itsm", "fsm", "portals"),
    ),
    "hrsd": Domain(
        "hrsd",
        "HR Service Delivery",
        "product",
        "Employee HR cases, lifecycle events, and knowledge.",
        aliases=("hr service delivery", "employee service center"),
        related=("itsm", "workspaces", "portals"),
    ),
    "spm": Domain(
        "spm",
        "Strategic Portfolio Management",
        "product",
        "Project, demand, resource, and portfolio planning (formerly ITBM/PPM).",
        aliases=("itbm", "ppm", "project portfolio management", "demand management"),
        related=("app_engine", "flow_designer"),
    ),
    "cmdb": Domain(
        "cmdb",
        "Configuration Management Database",
        "platform",
        "Configuration items, relationships, CI classes, and the CSDM model.",
        aliases=("configuration management", "csdm", "ci"),
        related=("itom", "itam", "sam", "itsm"),
    ),
    "itom": Domain(
        "itom",
        "IT Operations Management",
        "product",
        "Discovery, service mapping, event management, and health.",
        aliases=("discovery", "service mapping", "event management"),
        related=("cmdb", "itsm"),
    ),
    "itam": Domain(
        "itam",
        "IT Asset Management",
        "product",
        "Hardware and software asset lifecycle and financials.",
        aliases=("asset management", "hardware asset management", "ham"),
        related=("sam", "cmdb"),
    ),
    "sam": Domain(
        "sam",
        "Software Asset Management",
        "product",
        "Software entitlements, license compliance, and reconciliation.",
        aliases=("software asset management", "license management"),
        related=("itam", "cmdb"),
    ),
    "grc": Domain(
        "grc",
        "Governance, Risk & Compliance",
        "product",
        "Policy, risk, audit, and compliance management.",
        aliases=("irm", "integrated risk management", "risk management", "audit"),
        related=("secops",),
    ),
    "secops": Domain(
        "secops",
        "Security Operations",
        "product",
        "Security incident response, vulnerability response, and threat intel.",
        aliases=("security incident response", "vulnerability response", "sir", "vr"),
        related=("grc", "itsm"),
    ),
    "fsm": Domain(
        "fsm",
        "Field Service Management",
        "product",
        "Field work orders, scheduling, dispatch, and parts.",
        aliases=("field service", "work order management"),
        related=("csm", "itsm"),
    ),
    "app_engine": Domain(
        "app_engine",
        "App Engine",
        "platform",
        "Low-code application development on the Now Platform.",
        aliases=("appengine", "now platform app development", "app engine studio"),
        related=("flow_designer", "script_includes", "business_rules", "ui_policies"),
    ),
    "flow_designer": Domain(
        "flow_designer",
        "Flow Designer",
        "platform",
        "No-code/low-code process automation: flows, actions, subflows.",
        aliases=("flow designer", "flows", "subflows"),
        related=("integrationhub", "business_rules", "app_engine"),
    ),
    "integrationhub": Domain(
        "integrationhub",
        "IntegrationHub",
        "platform",
        "Spokes and actions for integrating external systems within flows.",
        aliases=("integration hub", "spokes"),
        related=("flow_designer", "rest_soap"),
    ),
    "script_includes": Domain(
        "script_includes",
        "Script Includes",
        "platform",
        "Reusable server-side script libraries and classes.",
        aliases=("script include", "server script"),
        related=("business_rules", "acls", "app_engine"),
    ),
    "acls": Domain(
        "acls",
        "Access Control Lists",
        "platform",
        "Row/field-level security rules controlling CRUD access.",
        aliases=("acl", "access control", "security rules"),
        related=("business_rules", "script_includes"),
    ),
    "business_rules": Domain(
        "business_rules",
        "Business Rules",
        "platform",
        "Server-side automation triggered on database operations.",
        aliases=("business rule", "before/after rule"),
        related=("script_includes", "client_scripts", "ui_policies", "flow_designer"),
    ),
    "ui_policies": Domain(
        "ui_policies",
        "UI Policies",
        "platform",
        "Declarative form behaviour: mandatory, visible, read-only fields.",
        aliases=("ui policy",),
        related=("client_scripts", "business_rules"),
    ),
    "client_scripts": Domain(
        "client_scripts",
        "Client Scripts",
        "platform",
        "Client-side form scripting (onLoad/onChange/onSubmit).",
        aliases=("client script", "onchange script"),
        related=("ui_policies", "business_rules"),
    ),
    "catalog_items": Domain(
        "catalog_items",
        "Catalog Items",
        "platform",
        "Service catalog item definitions, variables, and workflows.",
        aliases=("catalog item", "record producer", "order guide"),
        related=("flow_designer", "portals", "itsm"),
    ),
    "workspaces": Domain(
        "workspaces",
        "Workspaces",
        "ui",
        "Configurable agent workspaces (UI Builder / Agent Workspace).",
        aliases=("agent workspace", "configurable workspace", "ui builder"),
        related=("portals", "csm", "hrsd"),
    ),
    "portals": Domain(
        "portals",
        "Service Portals",
        "ui",
        "Service Portal pages, widgets, and theming.",
        aliases=("service portal", "portal widget", "employee center"),
        related=("workspaces", "catalog_items"),
    ),
    "rest_soap": Domain(
        "rest_soap",
        "REST / SOAP Integrations",
        "platform",
        "Inbound/outbound REST and SOAP web services and scripted APIs.",
        aliases=("rest api", "soap", "scripted rest", "web service", "integration"),
        related=("integrationhub", "script_includes"),
    ),
}


def all_domain_keys() -> list[str]:
    return list(DOMAINS.keys())


def get_domain(key: str) -> Domain | None:
    return DOMAINS.get(key.lower())


def detect_domains(text: str, *, limit: int = 5) -> list[str]:
    """Heuristically detect the most relevant domains for a piece of text.

    Pure lexical scoring over names + aliases. This is deliberately cheap and
    deterministic; an LLM-based classifier can refine it (see the business
    analysis agent), but this gives every component a dependency-free baseline.
    """

    lowered = f" {text.lower()} "
    scores: dict[str, int] = {}
    for key, domain in DOMAINS.items():
        score = 0
        needles = (domain.name.lower(), key.replace("_", " "), *domain.aliases)
        for needle in needles:
            n = needle.lower()
            if not n:
                continue
            # Word-ish boundary match to avoid spurious substring hits.
            if f" {n} " in lowered or lowered.startswith(f"{n} ") or lowered.endswith(f" {n}"):
                score += 2
            elif n in lowered:
                score += 1
        if score:
            scores[key] = score
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [key for key, _ in ranked[:limit]]


@dataclass
class OverlapResult:
    domain_a: str
    domain_b: str
    related: bool
    shared_neighbours: list[str] = field(default_factory=list)


def analyze_overlap(domain_a: str, domain_b: str) -> OverlapResult:
    """Structural overlap between two domains via the ``related`` graph."""

    a = get_domain(domain_a)
    b = get_domain(domain_b)
    if a is None or b is None:
        raise KeyError("unknown domain in overlap analysis")
    shared = sorted(set(a.related) & set(b.related))
    related = b.key in a.related or a.key in b.related or bool(shared)
    return OverlapResult(a.key, b.key, related, shared)
