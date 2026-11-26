"""Integration tests for the monthly cost guard using real Redis."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from redis import Redis

import monthly_cost_guard as guard


class MonthlyCostGuardTests(unittest.TestCase):
    def setUp(self):
        self.url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis = Redis.from_url(self.url)
        self.addCleanup(self.redis.close)
        self.month = "2026-11"
        self.next_month = "2026-12"
        self.month_clock = self.enterContext(
            patch.object(guard, "_current_month", return_value=self.month)
        )
        self.user, self.key = self.new_user()

    def new_user(self):
        user = f"cost-guard-test-{uuid4().hex}"
        key = f"budget:{user}:{self.month}"
        self.addCleanup(self.redis.delete, key)
        return user, key

    def assert_spending(self, key, amount):
        stored = self.redis.get(key)
        self.assertIsNotNone(stored)
        self.assertEqual(Decimal(stored.decode("ascii")), Decimal(amount))

    def assert_fresh_ttl(self):
        ttl = self.redis.ttl(self.key)
        expected = 32 * 24 * 60 * 60
        self.assertGreaterEqual(ttl, expected - 5)
        self.assertLessEqual(ttl, expected)

    def test_cost_01_first_charge(self):
        self.assertTrue(guard.check_budget(self.user, 3))
        self.assert_spending(self.key, "3")

    def test_cost_02_accumulated_spending(self):
        self.assertTrue(guard.check_budget(self.user, 3))
        self.assertTrue(guard.check_budget(self.user, 4))
        self.assert_spending(self.key, "7")

    def test_cost_03_exact_budget(self):
        self.assertTrue(guard.check_budget(self.user, 7))
        self.assertTrue(guard.check_budget(self.user, 3))
        self.assert_spending(self.key, "10")

    def test_cost_04_rejection_preserves_spending(self):
        self.assertTrue(guard.check_budget(self.user, 10))
        self.assertFalse(guard.check_budget(self.user, 0.01))
        self.assert_spending(self.key, "10")

    def test_cost_05_rejected_first_charge_creates_no_key(self):
        self.assertFalse(guard.check_budget(self.user, 10.01))
        self.assertEqual(self.redis.exists(self.key), 0)

    def test_cost_06_independent_user_budgets(self):
        other_user, other_key = self.new_user()
        self.assertTrue(guard.check_budget(self.user, 10))
        self.assertTrue(guard.check_budget(other_user, 3))
        self.assert_spending(self.key, "10")
        self.assert_spending(other_key, "3")

    def test_cost_07_month_rollover(self):
        next_key = f"budget:{self.user}:{self.next_month}"
        self.addCleanup(self.redis.delete, next_key)
        self.assertTrue(guard.check_budget(self.user, 10))
        self.month_clock.return_value = self.next_month
        self.assertTrue(guard.check_budget(self.user, 3))
        self.assert_spending(self.key, "10")
        self.assert_spending(next_key, "3")

    def test_cost_08_ttl_creation_preservation_and_refresh(self):
        self.assertTrue(guard.check_budget(self.user, 3))
        self.assert_fresh_ttl()
        self.assertTrue(self.redis.expire(self.key, 60))
        expiry = self.redis.pexpiretime(self.key)
        self.assertGreater(expiry, 0)

        self.assertFalse(guard.check_budget(self.user, 8))
        self.assertEqual(self.redis.pexpiretime(self.key), expiry)

        self.assertTrue(guard.check_budget(self.user, 1))
        self.assert_fresh_ttl()

    def test_cost_09_spending_survives_client_close(self):
        with Redis.from_url(self.url) as writer:
            with patch.object(guard, "_redis", writer):
                self.assertTrue(guard.check_budget(self.user, 3))

        with Redis.from_url(self.url) as reader:
            self.assertEqual(reader.get(self.key), b"3")

    def test_cost_10_concurrent_charges_respect_budget(self):
        self.assertTrue(guard.check_budget(self.user, 7))
        start = Barrier(2, timeout=5)

        def charge():
            start.wait()
            return guard.check_budget(self.user, 3)

        with ThreadPoolExecutor(max_workers=2) as executor:
            requests = [executor.submit(charge) for _ in range(2)]
            decisions = [request.result() for request in requests]

        self.assertCountEqual(decisions, [True, False])
        self.assert_spending(self.key, "10")
