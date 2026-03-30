import json
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from src.services.template_search import TemplateSearchService

router = APIRouter()
_service: Optional[TemplateSearchService] = None

DOMAIN_LUMIN_PDF = "luminpdf.com"
DEFAULT_SORT = ["outdated:asc", "totalUsed:desc", "publishedDateTimestamp:desc", "title:asc"]

# Sorts that don't exist in our index (geo / computed fields from lumin-templates)
_UNSUPPORTED_SORTS = {"relevantLocation:desc", "relevantLocation:asc", "domainIndex:asc", "domainIndex:desc"}


def get_service() -> TemplateSearchService:
    global _service
    if _service is None:
        _service = TemplateSearchService()
    return _service


def parse_json_param(value: Optional[str], default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def build_filter_expression(filters: dict, extra: list[str] | None = None) -> Optional[str]:
    """Convert a webopt filters dict { formTypes, countries, states } to a Meilisearch filter string."""
    parts = []

    form_types = filters.get("formTypes") or []
    if form_types:
        ft_expr = " OR ".join(f"categories.slug = '{ft}'" for ft in form_types)
        parts.append(f"({ft_expr})")

    countries = filters.get("countries") or []
    if countries:
        c_expr = " OR ".join(f"countryCode = '{c}'" for c in countries)
        parts.append(f"({c_expr})")

    states = filters.get("states") or []
    if states:
        s_expr = " OR ".join(f"stateCode = '{s}'" for s in states)
        parts.append(f"({s_expr})")

    domain = filters.get("domain")
    if domain:
        parts.append(f"domain = '{domain}'")

    if extra:
        parts.extend(extra)

    return " AND ".join(parts) if parts else None


def sanitize_sort(sort: list[str]) -> list[str]:
    """Drop sort params that don't exist in our index."""
    return [s for s in sort if s not in _UNSUPPORTED_SORTS]


@router.get("/templates/new-in-lumin")
async def get_new_in_lumin(
    cursor: int = Query(0),
    limit: int = Query(24, ge=1, le=100),
    skip: int = Query(0),
    filters: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
):
    svc = get_service()
    filters_dict = parse_json_param(filters, {})
    sort_list = sanitize_sort(parse_json_param(sort, DEFAULT_SORT))

    filter_expr = build_filter_expression(
        filters_dict,
        extra=[f"domain = '{DOMAIN_LUMIN_PDF}'"],
    )

    try:
        return svc.search(
            query="",
            filter_expr=filter_expr,
            sort=sort_list,
            offset=cursor + skip,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/most-popular-in-lumin")
async def get_most_popular_in_lumin(
    cursor: int = Query(0),
    limit: int = Query(12, ge=1, le=100),
    filters: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
):
    svc = get_service()
    filters_dict = parse_json_param(filters, {})
    sort_list = sanitize_sort(parse_json_param(sort, DEFAULT_SORT))

    one_year_ago = int((datetime.now() - timedelta(days=365)).timestamp())
    filter_expr = build_filter_expression(
        filters_dict,
        extra=[f"publishedDateTimestamp >= {one_year_ago}"],
    )

    try:
        return svc.search(
            query="",
            filter_expr=filter_expr,
            sort=sort_list,
            offset=cursor,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/search")
async def search_combined(searchText: str = Query(...)):
    """Combined search — returns { results: [...] } matching Meilisearch multi-search shape."""
    svc = get_service()
    try:
        return svc.multi_search(query=searchText, limit=10)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/search/template")
async def search_template(
    searchText: str = Query(...),
    cursor: int = Query(0),
    limit: int = Query(24, ge=1, le=100),
    filters: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
):
    svc = get_service()
    filters_dict = parse_json_param(filters, {})
    # relevantLocation sort doesn't exist; fall back to totalUsed:desc
    sort_raw = sanitize_sort(parse_json_param(sort, ["relevantLocation:desc"]))
    sort_list = sort_raw or ["totalUsed:desc"]

    filter_expr = build_filter_expression(filters_dict)

    try:
        return svc.search(
            query=searchText,
            filter_expr=filter_expr,
            sort=sort_list,
            offset=cursor,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/id/{template_id}")
async def get_template_by_id(template_id: int):
    svc = get_service()
    try:
        doc = svc.get_by_id(template_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"template": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/related")
async def get_related_templates(
    ids: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    relatedFormByDomain: Optional[str] = Query(None),
    attributesToRetrieve: Optional[str] = Query(None),
):
    svc = get_service()
    ids_list = parse_json_param(ids, [])
    sort_list = sanitize_sort(parse_json_param(sort, DEFAULT_SORT))
    domains_list = parse_json_param(relatedFormByDomain, [])

    filter_parts: list[str] = []
    if ids_list:
        ids_expr = " OR ".join(f"id = {id_}" for id_ in ids_list)
        filter_parts.append(f"({ids_expr})")
    if domains_list:
        domain_expr = " OR ".join(f"domain = '{d}'" for d in domains_list)
        filter_parts.append(f"({domain_expr})")

    filter_expr = " OR ".join(filter_parts) if filter_parts else None

    try:
        result = svc.search(
            query="",
            filter_expr=filter_expr,
            sort=sort_list,
            offset=0,
            limit=10,
        )
        return result["hits"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/category/{slug}")
async def get_templates_by_category(
    slug: str,
    limit: int = Query(6, ge=1, le=100),
    sort: Optional[str] = Query(None),
    filters: Optional[str] = Query(None),
):
    svc = get_service()
    filters_dict = parse_json_param(filters, {})
    sort_list = sanitize_sort(parse_json_param(sort, DEFAULT_SORT))

    filter_expr = build_filter_expression(
        filters_dict,
        extra=[f"categories.slug = '{slug}'"],
    )

    try:
        result = svc.search(
            query="",
            filter_expr=filter_expr,
            sort=sort_list,
            offset=0,
            limit=limit,
        )
        return result["hits"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
