from __future__ import annotations

import logging
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from shlex import join as shell_join

from ado_ai_pr_review.errors import CommandExecutionError
from ado_ai_pr_review.redaction import SecretRedactor
from ado_ai_pr_review.tool_policy import CommandPolicy
from ado_ai_pr_review.workspace import ProcessContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class CliRunner:
    def __init__(
        self,
        policy: CommandPolicy,
        secrets: list[str] | None = None,
        timeout_seconds: int = 60,
        max_output_chars: int = 200_000,
        process_context: ProcessContext | None = None,
    ) -> None:
        self._policy = policy
        self._redactor = SecretRedactor(secrets or ())
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars
        self._process_context = process_context

    def run(
        self,
        argv: list[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> CommandResult:
        try:
            self._policy.validate(argv)
        except Exception:
            logger.debug("command rejected: %s", self._redactor.redact(shell_join(argv)))
            raise
        try:
            effective_cwd = self._process_context.require_cwd(cwd) if self._process_context else cwd
            effective_env = self._process_context.build_env(env) if self._process_context else env
        except Exception as exc:
            detail = self._redactor.redact(str(exc))
            if "outside workspace" in detail:
                detail = f"cwd outside workspace: {detail}"
            raise CommandExecutionError(detail) from exc

        try:
            completed: subprocess.CompletedProcess[str] = subprocess.run(
                argv,
                cwd=effective_cwd,
                env=effective_env,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = self._cap_and_redact(_output_to_text(exc.output))
            stderr = self._cap_and_redact(_output_to_text(exc.stderr))
            detail = self._diagnostic_snippet(stderr=stderr, stdout=stdout)
            raise CommandExecutionError(
                f"Command {self._safe_command_context(argv)} timed out after "
                f"{self._timeout_seconds} seconds{detail}",
            ) from exc
        except OSError as exc:
            detail = self._cap_and_redact(str(exc))
            raise CommandExecutionError(
                f"Command {self._safe_command_context(argv)} could not be executed: {detail}",
            ) from exc

        result = CommandResult(
            argv=list(argv),
            returncode=completed.returncode,
            stdout=self._cap_and_redact(completed.stdout),
            stderr=self._cap_and_redact(completed.stderr),
        )

        if check and result.returncode != 0:
            raise CommandExecutionError(
                f"Command {self._safe_command_context(argv)} failed with exit code "
                f"{result.returncode}{self._diagnostic_snippet(stderr=result.stderr, stdout=result.stdout)}",
            )

        return result

    def _cap_and_redact(self, output: str) -> str:
        # Output is capped after subprocess.run captures it. A streaming cap is future hardening.
        redacted = self._redactor.redact(output)
        return redacted[: self._max_output_chars]

    def _diagnostic_snippet(self, stderr: str, stdout: str) -> str:
        snippet = stderr or stdout
        if not snippet:
            return ""
        return f": {snippet}"

    def _safe_command_context(self, argv: list[str]) -> str:
        return shell_join(argv[:3])


def _output_to_text(output: object) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return str(output)
