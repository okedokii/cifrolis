import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from fdroid_repository import APP_ID,verify_index

class FdroidIndexTests(unittest.TestCase):
    def index(self,payload,selected):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(root/'index-v1.jar','w') as jar:
                jar.writestr('index-v1.json',json.dumps(payload))
            icons=root/APP_ID/'en-US'
            icons.mkdir(parents=True)
            (icons/'icon.png').write_bytes(b'\x89PNG\r\n\x1a\n')
            return verify_index(root,selected)
    def test_selected_app_present(self):
        payload={'apps':[{'packageName':APP_ID,'localized':{'en-US':{'icon':'icon.png'}}}],'packages':{APP_ID:[{'versionCode':2020000002}]}}
        self.assertEqual(self.index(payload,[{'code':2020000002}]),1)
    def test_empty_index_rejected_when_apk_selected(self):
        with self.assertRaises(ValueError):self.index({'apps':[],'packages':{}},[{'code':2020000002}])
    def test_missing_version_rejected(self):
        payload={'apps':[{'packageName':APP_ID,'localized':{'en-US':{'icon':'icon.png'}}}],'packages':{APP_ID:[{'versionCode':2020000001}]}}
        with self.assertRaises(ValueError):self.index(payload,[{'code':2020000002}])
    def test_missing_icon_rejected(self):
        payload={'apps':[{'packageName':APP_ID}],'packages':{APP_ID:[{'versionCode':2020000002}]}}
        with self.assertRaises(ValueError):self.index(payload,[{'code':2020000002}])
    def test_missing_icon_file_rejected(self):
        payload={'apps':[{'packageName':APP_ID,'localized':{'en-US':{'icon':'absent.png'}}}],'packages':{APP_ID:[{'versionCode':2020000002}]}}
        with self.assertRaises(ValueError):self.index(payload,[{'code':2020000002}])
    def test_intentionally_empty_repository(self):
        self.assertEqual(self.index({'apps':[],'packages':{}},[]),0)

if __name__=='__main__':unittest.main()
