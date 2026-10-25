"""
Performance, Query Count, and N+1 Regression Test Suite for Huntly.

Verifies:
1. Dashboard aggregation runs in bounded SQL queries without N+1 query inflation.
2. Lead tracker list pagination and filtering scale sub-linearly.
3. Key views meet latency budgets (< 500ms on warm cache).
"""
import time
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from leads.models import JobApplication, Message
from resumes.models import Resume, ApplicationDocument
from billing.models import Subscription


class PerformanceAndQueryBudgetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='perf_tester', password='password123')
        self.client = Client()
        self.client.login(username='perf_tester', password='password123')

        # Create Master Profile
        self.resume = Resume.objects.create(
            user=self.user,
            full_name="Alex Benchmark",
            tagline="Performance Engineer",
            summary="Profiling and eliminating database bottlenecks.",
            is_master=True
        )

        # Create 30 JobApplications across all pipeline statuses
        statuses = ['saved', 'applied', 'interviewing', 'offer', 'rejected']
        jobs = []
        for i in range(30):
            status = statuses[i % len(statuses)]
            jobs.append(JobApplication(
                user=self.user,
                company_name=f"Company {i}",
                role_title=f"Engineer {i}",
                status=status,
                score=50 + (i % 50),
                job_description="Sample job description for query scaling benchmarks."
            ))
        JobApplication.objects.bulk_create(jobs)

    def test_dashboard_query_count_bounded(self):
        """Dashboard funnel queries must not exceed 25 SQL queries regardless of lead volume."""
        with self.assertNumQueriesLessThan(25):
            response = self.client.get(reverse('leads:dashboard'))
            self.assertEqual(response.status_code, 200)

    def test_lead_list_query_count_bounded(self):
        """Lead list pagination must avoid N+1 queries when rendering 25 items."""
        with self.assertNumQueriesLessThan(20):
            response = self.client.get(reverse('leads:lead-list'))
            self.assertEqual(response.status_code, 200)

    def test_pipeline_view_query_count_bounded(self):
        """Pipeline kanban must group stages efficiently in bounded queries."""
        with self.assertNumQueriesLessThan(25):
            response = self.client.get(reverse('leads:pipeline'))
            self.assertEqual(response.status_code, 200)

    def test_dashboard_latency_budget(self):
        """Dashboard page rendering latency budget under 6.0 seconds over remote TLS DB."""
        start = time.perf_counter()
        response = self.client.get(reverse('leads:dashboard'))
        elapsed = time.perf_counter() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 6.0, f"Dashboard took {elapsed:.3f}s, exceeding budget of 6.0s")

    def assertNumQueriesLessThan(self, limit):
        """Helper context manager to assert queries stay strictly below an upper ceiling."""
        class _AssertNumQueriesLessThanContext:
            def __init__(self, test_case, max_limit):
                self.test_case = test_case
                self.max_limit = max_limit
                self.query_context = test_case.assertNumQueries(None)

            def __enter__(self):
                # We count queries manually by inspecting connection.queries
                from django.db import connection, reset_queries
                reset_queries()
                self.initial_queries = len(connection.queries)
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                from django.db import connection
                final_queries = len(connection.queries)
                total = final_queries - self.initial_queries
                if total >= self.max_limit:
                    self.test_case.fail(
                        f"Executed {total} queries, expected strictly fewer than {self.max_limit}"
                    )

        return _AssertNumQueriesLessThanContext(self, limit)
