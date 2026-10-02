import pytest

from abie_gpt.bot.max_handler import split_message


def test_split_message_keeps_short_text():
    assert split_message("hello", 10) == ["hello"]


def test_split_message_respects_limit():
    chunks = split_message("one two three four five", 8)
    assert "".join(chunks).replace(" ", "") == "onetwothreefourfive"
    assert all(len(chunk) <= 8 for chunk in chunks)


def test_split_empty():
    assert split_message("   ", 10) == []
