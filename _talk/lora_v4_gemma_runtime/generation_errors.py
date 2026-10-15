"""Narrow recoverable generation errors; programming errors are never swallowed."""
import traceback


class ContextBudgetError(ValueError):
    """Protected facts/Plan alone exceed the admitted input budget."""


class ConstraintGenerationError(ValueError):
    """The admitted schema engine cannot produce a valid next token."""


def classify(exc):
    message = str(exc)
    lower = message.lower()
    if isinstance(exc, ContextBudgetError):
        return {'code':'protected_context_overflow', 'retry':False, 'action':'planless_or_halt'}
    if isinstance(exc, ConstraintGenerationError):
        return {'code':'schema_constraint_failure', 'retry':True, 'action':'bounded_retry_then_planless'}
    if isinstance(exc, MemoryError) or type(exc).__name__ == 'OutOfMemoryError' or (
            isinstance(exc, RuntimeError) and any(x in lower for x in
            ['out of memory', 'cuda error', 'hip error', 'device-side assert', 'illegal memory access'])):
        return {'code':'model_execution_failure', 'retry':False, 'action':'halt_no_further_generation'}
    if isinstance(exc, (ValueError, RuntimeError)) and any(x in lower for x in
            ['maximum context length', 'max_position_embeddings', 'input sequence length exceeds']):
        return {'code':'input_context_overflow', 'retry':True, 'action':'shrink_recent_only'}
    return None


def audit_error(exc, prompt='', recent='', candidate_ids=()):
    policy = classify(exc)
    return {**(policy or {'code':'unexpected_implementation_error','retry':False,'action':'raise'}),
            'exception_type':type(exc).__name__, 'message':str(exc),
            'traceback':''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            'input_chars':len(prompt), 'recent_chars':len(recent), 'candidate_ids':list(candidate_ids)}
