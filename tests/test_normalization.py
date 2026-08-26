from __future__ import annotations

import unittest

from takhrij.normalization import (
    expand_orthographic_variants,
    normalize_token,
    tokenize_with_offsets,
)


class NormalizationTests(unittest.TestCase):
    def test_diacritics_and_tatweel_are_removed(self):
        self.assertEqual(normalize_token("التَّـخْرِيج"), "التخريج")

    def test_ta_marbuta_and_ha_remain_distinct(self):
        self.assertNotEqual(normalize_token("مدرسة"), normalize_token("مدرسه"))

    def test_offsets_point_into_raw_unicode_text(self):
        text = "قبلُ التَّخْرِيج، وبعده"
        tokens = tokenize_with_offsets(text)
        self.assertEqual([item[0] for item in tokens], ["قبلُ", "التَّخْرِيج", "وبعده"])
        for token, start, end in tokens:
            self.assertEqual(text[start:end], token)

    def test_spelling_expansion_is_enumerated_not_collapsed(self):
        variants = expand_orthographic_variants("إلى")
        self.assertIn("إلى", variants)
        self.assertIn("الي", variants)
        self.assertNotIn("إله", variants)

    def test_definite_article_alef_is_not_mutated(self):
        variants = expand_orthographic_variants("بالتخريج")
        self.assertEqual(variants, ["بالتخريج"])
        self.assertNotIn("بألتخريج", variants)

    def test_suffix_alefs_are_never_treated_as_lexical_alef_seats(self):
        tanween = expand_orthographic_variants("تخريجاً")
        unmarked_accusative = expand_orthographic_variants("تخريجا")
        feminine_plural = expand_orthographic_variants("التخريجات")
        pronoun = expand_orthographic_variants("تخريجنا")
        feminine_pronoun = expand_orthographic_variants("تخريجها")
        dual = expand_orthographic_variants("تخريجان")
        dual_with_pronoun = expand_orthographic_variants("تخريجانا")
        plural_with_pronoun = expand_orthographic_variants("تخريجاته")
        plural_with_feminine_pronoun = expand_orthographic_variants("تخريجاتها")

        self.assertNotIn("تخريجأً", tanween)
        self.assertNotIn("تخريجأ", unmarked_accusative)
        self.assertNotIn("التخريجأت", feminine_plural)
        self.assertNotIn("تخريجنأ", pronoun)
        self.assertNotIn("تخريجهأ", feminine_pronoun)
        self.assertNotIn("تخريجأن", dual)
        self.assertNotIn("تخريجأنا", dual_with_pronoun)
        self.assertNotIn("تخريجأته", plural_with_pronoun)
        self.assertNotIn("تخريجأتها", plural_with_feminine_pronoun)
        self.assertEqual(tanween, ["تخريجاً", "تخريجا"])
        self.assertEqual(unmarked_accusative, ["تخريجا"])
        self.assertEqual(feminine_plural, ["التخريجات"])
        self.assertEqual(pronoun, ["تخريجنا"])
        self.assertEqual(feminine_pronoun, ["تخريجها"])
        self.assertEqual(dual, ["تخريجان"])
        self.assertEqual(dual_with_pronoun, ["تخريجانا"])
        self.assertEqual(plural_with_pronoun, ["تخريجاته"])
        self.assertEqual(plural_with_feminine_pronoun, ["تخريجاتها"])

    def test_lexical_alef_still_expands_before_a_protected_suffix(self):
        variants = expand_orthographic_variants("إشارات")
        self.assertIn("اشارات", variants)
        self.assertIn("إشارات", variants)
        self.assertNotIn("أشارات", variants)
        self.assertNotIn("آشارات", variants)
        self.assertNotIn("إشأرات", variants)

    def test_plain_lexical_alef_never_acquires_a_hamza_seat(self):
        variants = expand_orthographic_variants("تخاريج")
        self.assertEqual(variants, ["تخاريج"])
        self.assertNotIn("تخأريج", variants)
        self.assertNotIn("تخإريج", variants)
        self.assertNotIn("تخآريج", variants)

    def test_pronominal_yeh_is_never_changed_to_alef_maqsura(self):
        variants = expand_orthographic_variants("تخريجي")
        self.assertEqual(variants, ["تخريجي"])
        self.assertNotIn("تخريجى", variants)


if __name__ == "__main__":
    unittest.main()
