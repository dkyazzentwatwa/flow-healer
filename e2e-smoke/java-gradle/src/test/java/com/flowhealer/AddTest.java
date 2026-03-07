package com.flowhealer;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AddTest {
    @Test
    void addReturnsSum() {
        assertEquals(5, Add.add(2, 3));
    }

    @Test
    void addHandlesNegativeNumbers() {
        assertEquals(-1, Add.add(2, -3));
    }

    @Test
    void addKeepsZeroAsIdentity() {
        assertEquals(7, Add.add(7, 0));
    }
}
