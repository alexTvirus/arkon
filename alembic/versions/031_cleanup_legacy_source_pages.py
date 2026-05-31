"""cleanup_legacy_source_pages

Revision ID: 031
Revises: 120ffbbffa7c
Create Date: 2026-05-31 21:22:00.000000
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers
revision: str = '031'
down_revision: Union[str, None] = '120ffbbffa7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQL commands to delete legacy 'source/' wiki pages, drafts, and revisions
    op.execute("DELETE FROM wiki_page_revisions WHERE slug LIKE 'source/%'")
    op.execute("DELETE FROM wiki_page_drafts WHERE page_slug LIKE 'source/%'")
    op.execute("DELETE FROM wiki_pages WHERE slug LIKE 'source/%'")


def downgrade() -> None:
    pass
