pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

#[cfg(test)]
mod tests {
    use super::add;

    #[test]
    fn test_add_returns_sum() {
        assert_eq!(add(2, 3), 5);
    }
}
