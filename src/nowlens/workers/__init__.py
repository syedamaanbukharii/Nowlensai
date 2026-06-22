"""Background workers.

The in-process entry point :func:`run_ingestion_job` is always available; the
arq-based out-of-process worker lives in :mod:`nowlens.workers.arq_worker` and
is only loaded when the optional ``arq`` dependency is present.
"""

from nowlens.workers.tasks import run_ingestion_job

__all__ = ["run_ingestion_job"]
