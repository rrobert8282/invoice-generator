from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app import models

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

# Swap this for a real business name/logo once you have one -- Phase 6 candidate:
# make this per-user/configurable instead of hardcoded.
BUSINESS_NAME = "Your Business Name"


def render_invoice_pdf(invoice: models.Invoice, client: models.Client) -> bytes:
    """Renders an Invoice + its Client into invoice PDF bytes.
    Kept as a standalone function (not inline in the router) so it can be
    unit-tested with a plain model instance, no HTTP layer involved."""
    template = _env.get_template("invoice.html")
    html_content = template.render(
        invoice=invoice,
        client=client,
        business_name=BUSINESS_NAME,
    )
    return HTML(string=html_content).write_pdf()
