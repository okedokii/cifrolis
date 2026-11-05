import unittest

from strip_release_optimization import clean, PHRASE


class ReleaseDescriptionTests(unittest.TestCase):
    def test_remove_sentence_and_preserve_identity(self):
        before = ("Цифролис — неофициальная сборка.\n\n"
                  "Скачайте APK из файлов релиза.\n\n"
                  + PHRASE + "\n\n"
                  '<!-- firefox-ruca {"firefox_version":"159.0.1","version_code":2020000010} -->\n')
        after = clean(before)
        self.assertNotIn(PHRASE, after)
        self.assertEqual(after, ("Цифролис — неофициальная сборка.\n\n"
                                 "Скачайте APK из файлов релиза.\n\n"
                                 '<!-- firefox-ruca {"firefox_version":"159.0.1","version_code":2020000010} -->\n'))
        self.assertEqual(clean(after), after)

    def test_preserve_other_descriptions(self):
        before = 'Другой релиз.\n\n<!-- firefox-ruca {} -->\n'
        self.assertEqual(clean(before), before)

    def test_crlf(self):
        self.assertEqual(clean('Начало\r\n\r\n' + PHRASE + '\r\n\r\nКонец'),
                         'Начало\r\n\r\nКонец')


if __name__ == '__main__':
    unittest.main()
