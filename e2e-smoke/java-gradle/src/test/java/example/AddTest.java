package example;

public final class AddTest {
    private AddTest() {}

    public static void main(String[] args) {
        int sum = Add.add(2, 3);
        if (sum != 5) {
            throw new AssertionError("expected 5 but got " + sum);
        }

        int sum3 = Add.add3(2, 3, 4);
        if (sum3 != 9) {
            throw new AssertionError("expected 9 but got " + sum3);
        }
    }
}
