"""Use fixed original Fact order on invalid Planner JSON; preserve raw output."""
from planner_policy import parse_plan

def resolve(raw,candidate_ids):
 try:
  plan=parse_plan(raw,candidate_ids)
  return dict(plan=plan,syntax_valid=True,format_fallback=False,error=None,fallback_policy=None)
 except (ValueError,TypeError,KeyError) as exc:
  return dict(plan=None,syntax_valid=False,format_fallback=True,error=str(exc),fallback_policy='discard_invalid_plan_use_fixed_source_fact_order_no_retry')
