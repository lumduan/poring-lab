"""The user-managed environment store's rules for a person's DECLARATION (ADR-0023 decision 1, Batt
2026-11-12: "don't lock; write a warning"). The store's other rules are tested through the Settings
routes (test_settings.py); these are the pure rules: what a declaration is, who may carry one, how a
change is classified, and what the interlock sees."""

import pytest
from pydantic import ValidationError

from poring_backend import envstore
from poring_backend.interlock import EnvironmentsConfig

STATEMENT = "The class server's owner, our teacher, runs it for bots."


def declaration(statement: str = STATEMENT, **over: str) -> envstore.Declaration:
    fields = {"at": "2026-11-12T07:03:41.123456+00:00", "peer": "192.168.1.50",
              "statement": statement} | over  # fmt: skip
    return envstore.Declaration(**fields)


def entry(env_id: str = "class", type_: envstore.EnvType = "allowed",
          declared: envstore.Declaration | None = None) -> envstore.EnvEntry:  # fmt: skip
    port = 6900 if type_ == "allowed" else None
    return envstore.EnvEntry(
        id=env_id, name=env_id.title(), type=type_, declared=declared,
        servers=[envstore.ServerEntry(host="203.0.113.7", port=port)],
    )  # fmt: skip


def es(*envs: envstore.EnvEntry) -> envstore.EnvSet:
    return envstore.EnvSet(environments=list(envs))


def test_a_declaration_is_the_persons_words_with_the_backends_time_and_peer() -> None:
    d = declaration()
    assert (d.peer, d.statement) == ("192.168.1.50", STATEMENT)
    with pytest.raises(ValidationError):
        declaration("too short")  # 9 characters: below MIN_REASON
    with pytest.raises(ValidationError):
        declaration("x" * (envstore.MAX_STATEMENT + 1))
    with pytest.raises(ValidationError):
        declaration(at="2026-11-12T07:03:41")  # no UTC offset
    with pytest.raises(ValidationError):
        declaration(at="yesterday")
    with pytest.raises(ValidationError):
        declaration(peer="")
    with pytest.raises(ValidationError):
        envstore.Declaration.model_validate({**declaration().model_dump(), "verified": True})


def test_a_declaration_is_technical_never_shipped_and_never_imported() -> None:
    assert "declared" in envstore.TECHNICAL  # an import keeps the current one, never sets it
    shipped = EnvironmentsConfig.model_validate({
        "version": 1, "attestation_max_age_s": 10, "window_max_s": 120,
        "environments": [{"id": "lab", "status": "allowed", "adr": "x", "signals": ["session"]},
                         {"id": "community", "status": "pending", "adr": "x"}],
    })  # fmt: skip
    assert all(e.declared is None for e in envstore.from_defaults(shipped, "sha").environments)


@pytest.mark.parametrize("type_", ["forbidden", "pending"])
def test_only_an_allowed_environment_may_carry_one(type_: envstore.EnvType) -> None:
    assert envstore.validate(es(entry(declared=declaration())), {}) is None
    bad = es(entry("other", type_, declared=declaration()))
    assert envstore.validate(bad, {}) == ("declaration_not_allowed_here", "other")


def test_the_interlock_sees_a_declaration_on_allowed_environments_only() -> None:
    stored = es(entry("declared", declared=declaration()), entry("plain"),
                entry("odd", "pending", declared=declaration()))  # fmt: skip
    seen = {e.id: e.declared for e in envstore.to_config(stored).environments}
    assert seen == {"declared": True, "plain": False, "odd": False}


def test_declaring_is_its_own_kind_and_withdrawing_is_easy() -> None:
    plain = es(entry())
    declared = es(entry(declared=declaration()))
    [c] = envstore.classify(plain, declared)
    assert (c.kind, c.action, c.env_id, c.note) == ("declare", "declare", "class", STATEMENT)
    assert "not verified" in c.text
    assert envstore.classify(declared, declared) == []  # kept as it was: no change
    other = "The owner wrote it on the server's home page."
    [c] = envstore.classify(declared, es(entry(declared=declaration(other))))
    assert (c.kind, c.action, c.note) == ("declare", "declare", other)
    restamped = es(entry(declared=declaration(at="2026-11-12T08:00:00+00:00")))
    assert [c.kind for c in envstore.classify(declared, restamped)] == ["declare"]
    [c] = envstore.classify(declared, plain)
    assert (c.kind, c.action, c.note) == ("easy", "withdraw", STATEMENT)


def test_a_new_environment_with_a_declaration_and_a_type_change_that_drops_it() -> None:
    kinds = {(c.action, c.kind) for c in envstore.classify(es(), es(entry(declared=declaration())))}
    assert kinds == {("env_create", "normal"), ("server_add", "normal"), ("declare", "declare")}
    dropped = es(entry(type_="pending"))  # the routes drop it when the type leaves allowed
    dropped.environments[0].servers = entry().servers
    kinds = {(c.action, c.kind)
             for c in envstore.classify(es(entry(declared=declaration())), dropped)}  # fmt: skip
    assert kinds == {("env_type", "easy"), ("withdraw", "easy")}  # both tightening


def test_an_attested_environment_takes_no_declaration() -> None:
    """The parent's review (2026-11-12): the lab's packet-verified environments keep their check
    alone; a declaration on one (a crafted PUT: the page never offers it) is refused."""
    lab = entry("lab-rathena", declared=declaration()).model_copy(
        update={"signals": ["lab_host", "session"]}
    )
    assert envstore.validate(es(lab), {}) == ("declaration_not_for_attested", "lab-rathena")
    assert (
        envstore.validate(es(entry("class", declared=declaration())), {}) is None
    )  # no signals: ok
