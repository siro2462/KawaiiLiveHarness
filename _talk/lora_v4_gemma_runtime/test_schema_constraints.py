"""CPU-only admission with the actual frozen Gemma tokenizer, no model weights."""
import json
import unittest
from pathlib import Path
from tokenizers import Tokenizer
from schema_constraints import SchemaConstraint, tokenizer_data, CachedTokenEnforcer
from lmformatenforcer import JsonSchemaParser, TokenEnforcer, TokenEnforcerTokenizerData
from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig
from planner_policy import decoding_schema

PATH = Path(__file__).resolve().parent.parent / 'lora_v4_multibase/models/gemma4_26b_a4b/tokenizer.json'


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = Tokenizer.from_file(str(PATH))
        cls.eos = json.loads(PATH.with_name('generation_config.json').read_text())['eos_token_id']
        cls.data = tokenizer_data(cls.tok, PATH, cls.eos)

    def feed(self, text, ids=('S2B',)):
        constraint = SchemaConstraint(self.data, ids)
        sequence = []
        for token in self.tok.encode(text, add_special_tokens=False).ids:
            if token not in constraint.allowed(sequence):
                return False, sequence, constraint
            sequence.append(token)
        return True, sequence, constraint

    def test_complete_japanese_json_and_unicode_escape(self):
        for ascii_mode in [False, True]:
            raw = json.dumps({'use_memory':True,'memory_id':'S2B','topic':'料理の「話」',
                              'flow':['ご飯がなかった\n出来事','甘めだったかな？']}, ensure_ascii=ascii_mode)
            accepted, sequence, constraint = self.feed(raw)
            self.assertTrue(accepted, self.tok.decode(sequence))
            self.assertIn(1, constraint.allowed(sequence))

    def test_html_multiple_objects_and_truncation(self):
        raw = json.dumps({'use_memory':False,'memory_id':None,'topic':'話','flow':['a','b']})
        for bad in ['<h1>', raw + raw]:
            accepted, _, _ = self.feed(bad)
            self.assertFalse(accepted)
        accepted, sequence, constraint = self.feed(raw[:-1])
        self.assertTrue(accepted)
        self.assertNotIn(1, constraint.allowed(sequence))

    def test_unknown_id_missing_extra_duplicate_fields(self):
        good = {'use_memory':True,'memory_id':'S2B','topic':'話','flow':['a','b']}
        bads = [dict(good,memory_id='FOREIGN'), dict(good,other='bad'),
                {k:v for k,v in good.items() if k != 'memory_id'}, dict(good,flow=['a']),
                dict(good,flow=['a','b','c','d','e']), dict(good,topic='')]
        for obj in bads:
            with self.subTest(obj=obj):
                self.assertFalse(self.feed(json.dumps(obj))[0])
        self.assertFalse(self.feed('{"topic":"話","topic":"話"')[0])

    def test_no_candidate_requires_null_and_special_tokens_masked(self):
        self.assertFalse(self.feed('{"memory_id":"S2B"', ids=())[0])
        allowed = SchemaConstraint(self.data, []).allowed([])
        for special in [0,1,2,3,106]:
            self.assertNotIn(special, allowed)

    def test_cached_subtree_preserves_valid_paths_and_rejects_literal_controls(self):
        alphabet = 'abcdefghijklmnopqrstuvwxyz_{}[]:,"\\0123456789 \n料理話'
        strings = list(dict.fromkeys(alphabet)) + ['{"','":"','":"料理','料理"','["話','話",','"}']
        data = TokenEnforcerTokenizerData([(i,s,False) for i,s in enumerate(strings)],
            lambda ids: ''.join(strings[i] for i in ids), len(strings), False, len(strings)+1)
        schema = decoding_schema([])
        config = CharacterLevelParserConfig(alphabet=data.tokenizer_alphabet)
        old = TokenEnforcer(data,JsonSchemaParser(schema,config=config))
        new = CachedTokenEnforcer(data,JsonSchemaParser(schema,config=config))
        sequence = []
        raw = '{"use_memory":false,"memory_id":null,"topic":"料理話","flow":["話","料理"]}'
        prefix = ''
        for character in raw:
            original = set(old.get_allowed_tokens(sequence).allowed_tokens)
            cached = set(new.get_allowed_tokens(sequence).allowed_tokens)
            self.assertFalse(cached - original)
            removed = original - cached
            if removed:
                # Upstream's recursive string path can offer a literal newline.
                # v5 deliberately rejects it; structural whitespace is retained.
                self.assertEqual(prefix.count('"') % 2, 1)
                self.assertTrue(all(any(ord(c) < 32 for c in strings[i]) for i in removed))
            sequence.append(strings.index(character))
            prefix += character

    def test_unescaped_control_in_string_is_not_allowed(self):
        self.assertFalse(self.feed('{"topic":"話\n')[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
