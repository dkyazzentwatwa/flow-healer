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

        int positiveSum = Add.addMany(2, 3, 4);
        if (positiveSum != 9) {
            throw new AssertionError("expected 9 but got " + positiveSum);
        }

        int mixedSignSum = Add.addMany(-2, 3, -4);
        if (mixedSignSum != -3) {
            throw new AssertionError("expected -3 but got " + mixedSignSum);
        }

        int multiOperandSum = Add.addMany(1, 2, 3, 4, 5);
        if (multiOperandSum != 15) {
            throw new AssertionError("expected 15 but got " + multiOperandSum);
        }

        int emptySum = Add.addMany();
        if (emptySum != 0) {
            throw new AssertionError("expected 0 but got " + emptySum);
        }
    }
}
