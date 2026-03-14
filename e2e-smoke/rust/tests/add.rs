use flow_healer_rust_smoke::{add, add_many, sum_slice};

#[test]
fn adds_two_numbers() {
    assert_eq!(add(2, 3), 5);
}

#[test]
fn adds_many_numbers() {
    let test_cases: &[(&str, &[i32], i32)] = &[
        ("three numbers", &[1, 2, 3], 6),
        ("mix of negative and positive", &[-2, 4, 3], 5),
        ("no inputs", &[], 0),
        ("single value", &[7], 7),
        ("longer list", &[1, 2, 3, 4, 5], 15),
    ];

    for (name, values, want) in test_cases {
        assert_eq!(add_many(values), *want, "{}", name);
    }
}

#[test]
fn sums_an_empty_slice() {
    assert_eq!(sum_slice(&[]), 0);
}

#[test]
fn sums_a_positive_slice() {
    assert_eq!(sum_slice(&[1, 2, 3, 4]), 10);
}

#[test]
fn sums_a_mixed_sign_slice() {
    assert_eq!(sum_slice(&[-5, 10, -2, 4]), 7);
}
