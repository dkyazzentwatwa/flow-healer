package example;

public final class AddTest {
    private AddTest() {}

    public static void main(String[] args) {
        int sum = Add.add(2, 3);
        if (sum != 5) {
            throw new AssertionError("expected 5 but got " + sum);
        }
    }
}
