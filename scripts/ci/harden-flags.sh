# shellcheck shell=bash
# The `docker run` flags every tool container of the CI checks gets. One definition, sourced by
# scripts/ci/local-container-checks.sh and by the hadolint and actionlint jobs of 300-test-codebase.yml, so the
# local run and CI cannot drift apart (tests/unit/test_ci_hygiene.py checks that both source it):
#   --rm                               disposable
#   --read-only                        the container filesystem is immutable (Trivy adds --tmpfs /tmp where it writes)
#   --cap-drop ALL                     no Linux capabilities
#   --security-opt no-new-privileges   no privilege gain through setuid binaries
# Use as: docker run "${HARDEN[@]}" ...
# shellcheck disable=SC2034  # used by the scripts and workflow steps that source this file
HARDEN=(--rm --read-only --cap-drop ALL --security-opt no-new-privileges)
