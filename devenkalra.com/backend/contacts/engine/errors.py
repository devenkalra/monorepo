class ConfigError(Exception):
    """The run can't start: missing settings, fields, or input files."""


class SafetyStop(Exception):
    """Stop the whole run immediately.

    Per-contact error handling must re-raise these instead of logging and moving on.
    """


class WritesDisabled(SafetyStop):
    pass


class DryRunViolation(SafetyStop):
    pass


class WriteBudgetExceeded(SafetyStop):
    pass


class ProtectionViolation(SafetyStop):
    pass


class TooManyErrors(SafetyStop):
    pass


class RunCancelled(SafetyStop):
    pass
