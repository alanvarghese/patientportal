from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.tests.client import TestClient
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import delete

import backend.attachments as attachments
from backend.main import app
from backend.models import PatientAttachment
from backend.tests.test_database import PostgresTestCase


def pdf_bytes(active=False, encrypted=False):
    writer=PdfWriter()
    writer.add_blank_page(width=300,height=300)
    if active:
        writer.add_js('app.alert("demo")')
    if encrypted:
        writer.encrypt('test')
    output=BytesIO();writer.write(output)
    return output.getvalue()


def image_bytes(format='PNG'):
    output=BytesIO()
    Image.new('RGB',(100,60),'#e8eedf').save(output,format=format)
    return output.getvalue()


class AttachmentTests(PostgresTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage=TemporaryDirectory(prefix='telemedicine-attachments-')
        cls.storage_patch=patch.object(attachments,'STORAGE_ROOT',Path(cls.storage.name))
        cls.storage_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.storage_patch.stop()
        cls.storage.cleanup()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        with self.sessions.begin() as session:
            session.execute(delete(PatientAttachment))

    def upload(self,client,data,filename='demo.pdf',mime='application/pdf',patient='patient-a1'):
        return client.post(f'/api/records/patients/{patient}/attachments',content=data,headers={'X-Practice-Client':'portal','X-File-Name':filename,'X-Attachment-Title':'Demo report','Content-Type':mime})

    def test_pdf_image_listing_download_and_scope(self):
        with TestClient(app, role='nurse') as client:
            data=pdf_bytes()
            result=self.upload(client,data)
            self.assertEqual(result.status_code,200,result.text)
            item=result.json()['attachment']
            self.assertNotIn('storage_key',item)
            duplicate=self.upload(client,data)
            self.assertTrue(duplicate.json()['already_attached'])
            self.assertEqual(duplicate.json()['attachment']['id'],item['id'])
            root='/api/records/patients/patient-a1/attachments'
            listed=client.get(root).json()
            self.assertEqual(listed['total'],1)
            content=client.get(f'{root}/{item["id"]}/content')
            self.assertEqual(content.content,data)
            self.assertEqual(content.headers['content-type'],'application/pdf')
            self.assertTrue(content.headers['content-disposition'].startswith('inline'))
            self.assertEqual(content.headers['cache-control'],'no-store')
            rendered=client.get(f'{root}/{item["id"]}/preview')
            self.assertEqual(rendered.status_code,200,rendered.text[:100] if rendered.status_code!=200 else '')
            self.assertEqual(rendered.headers['content-type'],'image/png')
            with Image.open(BytesIO(rendered.content)) as thumbnail:
                self.assertLessEqual(thumbnail.width,1200)
                self.assertLessEqual(thumbnail.height,1600)
            self.assertEqual(client.get(f'/api/records/patients/patient-a2/attachments/{item["id"]}/preview').status_code,404)
            self.assertTrue(client.get(f'{root}/{item["id"]}/content?download=true').headers['content-disposition'].startswith('attachment'))
            self.assertEqual(client.get(f'/api/records/patients/patient-a2/attachments/{item["id"]}/content').status_code,404)
            self.assertEqual(self.upload(client,data,patient='missing').status_code,404)
            for filename,mime,format in [('demo.png','image/png','PNG'),('demo.jpg','image/jpeg','JPEG')]:
                result=self.upload(client,image_bytes(format),filename,mime)
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['attachment']['mime_type'],mime)
                image=client.get(f'{root}/{result.json()["attachment"]["id"]}/content')
                with Image.open(BytesIO(image.content)) as opened:
                    self.assertEqual(opened.format,format)
            self.assertEqual(client.get(root+'?limit=1').json()['total'],3)
            self.assertEqual(len(client.get(root+'?limit=1&offset=1').json()['attachments']),1)
            # Missing bytes are reported explicitly, never replaced with another patient's file.
            with self.sessions() as session:
                stored=session.get(PatientAttachment,item['id'])
                (attachments.STORAGE_ROOT/stored.storage_key).unlink()
            self.assertEqual(client.get(f'{root}/{item["id"]}/content').status_code,404)

    def test_validation_rejects_unsafe_and_oversize_files(self):
        with TestClient(app, role='nurse') as client:
            cases=[(b'', 'empty.pdf','application/pdf',422),(b'fake PDF','fake.pdf','application/pdf',422),
                (pdf_bytes(),'wrong.png','image/png',422),(pdf_bytes(),'demo.pdf','image/jpeg',415),
                (b'<svg/>','file.svg','image/svg+xml',415),(pdf_bytes(),'../bad.pdf','application/pdf',422),
                (b'\x89PNG\r\n\x1a\ninvalid','fake.png','image/png',422),
                (pdf_bytes(active=True),'scripted.pdf','application/pdf',422),
                (pdf_bytes(encrypted=True),'locked.pdf','application/pdf',422)]
            for data,name,mime,expected in cases:
                result=self.upload(client,data,name,mime)
                self.assertEqual(result.status_code,expected,(name,result.text))
            self.assertEqual(self.upload(client,b'x'*(attachments.MAX_BYTES+1)).status_code,413)
            self.assertEqual(client.post('/api/records/patients/patient-a1/attachments',content=pdf_bytes(),headers={'X-Practice-Client':''}).status_code,403)
            self.assertEqual(client.get('/api/records/patients/patient-a1/attachments').json()['total'],0)

    def test_parallel_duplicate_uploads_are_idempotent(self):
        with TestClient(app, role='nurse') as client:
            payload=pdf_bytes()
            with ThreadPoolExecutor(max_workers=4) as executor:
                results=list(executor.map(lambda _:self.upload(client,payload),range(4)))
            self.assertEqual([r.status_code for r in results],[200]*4)
            self.assertEqual(len({r.json()['attachment']['id'] for r in results}),1)
            self.assertEqual(client.get('/api/records/patients/patient-a1/attachments').json()['total'],1)
