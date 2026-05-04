import time
import threading
import re
import random
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .models import ScraperJob, RawLead
from geopy.geocoders import Nominatim

def add_log(job, message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    job.logs += log_entry
    job.save()

def find_emails(text):
    return re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)

def find_phones(text):
    return re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)

def run_scraper(job_id):
    job = ScraperJob.objects.get(id=job_id)
    job.status = 'running'
    job.progress = 5
    job.logs = "" # Clear previous logs
    job.save()

    add_log(job, f"🚀 Initializing scraping session for {job.niche} in {job.region}...")

    try:
        # Validate location using geopy (3rd party API)
        try:
            add_log(job, "📍 Validating target region...")
            geolocator = Nominatim(user_agent="huntly_scraper")
            location = geolocator.geocode(job.region)
            if location:
                job.region = location.address
                job.save()
                add_log(job, f"✅ Region validated: {job.region}")
        except Exception as e:
            add_log(job, f"⚠️ Geocoding warning: {e}")
        
        # Setup Selenium
        add_log(job, "🌐 Setting up headless browser environment...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Search query
        search_query = f"{job.niche} in {job.region} {job.keywords}"
        url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}&num=20"
        
        add_log(job, f"🔍 Querying Google Search for: {search_query}")
        driver.get(url)
        time.sleep(random.uniform(2, 4))
        
        job.progress = 20
        job.save()

        # Extract organic results
        add_log(job, "📊 Extracting search results...")
        search_results = []
        
        # Look for result blocks (h3 is usually the title)
        links = driver.find_elements(By.CSS_SELECTOR, "div.g")
        for link in links:
            try:
                title_elem = link.find_element(By.TAG_NAME, "h3")
                anchor = link.find_element(By.TAG_NAME, "a")
                href = anchor.get_attribute("href")
                
                if href and "google.com" not in href:
                    search_results.append({
                        "name": title_elem.text,
                        "url": href
                    })
            except:
                continue

        add_log(job, f"🎯 Found {len(search_results)} potential business websites.")
        
        if not search_results:
            add_log(job, "❌ No organic results found. Session terminating.")
            job.status = 'failed'
            job.save()
            driver.quit()
            return

        # Process results
        for i, res in enumerate(search_results):
            # Check for stop request
            job.refresh_from_db()
            if job.stop_requested:
                add_log(job, "🛑 Stop requested by user. Terminating...")
                job.status = 'failed'
                job.save()
                driver.quit()
                return

            add_log(job, f"📡 Visiting: {res['url']}...")
            try:
                driver.get(res['url'])
                time.sleep(random.uniform(2, 5)) # Ethical delay
                
                page_source = driver.page_source
                emails = find_emails(page_source)
                phones = find_phones(page_source)
                
                email = emails[0] if emails else ""
                phone = phones[0] if phones else ""
                
                RawLead.objects.create(
                    job=job,
                    business_name=res['name'],
                    website=res['url'],
                    email=email,
                    phone=phone,
                    scraped_data={
                        "all_emails": list(set(emails)),
                        "all_phones": list(set(phones)),
                        "scraped_at": datetime.now().isoformat()
                    }
                )
                
                job.leads_found += 1
                job.progress = 20 + int(((i + 1) / len(search_results)) * 75)
                job.save()
                
                add_log(job, f"✅ Scraped {res['name']}. Email: {email or 'N/A'}, Phone: {phone or 'N/A'}")
                
            except Exception as e:
                add_log(job, f"⚠️ Error scraping {res['url']}: {str(e)[:50]}...")
                continue

        job.status = 'completed'
        job.progress = 100
        job.save()
        add_log(job, f"🏁 Session completed successfully! Total leads found: {job.leads_found}")
        
        driver.quit()
        
    except Exception as e:
        job.status = 'failed'
        job.save()
        add_log(job, f"🚨 FATAL ERROR: {e}")
        if 'driver' in locals():
            driver.quit()

def start_scraping_thread(job_id):
    thread = threading.Thread(target=run_scraper, args=(job_id,))
    thread.daemon = True
    thread.start()
