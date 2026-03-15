def test_count_vowels() -> None:
    from vowels import count_vowels
    assert count_vowels("hello") == 2
    assert count_vowels("rhythm") == 0
