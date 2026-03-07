/// Returns the arithmetic sum of two operands for the smoke fixture.
#[must_use]
pub const fn add(left: u64, right: u64) -> u64 {
    left + right
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
}
