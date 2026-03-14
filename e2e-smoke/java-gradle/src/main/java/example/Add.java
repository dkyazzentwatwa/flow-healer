package example;

public final class Add {
    private Add() {}

    public static int add(int left, int right) {
        return left + right;
    }

    public static int addMany(int... numbers) {
        int sum = 0;
        for (int number : numbers) {
            sum += number;
        }
        return sum;
    }

    public static int add3(int left, int right, int extra) {
        return addMany(left, right, extra);
    }
}
