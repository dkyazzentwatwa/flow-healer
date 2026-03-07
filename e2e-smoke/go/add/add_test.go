package add

import "testing"

func TestAddSmokeRegression(t *testing.T) {
	t.Parallel()

	if got := Add(2, 3); got != 5 {
		t.Fatalf("Add(2, 3) = %d, want 5", got)
	}
}

func TestAdd(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name string
		a    int
		b    int
		want int
	}{
		{name: "smoke issue regression", a: 2, b: 3, want: 5},
		{name: "commutative regression", a: 3, b: 2, want: 5},
		{name: "supports negatives", a: -1, b: 1, want: 0},
		{name: "supports zero values", a: 0, b: 0, want: 0},
		{name: "supports larger values", a: 100, b: 23, want: 123},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			if got := Add(tc.a, tc.b); got != tc.want {
				t.Fatalf("Add(%d, %d) = %d, want %d", tc.a, tc.b, got, tc.want)
			}
		})
	}
}
