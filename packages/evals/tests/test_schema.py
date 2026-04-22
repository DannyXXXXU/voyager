from voyager_evals.eric.schema import EricFixture, GoldHook, GoldSellingPoint


def test_fixture_roundtrip():
    f = EricFixture(
        id="f001",
        video_id="abc123",
        topic="Chengdu street food",
        difficulty="medium",
        content_type="food",
        holdout=False,
        gold_hooks=[GoldHook(text="spiciest noodles in china", aliases=["hottest noodles"])],
        gold_selling_points=[GoldSellingPoint(text="authentic sichuan", aliases=[])],
        transcript_sha256="deadbeef",
    )
    j = f.model_dump_json()
    f2 = EricFixture.model_validate_json(j)
    assert f2 == f
    assert f2.gold_hooks[0].aliases == ["hottest noodles"]


def test_fixture_defaults():
    f = EricFixture(
        id="f002",
        video_id="xyz",
        topic="t",
        difficulty="easy",
        content_type="vlog",
    )
    assert f.holdout is False
    assert f.gold_hooks == []
    assert f.gold_selling_points == []
