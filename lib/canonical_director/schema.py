"""JSON Schema generation for the CanonicalDirectorV1 contract."""

from __future__ import annotations

from lib.canonical_director.model import CANONICAL_DIRECTOR_SCHEMA_VERSION, CanonicalDirectorV1

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID = f"https://arcreel.dev/schemas/canonical-director/{CANONICAL_DIRECTOR_SCHEMA_VERSION}.json"


def canonical_director_json_schema() -> dict[str, object]:
    """Return the portable Draft 2020-12 schema derived from the Pydantic truth source."""

    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": SCHEMA_ID,
        **CanonicalDirectorV1.model_json_schema(),
    }


__all__ = ["JSON_SCHEMA_DIALECT", "SCHEMA_ID", "canonical_director_json_schema"]