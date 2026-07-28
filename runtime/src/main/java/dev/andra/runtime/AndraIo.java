package dev.andra.runtime;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;

public final class AndraIo {
    private AndraIo() {}

    public static String readUtf8(File file) throws Exception {
        try (FileInputStream in = new FileInputStream(file);
             ByteArrayOutputStream bos = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) >= 0) bos.write(buf, 0, n);
            return bos.toString(StandardCharsets.UTF_8.name());
        }
    }
}
