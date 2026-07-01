"""Salesforce domain data.

Curated Salesforce clouds, platform capabilities, and developer constructs. The
``related`` graph encodes commonly-confused or overlapping capabilities. Extend
as coverage grows.
"""

from __future__ import annotations

from nowlens.domain_packs.base import Domain

SALESFORCE_DOMAINS: dict[str, Domain] = {
    "sales_cloud": Domain(
        "sales_cloud",
        "Sales Cloud",
        "product",
        "Leads, opportunities, accounts, contacts, pipeline, and forecasting.",
        aliases=("sales cloud", "opportunity", "lead management", "forecasting", "pipeline"),
        related=("service_cloud", "data_model", "reports_dashboards"),
    ),
    "service_cloud": Domain(
        "service_cloud",
        "Service Cloud",
        "product",
        "Cases, knowledge, Omni-Channel routing, CTI, and entitlements.",
        aliases=("service cloud", "case management", "omni-channel", "knowledge base"),
        related=("sales_cloud", "experience_cloud", "data_model"),
    ),
    "experience_cloud": Domain(
        "experience_cloud",
        "Experience Cloud",
        "product",
        "Digital experience sites, communities, and portals (formerly Community Cloud).",
        aliases=("experience cloud", "community cloud", "communities", "digital experience"),
        related=("service_cloud", "lwc"),
    ),
    "apex": Domain(
        "apex",
        "Apex",
        "platform",
        "Server-side Apex classes, governor limits, async (Batch/Queueable/Future).",
        aliases=("apex class", "apex code", "governor limits", "batch apex", "queueable"),
        related=("triggers", "soql_sosl", "integration"),
    ),
    "triggers": Domain(
        "triggers",
        "Apex Triggers",
        "platform",
        "Record-level Apex triggers and trigger handler patterns.",
        aliases=("apex trigger", "trigger handler", "before insert", "after update"),
        related=("apex", "flow", "validation_rules"),
    ),
    "soql_sosl": Domain(
        "soql_sosl",
        "SOQL / SOSL",
        "platform",
        "Salesforce Object Query/Search Language for querying records.",
        aliases=("soql", "sosl", "query", "selective query"),
        related=("apex", "data_model"),
    ),
    "flow": Domain(
        "flow",
        "Flow",
        "platform",
        "Declarative automation: record-triggered, screen, and scheduled flows.",
        aliases=("flow builder", "record-triggered flow", "screen flow", "process builder"),
        related=("triggers", "validation_rules", "approval_process"),
    ),
    "lwc": Domain(
        "lwc",
        "Lightning Web Components",
        "ui",
        "LWC and Aura components, Lightning App Builder, and the Lightning UI.",
        aliases=(
            "lightning web component",
            "lwc",
            "aura",
            "lightning component",
            "lightning app builder",
        ),
        related=("experience_cloud", "apex"),
    ),
    "visualforce": Domain(
        "visualforce",
        "Visualforce",
        "ui",
        "Legacy Visualforce pages and controllers.",
        aliases=("visualforce page", "vf page", "apex controller"),
        related=("apex", "lwc"),
    ),
    "validation_rules": Domain(
        "validation_rules",
        "Validation Rules",
        "platform",
        "Declarative record validation via formula expressions.",
        aliases=("validation rule", "formula field", "error condition"),
        related=("flow", "triggers", "data_model"),
    ),
    "approval_process": Domain(
        "approval_process",
        "Approval Processes",
        "platform",
        "Multi-step record approval workflows.",
        aliases=("approval process", "approval workflow", "approval step"),
        related=("flow", "permissions"),
    ),
    "permissions": Domain(
        "permissions",
        "Profiles & Permissions",
        "platform",
        "Profiles, permission sets, sharing rules, OWD, and field-level security.",
        aliases=(
            "permission set",
            "profile",
            "sharing rule",
            "org-wide defaults",
            "field-level security",
            "owd",
        ),
        related=("data_model", "approval_process"),
    ),
    "data_model": Domain(
        "data_model",
        "Data Model & Schema",
        "platform",
        "Standard/custom objects, fields, relationships, and schema design.",
        aliases=("custom object", "custom field", "relationship", "schema", "record type"),
        related=("soql_sosl", "permissions", "validation_rules"),
    ),
    "integration": Domain(
        "integration",
        "Integration & APIs",
        "platform",
        "REST/SOAP/Bulk APIs, Platform Events, named credentials, and callouts.",
        aliases=(
            "rest api",
            "soap api",
            "bulk api",
            "platform event",
            "named credential",
            "callout",
        ),
        related=("apex", "data_model"),
    ),
    "reports_dashboards": Domain(
        "reports_dashboards",
        "Reports & Dashboards",
        "ui",
        "Report types, dashboards, and analytics on Salesforce data.",
        aliases=("report", "dashboard", "report type", "analytics"),
        related=("sales_cloud", "data_model"),
    ),
    "deployment": Domain(
        "deployment",
        "DevOps & Deployment",
        "platform",
        "Metadata API, change sets, SFDX, scratch orgs, and unlocked packages.",
        aliases=("sfdx", "change set", "metadata api", "scratch org", "unlocked package", "cli"),
        related=("apex", "integration"),
    ),
}
