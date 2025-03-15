from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
import tempfile
import shutil
import traceback
import threading

# Import ChromeDriverManager from webdriver-manager
from webdriver_manager.chrome import ChromeDriverManager

# Configure Selenium for headless operation with extra options for GitHub Actions
options = Options()
options.add_argument("--headless=new")  # new headless mode, more stable
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--remote-debugging-port=9222")

# Global list and lock to collect course data from all threads
all_course_data = []
data_lock = threading.Lock()

def scrape_pages(start_page):
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        # Load the initial page (adjust the URL as needed)
        url = "https://ttb.utoronto.ca/"  # Replace with the correct starting URL
        driver.get(url)
        
        # Disable CSS animations and transitions
        disable_animations = """
        var css = document.createElement("style");
        css.type = "text/css";
        css.innerHTML = "* { animation: none !important; transition: none !important; }";
        document.head.appendChild(css);
        """
        driver.execute_script(disable_animations)
        
        # Wait for the division dropdown to be present
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "division"))
        )
        # Wait until the custom checkbox options are present in the dropdown
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option")
            )
        )
        # Locate all division options (custom checkboxes) and click each one
        division_options = driver.find_elements(By.CSS_SELECTOR, "#division-combo-bottom-container app-ttb-option")
        print("Found division options:", len(division_options))
        for option in division_options:
            driver.execute_script("arguments[0].scrollIntoView(true);", option)
            driver.execute_script("arguments[0].click();", option)
            time.sleep(0.5)  # Optional: slight pause after clicking each option
        
        """
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "session"))
        )
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "#session-combo-bottom-container app-ttb-option")
            )
        )
        session_options = driver.find_elements(By.CSS_SELECTOR, "#session-combo-bottom-container app-ttb-option")
        print("Found session options:", len(session_options))
        for option in session_options:
            driver.execute_script("arguments[0].scrollIntoView(true);", option)
            driver.execute_script("arguments[0].click();", option)
            time.sleep(0.5)
        """
        
        # Wait until the "Search" button is clickable
        search_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Search']"))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
        driver.execute_script("arguments[0].click();", search_button)
        
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))
        
        # Navigate to the starting page (if start_page > 1, click Next repeatedly)
        for _ in range(start_page - 1):
            next_page_links = driver.find_elements(By.XPATH, "//a[contains(@class, 'page-link') and text()='Next' and not(ancestor::li[contains(@class, 'disabled')])]")
            if not next_page_links:
                break
            next_page_link = next_page_links[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", next_page_link)
            next_page_link.click()
            time.sleep(2)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))
        
        local_course_data = []
        
        # Start the loop to process each page for this thread
        while True:
            # Find and click all accordion buttons to expand course details
            accordion_buttons = driver.find_elements(By.CSS_SELECTOR, "button.accordion-button")
            for button in accordion_buttons:
                try:
                    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(button))
                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                    button.click()
                    time.sleep(0.1)  # Brief pause to allow content to expand
                except Exception as e:
                    print(f"Error clicking accordion button: {e}")
            
            # Get the current page source after expanding accordions
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract course data from the current page
            courses = soup.select("app-course")
            course_data = []
            for course_elem in courses:
                header = course_elem.select_one(".accordion-button span")
                code_title = header.get_text(strip=True) if header else "N/A"
    
                body = course_elem.select_one(".accordion-body")
                if not body:
                    campus = session = notes = "N/A"
                else:
                    campus_elem = body.select_one("label:contains('Campus') + span")
                    campus = campus_elem.get_text(strip=True) if campus_elem else "N/A"
                    
                    session_elem = body.select_one("label:contains('Session') + span")
                    session = session_elem.get_text(strip=True) if session_elem else "N/A"
                    
                    notes_elem = body.select_one(".notes-details .notes")
                    notes = notes_elem.get_text(strip=True) if notes_elem else "N/A"
    
                sections = []
                section_elems = course_elem.select(".course-sections app-course-section")
                for section_elem in section_elems:
                    section_code_elem = section_elem.select_one(".header span")
                    section_code = section_code_elem.get_text(strip=True) if section_code_elem else "N/A"
                    
                    details = section_elem.select(".section-item")
                    section_info = {"code": section_code}
                    
                    for detail in details:
                        label_elem = detail.select_one("label")
                        label = label_elem.get_text(strip=True) if label_elem else ""
                        value_elem = detail.select_one(".item-value")
                        value = value_elem.get_text(strip=True) if value_elem else "N/A"
                        
                        if "Day/Time" in label:
                            section_info["day_time"] = value
                        elif "Location" in label:
                            section_info["location"] = value
                        elif "Instructor" in label:
                            section_info["instructor"] = value
                        elif "Availability" in label:
                            section_info["availability"] = value
                        elif "Waitlist" in label:
                            section_info["waitlist"] = value
                        elif "Enrolment Controls" in label:
                            section_info["enrollment_control"] = value
                        elif "Delivery Mode" in label:
                            section_info["delivery_mode"] = value
                    
                    sections.append(section_info)
    
                course_data.append({
                    "code_title": code_title,
                    "campus": campus,
                    "session": session,
                    "notes": notes,
                    "sections": sections
                })
            
            local_course_data.extend(course_data)
    
            # Jump ahead 5 pages (each thread goes to the page 5 ahead)
            jumped = True
            for _ in range(5):
                next_page_links = driver.find_elements(By.XPATH, "//a[contains(@class, 'page-link') and text()='Next' and not(ancestor::li[contains(@class, 'disabled')])]")
                if not next_page_links:
                    jumped = False
                    break
                next_page_link = next_page_links[0]
                driver.execute_script("arguments[0].scrollIntoView(true);", next_page_link)
                next_page_link.click()
                time.sleep(0.2)
                try:
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "app-course")))
                except Exception as e:
                    jumped = False
                    break
            if not jumped:
                break
        
        # Add the local data to the global list
        with data_lock:
            all_course_data.extend(local_course_data)
    
    except Exception as e:
        print(f"An error occurred in thread starting at page {start_page}: {e}")
        traceback.print_exc()
    
    finally:
        driver.quit()
        shutil.rmtree(tempfile.mkdtemp(), ignore_errors=True)

# Create and start 5 threads, each starting at pages 1 to 5 respectively
threads = []
for i in range(1, 6):
    t = threading.Thread(target=scrape_pages, args=(i,))
    threads.append(t)
    t.start()

# Wait for all threads to finish
for t in threads:
    t.join()

# Save all collected data to a JSON file
with open('course_data.json', 'w') as f:
    json.dump(all_course_data, f, indent=4)
