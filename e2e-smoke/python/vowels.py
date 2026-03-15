def count_vowels(s: str) -> int:
    return sum(1 for c in s.lower() if c in "aeiou")
