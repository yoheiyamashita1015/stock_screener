import unittest

import pandas as pd

from src.fundamental import FundamentalAnalyzer


class DividendYieldTest(unittest.TestCase):
    def test_prefers_trailing_yield_ratio_and_converts_to_percent(self):
        info = {
            "dividendYield": 0.34,
            "trailingAnnualDividendYield": 0.0033140802,
        }

        result = FundamentalAnalyzer.calculate_dividend_yield(info)

        self.assertAlmostEqual(result, 0.33140802)

    def test_uses_dividend_yield_as_percent_without_multiplying_again(self):
        result = FundamentalAnalyzer.calculate_dividend_yield(
            {"dividendYield": 2.5}
        )

        self.assertEqual(result, 2.5)

    def test_returns_zero_when_yield_is_missing(self):
        result = FundamentalAnalyzer.calculate_dividend_yield({})

        self.assertEqual(result, 0)


class EpsGrowthTest(unittest.TestCase):
    def test_calculates_cagr_when_first_and_last_eps_are_positive(self):
        income_statement = pd.DataFrame(
            [[1.0, 2.0, 4.0]],
            index=["Basic EPS"],
            columns=pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"]),
        )

        result = FundamentalAnalyzer.calculate_eps_growth(
            {"income_stmt": income_statement}
        )

        self.assertAlmostEqual(result["eps_growth_rate"], 100.0)

    def test_returns_none_for_cagr_when_last_eps_is_negative(self):
        income_statement = pd.DataFrame(
            [[1.0, 0.5, -1.0]],
            index=["Basic EPS"],
            columns=pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"]),
        )

        result = FundamentalAnalyzer.calculate_eps_growth(
            {"income_stmt": income_statement}
        )

        self.assertIsNone(result["eps_growth_rate"])


if __name__ == "__main__":
    unittest.main()
