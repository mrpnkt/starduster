"""Taxonomy parsing and validation.

A malformed taxonomy must fail loudly: silently accepting one would mis-file
the whole corpus and cost a full reclassify to fix.
"""

import pytest

from starduster.taxonomy import (
    TaxonomyError,
    parse_taxonomy,
    taxonomy_to_dict,
)

VALID = {
    "version": "1",
    "groups": [{"id": "g1", "name": "Group One"}, {"id": "g2", "name": "Group Two"}],
    "categories": [
        {"id": "c1", "name": "Cat One", "parent": "g1",
         "definition": "first", "disambiguation": ""},
        {"id": "c2", "name": "Cat Two", "parent": "g2",
         "definition": "second", "disambiguation": "prefer c1 when local"},
    ],
}


class TestParse:
    def test_parses_valid_taxonomy(self):
        tax = parse_taxonomy(VALID)
        assert tax.version == "1"
        assert tax.leaf_ids == ("c1", "c2")
        assert tax.category("c2").disambiguation == "prefer c1 when local"

    def test_children_of_group(self):
        assert [c.id for c in parse_taxonomy(VALID).children_of("g1")] == ["c1"]

    def test_unknown_category_lookup_returns_none(self):
        assert parse_taxonomy(VALID).category("nope") is None

    def test_disambiguation_defaults_to_empty(self):
        data = {**VALID, "categories": [
            {"id": "c1", "name": "C", "parent": "g1", "definition": "d"}]}
        assert parse_taxonomy(data).category("c1").disambiguation == ""

    def test_round_trips_through_dict(self):
        tax = parse_taxonomy(VALID)
        assert parse_taxonomy(taxonomy_to_dict(tax)) == tax


class TestValidation:
    def test_rejects_duplicate_category_ids(self):
        data = {**VALID, "categories": [
            {"id": "dup", "name": "A", "parent": "g1", "definition": "d"},
            {"id": "dup", "name": "B", "parent": "g2", "definition": "d"},
        ]}
        with pytest.raises(TaxonomyError, match="[Dd]uplicate"):
            parse_taxonomy(data)

    def test_rejects_duplicate_group_ids(self):
        data = {**VALID, "groups": [
            {"id": "g1", "name": "A"}, {"id": "g1", "name": "B"}]}
        with pytest.raises(TaxonomyError, match="[Dd]uplicate"):
            parse_taxonomy(data)

    def test_rejects_category_with_unknown_parent(self):
        """An orphan is invisible in the sidebar — its repos would vanish."""
        data = {**VALID, "categories": [
            {"id": "c1", "name": "C", "parent": "ghost", "definition": "d"}]}
        with pytest.raises(TaxonomyError, match="ghost"):
            parse_taxonomy(data)

    def test_rejects_empty_categories(self):
        with pytest.raises(TaxonomyError, match="[Nn]o categories"):
            parse_taxonomy({**VALID, "categories": []})

    def test_rejects_missing_version(self):
        data = {k: v for k, v in VALID.items() if k != "version"}
        with pytest.raises(TaxonomyError, match="version"):
            parse_taxonomy(data)

    def test_rejects_ids_reserved_by_the_site(self):
        """`__none` marks unsorted repos in the UI."""
        data = {**VALID, "categories": [
            {"id": "__none", "name": "C", "parent": "g1", "definition": "d"}]}
        with pytest.raises(TaxonomyError, match="reserved"):
            parse_taxonomy(data)

    def test_rejects_blank_category_id(self):
        data = {**VALID, "categories": [
            {"id": "", "name": "C", "parent": "g1", "definition": "d"}]}
        with pytest.raises(TaxonomyError):
            parse_taxonomy(data)

    def test_rejects_non_mapping(self):
        with pytest.raises(TaxonomyError):
            parse_taxonomy([1, 2, 3])

    def test_reports_group_with_no_categories(self):
        """An empty group renders as a dead sidebar heading."""
        data = {**VALID, "categories": [
            {"id": "c1", "name": "C", "parent": "g1", "definition": "d"}]}
        with pytest.raises(TaxonomyError, match="g2"):
            parse_taxonomy(data, strict=True)

    def test_empty_group_tolerated_when_not_strict(self):
        data = {**VALID, "categories": [
            {"id": "c1", "name": "C", "parent": "g1", "definition": "d"}]}
        assert parse_taxonomy(data, strict=False).leaf_ids == ("c1",)
