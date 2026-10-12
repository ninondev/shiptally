# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ninon
"""API list-price equivalents, not subscription bills."""

PRICE_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
CHECKED_DATE = "2026-10-08"
PRICE_SNAPSHOT_NOTE = "Local price snapshot copied on 2026-10-08; not checked online."
# USD per million tokens: input, output, 5-minute write, 1-hour write, read.
PRICE = {
    "claude-fable-5-1": (10, 50, 12.5, 20, 0.25),
    "claude-fable-5": (10, 50, 12.5, 20, 1.0),
    "claude-opus-5-5": (4, 20, 5, 8, 0.20),
    "claude-opus-5": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-8": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-7": (5, 25, 6.25, 10, 0.50),
    "claude-opus-4-6": (5, 25, 6.25, 10, 0.50),
    "claude-sonnet-5-5": (2, 10, 2.5, 4, 0.10),
    "claude-sonnet-5": (2, 10, 2.5, 4, 0.20),
    "claude-sonnet-4-6": (3, 15, 3.75, 6, 0.30),
    "claude-haiku-4-5": (1, 5, 1.25, 2, 0.10),
}
HAIKU_55 = ((0.10, 0.50, 0.125, 0.20, 0.01),
            (0.50, 2.50, 0.625, 1.0, 0.05))
DEFAULT_PRICE = PRICE["claude-opus-5-5"]


def is_known_model(model):
    return model.startswith("claude-haiku-5-5") or any(model.startswith(name) for name in PRICE)


def rates(model, prompt_tokens):
    if model.startswith("claude-haiku-5-5"):
        return HAIKU_55[prompt_tokens > 100_000]
    for name, rate in PRICE.items():
        if model.startswith(name):
            return rate
    return DEFAULT_PRICE


def cost_of(model, usage):
    creation = usage.get("cache_creation") or {}
    read = usage.get("cache_read_input_tokens", 0) or 0
    fresh = usage.get("input_tokens", 0) or 0
    output = usage.get("output_tokens", 0) or 0
    hour = creation.get("ephemeral_1h_input_tokens", 0) or 0
    minute = creation.get("ephemeral_5m_input_tokens", 0) or 0
    if not (hour or minute):
        minute = usage.get("cache_creation_input_tokens", 0) or 0
    rate = rates(model, read + fresh + hour + minute)
    if rate is None:
        return None
    pi, po, p5, p1, pr = rate
    return (fresh * pi + output * po + minute * p5 + hour * p1 + read * pr) / 1_000_000


def cost_codex(event, prices):
    """Cached input is a subset of total input, as in Codex logs."""
    cached = min(event.get("cached_input_tokens", 0), event.get("input_tokens", 0))
    fresh = event.get("input_tokens", 0) - cached
    return (fresh * prices["input"] + cached * prices.get("cached_input", prices["input"])
            + event.get("output_tokens", 0) * prices["output"]) / 1_000_000
