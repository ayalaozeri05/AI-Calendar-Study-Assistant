"""Desktop styles and category colors."""

from pathlib import Path

CATEGORY_COLORS = {
    "Exam": {"bg": "#FFE1D4", "fg": "#9B3B2C", "accent": "#E8A090"},
    "Assignment": {"bg": "#DCE8FF", "fg": "#3D4A8A", "accent": "#8BB0E0"},
    "Project": {"bg": "#EEEAF8", "fg": "#5B4B8A", "accent": "#B8B0F0"},
    "Personal": {"bg": "#EEEAF8", "fg": "#5B4B8A", "accent": "#B8B0F0"},
    "Study": {"bg": "#DDF3E4", "fg": "#2F6F4E", "accent": "#8BC4A8"},
    "Class": {"bg": "#FFF1A8", "fg": "#7A6420", "accent": "#E0C84A"},
    "Meeting": {"bg": "#DDF3E4", "fg": "#2F6F4E", "accent": "#7DBFA0"},
    "Other": {"bg": "#F3F1EC", "fg": "#7A8090", "accent": "#C4BDB2"},
}


def load_app_stylesheet() -> str:
    return Path(__file__).with_name("app.qss").read_text(encoding="utf-8")


def category_style(category: str) -> dict[str, str]:
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["Other"])
