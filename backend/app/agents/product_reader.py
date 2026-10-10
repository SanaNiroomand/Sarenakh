"""Product from a link: read the page, extract its facts, turn them into the first message of the
profile chat. Pages are cached for a day and extractions by page content, so a repeat link is free."""

from __future__ import annotations

from ..config import Settings
from ..llm import LLM, Usage
from ..sources.web import Page
from .context import cache_get, cache_key, cache_put
from .prompts import PROMPT_VERSIONS, PRODUCT_PAGE_SYSTEM
from .schemas import ProductFacts


async def read_product(llm: LLM, settings: Settings, page: Page) -> tuple[ProductFacts, Usage | None]:
    """Returns (facts, usage); usage is None when the result came from the cache."""
    model = settings.profile_model
    key = cache_key("page_facts", model, PROMPT_VERSIONS["page"], page.for_model())
    if hit := cache_get(key):
        return ProductFacts(**hit[0]), None
    facts, usage = await llm.structured(
        model=model,
        instructions=PRODUCT_PAGE_SYSTEM,
        input=page.for_model(),
        output_type=ProductFacts,
        reasoning=settings.agent_reasoning,
        max_output_tokens=3000,
        cache_key="sarenakh-page",
    )
    cache_put(key, "page", facts.model_dump(), usage.cost_usd)
    return facts, usage


def facts_to_description(f: ProductFacts, url: str) -> str:
    """The extracted facts written as the owner's first message to the profile agent."""
    lines = [f"محصول: {f.product_name}" + (f" ({f.seller})" if f.seller else ""), f.summary]
    if f.audience:
        lines.append(f"برای: {f.audience}")
    if f.price:
        lines.append(f"قیمت: {f.price}")
    lines += [f"- {x}" for x in f.features]
    lines.append(f"(این مشخصات از صفحه محصول خوانده شد: {url})")
    return "\n".join(ln for ln in lines if ln.strip())[:4000]
