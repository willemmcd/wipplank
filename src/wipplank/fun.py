"""Fun layer - this is what makes it not boring email."""
import random

from rich.console import Console
from rich.panel import Panel

console = Console()

MOODS = [
    "Inbox Zero Hero incoming...",
    "Summoning email gremlins...",
    "Polishing the inbox disco ball...",
    "Bribing the spam filter with cookies...",
    "Teaching pigeons to deliver email...",
]

CELEBRATIONS = [
    "🎉 INBOX ZERO! Do a little dance!",
    "🦄 Your inbox fears you now.",
    "🚀 Email conquered. What's next?",
    "🍩 You deserve a donut.",
]

BOREDOM_PATROL = [
    "boring",
    "synergy",
    "circling back",
    "per my last email",
]


def random_mood() -> str:
    return random.choice(MOODS)


def celebrate():
    console.print(Panel(random.choice(CELEBRATIONS), style="bold magenta"))


def boring_patrol(subject: str) -> str | None:
    low = subject.lower()
    for phrase in BOREDOM_PATROL:
        if phrase in low:
            return f"⚠️  Boredom Patrol: subject contains '{phrase}'. Spice it up!"
    return None


def banner():
    console.print(
        Panel.fit(
            "[bold cyan]Wipplank[/] ✉️  [magenta]no boring email allowed[/]",
            border_style="cyan",
        )
    )
