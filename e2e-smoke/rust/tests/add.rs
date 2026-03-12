use flow_healer_rust_smoke::{add, add_many};

#[test]
fn adds_two_numbers() {
    assert_eq!(add(2, 3), 5);
}

#[test]
fn adds_three_numbers() {
    assert_eq!(add_many(2, 3, 4), 9);
}
