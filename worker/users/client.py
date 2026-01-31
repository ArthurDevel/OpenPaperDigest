import logging
from pydantic import EmailStr
from typing import List, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from papers.db.models import PaperRecord, PaperSlugRecord
from users.models import UserRow, UserListRow, UserRequestRow

logger = logging.getLogger(__name__)

async def sync_new_user(db: Session, auth_provider_id: str, email: EmailStr):
    """
    Ensure a user record exists for the given auth provider id.
    Idempotent: create only if not present.
    """
    logger.info(
        f"Syncing new user in users client. Auth Provider ID: {auth_provider_id}, Email: {email}"
    )
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if user:
        # Optionally update email if changed
        try:
            if user.email != str(email):
                user.email = str(email)
                db.add(user)
                db.commit()
        except Exception:
            logger.exception("Failed to update email for user %s", auth_provider_id)
        return {"status": "ok", "created": False}

    user = UserRow(id=auth_provider_id, email=str(email))
    db.add(user)
    db.commit()
    return {"status": "ok", "created": True}


async def add_list_entry(db: Session, auth_provider_id: str, paper_uuid: str) -> Dict[str, bool]:
    """
    Add a paper to the user's list. Idempotent: returns created=False if already present.
    """
    from sqlalchemy.orm import defer
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    paper = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == paper_uuid).first()
    if not paper:
        raise ValueError("Paper not found")
    existing = (
        db.query(UserListRow)
        .filter(UserListRow.user_id == user.id, UserListRow.paper_id == paper.id)
        .first()
    )
    if existing:
        return {"created": False}
    entry = UserListRow(user_id=user.id, paper_id=paper.id)
    db.add(entry)
    db.commit()
    return {"created": True}


async def remove_list_entry(db: Session, auth_provider_id: str, paper_uuid: str) -> Dict[str, bool]:
    from sqlalchemy.orm import defer
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    paper = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == paper_uuid).first()
    if not paper:
        raise ValueError("Paper not found")
    q = (
        db.query(UserListRow)
        .filter(UserListRow.user_id == user.id, UserListRow.paper_id == paper.id)
    )
    deleted = q.delete()
    db.commit()
    return {"deleted": bool(deleted)}


async def is_entry_present(db: Session, auth_provider_id: str, paper_uuid: str) -> Dict[str, bool]:
    from sqlalchemy.orm import defer
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    paper = db.query(PaperRecord).options(defer(PaperRecord.processed_content)).filter(PaperRecord.paper_uuid == paper_uuid).first()
    if not paper:
        return {"exists": False}
    exists = (
        db.query(UserListRow)
        .filter(UserListRow.user_id == user.id, UserListRow.paper_id == paper.id)
        .first()
        is not None
    )
    return {"exists": exists}


async def list_user_entries(db: Session, auth_provider_id: str) -> List[Dict[str, Any]]:
    """
    Return enriched paper items in the user's list.
    Includes latest non-tombstoned slug when available.
    """
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")

    # Join user_lists -> papers (include list row to expose created_at)
    rows = (
        db.query(PaperRecord, UserListRow)
        .join(UserListRow, UserListRow.paper_id == PaperRecord.id)
        .filter(UserListRow.user_id == user.id)
        .all()
    )

    # Fetch slugs for these papers
    paper_uuid_list = [p.paper_uuid for (p, _ul) in rows]
    slugs_by_uuid: Dict[str, str] = {}
    if paper_uuid_list:
        slug_rows = (
            db.query(PaperSlugRecord)
            .filter(PaperSlugRecord.paper_uuid.in_(paper_uuid_list))
            .filter(PaperSlugRecord.tombstone == False)  # noqa: E712
            .all()
        )
        for r in slug_rows:
            current = slugs_by_uuid.get(r.paper_uuid)
            if current is None:
                slugs_by_uuid[r.paper_uuid] = r.slug

    items: List[Dict[str, Any]] = []
    for (p, ul) in rows:
        items.append(
            {
                "paper_uuid": p.paper_uuid,
                "title": getattr(p, "title", None),
                "authors": getattr(p, "authors", None),
                "thumbnail_data_url": getattr(p, "thumbnail_data_url", None),
                "slug": slugs_by_uuid.get(p.paper_uuid),
                "created_at": (ul.created_at.isoformat() if getattr(ul, "created_at", None) else None),
            }
        )
    return items


async def does_any_user_request_exist(db: Session, arxiv_id_or_url: str) -> Dict[str, bool]:
    """
    Returns whether any user has requested the paper identified by this arXiv id or URL.
    """
    base_id = arXiv_base_id(arxiv_id_or_url)
    exists = (
        db.query(UserRequestRow.id)
        .filter(UserRequestRow.arxiv_id == base_id)
        .first()
        is not None
    )
    return {"exists": exists}


async def does_user_request_exist(db: Session, auth_provider_id: str, arxiv_id_or_url: str) -> Dict[str, bool]:
    """
    Returns whether this user has requested the paper identified by this arXiv id or URL.
    """
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    base_id = arXiv_base_id(arxiv_id_or_url)
    exists = (
        db.query(UserRequestRow.id)
        .filter(UserRequestRow.user_id == user.id, UserRequestRow.arxiv_id == base_id)
        .first()
        is not None
    )
    return {"exists": exists}


async def count_any_user_requests(db: Session, arxiv_id_or_url: str) -> Dict[str, int]:
    """
    Returns how many distinct users have requested the paper (unique by user).
    """
    base_id = arXiv_base_id(arxiv_id_or_url)
    count = (
        db.query(UserRequestRow)
        .filter(UserRequestRow.arxiv_id == base_id)
        .count()
    )
    return {"count": int(count)}


async def add_request_entry(db: Session, auth_provider_id: str, arxiv_id: str) -> Dict[str, bool]:
    """
    Add a user request for an arXiv id. Idempotent: returns created=False if already present.
    """
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    existing = (
        db.query(UserRequestRow)
        .filter(UserRequestRow.user_id == user.id, UserRequestRow.arxiv_id == arxiv_id)
        .first()
    )
    if existing:
        return {"created": False}
    # Try enrich via arXiv metadata
    title: str | None = None
    authors: str | None = None
    try:
        from shared.arxiv.client import fetch_metadata
        # Normalize to base id if version present (e.g., 2507.18071v2 -> 2507.18071)
        base_id = arXiv_base_id(arxiv_id)
        meta = await fetch_metadata(base_id)
        title = getattr(meta, 'title', None)
        # Join author names
        try:
            author_names = [getattr(a, 'name', '') for a in getattr(meta, 'authors', [])]
            authors = ", ".join([n for n in author_names if n]) or None
        except Exception:
            authors = None
        arxiv_id = base_id
    except Exception:
        # Best-effort: still create entry without metadata
        pass
    entry = UserRequestRow(user_id=user.id, arxiv_id=arxiv_id, title=title, authors=authors)
    db.add(entry)
    db.commit()
    return {"created": True}


async def remove_request_entry(db: Session, auth_provider_id: str, arxiv_id: str) -> Dict[str, bool]:
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    q = (
        db.query(UserRequestRow)
        .filter(UserRequestRow.user_id == user.id, UserRequestRow.arxiv_id == arxiv_id)
    )
    deleted = q.delete()
    db.commit()
    return {"deleted": bool(deleted)}


async def does_request_exist(db: Session, auth_provider_id: str, arxiv_id: str) -> Dict[str, bool]:
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    exists = (
        db.query(UserRequestRow)
        .filter(UserRequestRow.user_id == user.id, UserRequestRow.arxiv_id == arxiv_id)
        .first()
        is not None
    )
    return {"exists": exists}


async def list_user_requests(db: Session, auth_provider_id: str) -> List[Dict[str, Any]]:
    user = db.query(UserRow).filter(UserRow.id == auth_provider_id).first()
    if not user:
        raise ValueError("User not found")
    rows = (
        db.query(UserRequestRow)
        .filter(UserRequestRow.user_id == user.id)
        .all()
    )
    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append({
            "arxiv_id": r.arxiv_id,
            "title": getattr(r, 'title', None),
            "authors": getattr(r, 'authors', None),
            "is_processed": bool(getattr(r, 'is_processed', False)),
            "processed_slug": getattr(r, 'processed_slug', None),
            "created_at": (r.created_at.isoformat() if getattr(r, "created_at", None) else None),
        })
    return items


def arXiv_base_id(id_or_url: str) -> str:
    """Extract base arXiv id without version from an id or abs/pdf URL."""
    s = (id_or_url or '').strip()
    # If URL, extract terminal segment
    import re
    m = re.search(r"/(?:abs|pdf)/([^/?#]+)", s)
    if m:
        s = m.group(1)
    # Strip version suffix like v2
    s = re.sub(r"v\d+$", "", s)
    return s


def list_aggregated_user_requests_for_admin(db: Session, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Aggregate user_requests by arxiv_id with counts and timestamps.
    Returns dicts with fields suitable for admin:
    - arxiv_id, title, authors
    - request_count, first_requested_at, last_requested_at
    - arxiv_abs_url, arxiv_pdf_url
    - num_pages (from papers if exists), processed_slug (latest non-tombstoned)
    """
    from papers.db.models import PaperRecord, PaperSlugRecord

    sub = (
        db.query(
            UserRequestRow.arxiv_id.label('arxiv_id'),
            func.count(func.distinct(UserRequestRow.user_id)).label('request_count'),
            func.min(UserRequestRow.created_at).label('first_requested_at'),
            func.max(UserRequestRow.created_at).label('last_requested_at'),
            func.max(UserRequestRow.title).label('title'),
            func.max(UserRequestRow.authors).label('authors'),
            func.max(UserRequestRow.is_processed).label('any_processed'),
        )
        .group_by(UserRequestRow.arxiv_id)
        .subquery()
    )

    # Join to papers and slugs (latest non-tombstoned)
    rows = (
        db.query(
            sub.c.arxiv_id,
            sub.c.request_count,
            sub.c.first_requested_at,
            sub.c.last_requested_at,
            sub.c.title,
            sub.c.authors,
            PaperRecord.num_pages,
            PaperRecord.paper_uuid,
        )
        .outerjoin(PaperRecord, func.binary(PaperRecord.arxiv_id) == func.binary(sub.c.arxiv_id))
        .filter((sub.c.any_processed == 0) | (sub.c.any_processed.is_(None)))
        .order_by(sub.c.last_requested_at.desc())
        .limit(max(1, min(limit, 1000)))
        .offset(max(0, offset))
        .all()
    )

    # Load slugs for the paper_uuids present
    by_uuid: Dict[str, str] = {}
    uuids = [r.paper_uuid for r in rows if getattr(r, 'paper_uuid', None)]
    if uuids:
        slug_rows = (
            db.query(PaperSlugRecord)
            .filter(PaperSlugRecord.paper_uuid.in_(uuids))
            .filter(PaperSlugRecord.tombstone == False)  # noqa: E712
            .all()
        )
        for s in slug_rows:
            if s.paper_uuid and s.paper_uuid not in by_uuid:
                by_uuid[s.paper_uuid] = s.slug

    items: List[Dict[str, Any]] = []
    for r in rows:
        arxiv_id: str = r.arxiv_id
        abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        processed_slug = by_uuid.get(getattr(r, 'paper_uuid', None))
        items.append({
            'arxiv_id': arxiv_id,
            'arxiv_abs_url': abs_url,
            'arxiv_pdf_url': pdf_url,
            'request_count': int(getattr(r, 'request_count') or 0),
            'first_requested_at': getattr(r, 'first_requested_at'),
            'last_requested_at': getattr(r, 'last_requested_at'),
            'title': getattr(r, 'title', None),
            'authors': getattr(r, 'authors', None),
            'num_pages': getattr(r, 'num_pages', None),
            'processed_slug': processed_slug,
        })
    return items


def delete_all_requests_for_arxiv(db: Session, arxiv_id_or_url: str) -> Dict[str, int]:
    """
    Delete all per-user user_requests rows for the given arXiv id/URL (normalized).
    Returns {"deleted": N}.
    """
    base_id = arXiv_base_id(arxiv_id_or_url)
    q = db.query(UserRequestRow).filter(UserRequestRow.arxiv_id == base_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": int(deleted or 0)}


async def set_requests_processed(db: Session, arxiv_id: str, processed_slug: str) -> Dict[str, int]:
    """
    Mark all user requests for this base arXiv id as processed and set processed_slug.
    Requires a non-empty slug; will raise if slug is falsy per product decision.
    Returns {"updated": N}.
    """
    if not processed_slug or not isinstance(processed_slug, str):
        raise ValueError("processed_slug is required")
    base_id = arXiv_base_id(arxiv_id)
    q = db.query(UserRequestRow).filter(UserRequestRow.arxiv_id == base_id)
    updated = 0
    for r in q.all():
        try:
            r.is_processed = True
            r.processed_slug = processed_slug
            db.add(r)
            updated += 1
        except Exception:
            logger.exception("Failed to mark user request processed user_id=%s arxiv_id=%s", getattr(r, 'user_id', None), base_id)
    db.commit()
    return {"updated": updated}
