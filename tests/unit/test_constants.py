"""
Unit tests for constants module

Tests the update type normalization and review source resolution:
- normalize_update_type exact and fuzzy matching
- get_review_source_from_update_type classification
- Legacy format backward compatibility
"""
import pytest

from constants import (
    UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
    UPDATE_TYPE_STYLE_LEARNING,
    UPDATE_TYPE_EXPRESSION_LEARNING,
    UPDATE_TYPE_TRADITIONAL,
    LEGACY_UPDATE_TYPE_MAPPING,
    normalize_update_type,
    get_review_source_from_update_type,
)


@pytest.mark.unit
class TestNormalizeUpdateType:
    """Test normalize_update_type function."""

    def test_empty_input_returns_traditional(self):
        """Test empty or None input returns traditional type."""
        assert normalize_update_type("") == UPDATE_TYPE_TRADITIONAL
        assert normalize_update_type(None) == UPDATE_TYPE_TRADITIONAL

    def test_exact_match_progressive_learning(self):
        """Test exact match for progressive_learning legacy key."""
        result = normalize_update_type("progressive_learning")
        assert result == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING

    def test_exact_match_style_learning(self):
        """Test exact match for style_learning."""
        result = normalize_update_type("style_learning")
        assert result == UPDATE_TYPE_STYLE_LEARNING

    def test_exact_match_expression_learning(self):
        """Test exact match for expression_learning."""
        result = normalize_update_type("expression_learning")
        assert result == UPDATE_TYPE_EXPRESSION_LEARNING

    def test_legacy_chinese_progressive_style(self):
        """Test legacy Chinese format for progressive style analysis."""
        result = normalize_update_type("渐进式学习-风格分析")
        assert result == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING

    def test_legacy_chinese_progressive_persona(self):
        """Test legacy Chinese format for progressive persona update."""
        result = normalize_update_type("渐进式学习-人格更新")
        assert result == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING

    def test_fuzzy_match_chinese_progressive(self):
        """Test fuzzy match with Chinese progressive learning keyword."""
        result = normalize_update_type("渐进式学习-新类型")
        assert result == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING

    def test_fuzzy_match_english_progressive(self):
        """Test fuzzy match with English progressive keyword."""
        result = normalize_update_type("PROGRESSIVE_update")
        assert result == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING

    def test_unknown_type_returns_traditional(self):
        """Test unknown type returns traditional."""
        result = normalize_update_type("some_unknown_type")
        assert result == UPDATE_TYPE_TRADITIONAL

    def test_already_normalized_value(self):
        """Test passing an already normalized constant."""
        result = normalize_update_type(UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING)
        assert result == UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING


@pytest.mark.unit
class TestGetReviewSourceFromUpdateType:
    """Test get_review_source_from_update_type function."""

    def test_progressive_persona_learning_source(self):
        """Test progressive persona learning maps to persona_learning."""
        result = get_review_source_from_update_type(
            UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING
        )
        assert result == 'persona_learning'

    def test_style_learning_source(self):
        """Test style learning maps to style_learning."""
        result = get_review_source_from_update_type(UPDATE_TYPE_STYLE_LEARNING)
        assert result == 'style_learning'

    def test_expression_learning_source(self):
        """Test expression learning maps to persona_learning."""
        result = get_review_source_from_update_type(
            UPDATE_TYPE_EXPRESSION_LEARNING
        )
        assert result == 'persona_learning'

    def test_traditional_source(self):
        """Test traditional update maps to traditional."""
        result = get_review_source_from_update_type(UPDATE_TYPE_TRADITIONAL)
        assert result == 'traditional'

    def test_unknown_type_defaults_to_traditional(self):
        """Test unknown update type defaults to traditional source."""
        result = get_review_source_from_update_type("random_unknown_type")
        assert result == 'traditional'

    def test_legacy_format_normalization(self):
        """Test legacy Chinese format is normalized before classification."""
        result = get_review_source_from_update_type("渐进式学习-风格分析")
        assert result == 'persona_learning'

    def test_empty_string(self):
        """Test empty string defaults to traditional."""
        result = get_review_source_from_update_type("")
        assert result == 'traditional'


@pytest.mark.unit
class TestLegacyMapping:
    """Test legacy update type mapping completeness."""

    def test_all_legacy_keys_mapped(self):
        """Test all legacy keys exist in the mapping."""
        expected_keys = {
            "渐进式学习-风格分析",
            "渐进式学习-人格更新",
            "progressive_learning",
            "style_learning",
            "expression_learning",
        }

        assert set(LEGACY_UPDATE_TYPE_MAPPING.keys()) == expected_keys

    def test_all_legacy_values_are_valid_constants(self):
        """Test all legacy values map to valid update type constants."""
        valid_types = {
            UPDATE_TYPE_PROGRESSIVE_PERSONA_LEARNING,
            UPDATE_TYPE_STYLE_LEARNING,
            UPDATE_TYPE_EXPRESSION_LEARNING,
            UPDATE_TYPE_TRADITIONAL,
        }

        for value in LEGACY_UPDATE_TYPE_MAPPING.values():
            assert value in valid_types, f"Invalid mapping value: {value}"
