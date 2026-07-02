# AI Memory Chain Lab

AI Memory Chain Lab is a small, production-oriented research toolkit for turning an AI-infrastructure-driven memory inflation thesis into repeatable screening, valuation-model selection, and Wyckoff execution checks.

## What it does

- Models the AI memory supply chain across upstream materials/equipment, midstream chips/foundry/memory, downstream consumer terminals, and AI applications.
- Selects valuation models by lifecycle: `PS_EV_EBITDA` for capex-heavy semiconductor assets, `DCF_DDM` for mature cash-flow leaders, and `PEG_PE` for lighter high-growth assets.
- Scores cost advantage, strategic attractiveness, and risk under a configurable 2026 memory chipflation scenario.
- Classifies Wyckoff Spring setups so trading execution stays tied to observable supply-and-demand behavior.

## Quick start

```bash
python -m chain_lab.cli \
  --companies examples/companies.json \
  --wyckoff examples/wyckoff_spring.json \
  --output report.md
```

## Inputs

`examples/companies.json` contains normalized factor inputs from `0.0` to `1.0` for moat, growth, margin power, capex intensity, local supply access, edge-AI exposure, and balance-sheet strength.

Optional scenario files can override the defaults in `ScenarioAssumption`, including DRAM price pressure, local-memory priority, liquidity, and geopolitical risk.

## Important disclaimer

This project is a research and decision-support framework. It is not investment advice and does not forecast actual securities prices. Users should replace example data with audited, source-backed assumptions before making business or investment decisions.
