package com.classmanager.app.data;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class ApiClientTest {
    @Test
    public void resolvesRelativeApiPathWithoutCleartextFallback() {
        assertEquals(
                "https://120.27.231.112/api/v1/resources/students/",
                ApiClient.resolve("resources/students/")
        );
    }

    @Test
    public void preservesAbsoluteDownloadUrl() {
        assertEquals("https://example.test/file.zip", ApiClient.resolve("https://example.test/file.zip"));
    }
}
