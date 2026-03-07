/// Returns the arithmetic sum of two operands for the smoke fixture.
#[must_use]
pub const fn add(left: u64, right: u64) -> u64 {
    left
        .checked_add(right)
        .expect("addition overflowed for smoke fixture")
}

#[cfg(test)]
mod tests {
    use super::add;

    #[test]
    fn add_returns_sum() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn add_handles_zero() {
        assert_eq!(add(0, 0), 0);
    }

    #[test]
    fn add_handles_smoke_regression_case() {
        assert_eq!(add(2, 3), 5);
        assert_eq!(add(3, 2), 5);
    }

    #[test]
    fn add_handles_larger_values() {
        assert_eq!(add(20, 22), 42);
    }

    #[test]
    fn add_handles_upper_bound_without_overflow() {
        assert_eq!(add(u64::MAX - 1, 1), u64::MAX);
    }

    #[test]
    #[should_panic(expected = "addition overflowed for smoke fixture")]
    fn add_panics_on_overflow() {
        let _ = add(u64::MAX, 1);
    }
}
