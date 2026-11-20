package com.seerpeak.pvp;

import android.content.res.AssetManager;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** 只读静态资源服务：把 APK assets/www 挂到 127.0.0.1 的随机端口上。 */
final class AssetServer implements Runnable {

    private final AssetManager assets;
    private final ExecutorService pool = Executors.newFixedThreadPool(8);
    private ServerSocket socket;
    private volatile boolean running = true;

    AssetServer(AssetManager assets) {
        this.assets = assets;
    }

    int start() {
        try {
            socket = new ServerSocket(0, 64, InetAddress.getByName("127.0.0.1"));
            Thread t = new Thread(this, "asset-server");
            t.setDaemon(true);
            t.start();
            return socket.getLocalPort();
        } catch (IOException e) {
            throw new IllegalStateException("无法启动本地资源服务", e);
        }
    }

    void stop() {
        running = false;
        try {
            if (socket != null) socket.close();
        } catch (IOException ignored) {
        }
        pool.shutdownNow();
    }

    @Override
    public void run() {
        while (running) {
            try {
                final Socket client = socket.accept();
                pool.execute(new Runnable() {
                    @Override
                    public void run() {
                        handle(client);
                    }
                });
            } catch (IOException e) {
                if (running) continue;
                break;
            }
        }
    }

    private void handle(Socket client) {
        try (Socket c = client) {
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
            String request = in.readLine();
            if (request == null) return;
            String header;
            while ((header = in.readLine()) != null && !header.isEmpty()) {
                // 读完请求头
            }
            String[] parts = request.split(" ");
            if (parts.length < 2) return;
            String path = parts[1];
            int q = path.indexOf('?');
            if (q >= 0) path = path.substring(0, q);
            path = URLDecoder.decode(path, "UTF-8");
            if (path.equals("/")) path = "/references/spirit_synergy_view.html";
            if (path.contains("..")) {
                write(c, 403, "text/plain", "forbidden".getBytes(StandardCharsets.UTF_8));
                return;
            }
            byte[] data = readAsset("www" + path);
            if (data == null) {
                write(c, 404, "text/plain", "not found".getBytes(StandardCharsets.UTF_8));
                return;
            }
            write(c, 200, mimeOf(path), data);
        } catch (Exception ignored) {
            // 客户端断开或坏请求，忽略
        }
    }

    private byte[] readAsset(String path) {
        try (InputStream is = assets.open(path)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream(Math.max(8192, is.available()));
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = is.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        } catch (IOException e) {
            return null;
        }
    }

    private void write(Socket c, int code, String mime, byte[] body) throws IOException {
        // 入口 HTML 必须每次回源校验：WebView 会缓存 200，升级后仍加载旧页面；
        // 其余静态资源按内容长期缓存，省重复读取 assets。
        String cache = (code == 200 && !mime.startsWith("text/html"))
                ? "public, max-age=31536000, immutable" : "no-store";
        String head = "HTTP/1.1 " + code + (code == 200 ? " OK" : " ERROR") + "\r\n"
                + "Content-Type: " + mime + "\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Cache-Control: " + cache + "\r\n"
                + "Connection: close\r\n\r\n";
        OutputStream os = c.getOutputStream();
        os.write(head.getBytes(StandardCharsets.UTF_8));
        os.write(body);
        os.flush();
    }

    private static String mimeOf(String path) {
        String p = path.toLowerCase();
        if (p.endsWith(".html") || p.endsWith(".htm")) return "text/html; charset=utf-8";
        if (p.endsWith(".js")) return "application/javascript; charset=utf-8";
        if (p.endsWith(".css")) return "text/css; charset=utf-8";
        if (p.endsWith(".json")) return "application/json; charset=utf-8";
        if (p.endsWith(".webp")) return "image/webp";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".woff2")) return "font/woff2";
        if (p.endsWith(".ico")) return "image/x-icon";
        return "application/octet-stream";
    }
}