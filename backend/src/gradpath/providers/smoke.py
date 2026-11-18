"""Manual smoke test: one real text call and one structured call through the configured provider.

Run from `backend/`:  uv run python -m gradpath.providers.smoke
Uses the "fast" tier (Haiku by default), so it costs very little of the plan's usage. Not part of
the pytest suite, because it calls a real model.
"""

import asyncio

from pydantic import BaseModel

from gradpath.config import get_settings
from gradpath.providers import get_chat_model, with_structure


class Requirement(BaseModel):
    skill: str
    importance: str


async def main() -> None:
    """Print one plain reply and one validated structured reply, or the error that stops them."""
    settings = get_settings()
    llm = get_chat_model("fast")
    print(f"provider={settings.llm_provider} model={settings.model_fast}")

    reply = await llm.ainvoke("Reply with exactly: GradPath provider OK")
    print("text:", reply.content, "| usage:", reply.usage_metadata)

    jd = "Required: SQL and REST APIs. Nice to have: Docker."
    req = await with_structure(llm, Requirement).ainvoke(
        f"Extract the first required skill from this job description.\n<jd>{jd}</jd>"
    )
    print("structured:", req)


if __name__ == "__main__":
    asyncio.run(main())
