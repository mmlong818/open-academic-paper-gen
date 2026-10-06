import difflib
import logging
import urllib.parse

import httpx

from backend.literature.searchers.crossref import _parse_year
from backend.verification.cross_source import found_elsewhere, needs_lookup
from backend.verification.metadata_match import (
    author_issues,
    doi_format_issue,
    future_year_issue,
    pages_issue,
    retraction_issues,
    year_issue,
)
from backend.verification.schemas import CitationStatus, VerificationResult

logger = logging.getLogger(__name__)

_CROSSREF_BASE = "https://api.crossref.org/works"
_HANDLE_BASE = "https://doi.org/api/handles"
_TIMEOUT = 15.0
_TITLE_MATCH_THRESHOLD = 0.85


def _title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _with_issues(result: VerificationResult, issues: list[str]) -> VerificationResult:
    """Add field-level issues to a result; any of them makes a passing result a warning."""
    if not issues:
        return result
    status = CitationStatus.WARNED if result.status == CitationStatus.PASSED else result.status
    return result.model_copy(update={"status": status, "layer1_ok": False, "issues": [*result.issues, *issues]})


class ExistenceChecker:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def check(
        self,
        title: str,
        authors: list[str],
        doi: str | None,
        year: int | None = None,
        pages: str = "",
        source: str = "",
    ) -> VerificationResult:
        sanity = future_year_issue(year) + doi_format_issue(doi)
        if doi and not doi_format_issue(doi):
            result = await self._check_doi(title, doi, authors, year, pages)
        else:
            result = VerificationResult(title=title, doi=doi, layer1_ok=True)
        if needs_lookup(source, doi) and await found_elsewhere(await self._get_client(), title, authors, source) is False:
            sanity.append(f"Found in one database only ({source}) and has no DOI: check it by hand")
        return _with_issues(result, sanity)

    async def _check_doi(
        self, title: str, doi: str, authors: list[str] | None = None, year: int | None = None, pages: str = "",
    ) -> VerificationResult:
        encoded = urllib.parse.quote(doi, safe="")
        url = f"{_CROSSREF_BASE}/{encoded}"
        try:
            client = await self._get_client()
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("[crossref] doi=%s network error: %s", doi, exc)
            return VerificationResult(title=title, doi=doi, layer1_ok=True)

        if resp.status_code == 404:
            # CrossRef only knows its own DOIs; arXiv (DataCite) and others 404 there
            # although they resolve. Only a DOI unknown to doi.org itself is fabricated.
            if await self._handle_exists(doi) is not False:
                return VerificationResult(title=title, doi=doi, layer1_ok=True)
            return VerificationResult(
                title=title,
                doi=doi,
                status=CitationStatus.REMOVED,
                layer1_ok=False,
                issues=["DOI does not resolve (CrossRef 404, unknown to doi.org)"],
            )

        if resp.status_code != 200:
            # 限速 (429) 或服务错误 — 视为暂时不可验证，不扣分
            logger.warning("[crossref] doi=%s status=%d — accepting unverified", doi, resp.status_code)
            return VerificationResult(title=title, doi=doi, layer1_ok=True)

        data = resp.json().get("message", {})
        cr_titles: list[str] = data.get("title", [])
        if cr_titles:
            best_ratio = max(_title_similarity(title, t) for t in cr_titles)
            if best_ratio < _TITLE_MATCH_THRESHOLD:
                return VerificationResult(
                    title=title,
                    doi=doi,
                    status=CitationStatus.WARNED,
                    layer1_ok=False,
                    issues=[
                        f"Title mismatch with CrossRef record "
                        f"(similarity={best_ratio:.2f} < {_TITLE_MATCH_THRESHOLD})"
                    ],
                )

        # the title matches: do the authors, year and pages describe the same paper?
        fields = (retraction_issues(data)
                  + author_issues(authors or [], data.get("author") or [])
                  + year_issue(year, _parse_year(data))
                  + pages_issue(pages, str(data.get("page") or "")))
        return _with_issues(VerificationResult(title=title, doi=doi, layer1_ok=True), fields)

    async def _handle_exists(self, doi: str) -> bool | None:
        """Ask the DOI handle system, registrar-agnostic. None means it could not say."""
        url = f"{_HANDLE_BASE}/{urllib.parse.quote(doi, safe='/')}"
        try:
            client = await self._get_client()
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("[doi.org] doi=%s network error: %s", doi, exc)
            return None
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        logger.warning("[doi.org] doi=%s status=%d — accepting unverified", doi, resp.status_code)
        return None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
