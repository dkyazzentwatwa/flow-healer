package com.flowhealer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class AddTest {
    @Test
    void addReturnsSum() {
        assertEquals(5, Add.add(2, 3));
    }

    @Test
    void addHandlesRegressionCases() {
        assertEquals(5, Add.add(3, 2));
        assertEquals(7, Add.add(7, 0));
        assertEquals(7, Add.add(0, 7));
        assertEquals(42, Add.add(20, 22));
    }

    @Test
    void addHandlesUpperBoundWithoutOverflow() {
        assertEquals(Integer.MAX_VALUE, Add.add(Integer.MAX_VALUE - 1, 1));
    }

    @Test
    void addThrowsOnOverflow() {
        assertThrows(ArithmeticException.class, () -> Add.add(Integer.MAX_VALUE, 1));
    }
}
