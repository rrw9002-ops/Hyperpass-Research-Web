import unittest
from hyperpass.pine_identity import execution_source, new_execution, source_hash, title_span


class PineIdentityTests(unittest.TestCase):
    def verify(self, source, original):
        start,end = title_span(source)
        self.assertEqual(source[start:end], original)
        tagged,receipt = new_execution(source,(start,end))
        self.assertEqual(tagged[:start],source[:start])
        self.assertTrue(tagged.endswith('))' + source[end:]))
        self.assertIn(' : (' + original + '))',tagged)
        self.assertEqual(receipt['source_sha256'],source_hash(tagged))
        self.assertEqual(receipt['original_sha256'],source_hash(source))
        self.assertEqual(tagged,execution_source(source,receipt))
        self.assertNotEqual(receipt['title'],new_execution(source,(start,end))[1]['title'])

    def test_multiline_comments_quoting_and_keywords_in_any_order(self):
        expr = ('("Manual" + // fake , title= arguments )\n'
                "    (true ? 'A, )' : 'B'))")
        source = ('//@version=6\n// strategy("decoy")\n'
                  'strategy(\n  overlay = true,\n  shorttitle = "title=, it\\\"s",\n'
                  '  title = ' + expr + ', commission_value=3)\nstrategy.close("L")')
        self.verify(source,expr)

    def test_triple_quoted_text_cannot_inject_a_declaration(self):
        source = ('//@version=6\nconst string EXAMPLE = """\nstrategy("fake")\n"""\n'
                  'strategy(EXAMPLE, overlay=true)\nplot(close)')
        self.verify(source,'EXAMPLE')

    def test_versioned_and_unversioned_positional_arguments_and_crlf(self):
        for version in ('',*(f'//@version={v}\r\n' for v in range(1,7))):
            self.verify(version+"strategy('Name', 'Alias', overlay=true)\r\nplot(close)","'Name'")

    def test_ambiguous_or_unclosed_declarations_fail_before_compilation(self):
        for source in ('strategy()', 'strategy(overlay=true)', 'strategy(title="unterminated)',
                       'strategy(title="A", title="B")','strategy("A", title="B")',
                       'strategy("A")\nstrategy("B")', '// strategy("fake")\nplot(close)',
                       'strategy(title=(title[1), overlay=true)'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                title_span(source)
