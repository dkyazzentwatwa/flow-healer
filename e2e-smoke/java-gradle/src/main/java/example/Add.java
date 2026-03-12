package example;

public final class Add {
    private Add() {}

    public static int add(int left, int right) {
        return left + right;
    }

    public static int add3(int left, int right, int extra) {
        return left + right + extra;
    }
}
