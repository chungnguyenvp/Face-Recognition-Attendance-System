import unittest


class CsrfTests(unittest.TestCase):
    def test_valid_csrf_tokens_require_matching_cookie_and_header(self):
        try:
            from app.core.csrf import valid_csrf_tokens
        except ModuleNotFoundError as exc:
            if exc.name == "fastapi":
                self.skipTest("FastAPI is not installed in this test environment.")
            raise

        self.assertTrue(valid_csrf_tokens("token-123", "token-123"))
        self.assertFalse(valid_csrf_tokens("token-123", "wrong"))
        self.assertFalse(valid_csrf_tokens("token-123", None))
        self.assertFalse(valid_csrf_tokens(None, "token-123"))


if __name__ == "__main__":
    unittest.main()
