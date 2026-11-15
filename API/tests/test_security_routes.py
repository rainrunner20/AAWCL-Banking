"""Offline source-level safety checks; no live SQL or JWT credentials required."""

import ast
import unittest
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "API.py"


class RouteGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = API.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def route(self, name):
        return next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == name)

    def test_user_routes_enforce_jwt(self):
        for name in ("get_all_users", "get_user", "update_user", "delete_user"):
            with self.subTest(name=name):
                func = self.route(name)
                decorators = [node.func.id for node in func.decorator_list
                              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
                self.assertIn("jwt_required", decorators)

    def test_no_duplicate_user_password_route(self):
        self.assertNotIn("def update_user_password", self.source)
        self.assertNotIn("SELECT * FROM Users WHERE Username = ?", self.source)

    def test_full_user_dump_and_cvv_response_removed(self):
        self.assertNotIn("SELECT * FROM Users'\n    users = cursor.fetchall()", self.source)
        self.assertNotIn("'Cvv': card[4]", self.source)
        self.assertIn("Bulk user listing is disabled", self.source)
        self.assertIn("Account deletion is disabled", self.source)


if __name__ == "__main__":
    unittest.main()
