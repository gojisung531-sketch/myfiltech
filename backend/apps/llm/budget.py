"""Explicit-run budget guard; reserve uncertain/failed attempts without refunds."""

from decimal import Decimal


class BudgetExceeded(RuntimeError):
    pass


class AttemptBudget:
    def __init__(self, limit):
        self.limit = Decimal(str(limit))
        self.reserved = Decimal("0")
        self.attempts = []

    def reserve(self, maximum_cost):
        cost = Decimal(str(maximum_cost))
        if not cost.is_finite() or cost <= 0:
            raise ValueError("A finite positive attempt bound is required")
        if self.reserved + cost > self.limit:
            raise BudgetExceeded("Additional request would exceed the explicit run budget")
        self.reserved += cost
        self.attempts.append(cost)
        return len(self.attempts)
