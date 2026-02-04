"""Company profile module for dynamic target context."""

from .profile import (
    CompanyContext,
    CompanyProfileResult,
    load_default_context,
    generate_company_profile,
)

__all__ = [
    "CompanyContext",
    "CompanyProfileResult",
    "load_default_context",
    "generate_company_profile",
]
