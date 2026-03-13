pub fn add(left: i32, right: i32) -> i32 {
    left + right
}

pub fn add_many(left: i32, right: i32, extra: i32) -> i32 {
    left + right + extra
}

pub fn sum_slice(values: &[i32]) -> i32 {
    values.iter().sum()
}
