from __future__ import annotations

from lib.hedge_matching import match_market_reference, normalize_question


def test_match_market_reference_prefers_exact_id_then_question_then_substring() -> None:
    markets = [
        {"id": "101", "question": "Will election turnout exceed 60%?"},
        {"id": "202", "question": "Will the Democratic nominee win the 2028 election?"},
    ]

    assert normalize_question("  Hello   There ") == "hello there"
    by_id = match_market_reference(
        market_id="202", market_question="ignored", markets=markets
    )
    by_question = match_market_reference(
        market_id="",
        market_question="Will election turnout exceed 60%?",
        markets=markets,
    )
    by_substring = match_market_reference(
        market_id="",
        market_question="Democratic nominee win",
        markets=markets,
    )

    assert by_id is not None and by_id["id"] == "202"
    assert by_question is not None and by_question["id"] == "101"
    assert by_substring is not None and by_substring["id"] == "202"
