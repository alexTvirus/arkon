"""
Wiki REST router — admin/portal access to LLM-compiled wiki pages.

Read-only endpoints for browsing the wiki + a small graph endpoint for
visualizations. Direct edit/contribution flows are deferred to phase 3.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, WikiPage
from app.services import wiki_service
from app.services.auth_service import get_current_user, require_permission

router = APIRouter()


class WikiPageSummary(BaseModel):
    slug: str
    title: str
    page_type: str
    summary: str
    knowledge_type_slugs: list[str]
    source_ids: list[uuid.UUID]
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    version: int
    updated_at: str


class WikiPageDetail(WikiPageSummary):
    content_md: str
    backlinks: list[str]
    outlinks: list[str]


def _summary(p: WikiPage) -> WikiPageSummary:
    return WikiPageSummary(
        slug=p.slug,
        title=p.title,
        page_type=p.page_type,
        summary=p.summary or "",
        knowledge_type_slugs=p.knowledge_type_slugs or [],
        source_ids=list(p.source_ids or []),
        scope_type=p.scope_type or "global",
        scope_id=p.scope_id,
        version=p.version or 1,
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
    )


@router.get("/wiki/pages", response_model=list[WikiPageSummary])
async def list_wiki_pages(
    page_type: Optional[str] = Query(None),
    knowledge_type_slug: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("kb.read"),
):
    pages = await wiki_service.list_pages(
        db,
        page_type=page_type,
        knowledge_type_slug=knowledge_type_slug,
        limit=limit,
        offset=offset,
    )
    return [_summary(p) for p in pages]


@router.get("/wiki/pages/{slug:path}", response_model=WikiPageDetail)
async def get_wiki_page(
    slug: str,
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("kb.read"),
):
    sid = uuid.UUID(scope_id) if scope_id else None
    if scope_type:
        # Explicit scope requested
        page = await wiki_service.get_page_by_slug(db, slug, scope_type=scope_type, scope_id=sid)
    else:
        # No scope specified — try global first, then fallback to any scope
        page = await wiki_service.get_page_by_slug(db, slug, scope_type="global", scope_id=None)
        if not page:
            page = await wiki_service.get_page_by_slug_any_scope(db, slug)
    if not page:
        raise HTTPException(404, f"Wiki page not found: {slug}")
    backlinks = await wiki_service.get_backlinks(db, slug)
    outlinks = await wiki_service.get_outlinks(db, slug)
    base = _summary(page)
    return WikiPageDetail(
        **base.model_dump(),
        content_md=page.content_md or "",
        backlinks=sorted(backlinks),
        outlinks=sorted(outlinks),
    )


@router.get("/wiki/index")
async def get_wiki_index(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("kb.read"),
):
    page = await wiki_service.get_page_by_slug(db, wiki_service.INDEX_SLUG)
    return {"content_md": page.content_md if page else ""}


@router.get("/wiki/log")
async def get_wiki_log(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("kb.read"),
):
    page = await wiki_service.get_page_by_slug(db, wiki_service.LOG_SLUG)
    return {"content_md": page.content_md if page else ""}


@router.delete("/wiki/pages/{slug:path}")
async def delete_wiki_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("kb.delete"),
):
    """Delete a wiki page and cascade-cleanup all references."""
    if slug in (wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG):
        raise HTTPException(400, "Cannot delete reserved pages")

    page = await wiki_service.get_page_by_slug(db, slug)
    if not page:
        raise HTTPException(404, f"Wiki page not found: {slug}")

    # Check admin role (additional safeguard)
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(403, "Only admins can delete wiki pages")

    deleted_title = page.title
    await wiki_service.delete_page_cascade(db, slug)
    await wiki_service.regenerate_index(db)
    await wiki_service.append_log(db, f"Deleted page: {deleted_title} ({slug})")
    await db.commit()
    return {"ok": True, "deleted_slug": slug}


@router.get("/wiki/graph")
async def get_wiki_graph(
    slug: Optional[str] = Query(None, description="Center the graph on this slug; omit for full graph"),
    depth: int = Query(1, ge=1, le=3),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("kb.read"),
):
    """Return nodes/edges for visualization. Supports pagination for large graphs."""
    if slug:
        return await wiki_service.get_neighborhood(db, slug, depth=depth)

    # Full graph — paginated, include scope info for visual classification
    from sqlalchemy import select, outerjoin, func as sqlfunc
    from app.database.models import WikiLink, Project

    base_filter = WikiPage.slug.notin_([wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG])

    # Total count
    total = (await db.execute(
        select(sqlfunc.count()).select_from(WikiPage).where(base_filter)
    )).scalar() or 0

    # Fetch paginated nodes
    stmt = (
        select(
            WikiPage.slug,
            WikiPage.title,
            WikiPage.page_type,
            WikiPage.scope_type,
            WikiPage.scope_id,
            Project.name.label("scope_name"),
        )
        .select_from(
            outerjoin(WikiPage, Project, WikiPage.scope_id == Project.id)
        )
        .where(base_filter)
        .order_by(WikiPage.slug)
        .offset(offset)
        .limit(limit)
    )
    pages = (await db.execute(stmt)).all()
    page_slugs = [r.slug for r in pages]

    # Edges — return ALL on first batch (offset=0), empty on subsequent batches.
    # Edges are lightweight (two strings each), so sending all at once is fine.
    # This ensures cross-batch relationships are preserved during progressive loading.
    if offset == 0:
        edges = (await db.execute(
            select(WikiLink.from_slug, WikiLink.to_slug)
        )).all()
    else:
        edges = []

    return {
        "nodes": [
            {
                "slug": r.slug,
                "title": r.title,
                "page_type": r.page_type,
                "scope_type": r.scope_type or "global",
                "scope_id": str(r.scope_id) if r.scope_id else None,
                "scope_name": r.scope_name,
            }
            for r in pages
        ],
        "edges": [{"from": r.from_slug, "to": r.to_slug} for r in edges],
        "total": total,
        "offset": offset,
        "has_more": offset + limit < total,
    }
