"""The newsroom workflow graph (TECH_PLAN 1.7), one run per moment.

    ingest -> scout -switch-> fast_line -> factcheck -> director -> cuebus
                           -> proposer -> rollout -> tactician -> narrator -> factcheck -+-> director
                                                                  ^-- rejected, attempt<3 -+
                           -> panel -> factcheck;  -> fourth_official -> director
                           -> recap -> factcheck;  default -> drop

`build_workflow(deps)` wires the default executors; `overrides` swaps any of them by id (tests, later tickets).
Executor ids never change, so checkpoints stay restorable across those swaps.
"""

from __future__ import annotations

from agent_framework import Case, Default, Executor, Workflow, WorkflowBuilder

from newsroom.executors.base import Deps
from newsroom.messages import Draft, Routed

WORKFLOW_NAME = "newsroom"
EXECUTOR_IDS = ("ingest", "scout", "fast_line", "proposer", "rollout", "tactician", "narrator", "factcheck",
                "panel", "fourth_official", "recap", "director", "cuebus", "drop")


def is_fast(m: Routed) -> bool:
    return m.branch == "fast"


def is_explained(m: Routed) -> bool:
    return m.branch == "explained"


def is_panel(m: Routed) -> bool:
    return m.branch == "panel"


def is_referee(m: Routed) -> bool:
    return m.branch == "referee"


def is_recap(m: Routed) -> bool:
    return m.branch == "recap"


def needs_rewrite(m: Draft) -> bool:
    return not m.verified and m.attempt < 3


def ready_for_director(m: Draft) -> bool:
    return m.verified or m.attempt >= 3


def default_executors(deps: Deps) -> dict[str, Executor]:
    """The executor for each id. Real implementations replace the stubs ticket by ticket."""
    from newsroom.executors import stubs
    from newsroom.executors.drop import DropExecutor
    from newsroom.executors.ingest import IngestExecutor

    factories = {
        "ingest": IngestExecutor, "scout": stubs.StubScout, "fast_line": stubs.StubFastLine,
        "proposer": stubs.StubProposer, "rollout": stubs.StubRollout, "tactician": stubs.StubTactician,
        "narrator": stubs.StubNarrator, "factcheck": stubs.StubFactCheck, "panel": stubs.StubPanel,
        "fourth_official": stubs.StubFourthOfficial, "recap": stubs.StubRecap, "director": stubs.StubDirector,
        "cuebus": stubs.StubCueBus, "drop": DropExecutor,
    }
    for name, factory in _real_executors().items():
        factories[name] = factory
    return {name: factory(name, deps) for name, factory in factories.items()}


def _real_executors() -> dict:
    """Real executors that exist so far; each later ticket adds its line here."""
    from newsroom.cuebus import CueBus
    from newsroom.executors.director import DirectorExecutor
    from newsroom.executors.factcheck import FactCheckExecutor
    from newsroom.executors.fast_line import FastLineExecutor
    from newsroom.executors.narrator import NarratorExecutor
    from newsroom.executors.proposer import ProposerExecutor
    from newsroom.executors.rollout import RolloutExecutor
    from newsroom.executors.scout import ScoutExecutor
    from newsroom.executors.tactician import TacticianExecutor

    return {"factcheck": FactCheckExecutor, "narrator": NarratorExecutor, "fast_line": FastLineExecutor,
            "director": DirectorExecutor, "cuebus": CueBus, "scout": ScoutExecutor,
            "proposer": ProposerExecutor, "rollout": RolloutExecutor, "tactician": TacticianExecutor}


def build_workflow(deps: Deps, storage=None, overrides: dict[str, Executor] | None = None,
                   max_iterations: int = 100) -> Workflow:
    ex = default_executors(deps)
    ex.update(overrides or {})
    missing = set(EXECUTOR_IDS) - set(ex)
    if missing:
        raise ValueError(f"missing executors: {sorted(missing)}")
    return (
        WorkflowBuilder(start_executor=ex["ingest"], checkpoint_storage=storage, name=WORKFLOW_NAME,
                        max_iterations=max_iterations)
        .add_edge(ex["ingest"], ex["scout"])
        .add_switch_case_edge_group(ex["scout"], [
            Case(condition=is_fast, target=ex["fast_line"]),
            Case(condition=is_explained, target=ex["proposer"]),
            Case(condition=is_panel, target=ex["panel"]),
            Case(condition=is_referee, target=ex["fourth_official"]),
            Case(condition=is_recap, target=ex["recap"]),
            Default(target=ex["drop"]),
        ])
        .add_edge(ex["fast_line"], ex["factcheck"])
        .add_edge(ex["proposer"], ex["rollout"])
        .add_edge(ex["rollout"], ex["tactician"])
        .add_edge(ex["tactician"], ex["narrator"])
        .add_edge(ex["narrator"], ex["factcheck"])
        .add_edge(ex["factcheck"], ex["narrator"], condition=needs_rewrite)
        .add_edge(ex["factcheck"], ex["director"], condition=ready_for_director)
        .add_edge(ex["panel"], ex["factcheck"])
        .add_edge(ex["fourth_official"], ex["director"])
        .add_edge(ex["recap"], ex["factcheck"])
        .add_edge(ex["director"], ex["cuebus"])
        .build()
    )
