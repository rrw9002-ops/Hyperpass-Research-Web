from html.parser import HTMLParser
import unittest

from tools.build_student_guide import CHAPTERS, GUIDE, ROOT, build


class GuideElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
        self.anchors=[]
        self.dependencies=[]

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag=='a' and attrs.get('href','').startswith('#'):
            self.anchors.append(attrs['href'][1:])
        if tag=='script' and 'src' in attrs:
            self.dependencies.append(attrs['src'])
        if tag=='link' and attrs.get('rel')=='stylesheet':
            self.dependencies.append(attrs['href'])


class StudentGuideTest(unittest.TestCase):
    def test_packaged_and_single_file_guides_match_the_chapters(self):
        html=(ROOT/GUIDE).read_text(encoding='utf8')
        self.assertEqual(html,build())
        for standalone in (False,True):
            with self.subTest(standalone=standalone):
                text=build(standalone)
                tree=GuideElements()
                tree.feed(text)
                self.assertTrue(set(tree.anchors)<=tree.ids)
                self.assertTrue({key for key,_,_ in CHAPTERS}<=tree.ids)
                self.assertEqual(tree.dependencies,[] if standalone else ['static/student-guide.css','static/student-guide.js'])
                for dependency in tree.dependencies:
                    self.assertTrue((ROOT/dependency).is_file())
                self.assertIn('이 가이드의 설치 부분',text)
                self.assertIn('SK하이닉스',text)
                self.assertIn('최종 보고서',text)
                self.assertGreaterEqual(text.count('class="copy"'),5)
