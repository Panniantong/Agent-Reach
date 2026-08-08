# Fieldwork — Campaign Concept Studio

A production-minded full-stack concept generator for marketing teams. A single brief produces a focused campaign concept, three copy routes, an actionable launch checklist, three reusable image prompts, and generated key-visual studies.

## Architecture and security boundary

```text
Browser (HTML/CSS/JS) → POST /api/campaigns → FastAPI server → OpenAI Responses API
                                              ↳ text + JSON Schema
                                              ↳ image_generation tool
```

The browser sends only brief fields to this app's API. `OPENAI_API_KEY`, model selection, prompts, Structured Outputs schema, and all OpenAI calls live in `app.py`; the key is never serialized or bundled into client code. Keep the app behind authentication and rate limiting when deploying it publicly. Generated images are returned as short-lived response data URLs and are not persisted by this reference app.

## Install and run

Python 3.10+ is required.

```bash
cd campaign_studio
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Replace the placeholder with a server-side key, or export it in your shell:
export OPENAI_API_KEY="sk-..."
uvicorn campaign_studio.app:app --reload --port 8000
```

Run the final command from the repository root, then open <http://localhost:8000>. Do not commit `.env` files or expose the key through a `VITE_`, `NEXT_PUBLIC_`, or similar browser-visible variable.

## Current OpenAI implementation

Both stages use `client.responses.create(...)`—never legacy Completions or Chat Completions. The strategy stage requests strict JSON Schema output. Each visual is created through the Responses API `image_generation` tool. Defaults are `gpt-5.4-mini` for orchestration/text and `gpt-image-1.5` for images, based on the current model catalog; verify availability for your project in the [OpenAI model guide](https://developers.openai.com/api/docs/models) before deployment.

### Adjusting the system later

| What | Where | How |
| --- | --- | --- |
| Text/orchestration model | `OPENAI_TEXT_MODEL` | Change the environment value; retest schema adherence and copy quality. |
| Image model | `OPENAI_IMAGE_MODEL` | Change the environment value to a supported image model. |
| Creative behavior | `generate_concept()` in `app.py` | Edit `instructions`; preserve the exact counts expected by the UI and schema. |
| Output contract | `Concept` models and `_concept_schema()` | Update Pydantic types and the renderer together. |
| Image framing/quality | `generate_image()` | Adjust `size`, `quality`, `output_format`, and the art-direction wrapper. |
| Image quantity | `CAMPAIGN_IMAGE_COUNT` | Set 1–3; more images increase latency and cost. |

## Validation plan

1. **Contract:** unit test brief length/channel validation, strict output parsing, missing-key behavior, and provider-error sanitization with a mocked OpenAI client.
2. **Creative quality:** maintain 10–20 representative briefs; reviewers score specificity, claim safety, voice, route diversity, cross-channel usefulness, and visual consistency.
3. **Visual safety:** review generated assets for accidental typography, logos, unsafe content, biased representation, and product inaccuracies.
4. **UX:** verify keyboard navigation, mobile layouts, slow responses, retry, missing-key, invalid-input, and empty states. Confirm copy-all and image alt text behavior.
5. **Operations:** load test within project rate limits; add authentication, request quotas, structured server logs, moderation appropriate to the use case, and durable asset storage before public launch.

## Deployment

Build any Python 3.10+ service with `pip install -r campaign_studio/requirements.txt`, set `OPENAI_API_KEY` in the host's encrypted secrets manager, and start with:

```bash
uvicorn campaign_studio.app:app --host 0.0.0.0 --port "$PORT"
```

Use TLS, authentication, rate limits, request-size limits, timeouts, and a reverse proxy in production. Because image responses can be large, configure the proxy's response limit accordingly. For scale, move generation to a job queue, persist results in object storage, and return job status rather than holding one request open.
