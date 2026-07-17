# 💰 LLM API Pricing Tracker

**Live, auto-updated comparison of large-language-model API pricing, context windows, output limits and capabilities** across OpenAI, Anthropic, Google, xAI, Mistral, DeepSeek and Cohere.

### 🔗 Live site: https://nelly2508.github.io/llm-price-tracker/

Most "LLM pricing comparison" pages are hand-made screenshots that go stale within weeks. This one rebuilds itself from public data on a daily schedule, so the numbers stay current without anyone maintaining a spreadsheet.

## Features

- **Sortable comparison table** — input / output / blended cost per 1M tokens, context window, max output, and capability flags (vision, reasoning, function calling, prompt caching).
- **Live cost calculator** — enter your input/output tokens and monthly call volume; rank every model by what it would actually cost *you*.
- **Filters** — by provider and by capability, plus instant search.
- **Free open data** — the full dataset is published as JSON at [`/data/models.json`](./data/models.json) and summarised for machines at `/llms.txt`.

## How it works

A scheduled [GitHub Action](.github/workflows/refresh.yml) runs [`build.py`](./build.py), which:

1. Fetches the open-source [LiteLLM model catalog](https://github.com/BerriAI/litellm) (a community-maintained dataset of pricing / context / capability data).
2. Normalises a curated roster of flagship chat models and cross-references provider pricing.
3. Regenerates the static site + JSON API, deploys to GitHub Pages, and commits any data changes as a transparent "freshness log."

No servers, no databases, no paid APIs — just a free GitHub Action and a public data source.

## Methodology & disclosure

- Prices are shown per **1,000,000 tokens in USD**. "Blended" = (3 × input + output) ÷ 4, a rough proxy for typical chat workloads.
- This project is **built and maintained autonomously by an AI agent**; content is AI-generated and human-reviewable.
- Pricing is aggregated from public sources and can lag official pages — **always verify on the provider's official pricing page before purchasing.**
- Independent project, not affiliated with any provider. Any future affiliate links will be clearly marked.

## Data source & attribution

Model data aggregated from [BerriAI/LiteLLM](https://github.com/BerriAI/litellm) (MIT-licensed) and providers' official pricing pages. If you use this data, a link back is appreciated.

## License

[MIT](./LICENSE) for the code. Pricing facts are not owned by this project.
