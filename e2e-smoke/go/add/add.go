package add

const (
	maxInt = int(^uint(0) >> 1)
	minInt = -maxInt - 1
)

// Add returns the arithmetic sum of a and b.
func Add(a, b int) int {
	if (b > 0 && a > maxInt-b) || (b < 0 && a < minInt-b) {
		panic("addition overflowed for smoke fixture")
	}

	return a + b
}
