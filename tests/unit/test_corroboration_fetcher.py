"""The one generic corroboration fetcher (ADR-0019 §6).

These tests encode what the 158-request feasibility study found the hard way:
**a successful HTTP status is not evidence that anything was retrieved.** Seven
hosts answered 200 with a bot-challenge body or an empty JavaScript shell, and
12 of 41 artefacts returned different bytes on a second GET. A fetcher that
trusted the status code would have frozen interstitials as §4.3 evidence.

No test here touches the network: the transport is substituted, because what is
under test is the *refusal* logic, not `requests`.
"""

from __future__ import annotations

import base64

import pytest

from semintegrity.kb.corroboration import CorroborationPolicy, PolicyNotConfigured
from semintegrity.kb.fetchers import (
    HttpDocumentFetcher,
    UnsuitableArtifact,
    assess_response,
    looks_like_index_endpoint,
)

DOC = "<html><body>" + ("An authoritative document. " * 60) + "</body></html>"
URL = "https://treaties.un.org/doc/Publication/MTDSG/x.en.xml"


def _fetcher(provider: str = "un-treaties", responses=None, **kw) -> HttpDocumentFetcher:
    """A fetcher whose transport replays a scripted list of responses."""
    f = HttpDocumentFetcher(provider, min_interval_s=0.0, **kw)
    if responses is not None:
        queue = list(responses)
        f._get = lambda url: queue.pop(0) if len(queue) > 1 else queue[0]  # type: ignore[method-assign]
    return f


def _ok(body: str | bytes = DOC, ctype: str = "text/html; charset=utf-8", status: int = 200,
        final: str = URL):
    raw = body.encode("utf-8") if isinstance(body, str) else body
    return (status, {"Content-Type": ctype}, raw, final)


# --- the policy decides who may be fetched for ----------------------------
def test_an_unapproved_provider_cannot_be_fetched_for():
    """The fetcher obeys the policy; it does not get to extend it."""
    with pytest.raises(PolicyNotConfigured, match="not in the approved"):
        _fetcher("britannica", [_ok()]).fetch(URL, "a fact")


def test_an_unconfigured_policy_refuses_every_retrieval():
    """The behaviour that held for the whole period before ADR-0019."""
    empty = CorroborationPolicy({"approved_independent_providers": [],
                                 "independence_criterion": None})
    f = HttpDocumentFetcher("un-treaties", policy=empty, min_interval_s=0.0)
    f._get = lambda url: _ok()  # type: ignore[method-assign]
    with pytest.raises(PolicyNotConfigured):
        f.fetch(URL, "a fact")


def test_every_approved_provider_has_exactly_one_implementation():
    from semintegrity.kb.corroboration import available_fetchers

    fetchers = available_fetchers()
    assert set(fetchers) == set(CorroborationPolicy().approved_providers)
    assert {type(v).__name__ for v in fetchers.values()} == {"HttpDocumentFetcher"}


# --- a search endpoint is discovery, never evidence -----------------------
@pytest.mark.parametrize("url", [
    "https://ntrs.nasa.gov/api/citations/search?q=Apollo%2011",
    "https://discovery.nationalarchives.gov.uk/API/search/records?sps.searchQuery=cabinet",
    "https://api.checklistbank.org/dataset/3LR/nameusage/search?q=Panthera",
    "https://prd-tnm.s3.amazonaws.com/?list-type=2&prefix=StagedProducts/",
])
def test_index_endpoints_are_refused(url):
    assert looks_like_index_endpoint(url) is not None
    with pytest.raises(UnsuitableArtifact, match="discovery endpoint"):
        _fetcher(responses=[_ok()]).fetch(url, "a fact")


def test_a_document_url_is_not_mistaken_for_an_index():
    assert looks_like_index_endpoint(URL) is None
    assert looks_like_index_endpoint(
        "https://www.govinfo.gov/content/pkg/FR-2024-01-02/pdf/FR-2024-01-02.pdf"
    ) is None


# --- HTTP 200 is not retrieval --------------------------------------------
def test_a_waf_challenge_header_is_refused_even_with_a_success_status():
    status, headers, body, final = _ok()
    headers["x-amzn-waf-action"] = "challenge"
    with pytest.raises(UnsuitableArtifact, match="bot-mitigation challenge"):
        _fetcher(responses=[(status, headers, body, final)]).fetch(URL, "a fact")


def test_202_with_an_empty_body_is_refused():
    """Exactly what legislation.gov.uk returned on six consecutive requests."""
    with pytest.raises(UnsuitableArtifact, match="deferred bot-mitigation"):
        _fetcher(responses=[(202, {"Content-Type": "text/html"}, b"", URL)]).fetch(URL, "f")


def test_a_cloudflare_interstitial_served_with_200_is_refused():
    """What IUCN returned: a 200 whose body is a challenge page."""
    body = ('<html><body><noscript>Enable JavaScript and cookies to continue'
            '</noscript><script>window._cf_chl_opt={cFPWv:"g"}</script></body></html>'
            + "x" * 900)
    with pytest.raises(UnsuitableArtifact, match="challenge interstitial"):
        _fetcher(responses=[_ok(body)]).fetch(URL, "a fact")


def test_a_javascript_shell_is_refused():
    """eci.gov.in returned 1,279 bytes of shell; govinfo's app pages 2,616."""
    with pytest.raises(UnsuitableArtifact, match="document threshold"):
        _fetcher(responses=[_ok('<html><body><div id="root"></div></body></html>')]).fetch(
            URL, "a fact"
        )


@pytest.mark.parametrize("status", [301, 403, 404, 500])
def test_a_non_200_is_refused(status):
    assert assess_response(status, {}, b"x" * 1000) is not None


# --- hash stability is established, not assumed ---------------------------
def test_an_unstable_artifact_is_refused():
    """A nonce-bearing page: same length, different bytes. Observed 12 times."""
    first = _ok(DOC)
    second = _ok(DOC.replace("document", "docvment"))
    assert len(first[2]) == len(second[2])
    with pytest.raises(UnsuitableArtifact, match="not hash-stable"):
        _fetcher(responses=[first, second]).fetch(URL, "a fact")


def test_a_stable_artifact_is_accepted_and_records_its_provenance():
    f = _fetcher(responses=[_ok(final="https://treaties.un.org/final.xml")])
    art = f.fetch(URL, "a fact")
    assert art.provider == "un-treaties"
    assert art.url == URL
    assert art.final_url == "https://treaties.un.org/final.xml"
    assert art.charset == "utf-8"
    assert art.http_status == 200
    assert art.media_type == "text/html"
    assert art.content == DOC
    assert art.content_hash == __import__("hashlib").sha256(DOC.encode()).hexdigest()


def test_stability_checking_can_be_switched_off_by_policy_only():
    """The flag lives in the approved policy, not in a caller's argument."""
    relaxed = CorroborationPolicy({
        "approved_independent_providers": ["un-treaties"],
        "independence_criterion": "stated",
        "frozen_artifact_suitability": {"require_hash_stability": False},
    })
    f = HttpDocumentFetcher("un-treaties", policy=relaxed, min_interval_s=0.0)
    calls: list[str] = []

    def _get(url):
        calls.append(url)
        return _ok()

    f._get = _get  # type: ignore[method-assign]
    f.fetch(URL, "a fact")
    assert len(calls) == 1, "only one retrieval when stability is not required"
    assert CorroborationPolicy().cfg["frozen_artifact_suitability"][
        "require_hash_stability"
    ] is True, "the SHIPPED policy must still require it"


# --- representation: the document is stored, not an extraction of it ------
def test_a_pdf_is_stored_as_base64_with_its_true_media_type():
    """BIPM, govinfo, NTRS and the UNTC chapter artefacts are all PDF."""
    pdf = b"%PDF-1.7\n" + b"\x00\x01binary" * 200
    art = _fetcher(responses=[_ok(pdf, ctype="application/pdf")]).fetch(URL, "a fact")
    assert art.media_type == "application/pdf"
    assert art.charset == "base64"
    assert base64.b64decode(art.content) == pdf


def test_a_non_utf8_page_records_the_charset_it_was_decoded_with():
    """psp.cz serves Windows-1250; a different decode is a different hash."""
    text = "Zánik České a Slovenské Federativní Republiky. " * 30
    art = _fetcher(responses=[_ok(text.encode("cp1250"),
                                  ctype="text/html; charset=Windows-1250")]).fetch(URL, "f")
    assert art.charset == "windows-1250"
    assert art.content == text


def test_an_oversized_artifact_is_refused_in_favour_of_a_smaller_granule():
    """The 20.8 MB certified true copy versus the 204 KB chapter PDF."""
    small_limit = CorroborationPolicy({
        "approved_independent_providers": ["un-treaties"],
        "independence_criterion": "stated",
        "frozen_artifact_suitability": {"max_artifact_bytes": 1024,
                                        "require_hash_stability": False},
    })
    f = HttpDocumentFetcher("un-treaties", policy=small_limit, min_interval_s=0.0)
    f._get = lambda url: _ok("y" * 5000)  # type: ignore[method-assign]
    with pytest.raises(UnsuitableArtifact, match="smaller authoritative granule"):
        f.fetch(URL, "a fact")


# --- the assessor itself ---------------------------------------------------
def test_a_real_document_passes_assessment():
    assert assess_response(200, {"Content-Type": "application/json"}, b'{"ok":1}' * 100) is None


# ===========================================================================
# Q27 sub-finding, hardened 2026-10-08. A 1,039-byte JS shell from e-sbirka.cz
# PASSED min_document_bytes: 512 and was caught only by a human reading it.
# Byte size does not distinguish a document from a script that would fetch one,
# so an HTML response must additionally carry readable text. The rule is on the
# REPRESENTATION, never on the provider, and must not touch PDF/XML/JSON/text.
# ===========================================================================
SHELL_SMALL = '<html><body><div id="app"></div><script src="/a.js"></script></body></html>'
# Over the byte threshold, still no document: padding lives inside markup and
# script, exactly as a real single-page-app shell does.
SHELL_LARGE = (
    "<html><head>" + '<meta name="x" content="' + "y" * 700 + '">' + "</head><body>"
    '<div id="root"></div><script>' + "var pad='" + "z" * 900 + "';" + "</script>"
    "</body></html>"
)
REAL_HTML = (
    "<html><body><h1>Constitutional Act 542/1992</h1><p>"
    + ("The Czech and Slovak Federal Republic shall cease to exist. " * 12)
    + "</p></body></html>"
)


def test_a_small_html_shell_is_refused():
    assert len(SHELL_SMALL.encode()) < 512
    why = assess_response(200, {"Content-Type": "text/html"}, SHELL_SMALL.encode())
    assert why is not None and "document threshold" in why


def test_a_large_html_shell_is_refused_despite_clearing_the_byte_threshold():
    """The e-sbirka.cz case: big enough to pass, empty enough to be useless."""
    body = SHELL_LARGE.encode()
    assert len(body) > 512, "this fixture must clear the byte threshold to be the case"
    why = assess_response(200, {"Content-Type": "text/html; charset=utf-8"}, body)
    assert why is not None, "a shell that clears the byte threshold must still be refused"
    assert "readable text" in why
    with pytest.raises(UnsuitableArtifact, match="readable text"):
        _fetcher(responses=[_ok(SHELL_LARGE)]).fetch(URL, "a fact")


def test_a_genuine_html_document_still_passes():
    assert assess_response(
        200, {"Content-Type": "text/html; charset=utf-8"}, REAL_HTML.encode()
    ) is None
    art = _fetcher(responses=[_ok(REAL_HTML)]).fetch(URL, "a fact")
    assert art.content == REAL_HTML


def test_the_html_rule_does_not_touch_a_pdf():
    """A PDF has no readable HTML text by construction and must not be refused."""
    pdf = b"%PDF-1.7\n" + b"\x00\x01binary" * 100
    assert len(pdf) > 512
    assert assess_response(200, {"Content-Type": "application/pdf"}, pdf) is None
    art = _fetcher(responses=[_ok(pdf, ctype="application/pdf")]).fetch(URL, "a fact")
    assert art.media_type == "application/pdf"


def test_the_html_rule_does_not_touch_json_or_xml():
    """Crossref JSON and the UNTC MTDSG XML are both tag-or-brace dense."""
    js = b'{"message":{"title":["The Transistor, A Semi-Conductor Triode"]}}'
    assert assess_response(200, {"Content-Type": "application/json"}, js) is None
    xml = b'<?xml version="1.0"?><Document><Treaty><Numsect>10</Numsect></Treaty></Document>'
    assert assess_response(200, {"Content-Type": "text/xml;charset=UTF-8"}, xml) is None
    # The UNTC XML is served mislabelled as text/html, which WOULD reach the HTML
    # rule — so it must carry enough readable text to pass, and it does: element
    # content is text once tags are stripped.
    untc = ("<?xml version='1.0'?><Document><Titlesect>"
            + ("Rome Statute of the International Criminal Court. " * 12)
            + "</Titlesect></Document>").encode()
    assert assess_response(200, {"Content-Type": "text/html"}, untc) is None


def test_a_plain_text_artifact_is_not_subject_to_the_html_rule():
    assert assess_response(200, {"Content-Type": "text/plain"}, b"x" * 600) is None


def test_challenge_detection_still_runs_before_the_content_test():
    """A challenge must be reported as a challenge, not as an empty document."""
    body = ('<html><body><noscript>Enable JavaScript and cookies to continue</noscript>'
            '<script>window._cf_chl_opt={}</script></body></html>' + "<!--" + "x" * 900 + "-->")
    why = assess_response(200, {"Content-Type": "text/html"}, body.encode())
    assert why is not None and "challenge interstitial" in why


def test_the_threshold_is_a_policy_value_not_a_constant():
    from semintegrity.kb.corroboration import CorroborationPolicy

    shipped = CorroborationPolicy().cfg["frozen_artifact_suitability"]
    assert shipped["min_html_text_chars"] == 400
    assert shipped["min_document_bytes"] == 512
