package com.classmanager.app.ui;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class BaseActivityTest {
    @Test
    public void exitsOnlyOnSecondBackPressWithinWindow() {
        assertFalse(BaseActivity.isSecondBackPress(0, 1000));
        assertTrue(BaseActivity.isSecondBackPress(1000, 3000));
        assertFalse(BaseActivity.isSecondBackPress(1000, 3001));
        assertFalse(BaseActivity.isSecondBackPress(2000, 1000));
    }
}
