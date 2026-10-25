"""Automated test suite for Huntly Resume Import, Parsing, and Career Profile integration.

Tests:
1. Valid PDF and DOCX extraction and parsing
2. Invalid, corrupted, empty, and oversized files
3. Scanned PDF detection and OCR extension point
4. Structured schema validation and zero hallucination
5. Preservation of dates, metrics, and technical terminology
6. Human review, editing, selective inclusion, and approval
7. Duplicate detection and merging into existing Master Profile
8. Strict multi-tenant user isolation and cross-user access defenses
9. Private file streaming, deletion, and cascade cleanup
10. AI extraction fallback and error handling
11. End-to-end tailoring from approved imported profile facts
"""

import io
import json
from unittest.mock import patch
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from resumes.models import Resume, ResumeImport, ApplicationDocument
from resumes.services.extractor import (
    validate_file_bytes,
    extract_text_from_pdf,
    extract_text_from_docx,
    DocumentFormatError,
    DocumentOversizedError,
    DocumentExtractionError,
    OCRExtensionPoint,
)
from resumes.services.parser import (
    parse_resume_text_deterministic,
    validate_parsed_candidate_schema,
    parse_resume_text,
)
from resumes.services.merger import apply_import_to_profile
from leads.models import JobApplication
from leads.services.llm_tailor import tailor_application


def make_synthetic_pdf(lines) -> bytes:
    """Generate in-memory valid PDF with selectable text."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    if not lines:
        c.showPage()
    else:
        y = 750
        for line in lines:
            c.drawString(50, y, line)
            y -= 16
            if y < 50:
                c.showPage()
                y = 750
    c.save()
    buf.seek(0)
    return buf.getvalue()


def make_synthetic_docx(paragraphs) -> bytes:
    """Generate in-memory valid OpenXML DOCX document."""
    buf = io.BytesIO()
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


class ResumeImportServiceTests(TestCase):
    """Unit tests for the extraction, parsing, and merging service layer."""

    def test_file_validation_magic_bytes(self):
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj"
        detected = validate_file_bytes(pdf_bytes, "resume.pdf")
        self.assertEqual(detected, 'pdf')

        # DOCX valid zip container
        docx_bytes = make_synthetic_docx(["Test paragraph"])
        detected_docx = validate_file_bytes(docx_bytes, "cv.docx")
        self.assertEqual(detected_docx, 'docx')

        # Invalid format
        with self.assertRaises(DocumentFormatError):
            validate_file_bytes(b"MZ...", "program.exe")

        # Fake PDF without %PDF-
        with self.assertRaises(DocumentFormatError):
            validate_file_bytes(b"Not a PDF file", "fake.pdf")

        # Corrupt docx
        with self.assertRaises(DocumentFormatError):
            validate_file_bytes(b"PK\x03\x04CorruptZipData", "corrupt.docx")

        # Empty file
        with self.assertRaises(DocumentExtractionError):
            validate_file_bytes(b"", "empty.pdf")

    @override_settings(RESUME_IMPORT_MAX_SIZE_BYTES=1024)
    def test_oversized_file_rejection(self):
        large_bytes = b"%PDF-1.4" + (b"0" * 2048)
        with self.assertRaises(DocumentOversizedError):
            validate_file_bytes(large_bytes, "large.pdf")

    def test_scanned_pdf_detection(self):
        # A PDF with empty canvas has negligible character count
        empty_pdf = make_synthetic_pdf([])
        text, meta = extract_text_from_pdf(empty_pdf)
        self.assertTrue(meta['is_scanned'])
        self.assertTrue(meta['ocr_recommended'])
        self.assertGreater(len(meta['warnings']), 0)
        self.assertIn("scanned image", meta['warnings'][0])

        # OCR extension interface contract check
        self.assertFalse(OCRExtensionPoint.is_available())
        self.assertIsNone(OCRExtensionPoint.extract_scanned_text(empty_pdf))

    def test_deterministic_parsing_preserves_metrics_and_dates(self):
        resume_text = (
            "Alex Morgan\n"
            "alex.morgan@example.com | (555) 019-2834 | Chicago, IL\n"
            "https://linkedin.com/in/alexmorgan | https://github.com/alexmorgan\n\n"
            "PROFESSIONAL SUMMARY\n"
            "Senior Distributed Systems Engineer with 7+ years architecting high-throughput cloud platforms.\n\n"
            "TECHNICAL SKILLS\n"
            "Languages: Python, TypeScript, Go\n"
            "Databases: PostgreSQL, Redis, DynamoDB\n"
            "Cloud: AWS, Docker, Kubernetes\n\n"
            "WORK EXPERIENCE\n"
            "Lead Backend Engineer | CloudScale Tech | Jan 2021 - Present\n"
            "• Spearheaded backend architecture migration to event-driven microservices\n"
            "• Reduced database query latency by 45% through Redis caching and query indexing\n"
            "• Scaled ingest pipeline to handle 10M daily events with 99.99% uptime\n\n"
            "Software Engineer | NexaCorp | Jun 2017 - Dec 2020\n"
            "• Built automated ETL pipelines processing $2M in daily financial transactions\n"
            "• Mentored 4 junior developers and improved unit test coverage to 88%\n\n"
            "EDUCATION\n"
            "B.S. in Computer Science | University of Illinois | 2013 - 2017\n\n"
            "CERTIFICATIONS\n"
            "AWS Certified Solutions Architect | 2022\n"
        )

        parsed = parse_resume_text_deterministic(resume_text)
        is_valid, errors = validate_parsed_candidate_schema(parsed)
        self.assertTrue(is_valid, f"Schema validation errors: {errors}")

        # Contact & Identity
        self.assertEqual(parsed['full_name'], 'Alex Morgan')
        self.assertEqual(parsed['email'], 'alex.morgan@example.com')
        self.assertEqual(parsed['phone'], '(555) 019-2834')
        self.assertEqual(parsed['location'], 'Chicago, IL')
        self.assertIn('linkedin.com/in/alexmorgan', parsed['linkedin'])
        self.assertIn('github.com/alexmorgan', parsed['github'])

        # Summary
        self.assertIn("Senior Distributed Systems Engineer", parsed['summary'])

        # Skills & categorisation
        skill_names = [s['name'] for s in parsed['technical_skills']]
        self.assertIn('Python', skill_names)
        self.assertIn('PostgreSQL', skill_names)
        self.assertIn('Docker', skill_names)

        # Experience & preserved metrics
        self.assertEqual(len(parsed['experiences']), 2)
        exp1 = parsed['experiences'][0]
        self.assertIn("Jan 2021 - Present", exp1['dates'])
        # Accomplishments must separate metrics (45%, 10M events, 99.99%)
        acc_text = " ".join(exp1['accomplishments'])
        self.assertIn("45%", acc_text)
        self.assertIn("10M", acc_text)

        exp2 = parsed['experiences'][1]
        self.assertIn("Jun 2017 - Dec 2020", exp2['dates'])
        acc2_text = " ".join(exp2['accomplishments'])
        self.assertIn("$2M", acc2_text)

        # Education & Certifications
        self.assertEqual(len(parsed['education']), 1)
        self.assertIn("B.S. in Computer Science", parsed['education'][0]['degree'])
        self.assertEqual(len(parsed['certifications']), 1)
        self.assertIn("AWS Certified Solutions Architect", parsed['certifications'][0]['name'])

    def test_missing_information_remains_missing_no_hallucination(self):
        sparse_text = (
            "Taylor Swift\n"
            "taylor@example.com\n\n"
            "SKILLS\n"
            "Python, Django\n"
        )
        parsed = parse_resume_text_deterministic(sparse_text)
        self.assertEqual(parsed['full_name'], 'Taylor Swift')
        self.assertEqual(parsed['email'], 'taylor@example.com')
        self.assertEqual(parsed['phone'], '')
        self.assertEqual(parsed['location'], '')
        self.assertEqual(parsed['experiences'], [])
        self.assertEqual(parsed['education'], [])
        self.assertEqual(parsed['certifications'], [])
        # Warnings flag missing sections
        warning_str = " ".join(parsed['warnings'])
        self.assertIn("No work experiences", warning_str)

    def test_spacing_normalization_and_fused_dates(self):
        fused_text = (
            "John Samuel\n"
            "sayojami2007@gmail.com | +2348067954912 | Lagos, Nigeria\n"
            "github.com/jayo14 | linkedin.com/in/john-samuel-cgx | samueljohn.vercel.app\n\n"
            "SUMMARY\n"
            "Full stack engineer building complete products with React/Next.js and Python.\n\n"
            "WORK EXPERIENCE\n"
            "Full Stack Engineer|NeXaEsports Jul2025–Sep2025\n"
            "• Engineered resilient pipeline handling 5M daily events\n"
            "Full Stack Developer | Freelance&Contract 2024–Present\n"
            "• Reduced latency by 45%\n\n"
            "EDUCATION\n"
            "B.Sc. Computer Science, Lagos State University of Science and Technology (LASUSTECH), Ikorodu, Lagos (expected) 2024–2028\n"
        )
        parsed = parse_resume_text_deterministic(fused_text)

        # Contact & Links
        self.assertEqual(parsed['full_name'], 'John Samuel')
        self.assertEqual(parsed['email'], 'sayojami2007@gmail.com')
        self.assertEqual(parsed['phone'], '+2348067954912')
        self.assertEqual(parsed['linkedin'], 'https://linkedin.com/in/john-samuel-cgx')
        self.assertEqual(parsed['github'], 'https://github.com/jayo14')
        self.assertEqual(parsed['portfolio'], 'https://samueljohn.vercel.app')
        # Tagline must NOT be the links line
        self.assertNotIn('github.com', parsed['tagline'])
        self.assertNotIn('linkedin.com', parsed['tagline'])

        # Work Experiences correctly segmented
        self.assertEqual(len(parsed['experiences']), 2)
        exp1 = parsed['experiences'][0]
        self.assertEqual(exp1['role'], 'Full Stack Engineer')
        self.assertEqual(exp1['company'], 'NeXaEsports')
        self.assertIn('Jul 2025', exp1['dates'])
        self.assertIn('Sep 2025', exp1['dates'])

        exp2 = parsed['experiences'][1]
        self.assertEqual(exp2['role'], 'Full Stack Developer')
        self.assertEqual(exp2['company'], 'Freelance & Contract')
        self.assertIn('2024', exp2['dates'])

        # Education degree and institution properly separated
        self.assertEqual(len(parsed['education']), 1)
        edu = parsed['education'][0]
        self.assertEqual(edu['degree'], 'B.Sc. Computer Science')
        self.assertIn('Lagos State University of Science and Technology', edu['institution'])
        self.assertIn('2024', edu['dates'])
        self.assertIn('2028', edu['dates'])


class ResumeImportViewAndWorkflowTests(TestCase):
    """End-to-end integration tests for views, ownership, review, and tailoring."""

    def setUp(self):
        self.user = User.objects.create_user(username='importuser', password='StrongPassword123!')
        self.other_user = User.objects.create_user(username='otheruser', password='StrongPassword123!')
        self.client = Client()
        self.client.login(username='importuser', password='StrongPassword123!')
        self.ai_patcher = patch('resumes.services.ai_parser.parse_resume_with_ai', return_value=None)
        self.ai_patcher.start()
        self.addCleanup(self.ai_patcher.stop)

    def test_upload_valid_pdf_redirects_to_review(self):
        pdf_content = make_synthetic_pdf([
            "Jordan Lee",
            "jordan.lee@example.com | (555) 432-1098 | Austin, TX",
            "SUMMARY",
            "Full Stack Developer specializing in Django and React.",
            "SKILLS",
            "Python, Django, React, PostgreSQL",
            "EXPERIENCE",
            "Software Developer | Austin Tech | 2020 - 2023",
            "• Developed RESTful endpoints serving 500,000 monthly users",
            "EDUCATION",
            "B.S. in Software Engineering | 2016 - 2020",
        ])

        uploaded_file = SimpleUploadedFile("jordan_resume.pdf", pdf_content, content_type="application/pdf")

        response = self.client.post(reverse('resumes:resume-import'), {'resume_file': uploaded_file})
        self.assertEqual(response.status_code, 302)

        import_obj = ResumeImport.objects.filter(user=self.user).first()
        self.assertIsNotNone(import_obj)
        self.assertEqual(import_obj.status, 'review_required')
        self.assertEqual(import_obj.file_type, 'pdf')
        self.assertRedirects(response, reverse('resumes:resume-import-review', args=[import_obj.pk]))

        # Verify parsed data
        self.assertEqual(import_obj.parsed_data['full_name'], 'Jordan Lee')
        self.assertEqual(import_obj.parsed_data['email'], 'jordan.lee@example.com')

    def test_upload_corrupt_file_shows_error(self):
        corrupt_file = SimpleUploadedFile("corrupt.docx", b"PK\x03\x04InvalidOpenXMLBytes", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response = self.client.post(reverse('resumes:resume-import'), {'resume_file': corrupt_file})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resume Extraction Notice")

        import_obj = ResumeImport.objects.filter(user=self.user).first()
        self.assertIsNotNone(import_obj)
        self.assertEqual(import_obj.status, 'failed')

    def test_strict_multi_tenant_ownership_defense(self):
        # User 1 creates import
        pdf_content = make_synthetic_pdf(["Secret User Profile", "user1@example.com"])
        uploaded = SimpleUploadedFile("secret.pdf", pdf_content, content_type="application/pdf")
        self.client.post(reverse('resumes:resume-import'), {'resume_file': uploaded})
        import_obj = ResumeImport.objects.filter(user=self.user).first()

        # Switch to User 2 (otheruser)
        other_client = Client()
        other_client.login(username='otheruser', password='StrongPassword123!')

        # User 2 attempts to review User 1's draft
        res_review = other_client.get(reverse('resumes:resume-import-review', args=[import_obj.pk]))
        self.assertEqual(res_review.status_code, 404)

        # User 2 attempts to download User 1's private resume file
        res_file = other_client.get(reverse('resumes:resume-import-file', args=[import_obj.pk]))
        self.assertEqual(res_file.status_code, 404)

        # User 2 attempts to confirm User 1's draft
        res_confirm = other_client.post(reverse('resumes:resume-import-confirm', args=[import_obj.pk]), {})
        self.assertEqual(res_confirm.status_code, 404)

        # User 2 attempts to cancel User 1's draft
        res_cancel = other_client.post(reverse('resumes:resume-import-cancel', args=[import_obj.pk]))
        self.assertEqual(res_cancel.status_code, 404)

    def test_review_and_approval_creates_master_career_profile(self):
        import_obj = ResumeImport.objects.create(
            user=self.user,
            file_name="test.pdf",
            file_type="pdf",
            status="review_required",
            parsed_data={
                'full_name': 'Devon Vance',
                'email': 'devon@example.com',
                'phone': '555-9081',
                'location': 'Seattle, WA',
                'tagline': 'Lead Cloud Architect',
                'summary': 'Architecting distributed platforms across AWS.',
                'technical_skills': [
                    {'name': 'Python', 'proficiency': 'Expert'},
                    {'name': 'Kubernetes', 'proficiency': 'Advanced'},
                ],
                'experiences': [
                    {
                        'role': 'Cloud Architect',
                        'company': 'WaveTech',
                        'dates': '2019 - Present',
                        'accomplishments': ['Scaled multi-region cluster to 99.999% availability.'],
                    }
                ],
                'education': [{'degree': 'B.S. in Computer Science', 'institution': 'UW', 'dates': '2015 - 2019'}],
                'projects': [],
                'certifications': [],
            }
        )

        # Candidate reviews and submits approval
        payload = dict(import_obj.parsed_data)
        res = self.client.post(
            reverse('resumes:resume-import-confirm', args=[import_obj.pk]),
            {'approved_data': json.dumps(payload), 'merge_strategy': 'new'}
        )
        self.assertEqual(res.status_code, 302)

        # Verify Master Profile created
        master = Resume.objects.filter(user=self.user, is_master=True).first()
        self.assertIsNotNone(master)
        self.assertEqual(master.full_name, 'Devon Vance')
        self.assertEqual(master.email, 'devon@example.com')
        self.assertEqual(len(master.technical_skills), 2)
        self.assertEqual(master.technical_skills[0]['provenance'], 'confirmed_by_user')

        # Verify import record status updated
        import_obj.refresh_from_db()
        self.assertEqual(import_obj.status, 'completed')
        self.assertEqual(import_obj.target_resume, master)

    def test_smart_merge_with_existing_master_profile_deduplication(self):
        # 1. Existing Master Profile with 2 skills and 1 experience
        existing_master = Resume.objects.create(
            user=self.user,
            is_master=True,
            full_name='Casey Smith',
            email='casey@example.com',
            technical_skills=[
                {'name': 'Python', 'proficiency': 'Expert', 'provenance': 'user_entered'},
                {'name': 'Django', 'proficiency': 'Advanced', 'provenance': 'user_entered'},
            ],
            experiences=[
                {
                    'role': 'Backend Developer',
                    'company': 'Alpha Corp',
                    'dates': '2020 - 2022',
                    'accomplishments': ['Built initial MVP.'],
                }
            ]
        )

        # 2. Uploaded resume draft contains existing skill 'Python', new skill 'PostgreSQL',
        #    and the same role at 'Alpha Corp' plus a new achievement
        import_obj = ResumeImport.objects.create(
            user=self.user,
            file_name="new_resume.docx",
            file_type="docx",
            status="review_required",
            parsed_data={
                'full_name': 'Casey Smith',
                'email': 'casey@example.com',
                'phone': '555-1234',
                'location': 'New York, NY',
                'tagline': 'Senior Python Engineer',
                'summary': 'Updated summary description.',
                'technical_skills': [
                    {'name': 'Python', 'proficiency': 'Expert'},     # Duplicate
                    {'name': 'PostgreSQL', 'proficiency': 'Advanced'}, # Novel
                ],
                'experiences': [
                    {
                        'role': 'Backend Developer',
                        'company': 'Alpha Corp',
                        'dates': '2020 - 2022',
                        'accomplishments': ['Built initial MVP.', 'Reduced latency by 30%.'],
                    },
                    {
                        'role': 'Staff Engineer',
                        'company': 'Beta Inc',
                        'dates': '2022 - Present',
                        'accomplishments': ['Led team of 5.'],
                    }
                ],
                'education': [],
                'projects': [],
                'certifications': [],
            }
        )

        res = self.client.post(
            reverse('resumes:resume-import-confirm', args=[import_obj.pk]),
            {'approved_data': json.dumps(import_obj.parsed_data), 'merge_strategy': 'merge'}
        )
        self.assertEqual(res.status_code, 302)

        existing_master.refresh_from_db()
        # Skills deduplicated: Python, Django, PostgreSQL (3 total, not 4)
        skill_names = [s['name'] for s in existing_master.technical_skills]
        self.assertEqual(len(skill_names), 3)
        self.assertIn('PostgreSQL', skill_names)

        # Experiences merged: Alpha Corp updated with new accomplishment, Beta Inc appended
        self.assertEqual(len(existing_master.experiences), 2)
        alpha_exp = [e for e in existing_master.experiences if e['company'] == 'Alpha Corp'][0]
        self.assertEqual(len(alpha_exp['accomplishments']), 2)
        self.assertIn('Reduced latency by 30%.', alpha_exp['accomplishments'])

    def test_cancel_import_deletes_draft_and_file(self):
        pdf_content = make_synthetic_pdf(["Sample Candidate", "candidate@example.com"])
        uploaded = SimpleUploadedFile("candidate.pdf", pdf_content, content_type="application/pdf")
        self.client.post(reverse('resumes:resume-import'), {'resume_file': uploaded})

        import_obj = ResumeImport.objects.filter(user=self.user).first()
        self.assertIsNotNone(import_obj)

        # Cancel
        res = self.client.post(reverse('resumes:resume-import-cancel', args=[import_obj.pk]))
        self.assertRedirects(res, reverse('resumes:resume-list'))
        self.assertFalse(ResumeImport.objects.filter(pk=import_obj.pk).exists())

    def test_ai_parsing_graceful_fallback_on_malformed_response(self):
        with patch('resumes.services.parser.os.environ.get', return_value='fake-gemini-key'):
            with patch('resumes.services.ai_parser.parse_resume_with_ai', return_value={"invalid": "payload"}):
                # When AI returns an invalid dictionary that fails schema check,
                # parse_resume_text gracefully falls back to deterministic parsing
                text = "Dana Fox\ndana@example.com\n\nSKILLS\nPython, Docker\n"
                result = parse_resume_text(text, allow_ai=True)
                self.assertEqual(result['full_name'], 'Dana Fox')
                self.assertEqual(result['provenance']['extraction_method'], 'deterministic')

    def test_tailoring_pipeline_consumes_approved_imported_profile(self):
        # 1. Create and approve profile from imported facts
        resume = Resume.objects.create(
            user=self.user,
            is_master=True,
            full_name='Morgan Bailey',
            email='morgan@example.com',
            tagline='Senior Backend Engineer',
            technical_skills=[
                {'name': 'Python', 'proficiency': 'Expert', 'provenance': 'confirmed_by_user'},
                {'name': 'PostgreSQL', 'proficiency': 'Advanced', 'provenance': 'confirmed_by_user'},
                {'name': 'Redis', 'proficiency': 'Advanced', 'provenance': 'confirmed_by_user'},
            ],
            experiences=[
                {
                    'role': 'Senior Backend Engineer',
                    'company': 'FinFlow',
                    'dates': '2021 - Present',
                    'accomplishments': [
                        'Architected low-latency settlement service processing 500k transactions daily.',
                        'Optimized PostgreSQL query plans reducing CPU consumption by 35%.'
                    ]
                }
            ]
        )

        # 2. Target job description requiring Python, PostgreSQL, and Redis
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Stripe Partner Tech',
            role_title='Senior Infrastructure Engineer',
            job_description=(
                "We are hiring a Senior Infrastructure Engineer to scale our PostgreSQL and Redis data layer. "
                "Requires strong experience with Python backend services, query optimization, and high availability."
            )
        )

        tailored = tailor_application(
            resume=resume,
            company_name=job.company_name,
            role_title=job.role_title,
            job_description=job.job_description,
        )

        # Verify evidence-grounded tailoring output
        self.assertGreater(tailored['score'], 70)
        self.assertIn('Python', tailored['matched_keywords'])
        self.assertIn('PostgreSQL', tailored['matched_keywords'])

        # Cover letter and bullets reference verified facts
        bullets_text = " ".join(tailored['tailored_bullets'])
        self.assertIn("35%", bullets_text)
        self.assertIn("500k", bullets_text)

    def test_end_to_end_onboarding_import_tailor_export_journey(self):
        # 1. User arrives on dashboard, sees Next Action to complete profile
        dash_res = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "Complete Your Master Career Profile")

        # 2. User uploads existing resume PDF
        pdf_bytes = make_synthetic_pdf([
            "Avery Scott",
            "avery.scott@example.com | (555) 789-0123 | Seattle, WA",
            "SUMMARY",
            "DevOps Engineer with 6 years experience automating cloud infrastructures.",
            "SKILLS",
            "Docker, Kubernetes, Terraform, AWS, Python, CI/CD",
            "EXPERIENCE",
            "DevOps Lead | CloudOps Inc | 2021 - Present",
            "• Reduced deployment lead time by 60% through automated GitLab CI/CD pipelines",
            "• Managed multi-cluster Kubernetes deployment spanning 15 nodes on AWS",
            "EDUCATION",
            "B.S. in Information Technology | 2014 - 2018",
        ])

        upload_res = self.client.post(
            reverse('resumes:resume-import'),
            {'resume_file': SimpleUploadedFile("avery_resume.pdf", pdf_bytes, content_type="application/pdf")}
        )
        self.assertEqual(upload_res.status_code, 302)
        import_obj = ResumeImport.objects.filter(user=self.user).first()

        # 3. User reviews and approves extracted details
        review_res = self.client.get(reverse('resumes:resume-import-review', args=[import_obj.pk]))
        self.assertEqual(review_res.status_code, 200)
        self.assertContains(review_res, "Avery Scott")
        self.assertContains(review_res, "CloudOps Inc")

        confirm_res = self.client.post(
            reverse('resumes:resume-import-confirm', args=[import_obj.pk]),
            {'approved_data': json.dumps(import_obj.parsed_data), 'merge_strategy': 'new'}
        )
        self.assertEqual(confirm_res.status_code, 302)

        master = Resume.objects.filter(user=self.user, is_master=True).first()
        self.assertIsNotNone(master)
        self.assertEqual(master.full_name, 'Avery Scott')

        # 4. User tracks a job and generates tailored application
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Apex Cloud Services',
            role_title='Senior Kubernetes DevOps Engineer',
            job_description="Seeking a DevOps Engineer with Kubernetes, Terraform, and CI/CD automation expertise."
        )

        gen_res = self.client.post(reverse('leads:generate-message', args=[job.pk]))
        self.assertEqual(gen_res.status_code, 200)
        job.refresh_from_db()
        self.assertIn("60%", job.tailored_resume_text)

        # 5. User downloads tailored ATS DOCX
        download_res = self.client.get(f"{reverse('resumes:resume-download', args=[master.pk])}?job_id={job.pk}&format=docx")
        self.assertEqual(download_res.status_code, 200)
        self.assertEqual(download_res['Content-Type'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        self.assertIn("Avery_Scott", download_res['Content-Disposition'])
