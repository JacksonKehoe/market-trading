import pytest

from app.sentiment.news_provider import GoogleNewsRssProvider

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Google News</title>
<item><title>AAPL stock surges on strong earnings</title><link>https://example.com/1</link></item>
<item><title>Analysts raise AAPL price target</title><link>https://example.com/2</link></item>
<item><title>Apple faces regulatory scrutiny</title><link>https://example.com/3</link></item>
</channel>
</rss>"""


def test_get_headlines_parses_titles_from_rss() -> None:
    provider = GoogleNewsRssProvider(fetch=lambda url: _SAMPLE_RSS)

    headlines = provider.get_headlines("AAPL")

    assert headlines == [
        "AAPL stock surges on strong earnings",
        "Analysts raise AAPL price target",
        "Apple faces regulatory scrutiny",
    ]


def test_get_headlines_respects_limit() -> None:
    provider = GoogleNewsRssProvider(fetch=lambda url: _SAMPLE_RSS)

    headlines = provider.get_headlines("AAPL", limit=2)

    assert len(headlines) == 2


def test_get_headlines_builds_query_url_with_symbol(monkeypatch) -> None:
    captured_urls = []

    def fake_fetch(url: str) -> str:
        captured_urls.append(url)
        return _SAMPLE_RSS

    provider = GoogleNewsRssProvider(fetch=fake_fetch)
    provider.get_headlines("AAPL")

    assert len(captured_urls) == 1
    assert "AAPL" in captured_urls[0]
    assert captured_urls[0].startswith("https://news.google.com/rss/search")


def test_get_headlines_returns_empty_list_for_empty_feed() -> None:
    empty_rss = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    provider = GoogleNewsRssProvider(fetch=lambda url: empty_rss)

    assert provider.get_headlines("NOSUCHTICKER") == []


def test_get_headlines_propagates_parse_errors_for_malformed_xml() -> None:
    provider = GoogleNewsRssProvider(fetch=lambda url: "not xml at all")

    with pytest.raises(Exception):  # noqa: B017 - just confirming it doesn't silently return garbage
        provider.get_headlines("AAPL")
