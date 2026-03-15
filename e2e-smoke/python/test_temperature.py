def test_temperature() -> None:
    from temperature import celsius_to_fahrenheit
    assert celsius_to_fahrenheit(0) == 32.0
    assert celsius_to_fahrenheit(100) == 212.0
