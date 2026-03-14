pub fn add(left: i32, right: i32) -> i32 {
    left + right
}

pub fn add_many(values: &[i32]) -> i32 {
    sum_slice(values)
}

pub fn sum_slice(values: &[i32]) -> i32 {
    values.iter().sum()
}
