"""CPU token allowlists for the frozen Gemma tokenizer. No model import."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'dependencies'))
from lmformatenforcer import JsonSchemaParser, TokenEnforcer, TokenEnforcerTokenizerData
from lmformatenforcer.characterlevelparser import CharacterLevelParserConfig
from planner_policy import decoding_schema
from generation_errors import ConstraintGenerationError


class CachedTokenEnforcer(TokenEnforcer):
    """Cache plain string suffix subtrees; keep upstream quote/escape transitions.

    Upstream applies its freetext shortcut only at the vocabulary root. A token
    that opens a string midway can otherwise revisit the large Unicode trie.
    """
    def __init__(self, data, parser):
        super().__init__(data, parser)
        self.plain_chars = set(data.tokenizer_alphabet) - {'"', '\\'}
        self.plain_chars = {c for c in self.plain_chars if ord(c) >= 32}
        if not hasattr(data, 'v5_plain_subtrees'):
            data.v5_plain_subtrees = {}
        self.subtrees = data.v5_plain_subtrees
        if not hasattr(data, 'v5_mixed_subtrees'):
            data.v5_mixed_subtrees = {}
            data.v5_all_subtrees = {}
            data.v5_node_depths = {self.tokenizer_tree.root: 0}
        self.mixed = data.v5_mixed_subtrees
        self.all_subtrees = data.v5_all_subtrees
        self.depths = data.v5_node_depths

    def all_tokens(self, node):
        if node not in self.all_subtrees:
            result = list(node.tokens)
            for child in node.children.values():
                result.extend(self.all_tokens(child))
            self.all_subtrees[node] = tuple(result)
        return self.all_subtrees[node]

    def plain_tokens(self, node):
        if node not in self.subtrees:
            result = list(node.tokens)
            mixed = []
            for character, child in node.children.items():
                if character in self.plain_chars:
                    result.extend(self.plain_tokens(child))
                    mixed.extend(self.mixed[child])
                elif character in {'"', '\\'}:
                    mixed.extend(self.all_tokens(child))
            self.subtrees[node] = tuple(result)
            self.mixed[node] = tuple(mixed)
        return self.subtrees[node]

    def _collect_allowed_tokens(self, parser, node, allowed, shortcut):
        key = parser.shortcut_key()
        if node is not self.tokenizer_tree.root and isinstance(key, tuple) and key[0] == 'json_freetext':
            # No maxLength is used by v5. The cached suffix must be unlimited;
            # minLength is enforced by the delegated closing quote transition.
            if key[3] == sys.maxsize:
                allowed.extend(self.plain_tokens(node))
                # Closing quotes/escapes may occur *after* a plain suffix, e.g.
                # the single token '\":\"' can encode a string containing ':'.
                depth = self.depths[node]
                for token in self.mixed[node]:
                    suffix = self.tokenizer_tree.tokens_to_strs[token][depth:]
                    current = parser
                    valid = True
                    for character in suffix:
                        current_key = current.shortcut_key()
                        if (ord(character) < 32 and isinstance(current_key, tuple)
                                and current_key[0] == 'json_freetext') or character not in current.get_allowed_characters():
                            valid = False
                            break
                        current = current.add_character(character)
                    if valid:
                        allowed.append(token)
                return
        depth = self.depths[node]
        for child in node.children.values():
            self.depths.setdefault(child, depth + 1)
        super()._collect_allowed_tokens(parser, node, allowed, shortcut)


def tokenizer_data(tok, tokenizer_path, eos):
    """Upstream contextual-zero adapter; inputs remain exactly tokenized as before.

    Exclude special/empty/incomplete byte tokens. Rare literal byte-fallback-only
    characters are unavailable in output; JSON Unicode escapes remain allowed.
    """
    tokenizer_path = Path(tokenizer_path)
    raw = json.loads(tokenizer_path.read_text(encoding='utf-8'))
    specials = {t['id'] for t in raw['added_tokens'] if t['special']}
    config = json.loads(tokenizer_path.with_name('tokenizer_config.json').read_text(encoding='utf-8'))
    controls = [v for k, v in config.items() if k.endswith('_token') and isinstance(v, str)]
    controls += config.get('extra_special_tokens', [])
    specials.update(index for token in controls if (index := tok.token_to_id(token)) is not None)
    zero = tok.encode('0', add_special_tokens=False).ids
    assert len(zero) == 1 and tok.decode(zero) == '0'
    tokens = []
    excluded_bytes = 0
    for index in range(tok.get_vocab_size()):
        if index in specials:
            continue
        text = tok.decode(zero + [index], skip_special_tokens=False)[1:]
        single = tok.decode([index], skip_special_tokens=False)
        if not text or '\ufffd' in text or any(ord(c) < 32 and c not in '\n\r' for c in text):
            excluded_bytes += 1
            continue
        tokens.append((index, text, len(text) > len(single)))
    data = TokenEnforcerTokenizerData(tokens, lambda ids: tok.decode(ids, skip_special_tokens=False),
                                     eos, False, tok.get_vocab_size())
    # Structural whitespace is still handled by the JSON parser. Freetext
    # strings must escape control characters rather than emit them literally.
    data.tokenizer_alphabet = ''.join(c for c in data.tokenizer_alphabet if ord(c) >= 32)
    data.v5_metadata = {'regular_tokens': len(tokens), 'special_tokens_excluded': len(specials),
                        'incomplete_or_empty_tokens_excluded': excluded_bytes,
                        'tokenizer_adapter': 'contextual_zero; no input tokenization change'}
    return data


class SchemaConstraint:
    def __init__(self, data, ids, prompt_length=0):
        self.data = data
        self.ids = list(ids)
        self.schema = decoding_schema(ids)
        # Initialize the cached string alphabet *before* LMFE builds its context.
        # Setting only parser.config later leaves minLength's alphabet ASCII-only.
        config = CharacterLevelParserConfig(alphabet=data.tokenizer_alphabet)
        self.enforcer = CachedTokenEnforcer(data, JsonSchemaParser(self.schema, config=config))
        self.prompt_length = prompt_length
        self.trace = []

    def allowed(self, sequence):
        sequence = list(sequence)
        allowed = self.enforcer.get_allowed_tokens(sequence).allowed_tokens
        eos = set(self.data.eos_token_id if isinstance(self.data.eos_token_id, list)
                  else [self.data.eos_token_id])
        # LMFE can fall back to EOS after an internal error; fail visibly.
        if eos.intersection(allowed):
            try:
                if not isinstance(json.loads(self.data.decoder(sequence)), dict):
                    raise ValueError('not an object')
            except (ValueError, TypeError) as exc:
                raise ConstraintGenerationError('Constraint offered EOS before complete JSON') from exc
        if not allowed:
            raise ConstraintGenerationError('Empty JSON schema token allowlist')
        return allowed

    def __call__(self, batch_id, tensor):
        if batch_id != 0:
            raise ValueError('v5 initial admission is single-sequence generation')
        sequence = tensor.tolist()[self.prompt_length:]
        allowed = self.allowed(sequence)
        self.trace.append({'output_prefix_tokens': len(sequence), 'allowed_tokens': len(allowed)})
        return allowed
