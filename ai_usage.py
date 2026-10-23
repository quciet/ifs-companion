"""Provider usage receipts and explicitly labelled character-based fallbacks."""
import json
import math

FIELDS = ('calls', 'reported_calls', 'estimated_calls', 'failed_calls', 'input_tokens',
          'output_tokens', 'cached_input_tokens', 'reasoning_tokens', 'estimated_input_tokens',
          'estimated_output_tokens', 'unknown_output_calls', 'seconds')


def empty():
    return dict.fromkeys(FIELDS, 0)


def merge(*receipts):
    result = empty()
    for receipt in receipts:
        for key in FIELDS:
            value = (receipt or {}).get(key, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                result[key] += value
    result['seconds'] = round(result['seconds'], 3)
    return result


def event(provider_usage, request, response=None, seconds=0, failed=False):
    result = empty()
    result.update(calls=1, failed_calls=int(failed), seconds=max(0, seconds))
    usage = provider_usage if isinstance(provider_usage, dict) else {}
    def integer(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    prompt, completion = usage.get('prompt_tokens'), usage.get('completion_tokens')
    if integer(prompt) and integer(completion):
        prompt_details=usage.get('prompt_tokens_details') if isinstance(usage.get('prompt_tokens_details'),dict) else {}
        output_details=usage.get('completion_tokens_details') if isinstance(usage.get('completion_tokens_details'),dict) else {}
        cached = usage.get('prompt_cache_hit_tokens', prompt_details.get('cached_tokens',0))
        reasoning = output_details.get('reasoning_tokens',0)
        result.update(reported_calls=1, input_tokens=prompt, output_tokens=completion,
                      cached_input_tokens=min(prompt, cached) if integer(cached) else 0,
                      reasoning_tokens=min(completion, reasoning) if integer(reasoning) else 0)
    else:
        # Includes tool schemas and tool-call JSON, never credentials or transport headers.
        result.update(estimated_calls=1,
                      estimated_input_tokens=math.ceil(len(json.dumps(request, ensure_ascii=False))/4),
                      estimated_output_tokens=math.ceil(len(json.dumps(response, ensure_ascii=False))/4) if response is not None else 0,
                      unknown_output_calls=int(response is None))
    return result
