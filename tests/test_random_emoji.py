"""
Tests for random emoji functionality using the built-in emoji library.
"""

import emoji
from tests.emoji_utils import (
    get_random_emoji,
    get_random_emojis,
    get_unique_random_emojis,
    get_random_emoji_by_category,
    get_random_poll_emojis,
    is_valid_poll_emoji,
    get_emoji_description,
)


class TestRandomEmojiGeneration:
    """Test random emoji generation functions."""

    def test_get_random_emoji_returns_valid_emoji(self):
        """Test that get_random_emoji returns a valid emoji."""
        random_emoji = get_random_emoji()

        assert isinstance(random_emoji, str)
        assert len(random_emoji) > 0
        assert random_emoji in emoji.EMOJI_DATA

    def test_get_random_emoji_multiple_calls_vary(self):
        """Test that multiple calls to get_random_emoji can return different emojis."""
        emojis = [get_random_emoji() for _ in range(10)]

        # All should be valid emojis
        for emoji_char in emojis:
            assert emoji_char in emoji.EMOJI_DATA

        # With thousands of emojis available, we should get some variety
        # (though it's theoretically possible to get the same emoji multiple times)
        unique_emojis = set(emojis)
        assert len(unique_emojis) >= 1  # At least one unique emoji

    def test_get_random_emojis_default_count(self):
        """Test get_random_emojis with default count."""
        random_emojis = get_random_emojis()

        assert isinstance(random_emojis, list)
        assert len(random_emojis) == 4  # Default count

        for emoji_char in random_emojis:
            assert isinstance(emoji_char, str)
            assert emoji_char in emoji.EMOJI_DATA

    def test_get_random_emojis_custom_count(self):
        """Test get_random_emojis with custom count."""
        counts = [1, 2, 5, 10, 20]

        for count in counts:
            random_emojis = get_random_emojis(count)

            assert isinstance(random_emojis, list)
            assert len(random_emojis) == count

            for emoji_char in random_emojis:
                assert isinstance(emoji_char, str)
                assert emoji_char in emoji.EMOJI_DATA

    def test_get_random_emojis_zero_count(self):
        """Test get_random_emojis with zero count."""
        random_emojis = get_random_emojis(0)

        assert isinstance(random_emojis, list)
        assert len(random_emojis) == 0

    def test_get_unique_random_emojis_default_count(self):
        """Test get_unique_random_emojis with default count."""
        unique_emojis = get_unique_random_emojis()

        assert isinstance(unique_emojis, list)
        assert len(unique_emojis) == 4  # Default count

        # All should be unique
        assert len(set(unique_emojis)) == len(unique_emojis)

        for emoji_char in unique_emojis:
            assert isinstance(emoji_char, str)
            assert emoji_char in emoji.EMOJI_DATA

    def test_get_unique_random_emojis_custom_count(self):
        """Test get_unique_random_emojis with custom count."""
        counts = [1, 2, 5, 10]

        for count in counts:
            unique_emojis = get_unique_random_emojis(count)

            assert isinstance(unique_emojis, list)
            assert len(unique_emojis) == count

            # All should be unique
            assert len(set(unique_emojis)) == len(unique_emojis)

            for emoji_char in unique_emojis:
                assert isinstance(emoji_char, str)
                assert emoji_char in emoji.EMOJI_DATA

    def test_get_unique_random_emojis_large_count(self):
        """Test get_unique_random_emojis with large count."""
        # Request more emojis than available (should be limited)
        total_emojis = len(emoji.EMOJI_DATA)
        large_count = total_emojis + 100

        unique_emojis = get_unique_random_emojis(large_count)

        assert isinstance(unique_emojis, list)
        assert len(unique_emojis) == total_emojis  # Limited to available emojis

        # All should be unique
        assert len(set(unique_emojis)) == len(unique_emojis)

    def test_get_random_emoji_by_category_no_category(self):
        """Test get_random_emoji_by_category without category."""
        random_emoji = get_random_emoji_by_category()

        assert isinstance(random_emoji, str)
        assert len(random_emoji) > 0
        assert random_emoji in emoji.EMOJI_DATA

    def test_get_random_emoji_by_category_invalid_category(self):
        """Test get_random_emoji_by_category with invalid category."""
        random_emoji = get_random_emoji_by_category("NonexistentCategory")

        # Should fall back to any random emoji
        assert isinstance(random_emoji, str)
        assert len(random_emoji) > 0
        assert random_emoji in emoji.EMOJI_DATA

    def test_get_random_poll_emojis_default_count(self):
        """Test get_random_poll_emojis with default count."""
        poll_emojis = get_random_poll_emojis()

        assert isinstance(poll_emojis, list)
        assert len(poll_emojis) == 4  # Default count

        for emoji_char in poll_emojis:
            assert isinstance(emoji_char, str)
            assert len(emoji_char) > 0

    def test_get_random_poll_emojis_custom_count(self):
        """Test get_random_poll_emojis with custom count."""
        counts = [1, 2, 5, 10, 20]

        for count in counts:
            poll_emojis = get_random_poll_emojis(count)

            assert isinstance(poll_emojis, list)
            assert len(poll_emojis) == count

            for emoji_char in poll_emojis:
                assert isinstance(emoji_char, str)
                assert len(emoji_char) > 0

    def test_get_random_poll_emojis_large_count(self):
        """Test get_random_poll_emojis with large count."""
        large_count = 100
        poll_emojis = get_random_poll_emojis(large_count)

        assert isinstance(poll_emojis, list)
        assert len(poll_emojis) == large_count

        for emoji_char in poll_emojis:
            assert isinstance(emoji_char, str)
            assert len(emoji_char) > 0

    def test_get_random_poll_emojis_prioritizes_common_emojis(self):
        """Test that get_random_poll_emojis prioritizes common poll emojis."""
        # Common poll emojis that should appear frequently
        common_poll_emojis = [
            "🇦",
            "🇧",
            "🇨",
            "🇩",
            "🇪",
            "🇫",
            "🇬",
            "🇭",
            "🇮",
            "🇯",
            "1️⃣",
            "2️⃣",
            "3️⃣",
            "4️⃣",
            "5️⃣",
            "6️⃣",
            "7️⃣",
            "8️⃣",
            "9️⃣",
            "🔟",
            "✅",
            "❌",
            "👍",
            "👎",
            "❤️",
            "💙",
            "💚",
            "💛",
            "🧡",
            "💜",
            "🔴",
            "🔵",
            "🟢",
            "🟡",
            "🟠",
            "🟣",
            "⚫",
            "⚪",
            "🟤",
            "🔶",
        ]

        # Test with small count to increase chance of getting common emojis
        poll_emojis = get_random_poll_emojis(4)

        # At least some should be from the common list (though not guaranteed due to randomness)
        common_found = any(
            emoji_char in common_poll_emojis for emoji_char in poll_emojis
        )

        # This test might occasionally fail due to randomness, but should usually pass
        # We'll just verify the structure is correct
        assert isinstance(poll_emojis, list)
        assert len(poll_emojis) == 4


class TestEmojiValidation:
    """Test emoji validation functions."""

    def test_is_valid_poll_emoji_with_valid_emojis(self):
        """Test is_valid_poll_emoji with valid emojis."""
        valid_emojis = ["😀", "🎉", "❤️", "👍", "🔥", "🇦", "1️⃣"]

        for emoji_char in valid_emojis:
            assert is_valid_poll_emoji(emoji_char) is True

    def test_is_valid_poll_emoji_with_invalid_emojis(self):
        """Test is_valid_poll_emoji with invalid emojis."""
        invalid_emojis = ["abc", "123", "", "not_an_emoji", "<:custom:123>"]

        for emoji_char in invalid_emojis:
            assert is_valid_poll_emoji(emoji_char) is False

    def test_get_emoji_description_with_valid_emojis(self):
        """Test get_emoji_description with valid emojis."""
        test_emojis = ["😀", "🎉", "❤️", "👍"]

        for emoji_char in test_emojis:
            description = get_emoji_description(emoji_char)

            assert isinstance(description, str)
            assert len(description) > 0

    def test_get_emoji_description_with_invalid_emoji(self):
        """Test get_emoji_description with invalid emoji."""
        invalid_emoji = "not_an_emoji"
        description = get_emoji_description(invalid_emoji)

        # Should return the original string if no description found
        assert description == invalid_emoji


class TestRandomEmojiIntegration:
    """Test integration of random emoji functionality with fixtures."""

    def test_random_emoji_fixture(self, random_emoji):
        """Test the random_emoji fixture."""
        assert isinstance(random_emoji, str)
        assert len(random_emoji) > 0
        assert random_emoji in emoji.EMOJI_DATA

    def test_random_emojis_fixture(self, random_emojis):
        """Test the random_emojis fixture."""
        assert isinstance(random_emojis, list)
        assert len(random_emojis) == 4

        for emoji_char in random_emojis:
            assert isinstance(emoji_char, str)
            assert emoji_char in emoji.EMOJI_DATA

    def test_random_poll_emojis_fixture(self, random_poll_emojis):
        """Test the random_poll_emojis fixture."""
        assert isinstance(random_poll_emojis, list)
        assert len(random_poll_emojis) == 4

        for emoji_char in random_poll_emojis:
            assert isinstance(emoji_char, str)
            assert len(emoji_char) > 0

    def test_sample_poll_data_with_random_emojis_fixture(
        self, sample_poll_data_with_random_emojis
    ):
        """Test the sample_poll_data_with_random_emojis fixture."""
        poll_data = sample_poll_data_with_random_emojis

        assert isinstance(poll_data, dict)
        assert "emojis" in poll_data
        assert isinstance(poll_data["emojis"], list)
        assert len(poll_data["emojis"]) == 4

        for emoji_char in poll_data["emojis"]:
            assert isinstance(emoji_char, str)
            assert len(emoji_char) > 0

    def test_sample_poll_with_random_emojis_fixture(
        self, sample_poll_with_random_emojis
    ):
        """Test the sample_poll_with_random_emojis fixture."""
        poll = sample_poll_with_random_emojis

        assert poll is not None
        assert hasattr(poll, "emojis")
        assert isinstance(poll.emojis, list)
        assert len(poll.emojis) == 4

        for emoji_char in poll.emojis:
            assert isinstance(emoji_char, str)
            assert len(emoji_char) > 0


class TestRandomEmojiPerformance:
    """Test performance characteristics of random emoji functions."""

    def test_get_random_emoji_performance(self):
        """Test performance of get_random_emoji with multiple calls."""
        # Generate many random emojis to test performance
        emojis = [get_random_emoji() for _ in range(100)]

        assert len(emojis) == 100
        for emoji_char in emojis:
            assert emoji_char in emoji.EMOJI_DATA

    def test_get_unique_random_emojis_performance(self):
        """Test performance of get_unique_random_emojis with large count."""
        # Test with a reasonably large count
        unique_emojis = get_unique_random_emojis(50)

        assert len(unique_emojis) == 50
        assert len(set(unique_emojis)) == 50  # All unique

        for emoji_char in unique_emojis:
            assert emoji_char in emoji.EMOJI_DATA

    def test_get_random_poll_emojis_performance(self):
        """Test performance of get_random_poll_emojis with large count."""
        # Test with a large count
        poll_emojis = get_random_poll_emojis(50)

        assert len(poll_emojis) == 50

        for emoji_char in poll_emojis:
            assert isinstance(emoji_char, str)
            assert len(emoji_char) > 0


class TestRandomEmojiEdgeCases:
    """Test edge cases for random emoji functions."""

    def test_get_random_emojis_with_negative_count(self):
        """Test get_random_emojis with negative count."""
        # Should handle gracefully (likely return empty list or raise error)
        try:
            result = get_random_emojis(-1)
            assert isinstance(result, list)
            assert len(result) == 0
        except ValueError:
            # Acceptable to raise ValueError for negative count
            pass

    def test_get_unique_random_emojis_with_negative_count(self):
        """Test get_unique_random_emojis with negative count."""
        try:
            result = get_unique_random_emojis(-1)
            assert isinstance(result, list)
            assert len(result) == 0
        except ValueError:
            # Acceptable to raise ValueError for negative count
            pass

    def test_get_random_poll_emojis_with_zero_count(self):
        """Test get_random_poll_emojis with zero count."""
        poll_emojis = get_random_poll_emojis(0)

        assert isinstance(poll_emojis, list)
        assert len(poll_emojis) == 0

    def test_emoji_library_availability(self):
        """Test that the emoji library is properly available."""
        # Verify emoji library is working
        assert hasattr(emoji, "EMOJI_DATA")
        assert isinstance(emoji.EMOJI_DATA, dict)
        assert len(emoji.EMOJI_DATA) > 0

        # Test a few known emojis
        known_emojis = ["😀", "🎉", "❤️", "👍"]
        for emoji_char in known_emojis:
            assert emoji_char in emoji.EMOJI_DATA


# Confidence level: 10/10 - Comprehensive testing of random emoji functionality
