import asyncio
from django.core.management.base import BaseCommand
from leads.models import Lead
from playwright.async_api import async_playwright
import re

class Command(BaseCommand):
    help = 'Scrape leads from Google Maps (basic implementation)'

    def add_arguments(self, parser):
        parser.add_argument('query', type=str, help='Search query (e.g., "dentists in London")')
        parser.add_argument('--limit', type=int, default=5, help='Limit number of results')

    def handle(self, *args, **options):
        query = options['query']
        limit = options['limit']

        self.stdout.write(f'Starting scrape for: {query}')

        try:
            asyncio.run(self.scrape(query, limit))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Scrape failed: {str(e)}"))

    async def scrape(self, query, limit):
        async with async_playwright() as p:
            # Check if browser is installed, if not we might need to handle it or assume it is as per requirements
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Navigate to Google Maps
            await page.goto(f'https://www.google.com/maps/search/{query.replace(" ", "+")}')

            # Wait for results
            await page.wait_for_timeout(5000)

            # Find all result links
            results = await page.query_selector_all('a.hfpxzc')

            count = 0
            for res in results:
                if count >= limit:
                    break

                try:
                    title = await res.get_attribute('aria-label')
                    if not title:
                        continue

                    # Check for duplicates before expensive detail scraping
                    if Lead.objects.filter(business_name=title).exists():
                        self.stdout.write(f'Lead already exists: {title}')
                        continue

                    await res.click()
                    await page.wait_for_timeout(3000) # Wait for details

                    # Re-verify business name from detail view if possible
                    business_name = title

                    # Try to find website
                    website = ""
                    website_element = await page.query_selector('a[data-item-id="authority"]')
                    if website_element:
                        website = await website_element.get_attribute('href')

                    # Try to find phone
                    phone = ""
                    phone_element = await page.query_selector('button[data-item-id^="phone:tel:"]')
                    if phone_element:
                        phone = await phone_element.get_attribute('data-item-id')
                        phone = phone.replace('phone:tel:', '')

                    # Save Lead
                    problem = "No website" if not website else ""
                    evidence_note = "Marked for review" if website else ""

                    Lead.objects.create(
                        business_name=business_name,
                        website=website or "",
                        phone=phone or "",
                        problem=problem,
                        evidence_note=evidence_note,
                        status='new'
                    )

                    self.stdout.write(self.style.SUCCESS(f'Created lead: {business_name}'))
                    count += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error scraping a result: {str(e)}'))
                    continue

            await browser.close()
            self.stdout.write(self.style.SUCCESS(f'Successfully scraped {count} new leads.'))
