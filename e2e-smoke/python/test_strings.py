def test_is_palindrome() -> None:
    from strings import is_palindrome
    assert is_palindrome("racecar") is True
    assert is_palindrome("hello") is False
