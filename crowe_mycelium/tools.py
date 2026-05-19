"""Mycology tool schemas for Crowe Logic tool-use training and inference."""
import json

TOOLS = [
    {
        "name": "compute_biological_efficiency",
        "description": "Calculate BE% = (wet_mushroom_yield_g / dry_substrate_g) * 100.",
        "parameters": {
            "type": "object",
            "properties": {
                "wet_mushroom_g": {"type": "number", "description": "Total wet harvested mushroom weight in grams."},
                "dry_substrate_g": {"type": "number", "description": "Dry substrate weight before hydration in grams."},
            },
            "required": ["wet_mushroom_g", "dry_substrate_g"],
        },
    },
    {
        "name": "recommend_substrate_recipe",
        "description": "Suggest a substrate recipe (ingredients, ratios, hydration, sterilization) for a given species and scale.",
        "parameters": {
            "type": "object",
            "properties": {
                "species": {"type": "string", "description": "Scientific or common name (e.g. 'Hericium erinaceus')."},
                "scale_kg": {"type": "number", "description": "Total dry substrate target in kg."},
                "available_materials": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["species"],
        },
    },
    {
        "name": "suggest_climate_setpoints",
        "description": "Return temperature, RH, CO2, and FAE setpoints for species at a given growth stage.",
        "parameters": {
            "type": "object",
            "properties": {
                "species": {"type": "string"},
                "stage": {"type": "string", "enum": ["colonization", "primordia", "pinning", "fruiting", "harvest"]},
            },
            "required": ["species", "stage"],
        },
    },
    {
        "name": "identify_contamination_from_photo",
        "description": "Vision tool: classify a likely contaminant (Trichoderma, cobweb, bacterial blotch, etc.) from an image.",
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Local path or URL to image of the suspected contamination."},
                "context": {"type": "string", "description": "Optional grower-provided context (species, days since inoc, etc.)."},
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "identify_species_from_photo",
        "description": "Vision tool: identify mushroom species from a photo of the fruit body or substrate.",
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string"},
                "location_hint": {"type": "string", "description": "Optional geographic region for prior weighting."},
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "lookup_species_profile",
        "description": "Retrieve a structured profile (taxonomy, substrates, climate, BE range, bioactives, edibility) for a species.",
        "parameters": {
            "type": "object",
            "properties": {
                "species": {"type": "string"},
            },
            "required": ["species"],
        },
    },
    {
        "name": "estimate_yield_timeline",
        "description": "Estimate days to colonization, pinning, first flush, and projected yield for a setup.",
        "parameters": {
            "type": "object",
            "properties": {
                "species": {"type": "string"},
                "substrate_dry_g": {"type": "number"},
                "temperature_c": {"type": "number"},
                "spawn_rate_pct": {"type": "number", "description": "Spawn-to-substrate ratio as percent."},
            },
            "required": ["species", "substrate_dry_g"],
        },
    },
    {
        "name": "query_user_grow_log",
        "description": "Query the user's personal grow log for past runs of a species, contamination history, yields.",
        "parameters": {
            "type": "object",
            "properties": {
                "species": {"type": "string"},
                "since_days": {"type": "integer", "description": "Look back this many days. Default 365."},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["species"],
        },
    },
    {
        "name": "search_recent_research",
        "description": "Search recent mycology / fungal-biotech literature (PubMed, arXiv, bioRxiv) for a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "description": "Default 5."},
                "since_year": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "call_quantum_molecular_sim",
        "description": "Run a VQE / quantum molecular simulation on a fungal bioactive compound (psilocybin, erinacine, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "compound": {"type": "string", "description": "Compound name or SMILES."},
                "method": {"type": "string", "enum": ["VQE", "QPE", "DFT"], "description": "Default VQE."},
                "basis": {"type": "string", "description": "Basis set (e.g. 'sto-3g', '6-31g')."},
            },
            "required": ["compound"],
        },
    },
    {
        "name": "compute_psilocybin_dosage_disclaimer",
        "description": "Return a harm-reduction disclaimer text for psilocybin dosing inquiries. Does NOT compute or recommend a dose.",
        "parameters": {
            "type": "object",
            "properties": {
                "jurisdiction": {"type": "string", "description": "User's region for jurisdiction-specific legal note."},
            },
            "required": [],
        },
    },
    {
        "name": "schedule_contamination_check",
        "description": "Schedule a recurring visual contamination check reminder for a specific block / tub / jar.",
        "parameters": {
            "type": "object",
            "properties": {
                "block_id": {"type": "string"},
                "interval_hours": {"type": "integer", "description": "Default 24."},
                "until_stage": {"type": "string", "enum": ["colonized", "pinning", "harvested"]},
            },
            "required": ["block_id"],
        },
    },
]


def tools_as_prompt_text() -> str:
    """Render TOOLS as a compact system-prompt block for tool-aware models."""
    lines = ["Available tools (call via <tool_call>{\"name\":..., \"arguments\":{...}}</tool_call>):"]
    for t in TOOLS:
        props = t["parameters"].get("properties", {})
        req = set(t["parameters"].get("required", []))
        args = ", ".join(
            f"{k}:{v.get('type','any')}{'*' if k in req else ''}" for k, v in props.items()
        )
        lines.append(f"- {t['name']}({args}) — {t['description']}")
    lines.append("(* = required). Emit ONE tool call per turn.")
    return "\n".join(lines)


def tools_as_json() -> str:
    return json.dumps(TOOLS, indent=2)
