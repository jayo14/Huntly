import time
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .models import ScraperJob, RawLead
from geopy.geocoders import Nominatim

def run_scraper(job_id):
    job = ScraperJob.objects.get(id=job_id)
    job.status = 'running'
    job.progress = 5
    job.save()

    try:
        # Validate location using geopy (3rd party API)
        geolocator = Nominatim(user_agent="huntly_scraper")
        location = geolocator.geocode(job.region)
        if location:
            job.region = location.address
            job.save()
        
        # Setup Selenium
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Search query
        search_query = f"{job.niche} in {job.region} {job.keywords}"
        url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
        
        driver.get(url)
        job.progress = 20
        job.save()

        # Simple simulation of finding leads for demo purposes
        # In a real scenario, you'd parse Google Maps or specialized directories
        # Here we'll simulate finding 5-10 leads
        time.sleep(2)
        
        mock_leads = [
            {"business_name": f"{job.niche} Pro {i}", "website": f"https://example{i}.com", "email": f"contact@example{i}.com"}
            for i in range(1, 6)
        ]
        
        for i, lead_data in enumerate(mock_leads):
            RawLead.objects.create(
                job=job,
                business_name=lead_data['business_name'],
                website=lead_data['website'],
                email=lead_data['email']
            )
            job.leads_found += 1
            job.progress = 20 + (i + 1) * 15
            job.save()
            time.sleep(1)

        job.status = 'completed'
        job.progress = 100
        job.save()
        
        driver.quit()
        
    except Exception as e:
        job.status = 'failed'
        job.save()
        print(f"Scraper error: {e}")

def start_scraping_thread(job_id):
    thread = threading.Thread(target=run_scraper, args=(job_id,))
    thread.daemon = True
    thread.start()
