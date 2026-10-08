# Nebius verification evidence — 5 Oct 2026

Checked before implementing provider calls:

- Official [List models API](https://docs.tokenfactory.nebius.com/api-reference/models/list-models)
  requires Bearer authentication and returns exact available IDs from `/v1/models`.
- Official [Nebius vision overview](https://nebius.com/solutions/vision) names
  Qwen2.5-VL-72B-Instruct and Kimi-K2.6 as vision-language models available through
  Token Factory's OpenAI-compatible API. This establishes documented vision support,
  not access on this account, exact API IDs, or base64 support for the PRD's Gemma ID.
- [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)
  and [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
  are implemented as server-side authenticated runtime calls.

`NEBIUS_API_KEY` and `TAVILY_API_KEY` are absent from local `.env` and shell. The
user requested continued implementation and a checklist to configure/test later.
Authenticated model availability and base64 image support are **unverified**.
The reproducible probe is `python -m maxx.verify_providers` from `services/api`.
No provisional model ID is represented as verified.
