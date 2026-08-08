"""Server for Campaign Concept Studio.

The browser only talks to this FastAPI application. OpenAI credentials and API
calls remain here on the trusted server boundary.
"""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")


def _image_count() -> int:
    """Read and safely clamp an operator-controlled setting."""
    try:
        configured = int(os.getenv("CAMPAIGN_IMAGE_COUNT", "2"))
    except ValueError:
        configured = 2
    return min(max(configured, 1), 3)


class Brief(BaseModel):
    campaign_brief: str = Field(min_length=10, max_length=1_500)
    audience: str = Field(min_length=3, max_length=600)
    product: str = Field(min_length=3, max_length=1_000)
    tone: Literal["Bold", "Warm", "Playful", "Premium", "Direct", "Optimistic"]
    channels: list[Literal["Social", "Email", "Web", "OOH", "Paid media"]] = Field(
        min_length=1, max_length=5
    )

    @field_validator("campaign_brief", "audience", "product")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class CopyVariant(BaseModel):
    label: str
    headline: str
    body: str


class Concept(BaseModel):
    concept_name: str
    concept: str
    strategic_thought: str
    variants: list[CopyVariant] = Field(min_length=3, max_length=3)
    checklist: list[str] = Field(min_length=6, max_length=8)
    image_prompts: list[str] = Field(min_length=3, max_length=3)


class CampaignResponse(Concept):
    images: list[str]


app = FastAPI(title="Campaign Concept Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _concept_schema() -> dict:
    schema = Concept.model_json_schema()
    # Structured Outputs requires every object to opt out of undeclared keys.
    for definition in schema.get("$defs", {}).values():
        if definition.get("type") == "object":
            definition["additionalProperties"] = False
    schema["additionalProperties"] = False
    return schema


async def generate_concept(client: AsyncOpenAI, brief: Brief) -> Concept:
    response = await client.responses.create(
        model=TEXT_MODEL,
        instructions=(
            "You are a senior integrated creative director. Turn the supplied brief into one "
            "sharp, specific, executable campaign direction. Never invent product claims. Return "
            "exactly 3 meaningfully different copy variants, 6-8 ordered checklist items, and "
            "exactly 3 detailed, production-ready image prompts. Image prompts must describe the "
            "same visual world, include composition and lighting, avoid logos and text in-image, "
            "and account for the requested channels. Keep body copy under 45 words."
        ),
        input=brief.model_dump_json(),
        text={
            "format": {
                "type": "json_schema",
                "name": "campaign_concept",
                "strict": True,
                "schema": _concept_schema(),
            }
        },
    )
    return Concept.model_validate_json(response.output_text)


async def generate_image(client: AsyncOpenAI, prompt: str) -> str:
    response = await client.responses.create(
        model=TEXT_MODEL,
        input=(
            "Create a polished campaign key visual from this art direction. Do not render words, "
            f"letters, logos, or watermarks. Art direction: {prompt}"
        ),
        tools=[{
            "type": "image_generation",
            "model": IMAGE_MODEL,
            "size": "1536x1024",
            "quality": "medium",
            "output_format": "webp",
        }],
        tool_choice={"type": "image_generation"},
    )
    calls = [item for item in response.output if item.type == "image_generation_call"]
    if not calls or not calls[0].result:
        raise RuntimeError("The image model returned no image data.")
    # Validate base64 before passing it back as a browser-safe data URL.
    base64.b64decode(calls[0].result, validate=True)
    return f"data:image/webp;base64,{calls[0].result}"


@app.post("/api/campaigns", response_model=CampaignResponse)
async def create_campaign(brief: Brief) -> CampaignResponse:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "OPENAI_API_KEY is not configured on the server.")
    try:
        client = AsyncOpenAI()
        concept = await generate_concept(client, brief)
        # Independent visual studies run concurrently to avoid multiplying request latency.
        images = await asyncio.gather(
            *(generate_image(client, prompt) for prompt in concept.image_prompts[:_image_count()])
        )
        return CampaignResponse(**concept.model_dump(), images=images)
    except HTTPException:
        raise
    except Exception as exc:
        # Keep provider internals and potentially sensitive request details out of the client.
        raise HTTPException(502, "Campaign generation failed. Please retry in a moment.") from exc
