package add

import "testing"

func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Fatalf("Add(2, 3) = %d, want 5", got)
	}
}

func TestAddMany(t *testing.T) {
	if got := AddMany(2, 3, 4); got != 9 {
		t.Fatalf("AddMany(2, 3, 4) = %d, want 9", got)
	}
}
