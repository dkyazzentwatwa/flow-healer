use flow_healer_rust_smoke::{add, add_many, sum_slice};

#[test]
fn adds_two_numbers() {
    assert_eq!(add(2, 3), 5);
}

#[test]
fn adds_three_numbers() {
    assert_eq!(add_many(2, 3, 4), 9);
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
