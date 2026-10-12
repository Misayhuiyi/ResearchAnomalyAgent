"""Formal-package boundaries: real input validation, privacy and document parity."""
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'mvp-demo'))
sys.path.insert(0,str(ROOT/'delivery-src'/'Code'/'DataCode'))
sys.path.insert(0,str(ROOT/'tools'))
import delivery_support
import delivery_runner
from build_delivery import application_module, documents, INPUTS, OUTPUTS
from verify_baiyin_scope import html_tables


class DeliveryContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.inputs=self.root/'TempData';(self.inputs/'Materials').mkdir(parents=True)
        self.sample=(ROOT/'mvp-demo'/'samples'/'fixed_shift_demo.csv').read_bytes()
        (self.inputs/'Materials'/'sample.csv').write_bytes(self.sample)

    def test_real_upload_defaults_and_bounded_options(self):
        uploads,profile,checks,note=delivery_support.validate_inputs(self.inputs)
        self.assertEqual(uploads,[('sample.csv',self.sample)])
        self.assertEqual((profile,checks,note),('review',[],''))
        (self.inputs/'Profile.txt').write_text('unknown',encoding='utf-8')
        with self.assertRaises(ValueError):delivery_support.validate_inputs(self.inputs)

    def test_reject_unknown_input_nested_material_and_extension(self):
        (self.inputs/'secret.txt').write_text('private',encoding='utf-8')
        with self.assertRaises(ValueError):delivery_support.validate_inputs(self.inputs)
        (self.inputs/'secret.txt').unlink()
        (self.inputs/'Materials'/'nested').mkdir()
        with self.assertRaises(ValueError):delivery_support.validate_inputs(self.inputs)
        (self.inputs/'Materials'/'nested').rmdir()
        (self.inputs/'Materials'/'attack.exe').write_bytes(b'not a material')
        with self.assertRaises(ValueError):delivery_support.validate_inputs(self.inputs)

    def test_block_linked_parameter_before_reading(self):
        (self.inputs/'Profile.txt').write_text('review',encoding='utf-8')
        original=delivery_support.is_link
        with patch.object(delivery_support,'is_link',side_effect=lambda p:p.name=='Profile.txt' or original(p)):
            with self.assertRaisesRegex(ValueError,'链接'):delivery_support.validate_inputs(self.inputs)

    def test_block_linked_material_directory(self):
        with patch.object(delivery_support,'is_link',side_effect=lambda p:p.name=='Materials'):
            with self.assertRaisesRegex(ValueError,'链接'):delivery_support.validate_inputs(self.inputs)

    def test_parameter_limit_and_unconfirmed_reference(self):
        (self.inputs/'StudyNote.txt').write_text('x'*2001,encoding='utf-8')
        with self.assertRaises(ValueError):delivery_support.validate_inputs(self.inputs)
        (self.inputs/'StudyNote.txt').unlink()
        (self.inputs/'Reference.txt').write_text('https://example.org/paper',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'先在工作台'):delivery_support.validate_inputs(self.inputs)

    def test_note_repairs_do_not_expose_research_text(self):
        note='PRIVATE-RESEARCH-NOTE'
        change=delivery_runner.parameter_change('StudyNote.txt',' '+note,note)
        self.assertNotIn(note,json.dumps(change))
        self.assertEqual(change['after']['characters'],len(note))
        self.assertEqual(len(change['after']['sha256']),64)

    def test_failure_does_not_retry_or_forward_model_credentials(self):
        (self.inputs/'StudyNote.txt').write_text(' PRIVATE-NOTE ',encoding='utf-8')
        coding=self.root/'Coding';(coding/'Code').mkdir(parents=True)
        (coding/'Code'/'PaperAudit.py').write_text('pass',encoding='utf-8')
        completed=subprocess.CompletedProcess([],1,'','PRIVATE-NOTE TEST-CREDENTIAL')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'TEST-CREDENTIAL','PAPER_AUDIT_MODEL_CONFIG':'PRIVATE-CONFIG'}), patch.object(delivery_runner.subprocess,'run',return_value=completed) as run:
            report=delivery_runner.run_local(coding,self.inputs,self.root/'sandbox')
        self.assertEqual(run.call_count,1)
        self.assertEqual(report['retry_limit'],0)
        self.assertEqual(report['status'],'failed')
        self.assertNotIn('DEEPSEEK_API_KEY',run.call_args.kwargs['env'])
        self.assertNotIn('PAPER_AUDIT_MODEL_CONFIG',run.call_args.kwargs['env'])
        self.assertNotIn('PRIVATE-NOTE',json.dumps(report))
        self.assertNotIn('TEST-CREDENTIAL',(self.root/'sandbox'/'Data'/'internal-diagnostic.txt').read_text())

    def test_timeout_is_one_attempt(self):
        coding=self.root/'Coding';(coding/'Code').mkdir(parents=True)
        with patch.object(delivery_runner.subprocess,'run',side_effect=subprocess.TimeoutExpired('Coding',240)) as run:
            result=delivery_runner.run_local(coding,self.inputs,self.root/'sandbox')
        self.assertEqual(run.call_count,1)
        self.assertEqual(result['category'],'timeout')
        self.assertEqual(result['retry_limit'],0)

    def test_unrepairable_input_never_submits(self):
        (self.inputs/'Materials'/'attack.exe').write_bytes(b'unsupported')
        with patch.object(delivery_runner.subprocess,'run') as run:
            with self.assertRaises(ValueError):delivery_runner.run_local(self.root,self.inputs,self.root/'sandbox')
        run.assert_not_called()
        self.assertFalse((self.root/'sandbox').exists())

    def test_maintenance_detects_source_change_and_blocks(self):
        spec=importlib.util.spec_from_file_location('delivery_maintenance_test',ROOT/'delivery-src'/'AgentOM'/'run.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        package=self.root/'Package';source=package/'PaperAudit_Coding'/'Code'/'PaperAudit.py'
        source.parent.mkdir(parents=True);source.write_text('before',encoding='utf-8')
        om=package/'PaperAudit_AgentOM';om.mkdir()
        def reproduce(*_):
            source.write_text('unexpected external change',encoding='utf-8')
            return {'status':'succeeded','category':'local_coding'}
        with patch.object(module,'ROOT',om),patch.object(module,'run_local',side_effect=reproduce):result=module.main()
        self.assertFalse(result['source_unchanged'])
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['review_gate']['automatic_publication'])

    def test_packaged_service_preserves_functions_without_development_cli(self):
        source=(ROOT/'mvp-demo'/'app.py').read_text(encoding='utf-8')
        packed=application_module(source)
        old={n.name:ast.dump(n) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        new={n.name:ast.dump(n) for n in ast.parse(packed).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        self.assertEqual(old,new)
        self.assertNotIn('import argparse',packed)
        self.assertNotIn('parse_args()',packed)
        compile(packed,'packaged/app.py','exec')

    def test_word_html_input_output_tables_agree(self):
        from docx import Document
        documents(self.root)
        doc=Document(self.root/'PaperAudit 应用说明.docx')
        word=[[[c.text for c in row.cells] for row in table.rows] for table in doc.tables]
        html=html_tables((self.root/'PaperAudit 应用说明.html').read_text(encoding='utf-8'))
        self.assertEqual(word,html)
        self.assertEqual(word[0][1:],INPUTS)
        self.assertEqual(word[1][1:],OUTPUTS)
        self.assertEqual({row[0] for row in INPUTS},{'Materials','Profile.txt','Checks.txt','StudyNote.txt'})


if __name__=='__main__':unittest.main()
