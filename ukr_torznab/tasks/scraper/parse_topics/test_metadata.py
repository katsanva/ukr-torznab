import os

# The package reads these settings on import.
for _name in ("DATABASE_URL", "TOLOKA_USERNAME", "TOLOKA_PASSWORD"):
    os.environ.setdefault(_name, "unused")

from ukr_torznab.models import Lang
from ukr_torznab.tasks.scraper.parse_topics.metadata import detect_languages


def test_language_name_wins_over_uk_flag():
    text = (
        "аудіо:\n"
        "мова: англійська ![](//img.hurtom.com/i/2018/08/uk-flag.gif)\n"
        "субтитри: (full)\n"
        "мова: українська ![](//img.hurtom.com/i/2016/07/ukraine-flag-anim.gif)\n"
    )
    assert detect_languages(text) == ({Lang.ENGLISH}, {Lang.UKRAINIAN})


def test_flag_alone_still_detects_language():
    text = "аудіо:\nмова: ![](//img.hurtom.com/i/2016/07/ukraine-flag-anim.gif)\n"
    assert detect_languages(text) == ({Lang.UKRAINIAN}, set())
