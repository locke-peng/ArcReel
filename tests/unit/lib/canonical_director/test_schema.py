from jsonschema import Draft202012Validator

from lib.canonical_director.schema import SCHEMA_ID, canonical_director_json_schema


def test_generated_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(canonical_director_json_schema())


def test_schema_id_is_versioned():
    assert SCHEMA_ID.endswith("/1.0.json")


def test_schema_forbids_unknown_root_properties():
    schema = canonical_director_json_schema()
    assert schema["additionalProperties"] is False
