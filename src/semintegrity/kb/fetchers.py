"""The one generic corroboration fetcher (ADR-0019 §6, §9).

**One class, no provider-specific adapters, no credentials.** Every provider
approved in ``corroboration_policy.yaml`` was verified to serve its artefact to
an honest plain unauthenticated GET, which is the only thing this module does.

The hard-won part is not the retrieval; it is refusing the responses that *look*
like retrievals. Three findings from the 158-probe feasibility study are encoded
here:

1. **HTTP 200 is not evidence of retrieval.** Seven hosts returned ``200`` with
   a bot-challenge body or an empty JavaScript shell. A status-code check would
   have frozen an interstitial as §4.3 evidence.
2. **``content_hash`` is not a re-retrieval identifier for every source.** 12 of
   41 probed artefacts returned different bytes on a second GET, some from a
   per-response nonce at identical byte length. So suitability is established by
   fetching **twice** and comparing, not by fetching once and hoping.
3. **Index endpoints are not artefacts.** A search endpoint is a legitimate
   discovery tool and an illegitimate piece of evidence.

This module never attempts to pass, solve or work around a challenge. A
challenged host is reported unusable and that is the end of it: the policy's
approved providers do not need one.
"""

from __future__ import annotations

import base64
import datetime as dt
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..utils.logging import get_logger
from .corroboration import (
    CorroboratingSourceFetcher,
    CorroborationArtifact,
    CorroborationError,
    CorroborationPolicy,
    PolicyNotConfigured,
)

log = get_logger(__name__)

#: Identifies this project, as every provider's etiquette requires. Honest by
#: design: it never imitates a browser in order to get past a bot check.
USER_AGENT = (
    "SemIntegrity/0.1 (academic research; BITS Pilani M.E. dissertation) python-requests"
)

#: Response headers that mean a bot-mitigation challenge was served.
CHALLENGE_HEADERS = ("x-amzn-waf-action",)

#: Body markers of a challenge interstitial, as observed in the probe study.
CHALLENGE_BODY_MARKERS = (
    "_cf_chl_opt",
    "enable javascript and cookies",
    "cf-browser-verification",
    "attention required!",
    "checking if the site connection is secure",
)

#: URL shapes that identify a search or index endpoint rather than a document.
INDEX_PATH_MARKERS = ("/search", "/api/search", "/citations/search", "/query")
INDEX_QUERY_KEYS = ("q", "query", "search", "list-type", "searchquery", "sps.searchquery")

#: Markers of an HTML response, for the content-aware shell test. Deliberately
#: not provider-specific: it is a property of the representation, not the source.
HTML_MEDIA_MARKERS = ("text/html", "application/xhtml")

#: Content types stored as text; anything else is stored as base64 bytes.
TEXT_MEDIA_PREFIXES = ("text/", "application/json", "application/xml", "application/ld+json")
TEXT_MEDIA_SUFFIXES = ("+json", "+xml")


class UnsuitableArtifact(CorroborationError):
    """The response arrived but must not be frozen as §4.3 evidence.

    Distinct from a transport failure: the server answered, and the answer is
    not a usable authoritative artefact.
    """


def looks_like_index_endpoint(url: str) -> str | None:
    """Why this URL is a search/index endpoint rather than a document, or None."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for marker in INDEX_PATH_MARKERS:
        if path.endswith(marker) or f"{marker}/" in path or path == marker:
            return f"path {parsed.path!r} is a search endpoint"
    keys = {k.lower() for k in parse_qs(parsed.query)}
    hit = keys & set(INDEX_QUERY_KEYS)
    if hit:
        return f"query parameter(s) {sorted(hit)} make this a search endpoint"
    return None


def visible_text(html: str) -> str:
    """The readable text of an HTML document, scripts and markup removed.

    Crude on purpose. The question is not "what does this page say" but "does
    this page say anything at all": a JavaScript shell and a bot-challenge page
    both carry almost no text once their scripts are stripped, while any real
    document carries thousands of characters. Measured on the artefacts in the
    feasibility study, a Cloudflare interstitial yields 16 characters and the
    smallest genuine document yields about 5,000, so the two classes are not
    close together.
    """
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def assess_response(
    status: int,
    headers: dict[str, str],
    body: bytes,
    *,
    min_document_bytes: int = 512,
    min_html_text_chars: int = 400,
) -> str | None:
    """Why this response is not a usable artefact, or None if it is.

    Order matters: a challenge is reported as a challenge even when it arrives
    with a success status, because that is exactly how they arrive.
    """
    lower_headers = {k.lower(): v for k, v in headers.items()}
    for name in CHALLENGE_HEADERS:
        if name in lower_headers:
            return (
                f"bot-mitigation challenge: header {name}={lower_headers[name]!r}. "
                "Not to be worked around"
            )
    if status == 202 and not body:
        return (
            "HTTP 202 with an empty body: a deferred bot-mitigation challenge, "
            "not a document"
        )
    if status != 200:
        return f"HTTP {status} is not a successful retrieval"
    text = body[:200_000].decode("utf-8", "replace").lower()
    for marker in CHALLENGE_BODY_MARKERS:
        if marker in text:
            return (
                f"the body is a challenge interstitial (matched {marker!r}) served "
                "with HTTP 200; fetchability is not retrieval"
            )
    if not body:
        return "empty body"
    media = lower_headers.get("content-type", "")
    is_html = any(m in media for m in HTML_MEDIA_MARKERS) or not media
    if len(body) < min_document_bytes and is_html:
        return (
            f"only {len(body)} bytes of {media or 'untyped'} content, below the "
            f"{min_document_bytes}-byte document threshold: a JavaScript shell or "
            "placeholder rather than a document"
        )
    # Byte size alone does not separate a document from a script that would go
    # and fetch one: a 1,039-byte shell cleared the byte threshold and was caught
    # only by a human. So an HTML response must also carry readable text. The
    # test is on the REPRESENTATION, never on the provider, and PDF, XML, JSON
    # and plain text do not reach it.
    if is_html:
        readable = visible_text(body.decode("utf-8", "replace"))
        if len(readable) < min_html_text_chars:
            return (
                f"{len(body)} bytes of {media or 'untyped'} content but only "
                f"{len(readable)} characters of readable text, below the "
                f"{min_html_text_chars}-character threshold: markup and script "
                "without a document. Byte size alone does not make an artefact"
            )
    return None


def _declared_charset(content_type: str) -> str | None:
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    return m.group(1).lower() if m else None


def _is_text_media(content_type: str, body: bytes) -> bool:
    media = (content_type or "").split(";")[0].strip().lower()
    if body[:5] == b"%PDF-":
        return False
    if any(media.startswith(p) for p in TEXT_MEDIA_PREFIXES):
        return True
    return any(media.endswith(s) for s in TEXT_MEDIA_SUFFIXES)


class HttpDocumentFetcher(CorroboratingSourceFetcher):
    """Retrieves one document by plain GET and freezes it, or refuses.

    Parameters
    ----------
    provider:
        The approved provider id this retrieval is attributed to. Checked
        against the policy up front, so an unapproved provider cannot even be
        fetched for.
    accept:
        An optional ``Accept`` header. The only provider-shaped knob in the
        whole implementation, and it exists because content negotiation is how
        ``doi.org`` yields a small deterministic record instead of a publisher's
        marketing page. It is **not** a provider-specific adapter.
    """

    def __init__(
        self,
        provider: str,
        accept: str | None = None,
        *,
        policy: CorroborationPolicy | None = None,
        min_interval_s: float = 1.0,
        timeout: int = 60,
    ) -> None:
        self.provider = provider.strip().lower()
        self.accept = accept
        self.policy = policy or CorroborationPolicy()
        self.min_interval_s = min_interval_s
        self.timeout = timeout
        self._last_request = 0.0

    # -- policy reads --------------------------------------------------------
    @property
    def _suitability(self) -> dict[str, Any]:
        cfg = self.policy.cfg.get("frozen_artifact_suitability") or {}
        return cfg if isinstance(cfg, dict) else {}

    def _flag(self, key: str, default: bool = True) -> bool:
        return bool(self._suitability.get(key, default))

    def _limit(self, key: str, default: int) -> int:
        value = self._suitability.get(key, default)
        return int(value) if isinstance(value, int) else default

    # -- transport -----------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_request = time.monotonic()

    def _get(self, url: str) -> tuple[int, dict[str, str], bytes, str]:
        try:
            import requests  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - environment
            raise CorroborationError("requests is required for live retrieval") from exc
        headers = {"User-Agent": USER_AGENT}
        if self.accept:
            headers["Accept"] = self.accept
        self._throttle()
        resp = requests.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
        try:
            return resp.status_code, dict(resp.headers), resp.content, resp.url
        finally:
            resp.close()

    # -- the one public entry point -----------------------------------------
    def fetch(self, url: str, fact: str) -> CorroborationArtifact:
        """Retrieve ``url`` as a frozen-evidence artefact, or refuse.

        Raises :class:`UnsuitableArtifact` for anything that is fetchable but not
        suitable, and :class:`PolicyNotConfigured` when the provider is not
        approved — the fetcher does not decide policy, it obeys it.
        """
        log.debug("retrieving %s from %s for fact %r", url, self.provider, fact)
        if not self.policy.configured:
            raise PolicyNotConfigured(self.policy.describe())
        if self.provider not in self.policy.approved_providers:
            raise PolicyNotConfigured(
                f"provider {self.provider!r} is not in the approved independent "
                f"source list {list(self.policy.approved_providers)}"
            )
        if self._flag("require_document_not_index"):
            why = looks_like_index_endpoint(url)
            if why is not None:
                raise UnsuitableArtifact(
                    f"{url} is a discovery endpoint, not an authoritative document: "
                    f"{why}. Use it to find the document, never as the evidence"
                )

        status, headers, body, final_url = self._get(url)
        if self._flag("reject_challenge_or_shell_bodies"):
            why = assess_response(
                status, headers, body,
                min_document_bytes=self._limit("min_document_bytes", 512),
                min_html_text_chars=self._limit("min_html_text_chars", 400),
            )
            if why is not None:
                raise UnsuitableArtifact(f"{url}: {why}")

        if self._flag("require_hash_stability"):
            status2, _h2, body2, _u2 = self._get(url)
            if status2 != status or body2 != body:
                raise UnsuitableArtifact(
                    f"{url} is not hash-stable: two retrievals returned "
                    f"{len(body)} and {len(body2)} bytes with different content. "
                    "A nonce-bearing or live page cannot be a frozen artefact"
                )

        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        charset = _declared_charset(content_type)
        if _is_text_media(content_type, body):
            content = body.decode(charset or "utf-8", "replace")
            encoding = charset or "utf-8"
        else:
            content = base64.b64encode(body).decode("ascii")
            encoding = "base64"
        limit = self._limit("max_artifact_bytes", 26_214_400)
        if len(content.encode("utf-8")) > limit:
            raise UnsuitableArtifact(
                f"{url}: stored artefact would be {len(content)} characters, over the "
                f"{limit}-byte limit. Choose a smaller authoritative granule"
            )
        return CorroborationArtifact(
            provider=self.provider,
            url=url,
            retrieved=dt.date.today(),
            content=content,
            media_type=content_type.split(";")[0].strip() or "application/octet-stream",
            final_url=final_url,
            charset=encoding,
            http_status=status,
        )


def fetcher_for(provider: str, accept: str | None = None) -> HttpDocumentFetcher:
    """The fetcher for an approved provider. There is only one implementation."""
    return HttpDocumentFetcher(provider, accept)
