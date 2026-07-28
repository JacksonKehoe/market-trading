from app.models.enums import SentimentLabel
from app.sentiment.analyzer import VaderSentimentAnalyzer


def test_analyze_classifies_clearly_positive_headlines_as_bullish() -> None:
    analyzer = VaderSentimentAnalyzer()
    headlines = [
        "Company reports record profits and stellar growth",
        "Analysts are thrilled with the amazing earnings beat",
        "Stock soars to all-time high on excellent outlook",
    ]

    result = analyzer.analyze("AAPL", headlines)

    assert result.symbol == "AAPL"
    assert result.label == SentimentLabel.BULLISH
    assert result.score > 0
    assert result.headline_count == 3


def test_analyze_classifies_clearly_negative_headlines_as_bearish() -> None:
    analyzer = VaderSentimentAnalyzer()
    headlines = [
        "Company reports disastrous losses and terrible outlook",
        "Investors panic as stock crashes on awful earnings",
        "Regulators slam company with harsh fraud allegations",
    ]

    result = analyzer.analyze("AAPL", headlines)

    assert result.label == SentimentLabel.BEARISH
    assert result.score < 0


def test_analyze_classifies_neutral_factual_headlines_as_neutral() -> None:
    analyzer = VaderSentimentAnalyzer()
    headlines = [
        "Company to report quarterly earnings on Thursday",
        "Annual shareholder meeting scheduled for next month",
    ]

    result = analyzer.analyze("AAPL", headlines)

    assert result.label == SentimentLabel.NEUTRAL


def test_analyze_returns_neutral_zero_score_for_no_headlines() -> None:
    analyzer = VaderSentimentAnalyzer()

    result = analyzer.analyze("AAPL", [])

    assert result.label == SentimentLabel.NEUTRAL
    assert result.score == 0.0
    assert result.headline_count == 0
