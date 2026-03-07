package com.flowhealer;

public final class Add {
    private Add() {}

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
