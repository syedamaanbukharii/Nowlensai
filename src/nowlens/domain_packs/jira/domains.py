"""Jira domain data.

Curated Jira (and Jira Service Management) capability areas, agile constructs,
and admin/dev features. The ``related`` graph encodes commonly-confused or
overlapping capabilities. Extend as coverage grows.
"""

from __future__ import annotations

from nowlens.domain_packs.base import Domain

JIRA_DOMAINS: dict[str, Domain] = {
    "boards": Domain(
        "boards",
        "Boards",
        "product",
        "Scrum and Kanban boards, columns, swimlanes, and board configuration.",
        aliases=("scrum board", "kanban board", "board", "swimlane", "board configuration"),
        related=("agile", "workflows", "reports"),
    ),
    "agile": Domain(
        "agile",
        "Agile Planning",
        "product",
        "Epics, sprints, backlog, story points, and versions/releases.",
        aliases=("epic", "sprint", "backlog", "story points", "release", "version"),
        related=("boards", "issues", "reports"),
    ),
    "issues": Domain(
        "issues",
        "Issues & Fields",
        "platform",
        "Issue types, fields, screens, screen schemes, and issue configuration.",
        aliases=("issue type", "screen scheme", "field configuration", "sub-task", "linked issue"),
        related=("custom_fields", "workflows", "projects"),
    ),
    "custom_fields": Domain(
        "custom_fields",
        "Custom Fields",
        "platform",
        "Custom fields, field contexts, and field configuration schemes.",
        aliases=("custom field", "field context", "cascading select"),
        related=("issues", "jql"),
    ),
    "workflows": Domain(
        "workflows",
        "Workflows",
        "platform",
        "Statuses, transitions, conditions, validators, post functions, and schemes.",
        aliases=("workflow", "transition", "status", "post function", "workflow scheme"),
        related=("issues", "automation", "permissions"),
    ),
    "jql": Domain(
        "jql",
        "JQL",
        "platform",
        "Jira Query Language for searching issues and building filters.",
        aliases=("jira query language", "jql query", "filter", "saved filter"),
        related=("dashboards", "issues"),
    ),
    "automation": Domain(
        "automation",
        "Automation",
        "platform",
        "No-code automation rules: triggers, conditions, and actions.",
        aliases=("automation rule", "automation for jira", "trigger", "smart values"),
        related=("workflows", "rest_api"),
    ),
    "projects": Domain(
        "projects",
        "Projects",
        "platform",
        "Project configuration, project roles, components, and templates.",
        aliases=(
            "project configuration",
            "project role",
            "component",
            "team-managed",
            "company-managed",
        ),
        related=("permissions", "issues"),
    ),
    "permissions": Domain(
        "permissions",
        "Permissions & Security",
        "platform",
        "Permission schemes, issue security, roles, and group membership.",
        aliases=("permission scheme", "issue security", "role", "group", "global permission"),
        related=("projects", "workflows"),
    ),
    "dashboards": Domain(
        "dashboards",
        "Dashboards & Reports",
        "ui",
        "Dashboards, gadgets, and filters built on JQL.",
        aliases=("dashboard", "gadget", "wallboard"),
        related=("jql", "reports"),
    ),
    "reports": Domain(
        "reports",
        "Agile Reports",
        "ui",
        "Velocity, burndown, burnup, cumulative flow, and control charts.",
        aliases=("burndown", "burnup", "velocity chart", "cumulative flow", "control chart"),
        related=("agile", "boards"),
    ),
    "jsm": Domain(
        "jsm",
        "Jira Service Management",
        "product",
        "Requests, queues, SLAs, the customer portal, and approvals.",
        aliases=(
            "jira service management",
            "service desk",
            "sla",
            "request type",
            "customer portal",
        ),
        related=("workflows", "automation"),
    ),
    "rest_api": Domain(
        "rest_api",
        "REST API & Webhooks",
        "platform",
        "Jira Cloud/Server REST APIs, webhooks, and app integrations.",
        aliases=("rest api", "webhook", "api token", "forge", "connect app"),
        related=("automation", "marketplace"),
    ),
    "marketplace": Domain(
        "marketplace",
        "Marketplace Apps",
        "platform",
        "Atlassian Marketplace apps/plugins and app administration.",
        aliases=("marketplace app", "plugin", "add-on", "atlassian marketplace"),
        related=("rest_api",),
    ),
}
