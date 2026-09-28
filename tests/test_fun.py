from wipplank import fun


def test_random_mood_and_boring_patrol():
    assert fun.random_mood() in fun.MOODS
    assert "synergy" in (fun.boring_patrol("Synergy plan") or "")
    assert fun.boring_patrol("Rocket launch") is None


def test_banner_and_celebrate(capsys):
    fun.banner()
    fun.celebrate()
    out = capsys.readouterr().out
    assert "Wipplank" in out
