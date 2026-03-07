use flow_healer_rust_smoke::add;

#[test]
fn add_returns_expected_sum() {
    assert_eq!(add(2, 3), 5);
}

#[test]
fn add_covers_smoke_regression_cases() {
    let cases = [
        (2, 3, 5),
        (3, 2, 5),
        (7, 0, 7),
        (0, 7, 7),
        (20, 22, 42),
    ];

    for (left, right, expected) in cases {
        assert_eq!(add(left, right), expected);
    }
}

#[test]
fn add_can_be_evaluated_constantly() {
    const SUM: u64 = add(2, 3);
    assert_eq!(SUM, 5);
}
