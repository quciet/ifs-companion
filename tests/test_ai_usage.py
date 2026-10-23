import unittest
import ai_usage


class UsageTests(unittest.TestCase):
    def test_reported_cache_and_reasoning_are_subsets(self):
        receipt=ai_usage.event({'prompt_tokens':100,'completion_tokens':20,
            'prompt_tokens_details':{'cached_tokens':80},
            'completion_tokens_details':{'reasoning_tokens':12}}, {},seconds=1.25)
        self.assertEqual(receipt['input_tokens']+receipt['output_tokens'],120)
        self.assertEqual(receipt['cached_input_tokens'],80)
        self.assertEqual(receipt['reasoning_tokens'],12)
        self.assertEqual(receipt['estimated_calls'],0)

    def test_unreported_failed_call_is_explicit_estimate(self):
        receipt=ai_usage.event(None,{'messages':['Hello']},failed=True)
        self.assertEqual(receipt['reported_calls'],0)
        self.assertEqual(receipt['failed_calls'],1)
        self.assertEqual(receipt['unknown_output_calls'],1)
        self.assertGreater(receipt['estimated_input_tokens'],0)
        self.assertEqual(receipt['input_tokens'],0)

    def test_malformed_details_and_negative_counts(self):
        receipt=ai_usage.event({'prompt_tokens':10,'completion_tokens':4,
            'prompt_tokens_details':None,'completion_tokens_details':[]}, {})
        self.assertEqual(receipt['cached_input_tokens'],0)
        self.assertEqual(ai_usage.merge(receipt,{'calls':-10})['calls'],1)
