from __future__ import annotations

import threading
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from unittest.mock import patch

from mfblue.server import Handler, ThreadingHTTPServer, bind_server


@contextmanager
def running_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ServerSecurityTests(unittest.TestCase):
    def test_bind_server_rejects_non_loopback_host(self) -> None:
        unexpected_server = None
        try:
            with self.assertRaises(ValueError):
                unexpected_server, _ = bind_server("0.0.0.0", 0, max_tries=1)
        finally:
            if unexpected_server is not None:
                unexpected_server.server_close()

    def test_rejects_untrusted_host_header_before_get_handler(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_get") as handle_get:
                handle_get.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.putrequest("GET", "/api/accounts", skip_host=True)
                    conn.putheader("Host", "evil.example")
                    conn.endheaders()
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 421)
            handle_get.assert_not_called()

    def test_rejects_text_plain_post_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "text/plain",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 415)
            handle_post.assert_not_called()

    def test_rejects_cross_origin_json_post_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                            "Origin": "https://evil.example",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 403)
            handle_post.assert_not_called()

    def test_allows_same_origin_json_post(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json; charset=utf-8",
                            "Origin": f"http://127.0.0.1:{port}",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 200)
            handle_post.assert_called_once()

    def test_rejects_cross_origin_referer_post_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/assets/purchases",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                            "Referer": "https://evil.example/some/page",
                        },
                    )
                    response = conn.getresponse()
                    body = response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 403)
            self.assertIn(b"untrusted_referer", body)
            handle_post.assert_not_called()

    def test_rejects_wrong_port_referer_post_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            wrong_port = 8765 if port != 8765 else 8766
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                            "Referer": f"http://127.0.0.1:{wrong_port}/",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 403)
            handle_post.assert_not_called()

    def test_allows_same_origin_referer_with_path_post(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                            "Referer": f"http://127.0.0.1:{port}/index.html",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 200)
            handle_post.assert_called_once()

    def test_allows_json_post_without_origin_or_referer(self) -> None:
        # Non-browser local clients (curl, scripts) send neither header;
        # Host + Content-Type checks still apply to them.
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 200)
            handle_post.assert_called_once()

    def test_rejects_missing_content_type_post_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/sync",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Origin": f"http://127.0.0.1:{port}",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 415)
            handle_post.assert_not_called()

    def test_rejects_form_urlencoded_post_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_post") as handle_post:
                handle_post.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/assets/refresh-prices",
                        body="period_month=2026-10",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": f"http://127.0.0.1:{port}",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 415)
            handle_post.assert_not_called()

    def test_rejects_cross_origin_patch_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_patch") as handle_patch:
                handle_patch.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "PATCH",
                        "/api/transactions/1",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                            "Origin": "https://evil.example",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 403)
            handle_patch.assert_not_called()

    def test_rejects_cross_origin_referer_patch_before_side_effect(self) -> None:
        with running_server() as server:
            port = server.server_address[1]
            with patch("mfblue.server.handle_patch") as handle_patch:
                handle_patch.side_effect = lambda handler: handler.send_json({"status": "called"})
                conn = HTTPConnection("127.0.0.1", port, timeout=3)
                try:
                    conn.request(
                        "PATCH",
                        "/api/transactions/1",
                        body="{}",
                        headers={
                            "Host": f"127.0.0.1:{port}",
                            "Content-Type": "application/json",
                            "Referer": "https://evil.example/some/page",
                        },
                    )
                    response = conn.getresponse()
                    response.read()
                finally:
                    conn.close()

            self.assertEqual(response.status, 403)
            handle_patch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
