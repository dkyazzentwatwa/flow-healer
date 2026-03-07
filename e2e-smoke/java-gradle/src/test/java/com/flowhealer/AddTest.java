package com.flowhealer;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class AddTest {
    @Test
    void addReturnsSum() {
        assertEquals(5, Add.add(2, 3));
    }
}
