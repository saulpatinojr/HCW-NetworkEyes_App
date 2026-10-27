"""The image build starts for every repository path the images copy in (owner decision 2026-10-27, answer `yes`).

``200-build-images.yml`` builds on a push to ``main`` only when a changed file matches ``on.push.paths``. For a
long time the list did not name ``packages/``, although the CLI and API Dockerfiles ``COPY`` the engine package
from there, so a commit that touched only the engine started no build and no image carried it. ``310`` is hit
twice by that gap: it reads the same list (through ``scripts/ci/paths_touch_build.py``) to decide whether a tagged
commit still counts as "built", so it would have accepted a tag on an engine-only commit and promoted an image that
did not contain the change. The gap was noted in ``CHANGELOG.md`` (rename step 4) and closed here.

This test closes the class of defect, not only the one path. It derives, from the Dockerfiles of the images that
workflow builds, every repository path they copy in, and asserts that the workflow's path filter covers each one.

How the paths are derived (so the test cannot agree with the workflow by accident):

* the builds are read from the workflow itself: every ``docker/build-push-action`` step, its ``context`` and its
  ``file`` (a matrix value is substituted), so a Dockerfile added to the workflow is checked without editing this file;
* each Dockerfile is read for its ``COPY`` and ``ADD`` instructions; a ``--from`` copy takes files from another stage
  or image, not from the repository, and is skipped; the sources are resolved against the build context;
* a source that is a directory counts as covered only when files at any depth below it are covered, which is what
  ``packages/**`` says and ``packages/network-assessment-azure-engine/pyproject.toml`` alone does not;
* the Dockerfile itself, and the ``.dockerignore`` of the context when there is one, are inputs too;
* the path filter of every event that has one is checked (today only ``push``: the workflow has no ``pull_request``
  trigger, and ``workflow_dispatch`` takes no path filter), using the glob rules of GitHub that ``paths_touch_build.py``
  implements, which is also what ``310`` and the ``tag-images`` job use, so the test and the release agree.

Anything the test cannot read stops it (a heredoc ``COPY``, a variable or a bracket in a source, a build whose
context is not a repository path) instead of being skipped. Local evidence: this proves what the files say. Whether
GitHub starts the workflow for a given push is only known from a real run.
"""

from __future__ import annotations

import importlib.util
import json
import posixpath
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / ".github" / "workflows" / "200-build-images.yml"
PATHS_HELPER = REPO_ROOT / "scripts" / "ci" / "paths_touch_build.py"

#: Jobs of 200 whose build context is made at run time (not a repository path), by name. The only one is the
#: rehearsal: a throwaway ``FROM scratch`` image written into the runner's temp directory. Any other job whose
#: context cannot be read as a repository path fails the test.
RUNTIME_CONTEXT_JOBS = frozenset({"rehearse-docker-login"})

#: Events whose path filter is checked. ``paths-ignore`` is not supported: the test refuses it rather than guess.
EVENTS = ("push", "pull_request", "pull_request_target")

#: (Dockerfile, COPY source as written) -> why the path filter does not have to cover it. Keep this tiny. Each
#: entry must name a COPY that exists today, so the list cannot go stale (a test below).
ALLOWED: dict[tuple[str, str], str] = {
    ("Dockerfile", "."): (
        "The CLI image's last stage copies the whole build context (`COPY . .`, minus .dockerignore). The files that "
        "reaches and that no other input names (README.md, LICENSE, NOTICE, docker-compose.yml, docs/, the scripts no "
        "build step reads, repository settings files) do not change what the image does, and covering them would start "
        "a build, and strand the *-latest tags, for every documentation commit (tests/security/"
        "test_release_scripts_behaviour.py pins that README.md and CHANGELOG.md must NOT trigger it). Every code "
        "directory in that copy is named by the filter or by an explicit COPY, which this test checks. Narrowing the "
        "copy is REVIEW.md R-017."
    ),
}


def _load_paths_helper():
    spec = importlib.util.spec_from_file_location(
        "paths_touch_build_for_trigger_guard", PATHS_HELPER
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paths_touch_build = _load_paths_helper()


# --- reading the workflow ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Build:
    job: str
    context: str  # repository-relative, "." for the root
    dockerfile: str  # repository-relative


def _substitute(value: str, row: dict | None) -> str:
    for key, item in (row or {}).items():
        value = value.replace("${{ matrix." + key + " }}", str(item))
    return value


def builds_of(workflow: dict) -> list[Build]:
    """Every repository Dockerfile build of the workflow, one per matrix row."""
    found: list[Build] = []
    for job_name, job in workflow["jobs"].items():
        rows = job.get("strategy", {}).get("matrix", {}).get("include") or [None]
        for step in job.get("steps", []):
            if not str(step.get("uses", "")).startswith("docker/build-push-action@"):
                continue
            settings = step.get("with", {})
            for row in rows:
                context = _substitute(str(settings.get("context", ".")), row)
                dockerfile = _substitute(str(settings.get("file", f"{context}/Dockerfile")), row)
                if "${{" in context or "${{" in dockerfile:
                    assert job_name in RUNTIME_CONTEXT_JOBS, (
                        f"job {job_name!r} builds from a context the test cannot read as a repository path "
                        f"({context!r}, {dockerfile!r}); read it here or add the job to RUNTIME_CONTEXT_JOBS "
                        "with a reason"
                    )
                    continue
                found.append(
                    Build(
                        job_name,
                        posixpath.normpath(context),
                        posixpath.normpath(dockerfile),
                    )
                )
    return found


# --- reading a Dockerfile ----------------------------------------------------------------------------------


def instructions_of(text: str) -> list[tuple[int, str, str]]:
    """(line number, KEYWORD, arguments), continuation lines joined, comment lines dropped."""
    result: list[tuple[int, str, str]] = []
    pending, start = "", 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if not pending:
            start = number
        if pending and line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        full = (pending + line).strip()
        pending = ""
        keyword, _, arguments = full.partition(" ")
        result.append((start, keyword.upper(), arguments.strip()))
    return result


def copy_sources(arguments: str) -> list[str] | None:
    """The build-context sources of one COPY or ADD, or ``None`` when it copies from another stage or image."""
    assert "<<" not in arguments, f"a heredoc COPY is not supported by the guard: {arguments!r}"
    tokens = json.loads(arguments) if arguments.startswith("[") else shlex.split(arguments)
    flags = [token for token in tokens if token.startswith("--")]
    operands = [token for token in tokens if not token.startswith("--")]
    if any(flag.startswith("--from") for flag in flags):
        return None
    assert len(operands) >= 2, f"a COPY needs a source and a destination: {arguments!r}"
    sources = operands[:-1]
    for source in sources:
        assert "$" not in source, (
            f"a variable in a COPY source is not supported by the guard: {source!r}"
        )
        assert "[" not in source, f"a bracket pattern in a COPY source is not supported: {source!r}"
    return [source for source in sources if not re.match(r"^[a-z][a-z0-9+.-]*://", source)]


@dataclass(frozen=True)
class Input:
    """One thing a build reads from the repository, and a file name that stands for all of it."""

    dockerfile: str
    source: str  # as written in the Dockerfile ("" for the Dockerfile itself or its .dockerignore)
    path: str  # repository-relative
    sample: str  # a file name that the path filter must match


def _sample_for(path: str) -> str:
    if any(char in path for char in "*?"):
        assert list(REPO_ROOT.glob(path)), f"COPY source matches nothing in the repository: {path}"
        return path.replace("**", "a/b").replace("*", "z").replace("?", "z")
    target = REPO_ROOT / path if path != "." else REPO_ROOT
    if target.is_dir():
        # A directory is covered only when a file at any depth below it is: `dir/**`, not `dir/one-file`.
        return "__guard_dir__/file.txt" if path == "." else f"{path}/__guard_dir__/file.txt"
    assert target.is_file(), f"COPY source does not exist in the repository: {path}"
    return path


def inputs_of(build: Build, dockerfile_text: str) -> list[Input]:
    found = [Input(build.dockerfile, "", build.dockerfile, build.dockerfile)]
    ignore_file = posixpath.normpath(posixpath.join(build.context, ".dockerignore"))
    if (REPO_ROOT / ignore_file).is_file():
        found.append(Input(build.dockerfile, "", ignore_file, ignore_file))
    for _number, keyword, arguments in instructions_of(dockerfile_text):
        if keyword not in {"COPY", "ADD"}:
            continue
        sources = copy_sources(arguments)
        if sources is None:
            continue
        for source in sources:
            path = posixpath.normpath(posixpath.join(build.context, source))
            found.append(Input(build.dockerfile, source, path, _sample_for(path)))
    return found


def derived_inputs(workflow: dict) -> list[Input]:
    found: list[Input] = []
    for build in builds_of(workflow):
        text = (REPO_ROOT / build.dockerfile).read_text(encoding="utf-8")
        found.extend(inputs_of(build, text))
    return found


# --- the check ---------------------------------------------------------------------------------------------


def gaps(inputs: list[Input], patterns: list[str]) -> list[str]:
    """The inputs no pattern covers and the allow-list does not excuse, as readable lines."""
    missing = []
    for item in inputs:
        if (item.dockerfile, item.source) in ALLOWED and item.source:
            continue
        if not paths_touch_build.touching([item.sample], patterns):
            via = f"COPY {item.source}" if item.source else "the build file itself"
            missing.append(f"{item.path}  ({via} in {item.dockerfile}; checked as {item.sample})")
    return sorted(set(missing))


def event_filters(workflow: dict) -> dict[str, list[str]]:
    triggers = workflow.get("on", workflow.get(True))
    found: dict[str, list[str]] = {}
    for event in EVENTS:
        settings = triggers.get(event) if isinstance(triggers, dict) else None
        if not isinstance(settings, dict):
            continue
        assert "paths-ignore" not in settings, (
            f"{event}: paths-ignore is not supported by the guard"
        )
        if "paths" in settings:
            found[event] = list(settings["paths"])
    return found


def load_workflow() -> dict:
    return yaml.safe_load(BUILD.read_text(encoding="utf-8"))


# --- the real workflow -------------------------------------------------------------------------------------


def test_the_path_filter_covers_every_path_the_images_copy_in():
    filters = event_filters(load_workflow())
    # Not vacuous: the push filter is the one that exists today; a workflow that lost it would build on every push
    # and this test would have nothing to check, which is a decision to make here, not by accident.
    assert "push" in filters, (
        "200-build-images.yml has no on.push.paths; update this guard on purpose"
    )
    inputs = derived_inputs(load_workflow())
    problems = {event: gaps(inputs, patterns) for event, patterns in filters.items()}
    problems = {event: missing for event, missing in problems.items() if missing}
    assert not problems, (
        "A change to only these paths would not start 200-build-images.yml, although the images copy them in. "
        "Add them to the path filter of the event named:\n"
        + "\n".join(
            f"  on.{event}.paths:\n    " + "\n    ".join(missing)
            for event, missing in problems.items()
        )
    )


def test_the_workflow_filter_is_the_one_list_the_release_scripts_read():
    # 310 and the tag-images job read on.push.paths with scripts/ci/paths_touch_build.py (a small parser, because the
    # runner's Python has no PyYAML). If that parser and a real YAML reader ever disagree, a release would decide
    # from a list other than the one GitHub uses.
    assert (
        paths_touch_build.push_paths(BUILD.read_text(encoding="utf-8"))
        == event_filters(load_workflow())["push"]
    )


def test_the_guard_reads_the_builds_the_workflow_makes():
    builds = {(b.job, b.dockerfile, b.context) for b in builds_of(load_workflow())}
    assert ("build-images", "Dockerfile", ".") in builds
    assert ("build-images", "apps/network-assessment-api/Dockerfile", ".") in builds
    web = "apps/network-assessment-web"
    assert ("build-web", f"{web}/Dockerfile", web) in builds
    # The rehearsal's throwaway image is the one build that is not a repository path, and it is named on purpose.
    assert not [b for b in builds if b[0] in RUNTIME_CONTEXT_JOBS]


def test_the_guard_finds_the_engine_package_among_the_copied_paths():
    # What this guard exists for. If the derivation stopped seeing packages/, the check above would pass for the
    # wrong reason.
    paths = {item.path for item in derived_inputs(load_workflow())}
    assert "packages/network-assessment-azure-engine" in paths
    assert "packages/network-assessment-azure-engine/pyproject.toml" in paths
    assert "network_assessment" in paths and "apps/network-assessment-api" in paths


def test_every_allow_list_entry_names_a_copy_that_exists():
    seen = {(item.dockerfile, item.source) for item in derived_inputs(load_workflow())}
    stale = sorted(set(ALLOWED) - seen)
    assert not stale, f"allow-list entries that no COPY matches any more (delete them): {stale}"
    for entry, reason in ALLOWED.items():
        assert len(reason) > 200, f"{entry}: the allow-list wants a written reason, not a label"


# --- the guard guards itself: the same code, on a filter and a Dockerfile that are known to be wrong -------------


def test_the_check_fails_on_a_filter_without_packages():
    patterns = [p for p in event_filters(load_workflow())["push"] if not p.startswith("packages/")]
    missing = gaps(derived_inputs(load_workflow()), patterns)
    assert any("packages/network-assessment-azure-engine" in line for line in missing), missing


def test_the_check_fails_on_the_engine_only_when_a_single_file_of_it_is_listed():
    # A directory COPY needs `dir/**`; naming one file in it is not enough.
    patterns = [
        *[p for p in event_filters(load_workflow())["push"] if not p.startswith("packages/")],
        "packages/network-assessment-azure-engine/pyproject.toml",
    ]
    missing = gaps(derived_inputs(load_workflow()), patterns)
    assert any(line.startswith("packages/network-assessment-azure-engine ") for line in missing)


def test_the_check_passes_on_the_real_filter_and_on_one_that_adds_the_engine_directory():
    patterns = event_filters(load_workflow())["push"]
    assert gaps(derived_inputs(load_workflow()), patterns) == []
    narrower = [p for p in patterns if p != "packages/**"] + [
        "packages/network-assessment-azure-engine/**"
    ]
    assert gaps(derived_inputs(load_workflow()), narrower) == []


def test_a_new_copy_nobody_put_in_the_filter_is_found():
    build = Build("build-images", ".", "Dockerfile")
    text = (
        "FROM python:3.14-slim\nCOPY network_assessment/ network_assessment/\nCOPY docs/ /docs/\n"
    )
    items = inputs_of(build, text)
    missing = gaps(items, event_filters(load_workflow())["push"])
    assert any(line.startswith("docs ") for line in missing), missing
    assert not any(line.startswith("network_assessment ") for line in missing)


def test_a_whole_context_copy_that_is_not_allow_listed_is_found():
    build = Build("build-images", ".", "apps/network-assessment-api/Dockerfile")
    items = inputs_of(build, "FROM python:3.14-slim\nCOPY . .\n")
    missing = gaps(items, event_filters(load_workflow())["push"])
    assert missing and missing[0].startswith(". ")


def test_copy_parsing_reads_flags_stage_copies_json_and_urls():
    assert copy_sources("--chown=a:b --chmod=755 scripts/x.sh /usr/local/bin/x") == ["scripts/x.sh"]
    assert copy_sources("--from=builder --chown=a:b /install /usr/local") is None
    assert copy_sources("--from=uv /uv /usr/local/bin/uv") is None
    assert copy_sources('["a b.txt", "c/", "/dest/"]') == ["a b.txt", "c/"]
    assert copy_sources("https://example.invalid/x.tgz /tmp/") == []
    assert copy_sources("package.json package-lock.json* ./") == [
        "package.json",
        "package-lock.json*",
    ]
    with pytest.raises(AssertionError):
        copy_sources("<<EOF /tmp/x")
    with pytest.raises(AssertionError):
        copy_sources("${SRC} /tmp/")


def test_instruction_parsing_joins_continuations_and_drops_comments():
    text = "# a comment\nRUN a \\\n  # inside\n  && b\nCOPY x \\\n  y\n"
    assert instructions_of(text) == [(2, "RUN", "a && b"), (5, "COPY", "x y")]
