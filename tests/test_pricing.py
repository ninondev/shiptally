# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 Ninon

import unittest

from shiptally.pricing import cost_of, cost_codex, is_known_model


class PricingTests(unittest.TestCase):
    def test_opus_cache_split_hand_calculation(self):
        # 4 + 40 + 15 + 32 + 1 = 92 USD.
        usage = {"input_tokens": 1_000_000, "output_tokens": 2_000_000,
                 "cache_read_input_tokens": 5_000_000, "cache_creation_input_tokens": 999_000_000,
                 "cache_creation": {"ephemeral_5m_input_tokens": 3_000_000,
                                    "ephemeral_1h_input_tokens": 4_000_000}}
        self.assertEqual(cost_of("claude-opus-5-5-20261001", usage), 92)

    def test_cache_creation_total_is_fallback_only(self):
        self.assertEqual(cost_of("claude-sonnet-4-6", {"cache_creation_input_tokens": 1_000_000}), 3.75)

    def test_haiku_threshold_includes_all_prompt_tokens(self):
        low = {"input_tokens": 90_000, "cache_read_input_tokens": 10_000, "output_tokens": 1000}
        high = dict(low, cache_read_input_tokens=10_001)
        self.assertAlmostEqual(cost_of("claude-haiku-5-5", low), 0.009 + 0.0001 + 0.0005)
        self.assertAlmostEqual(cost_of("claude-haiku-5-5", high), 0.045 + 0.00050005 + 0.0025)

    def test_fable_longest_prefix_wins(self):
        self.assertEqual(cost_of("claude-fable-5-1-20261001", {"cache_read_input_tokens": 1_000_000}), 0.25)
        self.assertEqual(cost_of("claude-fable-5-20261001", {"cache_read_input_tokens": 1_000_000}), 1)

    def test_unknown_model_matches_snapshot_fallback(self):
        self.assertFalse(is_known_model("future-model"))
        self.assertEqual(cost_of("future-model", {"input_tokens": 1_000_000}), 4)

    def test_codex_cached_input_is_a_subset(self):
        self.assertEqual(cost_codex({"input_tokens": 1_000_000, "cached_input_tokens": 200_000,
                                     "output_tokens": 100_000},
                                    {"input": 2, "cached_input": 0.5, "output": 10}), 2.7)


if __name__ == "__main__":
    unittest.main()
